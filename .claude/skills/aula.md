# Skill: aula

Triggered when the user types "aula" or asks to see today's lesson.

## Instructions

1. Read the file `aula_atual.json` from the project root.
2. Read each MP3 file listed in the JSON and encode it as base64.
3. Use `show_widget` to render an interactive HTML widget with:
   - A card for each language (flag, label, level badge)
   - The story paragraphs
   - An `<audio>` element with the base64-encoded MP3 as a data URI so it plays inline
   - A play/pause button that controls the audio
   - A "Ver tradução" button that toggles the translation panel (using JS)
   - Dark theme matching the project style (#0f172a background, #1e293b cards)
4. If `aula_atual.json` does not exist, tell the user to run `python3 gerar_aula.py` first.
