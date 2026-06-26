"""
Sincroniza arquivos de estado com o GitHub via API.
Usado pelo bot.py para persistir progresso.json e perfil.json
mesmo em servidores sem disco persistente (ex: Koyeb free tier).
"""

import os, base64, json, requests
from pathlib import Path

GITHUB_TOKEN  = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO   = "nivapinto/language-tutor"
GITHUB_BRANCH = "main"
BASE_DIR      = Path(__file__).parent

_HEADERS = lambda: {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
}


def _get_sha(path_in_repo: str) -> str | None:
    r = requests.get(
        f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path_in_repo}",
        headers=_HEADERS(), params={"ref": GITHUB_BRANCH}, timeout=10,
    )
    return r.json().get("sha") if r.ok else None


def push_file(path_in_repo: str, content_bytes: bytes, message: str = "sync") -> bool:
    """Envia um arquivo para o GitHub. Retorna True se bem-sucedido."""
    sha = _get_sha(path_in_repo)
    payload = {
        "message": message,
        "branch": GITHUB_BRANCH,
        "content": base64.b64encode(content_bytes).decode(),
    }
    if sha:
        payload["sha"] = sha
    r = requests.put(
        f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path_in_repo}",
        headers=_HEADERS(), json=payload, timeout=15,
    )
    return r.ok


def pull_file(path_in_repo: str) -> bytes | None:
    """Baixa um arquivo do GitHub. Retorna bytes ou None."""
    r = requests.get(
        f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path_in_repo}",
        headers=_HEADERS(), params={"ref": GITHUB_BRANCH}, timeout=10,
    )
    if r.ok:
        return base64.b64decode(r.json()["content"])
    return None


def salvar_json_e_sync(filepath: Path, data: dict) -> None:
    """Salva JSON localmente e sincroniza com GitHub."""
    texto = json.dumps(data, ensure_ascii=False, indent=2)
    filepath.write_text(texto, encoding="utf-8")
    try:
        push_file(filepath.name, texto.encode(), f"sync {filepath.name}")
    except Exception as e:
        print(f"  ⚠ sync {filepath.name}: {e}")


def restaurar_estado() -> None:
    """Na inicialização, baixa progresso.json e perfil.json do GitHub
    para garantir que temos o estado mais recente (importante após restart)."""
    for fname in ["progresso.json", "perfil.json"]:
        local = BASE_DIR / fname
        remoto = pull_file(fname)
        if remoto:
            local.write_bytes(remoto)
            print(f"  ✓ {fname} restaurado do GitHub")
