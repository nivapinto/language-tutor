#!/usr/bin/env python3
"""
Language Tutor Bot — Telegram interativo
- "aula" → escolhe idioma com botões
- Após história: botões Tradução | Vocabulário | Fácil | Difícil | Conversar
- Conversar: modo chat sobre a aula (texto ou áudio)
"""

import os, json, time, tempfile, asyncio, requests, importlib, sys, threading, datetime
from pathlib import Path
from groq import Groq
import edge_tts
from dotenv import load_dotenv
from github_sync import salvar_json_e_sync, restaurar_estado

load_dotenv()

BASE_DIR       = Path(__file__).parent
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT  = os.environ["TELEGRAM_CHAT_ID"]
groq_client    = Groq(api_key=os.environ["GROQ_API_KEY"])
BASE_URL       = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
VOZ_PT         = "pt-BR-FranciscaNeural"
PAGES_URL      = "https://nivapinto.github.io/language-tutor/"

NOMES = {"fr": "🇫🇷 Francês", "es": "🇪🇸 Espanhol", "en": "🇬🇧 Inglês"}

# Estado em memória
conv_mode: dict = {}       # {chat_id: dict} — modo conversa ou avaliação ativo
aula_cache: dict = {}      # {chat_id+lang: dados da aula} — para os botões


# ── helpers Telegram ──────────────────────────────────────────────────────────

def tg_get(method, params=None):
    return requests.get(f"{BASE_URL}/{method}", params=params or {}, timeout=30).json()

def tg_post(method, data=None, files=None):
    return requests.post(f"{BASE_URL}/{method}", data=data or {}, files=files, timeout=30).json()

def msg(chat_id, texto, parse_mode="Markdown", keyboard=None, preview=False):
    payload = {"chat_id": chat_id, "text": texto, "parse_mode": parse_mode,
               "disable_web_page_preview": str(not preview).lower()}
    if keyboard:
        payload["reply_markup"] = json.dumps({"inline_keyboard": keyboard})
    tg_post("sendMessage", payload)

def ack(cb_id, texto=""):
    tg_post("answerCallbackQuery", {"callback_query_id": cb_id, "text": texto})

def digitando(chat_id):
    tg_post("sendChatAction", {"chat_id": chat_id, "action": "typing"})

def gravando(chat_id):
    tg_post("sendChatAction", {"chat_id": chat_id, "action": "record_voice"})


# ── áudio ─────────────────────────────────────────────────────────────────────

def transcrever(file_id):
    info = tg_get("getFile", {"file_id": file_id})
    url  = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{info['result']['file_path']}"
    dados = requests.get(url, timeout=30).content
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        tmp.write(dados); path = tmp.name
    try:
        with open(path, "rb") as f:
            return groq_client.audio.transcriptions.create(
                model="whisper-large-v3", file=("audio.ogg", f, "audio/ogg")
            ).text
    finally:
        os.unlink(path)

async def _tts(texto, path):
    await edge_tts.Communicate(texto, VOZ_PT).save(path)

def resposta_audio(chat_id, texto):
    gravando(chat_id)
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        path = tmp.name
    asyncio.run(_tts(texto, path))
    try:
        with open(path, "rb") as f:
            tg_post("sendVoice", {"chat_id": chat_id}, files={"voice": f})
    finally:
        os.unlink(path)


# ── visão ─────────────────────────────────────────────────────────────────────

def descrever_foto(file_id):
    import base64
    info = tg_get("getFile", {"file_id": file_id})
    url  = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{info['result']['file_path']}"
    b64  = base64.b64encode(requests.get(url, timeout=30).content).decode()
    r = groq_client.chat.completions.create(
        model="meta-llama/llama-4-scout-17b-16e-instruct",
        messages=[{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            {"type": "text", "text": "Descreva objetivamente. Se houver texto, transcreva."},
        ]}], max_tokens=300,
    )
    return r.choices[0].message.content.strip()


# ── IA ────────────────────────────────────────────────────────────────────────

def contexto_aula() -> str:
    try:
        data = json.loads((BASE_DIR / "aula_atual.json").read_text(encoding="utf-8"))
        return " | ".join(
            f"{a['flag']} Lição {a['licao']['numero']}: {a['licao']['titulo']}"
            for a in data.get("aulas", [])
        )
    except Exception:
        return ""

def ia(pergunta, sistema_extra="", max_tokens=200):
    system = (
        "Você é o Professor Tutor, professor particular de idiomas. "
        "Respostas CURTAS (máximo 3 frases), diretas, amigáveis. "
        "Corrija erros em 1 frase com o exemplo certo. "
        "Responda em português; use o idioma-alvo só em exemplos."
    )
    ctx = contexto_aula()
    if ctx: system += f"\n\nAula de hoje: {ctx}"
    if sistema_extra: system += f"\n\n{sistema_extra}"
    r = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "system", "content": system},
                  {"role": "user",   "content": pergunta}],
        max_tokens=max_tokens,
    )
    return r.choices[0].message.content.strip()


# ── gerar vocabulário rápido ──────────────────────────────────────────────────

def gerar_vocab(lang_code, historia_texto, licao):
    sys.path.insert(0, str(BASE_DIR))
    ga = importlib.import_module("gerar_aula"); importlib.reload(ga)
    lang = next(l for l in ga.LANGS if l["code"] == lang_code)
    raw = ga.groq(ga.SYS_PROF, f"""
Da história abaixo em {lang['lingua']} (nível {licao['nivel']}), selecione 5 palavras-chave.

{historia_texto}

Para cada palavra, use EXATAMENTE este formato (uma por linha):
PALAVRA: <palavra no idioma> | PT: <tradução em português> | EX: <frase curta de exemplo>
""", tokens=400)
    words = []
    for line in raw.splitlines():
        if "PALAVRA:" in line and "PT:" in line:
            try:
                parts = {p.split(":")[0].strip(): p.split(":", 1)[1].strip() for p in line.split("|")}
                words.append(parts)
            except Exception:
                pass
    return words[:5]


# ── enviar aula de um idioma ──────────────────────────────────────────────────

def enviar_aula_idioma(chat_id, lang_code, cb_id=None):
    if cb_id: ack(cb_id)
    msg(chat_id, f"⏳ Gerando aula de {NOMES[lang_code]}...")

    sys.path.insert(0, str(BASE_DIR))
    ga = importlib.import_module("gerar_aula"); importlib.reload(ga)
    lang  = next(l for l in ga.LANGS if l["code"] == lang_code)
    licao = ga.licao_do_dia(lang_code)
    hist  = ga.gerar_historia(lang, licao)

    audio_path = BASE_DIR / f"{lang_code}_historia.mp3"
    ga.gerar_audio(hist["texto_completo"], lang_code, audio_path)

    # Salva no cache para os botões usarem depois
    cache_key = f"{chat_id}_{lang_code}"
    aula_cache[cache_key] = {"licao": licao, "historia": hist, "lang": lang}

    # Envia texto
    nivel = licao.get("nivel", "")
    nivel_titulo = licao.get("nivel_titulo", "")
    texto = "\n\n".join(hist["paragrafos"])
    cabecalho = f"{lang['flag']} *{lang['label']}* — {nivel} · Lição {licao['numero']}\n_{licao['titulo']}_"
    if nivel_titulo:
        cabecalho += f"\n`{nivel_titulo}`"
    msg(chat_id, f"{cabecalho}\n\n{texto}")

    # Envia áudio
    with open(audio_path, "rb") as f:
        tg_post("sendAudio", {
            "chat_id": chat_id,
            "title": f"{lang['label']} — Lição {licao['numero']}",
            "performer": "Language Tutor"
        }, files={"audio": f})

    # Botões de ação
    tg_post("sendMessage", {
        "chat_id": chat_id,
        "text": "O que quer fazer?",
        "reply_markup": json.dumps({"inline_keyboard": [
            [
                {"text": "🌐 Tradução",    "callback_data": f"trad_{lang_code}"},
                {"text": "📝 Vocabulário", "callback_data": f"vocab_{lang_code}"},
            ],
            [
                {"text": "😴 Fácil demais", "callback_data": f"fb_facil_{lang_code}"},
                {"text": "👍 Na medida",    "callback_data": f"fb_ok_{lang_code}"},
                {"text": "😰 Difícil demais","callback_data": f"fb_dificil_{lang_code}"},
            ],
            [
                {"text": "💬 Conversar sobre esta aula", "callback_data": f"conv_{lang_code}"},
                {"text": "🎯 Avaliar meu nível",         "callback_data": f"avaliar_{lang_code}"},
            ],
        ]}),
    })


# ── callbacks dos botões ──────────────────────────────────────────────────────

def handle_callback(chat_id, data, cb_id):
    parts     = data.split("_", 1)
    acao      = parts[0]
    lang_code = parts[1] if len(parts) > 1 else ""
    cache_key = f"{chat_id}_{lang_code}"
    cached    = aula_cache.get(cache_key, {})

    ack(cb_id)

    # ── Tradução ──────────────────────────────────────────────────────────────
    if acao == "trad":
        hist = cached.get("historia", {})
        trad = hist.get("traducao", "Tradução não disponível.")
        msg(chat_id, f"🌐 *Tradução*\n\n{trad}")

    # ── Vocabulário ───────────────────────────────────────────────────────────
    elif acao == "vocab":
        hist  = cached.get("historia", {})
        licao = cached.get("licao", {})
        msg(chat_id, "📝 Buscando vocabulário...")
        try:
            words = gerar_vocab(lang_code, hist.get("texto_completo", ""), licao)
            linhas = "\n\n".join(
                f"*{w.get('PALAVRA','')}*\n"
                f"↳ {w.get('PT','')}\n"
                f"_{w.get('EX','')}_"
                for w in words
            )
            msg(chat_id, f"📝 *Vocabulário da aula*\n\n{linhas}")
        except Exception as e:
            msg(chat_id, f"Não consegui gerar o vocabulário. ({e})")

    # ── Feedback (3 opções) ───────────────────────────────────────────────────
    elif acao == "fb":
        tipo  = lang_code          # aqui lang_code é "facil_fr", "ok_fr" etc.
        partes = tipo.split("_", 1)
        fb_tipo   = partes[0]      # facil | ok | dificil
        lang_code = partes[1]      # fr | es | en
        cached    = aula_cache.get(f"{chat_id}_{lang_code}", {})
        licao     = cached.get("licao", {})
        num       = licao.get("numero", 1)
        hoje      = __import__("datetime").date.today().isoformat()

        # Salva feedback no perfil
        try:
            perfil = json.loads((BASE_DIR / "perfil.json").read_text(encoding="utf-8"))
            perfil[lang_code]["feedback_historia"].append(
                {"data": hoje, "licao": num, "feedback": fb_tipo}
            )
            # Ajusta preferência de dificuldade
            contagens = [f["feedback"] for f in perfil[lang_code]["feedback_historia"][-5:]]
            if contagens.count("facil") >= 3:
                perfil[lang_code]["dificuldade_preferida"] = "mais_dificil"
            elif contagens.count("dificil") >= 3:
                perfil[lang_code]["dificuldade_preferida"] = "mais_facil"
            else:
                perfil[lang_code]["dificuldade_preferida"] = "normal"
            salvar_json_e_sync(BASE_DIR / "perfil.json", perfil)
        except Exception:
            pass

        # Avança lição se ok ou facil
        if fb_tipo in ("ok", "facil"):
            try:
                prog = json.loads((BASE_DIR / "progresso.json").read_text(encoding="utf-8"))
                prog[lang_code]["licao_atual"] = num + 1
                prog[lang_code].setdefault("historico", []).append(
                    {"data": hoje, "licao": num, "resultado": fb_tipo})
                salvar_json_e_sync(BASE_DIR / "progresso.json", prog)
            except Exception:
                pass

        if fb_tipo == "dificil":
            tg_post("sendMessage", {
                "chat_id": chat_id,
                "text": f"😰 Anotado! Essa lição estava difícil demais.\n\nQuer que eu gere uma nova versão mais fácil agora?",
                "reply_markup": json.dumps({"inline_keyboard": [[
                    {"text": "✅ Sim, gerar mais fácil", "callback_data": f"refazer_facil_{lang_code}"},
                    {"text": "❌ Não, só registrar",     "callback_data": f"refazer_nao_{lang_code}"},
                ]]}),
            })
        elif fb_tipo == "facil":
            msg(chat_id, f"😴 Registrado! Próximas aulas de {NOMES[lang_code]} serão mais desafiadoras. Lição {num+1} na próxima vez. 🚀")
        else:
            msg(chat_id, f"👍 Ótimo! Nível ideal. Lição {num} concluída — próxima vez vem a Lição {num+1}. Continua assim! 💪")

    # ── Refazer aula mais fácil ───────────────────────────────────────────────
    elif acao == "refazer":
        opcao     = lang_code.split("_", 1)[0]   # facil | nao
        lang_code = lang_code.split("_", 1)[1]   # fr | es | en
        if opcao == "nao":
            msg(chat_id, "Ok! Feedback salvo. A próxima aula virá mais fácil. 💪")
        else:
            msg(chat_id, f"⏳ Gerando uma versão mais fácil de {NOMES[lang_code]}...")
            def _refazer():
                try:
                    sys.path.insert(0, str(BASE_DIR))
                    ga   = importlib.import_module("gerar_aula"); importlib.reload(ga)
                    lang = next(l for l in ga.LANGS if l["code"] == lang_code)
                    licao = ga.licao_do_dia(lang_code)
                    # Injeta instrução de simplificar no prompt
                    licao_facil = dict(licao)
                    licao_facil["_dica_dificuldade"] = "mais_facil"

                    # Gera história com override de dificuldade
                    import random
                    tema = random.choice(ga.TEMAS)
                    lingua_nome = {"fr": "FRANCÊS", "es": "ESPANHOL", "en": "INGLÊS"}.get(lang_code, lang["lingua"].upper())
                    raw = ga.groq(ga.SYS_PROF, f"""
ATENÇÃO: a história INTEIRA deve ser escrita em {lingua_nome} — nunca em português.

O aluno achou a última história MUITO DIFÍCIL. Escreva uma versão MAIS SIMPLES e MAIS CURTA.

Regras:
- Nível: {licao['nivel']} mas com linguagem ainda mais básica e acessível
- Frases MUITO curtas (máximo 8 palavras por frase)
- Vocabulário ultra simples — use as palavras da lição: {', '.join(licao['vocabulario'])}
- Tema: {tema}
- 3 parágrafos com 2-3 frases cada
- TODO o texto em {lang['lingua']}
- NÃO inclua título ou instruções

Após a história, coloque a tradução em português separada por: ---TRADUCAO---
""", tokens=700)

                    seps = ["---TRADUCAO---","---Tradução---","Tradução:","Translation:"]
                    orig, trad = raw, ""
                    for sep in seps:
                        if sep in raw:
                            orig, trad = raw.split(sep, 1); break
                    def _limpar(t):
                        out = []
                        for l in t.splitlines():
                            ls = l.strip()
                            if not ls: continue
                            if ls.endswith(":") and len(ls)<30: continue
                            if ls.startswith(("**","##","Paragraphe","Párrafo","Paragraph","---")): continue
                            out.append(ls)
                        return "\n".join(out)
                    orig = _limpar(orig)
                    paragrafos = [p.strip() for p in orig.split("\n\n") if p.strip()]
                    if len(paragrafos) == 1:
                        linhas = [l for l in orig.splitlines() if l.strip()]
                        paragrafos = [" ".join(linhas[i:i+3]) for i in range(0,len(linhas),3) if linhas[i:i+3]]
                    hist = {"titulo": tema.capitalize(), "paragrafos": paragrafos,
                            "texto_completo": "\n\n".join(paragrafos), "traducao": _limpar(trad).strip()}

                    audio_path = BASE_DIR / f"{lang_code}_historia.mp3"
                    ga.gerar_audio(hist["texto_completo"], lang_code, audio_path)

                    aula_cache[f"{chat_id}_{lang_code}"] = {"licao": licao, "historia": hist, "lang": lang}

                    texto = "\n\n".join(hist["paragrafos"])
                    msg(chat_id, f"{lang['flag']} *Versão mais fácil* — {lang['label']} Lição {licao['numero']}\n\n{texto}")
                    with open(audio_path, "rb") as f:
                        tg_post("sendAudio", {"chat_id": chat_id,
                            "title": f"{lang['label']} — mais fácil", "performer": "Language Tutor"},
                            files={"audio": f})
                    tg_post("sendMessage", {"chat_id": chat_id, "text": "O que quer fazer?",
                        "reply_markup": json.dumps({"inline_keyboard": [
                            [{"text": "🌐 Tradução", "callback_data": f"trad_{lang_code}"},
                             {"text": "📝 Vocabulário", "callback_data": f"vocab_{lang_code}"}],
                            [{"text": "😴 Fácil demais", "callback_data": f"fb_facil_{lang_code}"},
                             {"text": "👍 Na medida",    "callback_data": f"fb_ok_{lang_code}"},
                             {"text": "😰 Difícil demais","callback_data": f"fb_dificil_{lang_code}"}],
                            [{"text": "💬 Conversar", "callback_data": f"conv_{lang_code}"},
                             {"text": "🎯 Avaliar nível", "callback_data": f"avaliar_{lang_code}"}],
                        ]})})
                except Exception as e:
                    msg(chat_id, f"Não consegui gerar a versão mais fácil. ({e})", parse_mode="")
            threading.Thread(target=_refazer, daemon=True).start()

    # ── Avaliação de nível ────────────────────────────────────────────────────
    elif acao == "avaliar":
        perguntas = {
            "fr": [
                "Bonjour ! Comment tu t'appelles et d'où tu viens ?",
                "Qu'est-ce que tu fais dans la vie ? Tu travailles ou tu étudies ?",
                "Parle-moi d'une journée typique dans ta vie.",
            ],
            "es": [
                "Hola, ¿me puedes contar un poco sobre ti? ¿De dónde eres y qué haces?",
                "¿Cuáles son tus hobbies? ¿Qué haces en tu tiempo libre?",
                "¿Puedes describirme una situación difícil que hayas superado?",
            ],
            "en": [
                "Tell me about yourself — your background, what you do, and what brings you to language learning.",
                "What's a topic you're passionate about? Can you elaborate on why?",
                "Describe a complex situation you had to navigate recently — what was the challenge and how did you handle it?",
            ],
        }
        conv_mode[chat_id] = {
            "modo": "avaliacao",
            "lang_code": lang_code,
            "pergunta_idx": 0,
            "perguntas": perguntas[lang_code],
            "respostas": [],
        }
        intro = (
            f"🎯 *Avaliação de nível — {NOMES[lang_code]}*\n\n"
            f"Vou te fazer 3 perguntas em {NOMES[lang_code]}. "
            f"Responda por *áudio*, da forma mais natural possível — sem se preocupar com erros.\n\n"
            f"Vamos lá! Primeira pergunta:"
        )
        msg(chat_id, intro)
        resposta_audio(chat_id, perguntas[lang_code][0])

    # ── Conversar ─────────────────────────────────────────────────────────────
    elif acao == "conv":
        licao = cached.get("licao", {})
        conv_mode[chat_id] = {
            "modo": "conversa",
            "lang_code": lang_code,
            "licao": licao,
            "historia": cached.get("historia", {}),
        }
        msg(chat_id,
            f"💬 Modo conversa ativado para *{NOMES[lang_code]}*!\n\n"
            f"Pode me perguntar qualquer coisa sobre a aula — "
            f"por texto ou áudio. Para sair, digite *sair*.")

    # ── Escolha de idioma para nova aula ─────────────────────────────────────
    elif acao == "aula":
        enviar_aula_idioma(chat_id, lang_code)


# ── processamento de mensagens ────────────────────────────────────────────────

def processar(msg_data):
    chat_id = str(msg_data["chat"]["id"])
    if chat_id != TELEGRAM_CHAT:
        return

    # Verifica se está em modo conversa
    em_conv = chat_id in conv_mode

    if "text" in msg_data:
        texto = msg_data["text"].strip()

        if texto.lower() == "sair" and em_conv:
            del conv_mode[chat_id]
            msg(chat_id, "👋 Saindo do modo conversa. Até mais!")
            return

        if texto.startswith("/start"):
            msg(chat_id,
                "👋 Olá! Sou o *Professor Tutor*.\n\n"
                "• Digite *aula* → escolha o idioma e receba a lição\n"
                "• Mande *texto* → respondo em texto\n"
                "• Mande *áudio* → respondo em áudio\n"
                "• Mande *foto* → interpreto o conteúdo\n\n"
                "Pode começar! 😊")
            return

        if texto.lower() == "aula" and not em_conv:
            tg_post("sendMessage", {
                "chat_id": chat_id,
                "text": "🌍 Qual idioma você quer estudar?",
                "reply_markup": json.dumps({"inline_keyboard": [[
                    {"text": "🇫🇷 Francês",  "callback_data": "aula_fr"},
                    {"text": "🇪🇸 Espanhol", "callback_data": "aula_es"},
                    {"text": "🇬🇧 Inglês",   "callback_data": "aula_en"},
                ]]}),
            })
            return

        digitando(chat_id)
        estado = conv_mode.get(chat_id, {})
        if estado.get("modo") == "conversa":
            sistema = (
                f"O aluno está conversando sobre {NOMES[estado['lang_code']]} "
                f"(Lição {estado['licao'].get('numero',1)}: {estado['licao'].get('titulo','')}).\n"
                f"História: {estado['historia'].get('texto_completo','')[:500]}"
            )
            resposta = ia(texto, sistema_extra=sistema)
        elif estado.get("modo") == "avaliacao":
            resposta = "Por favor, responda por *áudio* durante a avaliação. 🎤"
        else:
            resposta = ia(texto)
        msg(chat_id, resposta, parse_mode="")

    elif "voice" in msg_data or "audio" in msg_data:
        file_id = msg_data.get("voice", msg_data.get("audio", {})).get("file_id")
        if not file_id: return
        try:
            digitando(chat_id)
            transcricao = transcrever(file_id)
            estado = conv_mode.get(chat_id, {})

            # Modo avaliação de nível
            if estado.get("modo") == "avaliacao":
                estado["respostas"].append(transcricao)
                idx = estado["pergunta_idx"] + 1
                estado["pergunta_idx"] = idx
                perguntas = estado["perguntas"]

                if idx < len(perguntas):
                    # Próxima pergunta
                    conv_mode[chat_id] = estado
                    msg(chat_id, f"Ótimo! Próxima pergunta:")
                    resposta_audio(chat_id, perguntas[idx])
                else:
                    # Avaliação completa
                    del conv_mode[chat_id]
                    lang_code = estado["lang_code"]
                    respostas_txt = "\n".join(
                        f"P{i+1}: {p}\nR{i+1}: {r}"
                        for i, (p, r) in enumerate(zip(perguntas, estado["respostas"]))
                    )
                    # Análise estruturada: retorna nível CEFR + feedback
                    analise_raw = ia(
                        f"Analise as respostas do aluno em {NOMES[lang_code]}:\n\n"
                        f"{respostas_txt}\n\n"
                        f"Responda EXATAMENTE neste formato:\n"
                        f"NIVEL: <apenas o código, ex: A1, B2, C1>\n"
                        f"RESUMO: <2-3 frases: pontos fortes, pontos a melhorar e recomendação encorajadora>",
                        max_tokens=300,
                    )
                    # Extrai nível CEFR
                    nivel_detectado = "A1"
                    resumo = analise_raw
                    for linha in analise_raw.splitlines():
                        if linha.startswith("NIVEL:"):
                            candidato = linha.split(":", 1)[1].strip().upper()
                            if candidato in ("A0","A1","A2","B1","B2","C1","C2"):
                                nivel_detectado = candidato
                        if linha.startswith("RESUMO:"):
                            resumo = linha.split(":", 1)[1].strip()

                    # Posiciona no currículo na primeira lição do nível detectado
                    try:
                        sys.path.insert(0, str(BASE_DIR))
                        ga   = importlib.import_module("gerar_aula"); importlib.reload(ga)
                        curr = ga.carregar_curriculo()
                        licao_alvo = None
                        for bloco in curr[lang_code]["jornada"]:
                            if bloco["nivel"] == nivel_detectado and bloco["licoes"]:
                                licao_alvo = bloco["licoes"][0]["numero"]
                                break
                        if licao_alvo is None:
                            # Nível não existe no currículo → usa o mais próximo disponível
                            todos = [l for b in curr[lang_code]["jornada"] for l in b["licoes"]]
                            licao_alvo = todos[0]["numero"]

                        prog = json.loads((BASE_DIR / "progresso.json").read_text(encoding="utf-8"))
                        prog[lang_code]["licao_atual"] = licao_alvo
                        salvar_json_e_sync(BASE_DIR / "progresso.json", prog)
                    except Exception as e:
                        print(f"  ⚠ posicionamento: {e}")
                        licao_alvo = "?"

                    # Salva avaliação no perfil
                    try:
                        perfil = json.loads((BASE_DIR / "perfil.json").read_text(encoding="utf-8"))
                        perfil[lang_code]["nivel_atual"] = nivel_detectado
                        perfil[lang_code]["avaliacoes"].append({
                            "data": datetime.date.today().isoformat(),
                            "respostas": estado["respostas"],
                            "nivel_detectado": nivel_detectado,
                            "resumo": resumo,
                        })
                        salvar_json_e_sync(BASE_DIR / "perfil.json", perfil)
                    except Exception:
                        pass

                    resultado = (
                        f"🎯 *Avaliação concluída!*\n\n"
                        f"Nível detectado: *{nivel_detectado}*\n\n"
                        f"{resumo}\n\n"
                        f"✅ Suas próximas aulas de {NOMES[lang_code]} começam na lição {licao_alvo} — "
                        f"nível {nivel_detectado}. Mande *aula* quando quiser começar!"
                    )
                    msg(chat_id, resultado)
                    resposta_audio(chat_id, f"Nível detectado: {nivel_detectado}. {resumo}")

            # Modo conversa normal
            elif estado.get("modo") == "conversa":
                sistema = (
                    f"O aluno está conversando sobre {NOMES[estado['lang_code']]} "
                    f"(Lição {estado['licao'].get('numero',1)}: {estado['licao'].get('titulo','')}).\n"
                    f"História: {estado['historia'].get('texto_completo','')[:500]}"
                )
                resposta = ia(transcricao, sistema_extra=sistema)
                resposta_audio(chat_id, resposta)
            else:
                resposta = ia(transcricao)
                resposta_audio(chat_id, resposta)

        except Exception as e:
            msg(chat_id, f"Não consegui processar o áudio. ({e})", parse_mode="")

    elif "photo" in msg_data:
        caption = msg_data.get("caption", "O que você vê nesta imagem?")
        try:
            digitando(chat_id)
            desc = descrever_foto(msg_data["photo"][-1]["file_id"])
            resposta = ia(caption, sistema_extra=f"Foto enviada pelo aluno: {desc}")
            msg(chat_id, resposta, parse_mode="")
        except Exception as e:
            msg(chat_id, f"Não consegui processar a foto. ({e})", parse_mode="")


# ── loop principal ────────────────────────────────────────────────────────────

def _gerar_se_necessario():
    """Gera a aula do dia se ainda não foi gerada hoje."""
    try:
        aula_path = BASE_DIR / "aula_atual.json"
        if aula_path.exists():
            data = json.loads(aula_path.read_text(encoding="utf-8")).get("data", "")
            if data == datetime.date.today().isoformat():
                print("  Aula de hoje já existe, pulando geração.")
                return
        print("  Aula de hoje não encontrada — gerando agora...")
        import importlib.util
        spec = importlib.util.spec_from_file_location("gerar_aula", BASE_DIR / "gerar_aula.py")
        mod  = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.main()
    except Exception as e:
        print(f"  ⚠ Não foi possível gerar aula: {e}")


def main():
    print("Language Tutor Bot — iniciando...")
    try:
        restaurar_estado()
    except Exception as e:
        print(f"  ⚠ Não foi possível restaurar do GitHub: {e}")
    threading.Thread(target=_gerar_se_necessario, daemon=True).start()
    print("Language Tutor Bot — ouvindo... (Ctrl+C para parar)")
    offset = None
    while True:
        try:
            params = {"timeout": 25, "allowed_updates": ["message", "callback_query"]}
            if offset: params["offset"] = offset
            for u in tg_get("getUpdates", params).get("result", []):
                offset = u["update_id"] + 1
                try:
                    if "message" in u:
                        processar(u["message"])
                    elif "callback_query" in u:
                        cb      = u["callback_query"]
                        chat_id = str(cb["message"]["chat"]["id"])
                        handle_callback(chat_id, cb.get("data", ""), cb["id"])
                except Exception as e:
                    print(f"Erro: {e}")
        except requests.exceptions.Timeout:
            pass
        except KeyboardInterrupt:
            print("Bot encerrado.")
            break
        except Exception as e:
            print(f"Erro geral: {e}")
            time.sleep(5)

def _scheduler():
    """Roda gerar_aula.py todo dia às 5h (horário do servidor)."""
    import importlib.util, traceback
    ultimo_dia = None
    while True:
        agora = datetime.datetime.now()
        hoje  = agora.date()
        if agora.hour == 5 and ultimo_dia != hoje:
            print(f"[scheduler] 5h — gerando aulas de {hoje}")
            try:
                spec = importlib.util.spec_from_file_location(
                    "gerar_aula", BASE_DIR / "gerar_aula.py")
                mod  = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                mod.main()
                ultimo_dia = hoje
            except Exception:
                traceback.print_exc()
        time.sleep(60)


if __name__ == "__main__":
    t = threading.Thread(target=_scheduler, daemon=True)
    t.start()
    main()
