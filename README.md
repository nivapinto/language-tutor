# 🌍 Language Tutor

Gerador diário de histórias em 3 idiomas com áudio TTS e tradução revelável.

| Idioma | Nível | Voz TTS |
|--------|-------|---------|
| 🇫🇷 Français | Iniciante (A1-A2) | alloy |
| 🇪🇸 Español | Intermediário (B1-B2) | nova |
| 🇬🇧 English | Avançado C1 | shimmer |

## Como usar

### 1. Instalar dependências

```bash
pip install anthropic openai python-dotenv
```

### 2. Configurar credenciais

```bash
cp .env.example .env
# edite .env com suas chaves
```

Variáveis necessárias:

| Variável | Como obter |
|----------|-----------|
| `ANTHROPIC_API_KEY` | console.anthropic.com |
| `OPENAI_API_KEY` | platform.openai.com |
| `GMAIL_USER` | seu endereço Gmail |
| `GMAIL_APP_PASSWORD` | Gmail → Segurança → Senhas de app |

### 3. Gerar a aula do dia

```bash
python gerar_aula.py
```

Isso vai:
1. Gerar 3 histórias com Claude (claude-opus-4-8)
2. Criar 3 arquivos MP3 via OpenAI TTS
3. Atualizar o `index.html` com as histórias, áudios e traduções
4. Enviar e-mail para `anivaldojr@gmail.com` com tudo anexado

Abra o `index.html` no navegador para ler, ouvir e ver a tradução.

---

## Servidor TTS local (opcional)

Se quiser que o player de áudio chame a API em tempo real (sem MP3 pré-gerados):

```bash
python server.py
```

O servidor sobe em `http://localhost:5050/tts` e resolve CORS para chamadas diretas do browser.

---

## Automatizar com cron (macOS/Linux)

Para rodar todo dia às 7h:

```bash
crontab -e
# adicione:
0 7 * * * cd /caminho/para/language-tutor && python gerar_aula.py
```
