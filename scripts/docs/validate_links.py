"""Valida enlaces markdown internos contra el workspace."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LINK_PATTERN = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
EXCLUDED_PATH_PARTS = {
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "site-packages",
    "node_modules",
    "storage",
}


def iter_markdown_files(root: Path) -> list[Path]:
    """Retorna todos los archivos markdown del repositorio."""
    return [
        p for p in root.rglob("*.md")
        if not any(part in EXCLUDED_PATH_PARTS for part in p.parts)
    ]


def is_external_link(target: str) -> bool:
    """Indica si el enlace apunta a recurso externo o ancla local."""
    return target.startswith("http://") or target.startswith("https://") or target.startswith("#")


def validate_file(file_path: Path) -> list[str]:
    """Valida enlaces internos de un archivo markdown."""
    errors: list[str] = []
    content = file_path.read_text(encoding="utf-8")

    for match in LINK_PATTERN.finditer(content):
        raw_target = match.group(1).strip()
        target = raw_target.split("#", 1)[0]
        if not target or is_external_link(target):
            continue

        candidate = (file_path.parent / target).resolve()
        if not candidate.exists():
            rel = file_path.relative_to(ROOT).as_posix()
            errors.append(f"{rel}: broken link -> {raw_target}")

    return errors


def main() -> int:
    """Ejecuta validacion de links en markdown."""
    all_errors: list[str] = []
    for markdown_file in iter_markdown_files(ROOT):
        all_errors.extend(validate_file(markdown_file))

    if all_errors:
        print("Broken links found:")
        for error in all_errors:
            print(f"- {error}")
        return 1

    print("No broken internal markdown links found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
