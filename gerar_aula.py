#!/usr/bin/env python3
"""
Gera 3 histórias em 3 idiomas via Groq (gratuito), cria os MP3 via Edge TTS
(gratuito, sem API key), atualiza o index.html, salva aula_atual.json
e envia e-mail com as histórias no corpo + MP3s anexados.

Uso: python gerar_aula.py
"""

import os
import json
import smtplib
import asyncio
import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path

import edge_tts
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

groq_client = Groq(api_key=os.environ["GROQ_API_KEY"])

RECIPIENT_EMAIL = "anivaldojr@gmail.com"

VOICE_MAP = {
    "fr": "fr-FR-DeniseNeural",
    "es": "es-ES-ElviraNeural",
    "en": "en-US-JennyNeural",
}

LANGS = [
    {"code": "fr", "label": "Français",  "level": "iniciante (A1-A2)",            "prompt_lang": "francês",  "flag": "🇫🇷"},
    {"code": "es", "label": "Español",   "level": "intermediário (B1-B2)",         "prompt_lang": "espanhol", "flag": "🇪🇸"},
    {"code": "en", "label": "English",   "level": "avançado conversacional (C1)",  "prompt_lang": "inglês",   "flag": "🇬🇧"},
]


# ── 1. Gerar histórias ────────────────────────────────────────────────────────

def gerar_historia(lang: dict) -> dict:
    today = datetime.date.today().strftime("%d/%m/%Y")
    prompt = f"""Crie uma história curta em {lang['prompt_lang']} para nível {lang['level']}.

Requisitos:
- Exatamente 3 parágrafos separados por linha em branco
- Cada parágrafo com 3-4 frases naturais e fluentes
- Tema do dia ({today}): algo do cotidiano, viagem, cultura ou gastronomia
- NÃO inclua título, numeração ou qualquer texto fora da história

Após a história, forneça a tradução completa para o português brasileiro,
separada por uma linha contendo exatamente: ---TRADUCAO---"""

    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": (
                "Você é um professor de idiomas experiente que cria textos pedagógicos "
                "envolventes, culturalmente ricos e adequados ao nível do aluno."
            )},
            {"role": "user", "content": prompt},
        ],
        max_tokens=1200,
    )
    raw = response.choices[0].message.content.strip()

    if "---TRADUCAO---" in raw:
        original_part, traducao_part = raw.split("---TRADUCAO---", 1)
    else:
        original_part = raw
        traducao_part = "(tradução não gerada)"

    paragraphs = [p.strip() for p in original_part.strip().split("\n\n") if p.strip()]
    return {
        "text": "\n\n".join(paragraphs),
        "paragraphs": paragraphs,
        "translation": traducao_part.strip(),
    }


# ── 2. Gerar áudios ──────────────────────────────────────────────────────────

async def _gerar_audio_async(text: str, voice: str, output_path: Path) -> None:
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(str(output_path))


def gerar_audio(text: str, lang_code: str, output_path: Path) -> None:
    asyncio.run(_gerar_audio_async(text, VOICE_MAP[lang_code], output_path))
    print(f"  Áudio salvo: {output_path.name}")


# ── 3. Gerar index.html (player local) ───────────────────────────────────────

def gerar_html(stories: list) -> str:
    today_str = datetime.date.today().strftime("%d de %B de %Y")
    cards = ""
    for story in stories:
        lang = story["lang"]
        paragraphs_html = "".join(f'        <p class="para">{p}</p>\n' for p in story["paragraphs"])
        trans_html = "".join(f"<p>{p.strip()}</p>" for p in story["translation"].split("\n\n") if p.strip())
        cards += f"""
  <div class="card">
    <div class="card-header">
      <span class="flag">{lang['flag']}</span>
      <h2>{lang['label']}</h2>
      <span class="level-badge">{lang['level'].split('(')[1].rstrip(')')}</span>
    </div>
    <div class="story-text">
{paragraphs_html}    </div>
    <div class="controls">
      <button class="btn btn-audio" onclick="toggleAudio('{lang['code']}', this)">▶ Ouvir história</button>
      <button class="btn btn-trans" onclick="toggleTranslation('{lang['code']}')">🌐 Ver tradução</button>
    </div>
    <audio id="audio-{lang['code']}" src="{lang['code']}_historia.mp3" preload="none"></audio>
    <div class="translation" id="trans-{lang['code']}" hidden>
      <h3>Tradução</h3>{trans_html}
    </div>
  </div>
"""
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Language Tutor — {today_str}</title>
  <style>
    *,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:'Segoe UI',system-ui,sans-serif;background:#0f172a;color:#e2e8f0;min-height:100vh;padding:2rem 1rem}}
    header{{text-align:center;margin-bottom:2.5rem}}
    header h1{{font-size:2rem;color:#f8fafc;letter-spacing:-.02em}}
    header p{{color:#94a3b8;margin-top:.4rem}}
    .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:1.5rem;max-width:1100px;margin:0 auto}}
    .card{{background:#1e293b;border:1px solid #334155;border-radius:16px;padding:1.5rem;display:flex;flex-direction:column;gap:1rem}}
    .card-header{{display:flex;align-items:center;gap:.6rem}}
    .flag{{font-size:1.6rem}}
    .card-header h2{{font-size:1.2rem;color:#f1f5f9;flex:1}}
    .level-badge{{background:#0f172a;border:1px solid #475569;border-radius:999px;padding:.2rem .6rem;font-size:.7rem;color:#94a3b8}}
    .story-text .para{{color:#cbd5e1;line-height:1.75;margin-bottom:.8rem}}
    .story-text .para:last-child{{margin-bottom:0}}
    .controls{{display:flex;gap:.75rem;flex-wrap:wrap}}
    .btn{{flex:1;padding:.6rem 1rem;border:none;border-radius:8px;font-size:.9rem;font-weight:600;cursor:pointer;transition:opacity .15s,transform .1s}}
    .btn:active{{transform:scale(.97)}}
    .btn-audio{{background:#6366f1;color:#fff}}
    .btn-trans{{background:#0f172a;color:#94a3b8;border:1px solid #334155}}
    .btn-audio:hover{{opacity:.88}}
    .btn-trans:hover{{background:#1e293b;color:#e2e8f0}}
    .translation{{background:#0f172a;border-left:3px solid #6366f1;border-radius:0 8px 8px 0;padding:1rem 1.2rem}}
    .translation h3{{font-size:.8rem;letter-spacing:.08em;color:#6366f1;text-transform:uppercase;margin-bottom:.6rem}}
    .translation p{{color:#94a3b8;line-height:1.7;margin-bottom:.6rem}}
    .translation p:last-child{{margin-bottom:0}}
    footer{{text-align:center;margin-top:3rem;color:#475569;font-size:.8rem}}
  </style>
</head>
<body>
<header><h1>🌍 Language Tutor</h1><p>Histórias do dia — {today_str}</p></header>
<main class="grid">{cards}</main>
<footer>Gerado automaticamente por Language Tutor · {today_str}</footer>
<script>
  function toggleAudio(lang,btn){{
    const audio=document.getElementById('audio-'+lang);
    if(audio.paused){{
      document.querySelectorAll('audio').forEach(a=>a.pause());
      document.querySelectorAll('.btn-audio').forEach(b=>b.textContent='▶ Ouvir história');
      audio.play();btn.textContent='⏸ Pausar';
    }}else{{audio.pause();btn.textContent='▶ Ouvir história';}}
    audio.onended=()=>{{btn.textContent='▶ Ouvir história';}};
  }}
  function toggleTranslation(lang){{
    const el=document.getElementById('trans-'+lang);el.hidden=!el.hidden;
  }}
</script>
</body></html>
"""


# ── 4. Gerar HTML do e-mail (sem JS, compatível com Gmail) ───────────────────

def gerar_html_email(stories: list) -> str:
    today_str = datetime.date.today().strftime("%d/%m/%Y")
    cards = ""
    for story in stories:
        lang = story["lang"]
        paragraphs_html = "".join(
            f'<p style="color:#374151;line-height:1.8;margin:0 0 12px 0;font-size:15px">{p}</p>'
            for p in story["paragraphs"]
        )
        trans_paras = "".join(
            f'<p style="color:#6b7280;line-height:1.7;margin:0 0 8px 0;font-size:14px">{p.strip()}</p>'
            for p in story["translation"].split("\n\n") if p.strip()
        )
        level_short = lang["level"].split("(")[1].rstrip(")")
        cards += f"""
<table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:24px;border:1px solid #e5e7eb;border-radius:12px;overflow:hidden;background:#ffffff">
  <tr><td style="background:#f8fafc;padding:16px 20px;border-bottom:1px solid #e5e7eb">
    <span style="font-size:24px">{lang['flag']}</span>
    <span style="font-size:18px;font-weight:700;color:#111827;margin-left:8px">{lang['label']}</span>
    <span style="font-size:11px;color:#6b7280;background:#f1f5f9;border:1px solid #d1d5db;border-radius:20px;padding:2px 8px;margin-left:8px">{level_short}</span>
  </td></tr>
  <tr><td style="padding:20px">
    {paragraphs_html}
    <details style="margin-top:16px">
      <summary style="cursor:pointer;font-size:13px;font-weight:600;color:#6366f1;padding:8px 12px;background:#eef2ff;border-radius:8px;list-style:none;user-select:none">
        🌐 Ver tradução em português
      </summary>
      <div style="margin-top:12px;padding:12px 16px;background:#f9fafb;border-left:3px solid #6366f1;border-radius:0 8px 8px 0">
        <p style="font-size:11px;font-weight:700;color:#6366f1;letter-spacing:.08em;text-transform:uppercase;margin:0 0 8px 0">TRADUÇÃO</p>
        {trans_paras}
      </div>
    </details>
    <p style="margin-top:16px;font-size:12px;color:#9ca3af">🎧 Ouça o áudio no MP3 anexo: <strong>{lang['code']}_historia.mp3</strong></p>
  </td></tr>
</table>
"""
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="font-family:'Segoe UI',Arial,sans-serif;background:#f3f4f6;margin:0;padding:24px">
  <table width="100%" max-width="640" cellpadding="0" cellspacing="0" style="max-width:640px;margin:0 auto">
    <tr><td style="text-align:center;padding:32px 0 24px">
      <h1 style="font-size:28px;color:#111827;margin:0">🌍 Language Tutor</h1>
      <p style="color:#6b7280;margin:6px 0 0;font-size:14px">Suas histórias do dia — {today_str}</p>
    </td></tr>
    <tr><td>
      {cards}
    </td></tr>
    <tr><td style="text-align:center;padding:24px 0;color:#9ca3af;font-size:12px">
      Gerado automaticamente por Language Tutor · {today_str}
    </td></tr>
  </table>
</body></html>
"""


# ── 5. Salvar dados em JSON (para o widget do Claude) ────────────────────────

def salvar_json(stories: list, base_dir: Path) -> None:
    data = {
        "data": datetime.date.today().isoformat(),
        "stories": [
            {
                "code": s["lang"]["code"],
                "label": s["lang"]["label"],
                "flag": s["lang"]["flag"],
                "level": s["lang"]["level"],
                "paragraphs": s["paragraphs"],
                "translation": s["translation"],
                "audio_file": f"{s['lang']['code']}_historia.mp3",
            }
            for s in stories
        ],
    }
    (base_dir / "aula_atual.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print("  aula_atual.json salvo")


# ── 6. Enviar e-mail ──────────────────────────────────────────────────────────

def enviar_email(html_email: str, audio_paths: list) -> None:
    gmail_user = os.environ["GMAIL_USER"]
    gmail_pass = os.environ["GMAIL_APP_PASSWORD"]
    today_str = datetime.date.today().strftime("%d/%m/%Y")

    msg = MIMEMultipart("alternative")
    msg["From"] = gmail_user
    msg["To"] = RECIPIENT_EMAIL
    msg["Subject"] = f"🌍 Language Tutor — Histórias do dia {today_str}"

    msg.attach(MIMEText(html_email, "html", "utf-8"))

    # Converte para MIMEMultipart mixed para adicionar anexos
    outer = MIMEMultipart("mixed")
    outer["From"] = gmail_user
    outer["To"] = RECIPIENT_EMAIL
    outer["Subject"] = msg["Subject"]
    outer.attach(MIMEText(html_email, "html", "utf-8"))

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
    print(f"  E-mail enviado para {RECIPIENT_EMAIL}")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    base_dir = Path(__file__).parent

    print("=" * 55)
    print(f"  Language Tutor — {datetime.date.today().strftime('%d/%m/%Y')}")
    print("=" * 55)

    stories = []
    audio_paths = []

    for lang in LANGS:
        print(f"\n[{lang['flag']} {lang['label']}]")
        print("  Gerando história com Groq / Llama 3...")
        story_data = gerar_historia(lang)
        story_data["lang"] = lang
        stories.append(story_data)

        audio_path = base_dir / f"{lang['code']}_historia.mp3"
        print("  Gerando áudio com Edge TTS...")
        gerar_audio(story_data["text"], lang["code"], audio_path)
        audio_paths.append(audio_path)

    print("\n[📄 Gerando index.html...]")
    html_path = base_dir / "index.html"
    html_path.write_text(gerar_html(stories), encoding="utf-8")
    print(f"  Salvo em {html_path}")

    print("\n[💾 Salvando aula_atual.json...]")
    salvar_json(stories, base_dir)

    print("\n[📧 Enviando e-mail...]")
    try:
        html_email = gerar_html_email(stories)
        enviar_email(html_email, audio_paths)
    except Exception as e:
        print(f"  AVISO: falha ao enviar e-mail — {e}")

    print("\n✅ Pronto! Abra o index.html no navegador.")


if __name__ == "__main__":
    main()
