"""repo_context — leitura read-only e allowlisted de arquivos-fonte do próprio
repositório, para dar contexto real ao coding_agent (ferramenta de suporte
interno pros devs do AFJ). NUNCA escreve em disco. NUNCA lê fora das raízes
permitidas (backend/app/, frontend/src/)."""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
ALLOWED_ROOTS = (REPO_ROOT / "backend" / "app", REPO_ROOT / "frontend" / "src")
MAX_BYTES_PER_FILE = 50_000
MAX_FILES = 5
MAX_TOTAL_BYTES = 150_000
_BLOCKLIST_MARKERS = (".env", "secret", "credential", ".pem", ".key", "id_rsa")


class RepoContextError(Exception):
    """Caminho inválido, fora do allowlist, ou não legível."""


def _validar_caminho(rel_path: str) -> Path:
    if not rel_path or not isinstance(rel_path, str):
        raise RepoContextError("caminho vazio")
    if rel_path.startswith("/") or (len(rel_path) > 1 and rel_path[1] == ":"):
        raise RepoContextError(f"caminho absoluto não permitido: {rel_path}")
    if ".." in Path(rel_path).parts:
        raise RepoContextError(f"path traversal não permitido: {rel_path}")

    baixo = rel_path.lower()
    if any(marcador in baixo for marcador in _BLOCKLIST_MARKERS):
        raise RepoContextError(f"caminho bloqueado por política de segurança: {rel_path}")

    candidato = (REPO_ROOT / rel_path).resolve()  # resolve() segue symlinks

    dentro_de_alguma_raiz = any(
        candidato == raiz or raiz in candidato.parents for raiz in ALLOWED_ROOTS
    )
    if not dentro_de_alguma_raiz:
        raise RepoContextError(
            f"caminho fora das raízes permitidas (backend/app/, frontend/src/): {rel_path}"
        )
    if not candidato.is_file():
        raise RepoContextError(f"arquivo não encontrado: {rel_path}")
    return candidato


def read_arquivo(rel_path: str, max_bytes: int = MAX_BYTES_PER_FILE) -> str:
    """Lê um arquivo-fonte validado. Levanta RepoContextError se inválido."""
    caminho = _validar_caminho(rel_path)
    dados = caminho.read_bytes()
    truncado = len(dados) > max_bytes
    texto = dados[:max_bytes].decode("utf-8", errors="replace")
    if truncado:
        texto += f"\n... [truncado — arquivo maior que {max_bytes} bytes]"
    return texto


def build_contexto(arquivos: list[str], max_files: int = MAX_FILES) -> str:
    """Monta um bloco de contexto textual a partir de caminhos relativos,
    tolerante a erros por arquivo (um caminho inválido não derruba os demais)."""
    partes: list[str] = []
    total = 0
    for rel_path in (arquivos or [])[:max_files]:
        try:
            conteudo = read_arquivo(rel_path)
        except RepoContextError as exc:
            partes.append(f"### {rel_path}\n[ERRO: {exc}]")
            continue
        bloco = f"### {rel_path}\n```\n{conteudo}\n```"
        if total + len(bloco) > MAX_TOTAL_BYTES:
            partes.append(f"### {rel_path}\n[OMITIDO: limite total de contexto ({MAX_TOTAL_BYTES} chars) atingido]")
            break
        total += len(bloco)
        partes.append(bloco)
    if len(arquivos or []) > max_files:
        partes.append(f"[{len(arquivos) - max_files} arquivo(s) adicional(is) ignorado(s) — máximo {max_files} por chamada]")
    return "\n\n".join(partes)
