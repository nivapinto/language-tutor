#!/usr/bin/env python3
"""
Language Tutor — Agente diário de idiomas
Currículo do zero | Estilo Cambridge Grammar in Use
Groq (gratuito) + Edge TTS (gratuito)

Uso: python3 gerar_aula.py
Agendado: cron às 5h todo dia
"""

import os, json, smtplib, asyncio, datetime, base64
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path

import edge_tts, requests
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

groq_client     = Groq(api_key=os.environ["GROQ_API_KEY"])
TELEGRAM_TOKEN  = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT   = os.environ.get("TELEGRAM_CHAT_ID", "")
RECIPIENT_EMAIL = "anivaldojr@gmail.com"
BASE_DIR        = Path(__file__).parent
PAGES_URL       = "https://nivapinto.github.io/language-tutor/"

VOICE_MAP = {"fr": "fr-FR-DeniseNeural", "es": "es-ES-ElviraNeural", "en": "en-US-JennyNeural"}

LANGS = [
    {"code": "fr", "label": "Français",  "flag": "🇫🇷", "lingua": "francês"},
    {"code": "es", "label": "Español",   "flag": "🇪🇸", "lingua": "espanhol"},
    {"code": "en", "label": "English",   "flag": "🇬🇧", "lingua": "inglês"},
]


# ── utilitário Groq ───────────────────────────────────────────────────────────

def groq(system: str, user: str, tokens: int = 1500) -> str:
    r = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        max_tokens=tokens,
    )
    return r.choices[0].message.content.strip()


# ── progresso ─────────────────────────────────────────────────────────────────

def carregar_progresso() -> dict:
    p = BASE_DIR / "progresso.json"
    return json.loads(p.read_text(encoding="utf-8"))

def salvar_progresso(prog: dict) -> None:
    (BASE_DIR / "progresso.json").write_text(json.dumps(prog, ensure_ascii=False, indent=2), encoding="utf-8")

def carregar_curriculo() -> dict:
    return json.loads((BASE_DIR / "curriculo.json").read_text(encoding="utf-8"))

def licao_do_dia(lang_code: str) -> dict:
    prog  = carregar_progresso()
    curr  = carregar_curriculo()
    num   = prog[lang_code]["licao_atual"]
    licoes = curr[lang_code]["licoes"]
    # se passou do currículo pré-definido, gera dados genéricos
    for l in licoes:
        if l["numero"] == num:
            return l
    ultimo = licoes[-1]
    return {**ultimo, "numero": num, "titulo": f"Revisão e expansão — lição {num}"}


# ── geração de conteúdo ───────────────────────────────────────────────────────

SYS_PROF = (
    "Você é um professor de idiomas experiente, simpático e encorajador, especialista no método Cambridge Grammar in Use. "
    "Seu tom é simples, direto e acolhedor — como um professor particular de confiança. "
    "Cria conteúdo progressivo e adequado ao nível do aluno, começando sempre pelo mais básico. "
    "Nunca use palavras ou estruturas além do vocabulário da lição atual. "
    "Explicações sempre em português claro. Exemplos sempre no idioma-alvo. "
    "Seja encorajador: o aluno está começando do zero."
)

def gerar_gramatica(lang: dict, licao: dict) -> dict:
    raw = groq(SYS_PROF, f"""
Crie a seção GRAMÁTICA da lição {licao['numero']} de {lang['lingua']} (nível {licao['nivel']}).

Tópico gramatical: {licao['gramatica']}
Vocabulário da lição: {', '.join(licao['vocabulario'])}

Use EXATAMENTE este formato:

TITULO: <título da regra gramatical>
EXPLICACAO: <explicação em português, máximo 4 frases simples e diretas>
TABELA:
<linha 1 da tabela no formato: Pronome | Forma | Exemplo>
<linha 2>
<linha 3>
(máximo 6 linhas)
FIM_TABELA
EXEMPLO_1: <frase muito simples usando o vocabulário da lição>
EXEMPLO_2: <frase muito simples>
EXEMPLO_3: <frase muito simples>
DICA: <dica de memorização em 1 frase>
""", tokens=800)

    result = {"titulo": "", "explicacao": "", "tabela": [], "exemplos": [], "dica": ""}
    em_tabela = False
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("TITULO:"): result["titulo"] = line.split(":", 1)[1].strip()
        elif line.startswith("EXPLICACAO:"): result["explicacao"] = line.split(":", 1)[1].strip()
        elif line == "TABELA:": em_tabela = True
        elif line == "FIM_TABELA": em_tabela = False
        elif em_tabela and line: result["tabela"].append(line)
        elif line.startswith("EXEMPLO_"): result["exemplos"].append(line.split(":", 1)[1].strip())
        elif line.startswith("DICA:"): result["dica"] = line.split(":", 1)[1].strip()
    return result


def gerar_exercicios(lang: dict, licao: dict, gramatica: dict) -> dict:
    raw = groq(SYS_PROF, f"""
Crie 5 exercícios para a lição {licao['numero']} de {lang['lingua']} (nível {licao['nivel']}).
Tópico: {licao['gramatica']}
Vocabulário: {', '.join(licao['vocabulario'])}
Exemplos da gramática: {'; '.join(gramatica['exemplos'])}

Use tipos variados. Formato EXATO:

EX1_TIPO: lacuna
EX1_ENUNCIADO: Complete: ___ m'appelle Marie. (eu)
EX1_RESPOSTA: Je

EX2_TIPO: multipla_escolha
EX2_ENUNCIADO: Qual é a tradução de "merci"?
EX2_OPCOES: A) por favor | B) obrigado | C) bom dia
EX2_RESPOSTA: B

EX3_TIPO: lacuna
EX3_ENUNCIADO: <enunciado com lacuna>
EX3_RESPOSTA: <resposta>

EX4_TIPO: verdadeiro_falso
EX4_ENUNCIADO: "Bonjour" significa "boa noite". Verdadeiro ou Falso?
EX4_RESPOSTA: Falso — "Bonjour" significa "bom dia"

EX5_TIPO: traducao
EX5_ENUNCIADO: Traduza para {lang['lingua']}: "Thank you, please."
EX5_RESPOSTA: <resposta>
""", tokens=900)

    exercises = []
    atual = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line: continue
        for i in range(1, 6):
            prefix = f"EX{i}_"
            if line.startswith(prefix):
                key = line[len(prefix):line.index(":")].lower()
                val = line.split(":", 1)[1].strip()
                if key == "tipo" and atual:
                    exercises.append(atual)
                    atual = {}
                if key == "opcoes":
                    atual["opcoes"] = [o.strip() for o in val.split("|")]
                else:
                    atual[key] = val
    if atual:
        exercises.append(atual)
    return exercises[:5]


TEMAS = [
    "uma viagem surpreendente", "uma descoberta científica recente", "um festival cultural",
    "um chef famoso e sua receita secreta", "uma cidade inusitada no mundo",
    "um atleta que superou um obstáculo", "uma invenção que mudou o cotidiano",
    "um mercado de rua cheio de vida", "uma história de amizade improvável",
    "um dia na vida de uma pessoa comum em outro país",
]

def gerar_historia(lang: dict, licao: dict) -> dict:
    import random, datetime
    tema = random.choice(TEMAS)
    hoje = datetime.date.today().strftime("%d/%m/%Y")

    raw = groq(SYS_PROF, f"""
Escreva uma história narrativa envolvente em {lang['lingua']} para um aluno nível {licao['nivel']}.

Tema sugerido: {tema}
Vocabulário da lição para incluir naturalmente: {', '.join(licao['vocabulario'])}
Data: {hoje}

Regras da história:
- 3 parágrafos com 3-4 frases cada
- Narrativa real e interessante, com início, meio e fim — não um diálogo de sala de aula
- Linguagem simples e direta, adequada ao nível {licao['nivel']}
- Frases curtas, vocabulário acessível para iniciantes
- Tom jornalístico leve ou narrativo — como uma notícia interessante ou um conto curto
- Use o vocabulário da lição de forma natural dentro da história
- NÃO inclua título, numeração ou instruções

Após a história, coloque a tradução completa em português separada por: ---TRADUCAO---

Formato de saída:
<parágrafo 1>

<parágrafo 2>

<parágrafo 3>

---TRADUCAO---
<tradução em português>
""", tokens=900)

    if "---TRADUCAO---" in raw:
        orig, trad = raw.split("---TRADUCAO---", 1)
    else:
        orig, trad = raw, ""

    paragrafos = [p.strip() for p in orig.strip().split("\n\n") if p.strip()]
    return {
        "titulo": tema.capitalize(),
        "paragrafos": paragrafos,
        "texto_completo": "\n\n".join(paragrafos),
        "traducao": trad.strip(),
    }


# ── áudio ─────────────────────────────────────────────────────────────────────

async def _audio_async(text: str, voice: str, path: Path):
    await edge_tts.Communicate(text, voice).save(str(path))

def gerar_audio(text: str, lang_code: str, path: Path):
    asyncio.run(_audio_async(text, VOICE_MAP[lang_code], path))
    print(f"  Áudio: {path.name}")


# ── HTML principal (GitHub Pages) ─────────────────────────────────────────────

def gerar_html(aulas: list) -> str:
    today = datetime.date.today().strftime("%d/%m/%Y")
    cards = ""

    for a in aulas:
        lang  = a["lang"]
        licao = a["licao"]
        g     = a["gramatica"]
        exs   = a["exercicios"]
        h     = a["historia"]
        code  = lang["code"]

        tabela_rows   = "".join("<tr>" + "".join(f"<td>{c.strip()}</td>" for c in r.split("|")) + "</tr>" for r in g["tabela"])
        exemplos_html = "".join(f'<div class="example"><span class="ex-num">{i+1}</span>{e}</div>' for i, e in enumerate(g["exemplos"]))
        paras_html    = "".join(f'<p class="story-para">{p}</p>' for p in h["paragrafos"])

        exs_html = ""
        for i, ex in enumerate(exs):
            tipo = ex.get("tipo", "")
            enun = ex.get("enunciado", "")
            resp = ex.get("resposta", "")
            opcoes_html = ""
            if "opcoes" in ex:
                opcoes_html = '<div class="opcoes">' + "".join(f'<span class="opcao">{o}</span>' for o in ex["opcoes"]) + "</div>"
            badge = {"lacuna": "Preencha", "multipla_escolha": "Escolha", "verdadeiro_falso": "V ou F", "traducao": "Traduza"}.get(tipo, "")
            exs_html += f"""
<div class="exercise">
  <div class="ex-header"><span class="ex-n">{i+1}</span><span class="ex-badge">{badge}</span></div>
  <p class="ex-text">{enun}</p>{opcoes_html}
  <button class="btn-gabarito" onclick="toggleEl('resp-{code}-{i}')">Ver resposta</button>
  <div class="resposta" id="resp-{code}-{i}" hidden>✅ {resp}</div>
</div>"""

        cards += f"""
<div class="lang-block" id="block-{code}">
  <div class="lang-header">
    <span class="flag">{lang['flag']}</span>
    <div class="lang-info">
      <h2>{lang['label']}</h2>
      <span class="licao-badge">Lição {licao['numero']} · {licao['nivel']}</span>
    </div>
  </div>
  <h3 class="licao-titulo">{licao['titulo']}</h3>

  <div class="tabs">
    <button class="tab active" onclick="tab('{code}','hist',this)">🎧 História</button>
    <button class="tab" onclick="tab('{code}','gram',this)">📘 Gramática</button>
    <button class="tab" onclick="tab('{code}','ex',this)">✏️ Exercícios</button>
  </div>

  <!-- HISTÓRIA + ÁUDIO -->
  <div id="{code}-hist" class="panel active">
    <audio controls src="{code}_historia.mp3" style="width:100%;margin-bottom:1rem"></audio>
    <div class="story-block">{paras_html}</div>
    <button class="btn-trad" onclick="toggleEl('trad-{code}')">🌐 Ver tradução</button>
    <div class="trad-box" id="trad-{code}" hidden>
      <p class="section-label">Tradução</p>
      <p class="trad-text">{h['traducao'].replace(chr(10), '<br>')}</p>
    </div>
  </div>

  <!-- GRAMÁTICA -->
  <div id="{code}-gram" class="panel">
    <div class="rule-box">
      <h4 class="rule-title">{g['titulo']}</h4>
      <p class="rule-exp">{g['explicacao']}</p>
    </div>
    <table class="gram-table"><tbody>{tabela_rows}</tbody></table>
    <div class="examples-block">
      <p class="section-label">Exemplos</p>{exemplos_html}
    </div>
    <div class="tip-box">💡 {g['dica']}</div>
  </div>

  <!-- EXERCÍCIOS -->
  <div id="{code}-ex" class="panel">
    <p class="section-label">Exercícios — Lição {licao['numero']}</p>
    {exs_html}
  </div>
</div>
"""

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Language Tutor — {today}</title>
  <style>
    :root {{
      --bg: #0f172a; --surface: #1e293b; --border: #334155;
      --text: #e2e8f0; --muted: #94a3b8; --accent: #6366f1;
      --accent2: #a5b4fc; --success: #22c55e; --warn: #fbbf24;
    }}
    *,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:'Segoe UI',system-ui,sans-serif;background:var(--bg);color:var(--text);min-height:100vh;padding:1rem}}
    header{{text-align:center;padding:1.5rem 0 1rem}}
    header h1{{font-size:1.8rem;color:#f8fafc;font-weight:700}}
    header p{{color:var(--muted);font-size:.875rem;margin-top:.3rem}}
    .lang-block{{background:var(--surface);border:1px solid var(--border);border-radius:16px;padding:1.25rem;margin-bottom:1.5rem;max-width:680px;margin-left:auto;margin-right:auto}}
    .lang-header{{display:flex;align-items:center;gap:.75rem;margin-bottom:.5rem}}
    .flag{{font-size:2rem}}
    .lang-info h2{{font-size:1.15rem;color:#f1f5f9;font-weight:700}}
    .licao-badge{{font-size:.7rem;color:var(--muted);background:var(--bg);border:1px solid var(--border);border-radius:99px;padding:.15rem .6rem;display:inline-block;margin-top:.2rem}}
    .licao-titulo{{font-size:1rem;color:var(--accent2);margin-bottom:1rem;padding-left:.25rem}}
    .tabs{{display:flex;gap:.4rem;margin-bottom:1rem}}
    .tab{{flex:1;padding:.5rem .25rem;border:1px solid var(--border);border-radius:8px;background:var(--bg);color:var(--muted);font-size:.8rem;font-weight:600;cursor:pointer;transition:.15s}}
    .tab.active,.tab:hover{{background:var(--accent);color:#fff;border-color:var(--accent)}}
    .panel{{display:none}}.panel.active{{display:block}}
    .rule-box{{background:var(--bg);border-left:4px solid var(--accent);border-radius:0 10px 10px 0;padding:1rem 1.1rem;margin-bottom:1rem}}
    .rule-title{{color:var(--accent2);font-size:.95rem;font-weight:700;margin-bottom:.5rem}}
    .rule-exp{{color:var(--text);line-height:1.7;font-size:.9rem}}
    .gram-table{{width:100%;border-collapse:collapse;margin-bottom:1rem;font-size:.88rem}}
    .gram-table td{{padding:.5rem .75rem;border-bottom:1px solid var(--border);color:var(--text)}}
    .gram-table tr:first-child td{{color:var(--accent2);font-weight:700;background:var(--bg);font-size:.78rem;text-transform:uppercase;letter-spacing:.05em}}
    .section-label{{font-size:.75rem;text-transform:uppercase;letter-spacing:.08em;color:var(--accent);font-weight:700;margin-bottom:.6rem}}
    .examples-block{{margin-bottom:.9rem}}
    .example{{display:flex;align-items:flex-start;gap:.6rem;padding:.5rem 0;border-bottom:1px solid var(--border);color:var(--text);font-size:.9rem;line-height:1.5}}
    .example:last-child{{border-bottom:none}}
    .ex-num{{background:var(--accent);color:#fff;border-radius:99px;width:1.3rem;height:1.3rem;display:flex;align-items:center;justify-content:center;font-size:.7rem;font-weight:700;flex-shrink:0;margin-top:.1rem}}
    .tip-box{{background:#1c1a00;border:1px solid #854d0e;border-radius:8px;padding:.75rem 1rem;color:var(--warn);font-size:.85rem;line-height:1.5}}
    .exercise{{background:var(--bg);border-radius:10px;padding:.9rem 1rem;margin-bottom:.75rem}}
    .ex-header{{display:flex;align-items:center;gap:.5rem;margin-bottom:.5rem}}
    .ex-n{{background:var(--accent);color:#fff;border-radius:99px;width:1.4rem;height:1.4rem;display:flex;align-items:center;justify-content:center;font-size:.75rem;font-weight:700}}
    .ex-badge{{font-size:.7rem;color:var(--muted);background:var(--surface);border:1px solid var(--border);border-radius:99px;padding:.1rem .5rem}}
    .ex-text{{color:var(--text);font-size:.9rem;line-height:1.6;margin-bottom:.5rem}}
    .opcoes{{display:flex;flex-wrap:wrap;gap:.4rem;margin-bottom:.5rem}}
    .opcao{{background:var(--surface);border:1px solid var(--border);border-radius:6px;padding:.3rem .7rem;font-size:.85rem;color:var(--text)}}
    .btn-gabarito{{font-size:.78rem;color:var(--accent);background:none;border:1px solid var(--accent);border-radius:6px;padding:.3rem .7rem;cursor:pointer}}
    .resposta{{margin-top:.5rem;padding:.5rem .75rem;background:#052e16;border-radius:6px;color:var(--success);font-size:.88rem}}
    .dialogo{{background:var(--bg);border-radius:10px;padding:.75rem;margin-bottom:1rem}}
    .fala{{padding:.5rem .75rem;border-radius:8px;margin-bottom:.4rem;font-size:.9rem;line-height:1.5;max-width:90%}}
    .fala-a{{background:var(--accent);color:#fff;margin-left:0}}
    .fala-b{{background:var(--surface);color:var(--text);border:1px solid var(--border);margin-left:auto}}
    .audio-block{{margin-bottom:.75rem}}
    audio{{border-radius:8px;margin-top:.4rem}}
    .btn-trad{{font-size:.85rem;color:var(--accent);background:none;border:1px solid var(--accent);border-radius:8px;padding:.5rem 1rem;cursor:pointer;margin-bottom:.5rem}}
    .trad-box{{background:var(--bg);border-left:3px solid var(--accent);border-radius:0 8px 8px 0;padding:.9rem 1rem}}
    .trad-text{{color:var(--muted);font-size:.88rem;line-height:1.7}}
    footer{{text-align:center;padding:2rem 0 1rem;color:var(--border);font-size:.75rem}}
  </style>
</head>
<body>
<header>
  <h1>🌍 Language Tutor</h1>
  <p>Aula do dia — {today}</p>
</header>
<main>{cards}</main>
<footer>Language Tutor · {today} · nivapinto.github.io/language-tutor</footer>
<script>
function tab(lang, panel, btn) {{
  ['gram','ex','dial'].forEach(p => document.getElementById(lang+'-'+p).classList.remove('active'));
  document.getElementById(lang+'-'+panel).classList.add('active');
  btn.closest('.tabs').querySelectorAll('.tab').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
}}
function toggleEl(id) {{ const e = document.getElementById(id); e.hidden = !e.hidden; }}
</script>
</body>
</html>"""


# ── JSON ──────────────────────────────────────────────────────────────────────

def salvar_json(aulas: list) -> None:
    data = {
        "data": datetime.date.today().isoformat(),
        "aulas": [
            {
                "code": a["lang"]["code"], "label": a["lang"]["label"],
                "flag": a["lang"]["flag"], "licao": a["licao"],
                "gramatica": a["gramatica"], "exercicios": a["exercicios"],
                "historia": a["historia"], "audio_file": f"{a['lang']['code']}_historia.mp3",
            }
            for a in aulas
        ],
    }
    (BASE_DIR / "aula_atual.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ── GitHub Pages (via API — funciona sem git local) ───────────────────────────

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO  = "nivapinto/language-tutor"
GITHUB_BRANCH = "main"

def _gh_put(path_in_repo: str, content_bytes: bytes, message: str) -> None:
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path_in_repo}"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    }
    # pega SHA atual (necessário para atualizar)
    r = requests.get(url, headers=headers, params={"ref": GITHUB_BRANCH})
    sha = r.json().get("sha") if r.ok else None
    payload = {
        "message": message,
        "branch": GITHUB_BRANCH,
        "content": base64.b64encode(content_bytes).decode(),
    }
    if sha:
        payload["sha"] = sha
    resp = requests.put(url, headers=headers, json=payload)
    if not resp.ok:
        raise RuntimeError(resp.text[:200])

def publicar_github() -> None:
    hoje = datetime.date.today().strftime("%d/%m/%Y")
    msg  = f"Aula {hoje}"
    try:
        # Arquivos de texto
        for fname in ["index.html", "aula_atual.json", "progresso.json", "perfil.json"]:
            p = BASE_DIR / fname
            if p.exists():
                _gh_put(fname, p.read_bytes(), msg)
        # Áudios
        for code in ["fr", "es", "en"]:
            p = BASE_DIR / f"{code}_historia.mp3"
            if p.exists():
                _gh_put(f"{code}_historia.mp3", p.read_bytes(), msg)
        print(f"  ✓ Publicado em {PAGES_URL}")
    except Exception as e:
        print(f"  ⚠ GitHub API: {e}")


# ── Telegram ──────────────────────────────────────────────────────────────────

def tg(method: str, **kwargs) -> None:
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/{method}", **kwargs)

def enviar_telegram(aulas: list, audio_paths: list) -> None:
    today = datetime.date.today().strftime("%d/%m/%Y")
    tg("sendMessage", data={
        "chat_id": TELEGRAM_CHAT,
        "text": f"🌍 *Language Tutor — {today}*",
        "parse_mode": "Markdown",
    })

    for a, audio_path in zip(aulas, audio_paths):
        lang  = a["lang"]
        licao = a["licao"]
        h     = a["historia"]

        # História (texto dos parágrafos)
        texto = "\n\n".join(h["paragrafos"])
        trad  = h["traducao"].replace("\n", " ").strip()

        tg("sendMessage", data={
            "chat_id": TELEGRAM_CHAT,
            "parse_mode": "Markdown",
            "text": f"{lang['flag']} *{lang['label']}* — Lição {licao['numero']}: _{licao['titulo']}_\n\n{texto}",
        })

        # Áudio da história
        with open(audio_path, "rb") as f:
            tg("sendAudio", files={"audio": f}, data={
                "chat_id": TELEGRAM_CHAT,
                "title": f"{lang['label']} — Lição {licao['numero']}",
                "performer": "Language Tutor",
            })

        # Tradução em spoiler + link para aula completa
        tg("sendMessage", data={
            "chat_id": TELEGRAM_CHAT,
            "parse_mode": "MarkdownV2",
            "text": (
                f"🌐 Tradução \\(toque para ver\\): ||{trad}||\n\n"
                f"[📘 Gramática e exercícios]({PAGES_URL})"
            ),
            "disable_web_page_preview": "true",
        })

    print("  ✓ Telegram enviado")


# ── E-mail ────────────────────────────────────────────────────────────────────

def gerar_html_email(aulas: list) -> str:
    today = datetime.date.today().strftime("%d/%m/%Y")
    cards = ""
    for a in aulas:
        lang  = a["lang"]
        licao = a["licao"]
        g     = a["gramatica"]
        exs   = a["exercicios"]
        h     = a["historia"]
        lv    = licao["nivel"]
        exemplos = "".join(f'<li style="margin-bottom:4px;color:#374151">{e}</li>' for e in g["exemplos"])
        paras_email = "".join(
            f'<p style="color:#374151;line-height:1.8;margin:0 0 10px 0;font-size:15px">{p}</p>'
            for p in h["paragrafos"]
        )
        ex_items = ""
        for i, ex in enumerate(exs[:3]):
            ex_items += f'<p style="font-size:13px;color:#374151;margin:6px 0"><strong>{i+1}.</strong> {ex.get("enunciado","")}</p>'
        cards += f"""
<table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:24px;border:1px solid #e5e7eb;border-radius:12px;overflow:hidden;background:#fff">
  <tr><td style="background:#f8fafc;padding:14px 18px;border-bottom:1px solid #e5e7eb">
    <span style="font-size:22px">{lang['flag']}</span>
    <span style="font-size:17px;font-weight:700;color:#111827;margin:0 8px">{lang['label']}</span>
    <span style="font-size:11px;color:#6b7280;background:#ede9fe;border-radius:20px;padding:2px 8px">Lição {licao['numero']} · {lv}</span>
    <div style="color:#6366f1;font-size:13px;margin-top:4px">{licao['titulo']}</div>
  </td></tr>
  <tr><td style="padding:18px">
    <p style="font-size:11px;font-weight:700;color:#6366f1;letter-spacing:.06em;text-transform:uppercase;margin:0 0 10px 0">🎧 HISTÓRIA</p>
    {paras_email}
    <details style="margin:12px 0">
      <summary style="cursor:pointer;font-size:13px;font-weight:600;color:#6366f1;padding:6px 10px;background:#eef2ff;border-radius:6px;list-style:none">🌐 Ver tradução</summary>
      <div style="margin-top:8px;padding:8px 12px;background:#f9fafb;border-left:3px solid #6366f1;border-radius:0 6px 6px 0;font-size:13px;color:#6b7280">{h['traducao'].replace(chr(10),'<br>')}</div>
    </details>
    <p style="font-size:12px;color:#9ca3af;margin:0 0 16px 0">🎧 Áudio em anexo: <strong>{lang['code']}_historia.mp3</strong></p>
    <hr style="border:none;border-top:1px solid #f3f4f6;margin:12px 0">
    <p style="font-size:11px;font-weight:700;color:#6366f1;letter-spacing:.06em;text-transform:uppercase;margin:0 0 8px 0">📘 GRAMÁTICA — {g['titulo']}</p>
    <p style="color:#374151;font-size:14px;line-height:1.7;margin:0 0 10px 0">{g['explicacao']}</p>
    <ul style="padding-left:16px;margin:0 0 8px 0">{exemplos}</ul>
    <p style="font-size:13px;color:#92400e;background:#fffbeb;padding:8px;border-radius:6px;margin:0 0 16px 0">💡 {g['dica']}</p>
    <hr style="border:none;border-top:1px solid #f3f4f6;margin:12px 0">
    <p style="font-size:11px;font-weight:700;color:#6366f1;letter-spacing:.06em;text-transform:uppercase;margin:0 0 8px 0">✏️ EXERCÍCIOS</p>
    {ex_items}
    <p style="font-size:12px;color:#9ca3af;margin-top:8px">→ Todos os exercícios e gabaritos em: <a href="{PAGES_URL}" style="color:#6366f1">{PAGES_URL}</a></p>
  </td></tr>
</table>"""

    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"></head>
<body style="font-family:'Segoe UI',Arial,sans-serif;background:#f3f4f6;margin:0;padding:20px">
<table width="100%" cellpadding="0" cellspacing="0" style="max-width:620px;margin:0 auto">
  <tr><td style="text-align:center;padding:24px 0 16px">
    <h1 style="font-size:24px;color:#111827;margin:0">🌍 Language Tutor</h1>
    <p style="color:#6b7280;margin:4px 0 12px;font-size:13px">Aula do dia — {today}</p>
    <a href="{PAGES_URL}" style="display:inline-block;padding:8px 20px;background:#6366f1;color:#fff;border-radius:8px;text-decoration:none;font-size:13px;font-weight:600">▶ Abrir com áudio completo</a>
  </td></tr>
  <tr><td>{cards}</td></tr>
  <tr><td style="text-align:center;padding:16px 0;color:#9ca3af;font-size:11px">Language Tutor · {today}</td></tr>
</table></body></html>"""


def enviar_email(aulas: list, audio_paths: list) -> None:
    gmail_user = os.environ["GMAIL_USER"]
    gmail_pass = os.environ["GMAIL_APP_PASSWORD"]
    today      = datetime.date.today().strftime("%d/%m/%Y")
    html       = gerar_html_email(aulas)

    outer = MIMEMultipart("mixed")
    outer["From"]    = gmail_user
    outer["To"]      = RECIPIENT_EMAIL
    outer["Subject"] = f"🌍 Language Tutor — {today}"
    outer.attach(MIMEText(html, "html", "utf-8"))

    for path in audio_paths:
        with open(path, "rb") as f:
            part = MIMEBase("audio", "mpeg")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f'attachment; filename="{path.name}"')
        outer.attach(part)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(gmail_user, gmail_pass)
        smtp.sendmail(gmail_user, RECIPIENT_EMAIL, outer.as_string())
    print(f"  ✓ E-mail enviado para {RECIPIENT_EMAIL}")


# ── avançar progresso ─────────────────────────────────────────────────────────

def registrar_aula(aulas: list) -> None:
    prog = carregar_progresso()
    today = datetime.date.today().isoformat()
    for a in aulas:
        code = a["lang"]["code"]
        prog[code]["historico"].append({"data": today, "licao": a["licao"]["numero"]})
    salvar_progresso(prog)


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 55)
    print(f"  Language Tutor — {datetime.date.today().strftime('%d/%m/%Y')}")
    print("=" * 55)

    aulas, audio_paths = [], []

    for lang in LANGS:
        print(f"\n[{lang['flag']} {lang['label']}]")
        licao = licao_do_dia(lang["code"])
        print(f"  Lição {licao['numero']}: {licao['titulo']}")

        print("  Gerando gramática...")
        gramatica = gerar_gramatica(lang, licao)

        print("  Gerando exercícios...")
        exercicios = gerar_exercicios(lang, licao, gramatica)

        print("  Gerando história...")
        historia = gerar_historia(lang, licao)

        print("  Gerando áudio...")
        audio_path = BASE_DIR / f"{lang['code']}_historia.mp3"
        gerar_audio(historia["texto_completo"], lang["code"], audio_path)
        audio_paths.append(audio_path)

        aulas.append({"lang": lang, "licao": licao, "gramatica": gramatica,
                      "exercicios": exercicios, "historia": historia})

    print("\n[📄 Gerando index.html...]")
    (BASE_DIR / "index.html").write_text(gerar_html(aulas), encoding="utf-8")

    print("[💾 Salvando JSON...]")
    salvar_json(aulas)
    registrar_aula(aulas)

    print("[🌐 Publicando no GitHub Pages...]")
    publicar_github()

    print("[📱 Enviando Telegram...]")
    try:
        enviar_telegram(aulas, audio_paths)
    except Exception as e:
        print(f"  ⚠ Telegram: {e}")

    print("[📧 Enviando e-mail...]")
    try:
        enviar_email(aulas, audio_paths)
    except Exception as e:
        print(f"  ⚠ E-mail: {e}")

    print(f"\n✅ Pronto! → {PAGES_URL}")


if __name__ == "__main__":
    main()
