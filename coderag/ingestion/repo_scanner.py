"""Escáner de repositorio para seleccionar archivos relevantes para la indexación."""

from pathlib import Path

from coderag.core.models import ScannedFile

LANG_MAP = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".java": "java",
    ".go": "go",
    ".md": "markdown",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".json": "json",
    ".toml": "toml",
}

def detect_language(path: Path) -> str:
    """Detecta una etiqueta de lenguaje lógico a partir de una extensión de archivo."""
    return LANG_MAP.get(path.suffix.lower(), "text")


def scan_repository(
    repo_path: Path,
    max_file_size: int,
    excluded_dirs: set[str] | None = None,
    excluded_extensions: set[str] | None = None,
) -> list[ScannedFile]:
    """Recopila archivos de código, configuración y documentación con filtros."""
    scanned: list[ScannedFile] = []
    excluded_dir_names = {item.lower() for item in (excluded_dirs or set())}
    excluded_file_extensions = {
        item.lower() for item in (excluded_extensions or set())
    }

    for file_path in repo_path.rglob("*"):
        if not file_path.is_file():
            continue

        if any(part.lower() in excluded_dir_names for part in file_path.parts):
            continue

        if file_path.suffix.lower() in excluded_file_extensions:
            continue

        if file_path.stat().st_size > max_file_size:
            continue

        try:
            content = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        rel_path = str(file_path.relative_to(repo_path)).replace("\\", "/")
        scanned.append(
            ScannedFile(
                path=rel_path,
                language=detect_language(file_path),
                content=content,
            )
        )
    return scanned
