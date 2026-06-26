#!/usr/bin/env python3
"""
Servidor local para TTS via OpenAI API.
Resolve o problema de CORS para chamadas diretas do browser.

Uso: python server.py
     (roda na porta 5050)
"""

import os
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

VOICE_MAP = {
    "fr": "alloy",
    "es": "nova",
    "en": "shimmer",
}


class TTSHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self._send_cors_headers(200)

    def do_POST(self):
        if self.path != "/tts":
            self._send_cors_headers(404)
            return

        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))
        text = body.get("text", "")
        lang = body.get("lang", "en")
        voice = VOICE_MAP.get(lang, "alloy")

        try:
            response = client.audio.speech.create(
                model="tts-1",
                voice=voice,
                input=text,
            )
            audio_bytes = response.content
            self._send_cors_headers(200, "audio/mpeg")
            self.wfile.write(audio_bytes)
        except Exception as e:
            self._send_cors_headers(500)
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def _send_cors_headers(self, status, content_type="application/json"):
        self.send_response(status)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Type", content_type)
        self.end_headers()

    def log_message(self, fmt, *args):
        print(f"[TTS Server] {fmt % args}")


if __name__ == "__main__":
    port = 5050
    print(f"TTS Server rodando em http://localhost:{port}")
    HTTPServer(("", port), TTSHandler).serve_forever()
