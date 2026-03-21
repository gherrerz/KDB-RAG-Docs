"""Valida consistencia minima de ejemplos y scripts de documentacion."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REQUIRED_FILES = [
    ROOT / "examples/python/ingest_and_poll.py",
    ROOT / "examples/python/query_with_llm.py",
    ROOT / "examples/python/query_retrieval_only.py",
    ROOT / "examples/powershell/ingest.ps1",
    ROOT / "examples/powershell/query_with_llm.ps1",
    ROOT / "examples/powershell/query_retrieval_only.ps1",
    ROOT / "examples/curl/ingest.sh",
    ROOT / "examples/curl/query_retrieval.sh",
]


def validate_required_files() -> list[str]:
    """Verifica existencia de archivos de ejemplos esperados."""
    errors: list[str] = []
    for file_path in REQUIRED_FILES:
        if not file_path.exists():
            errors.append(f"Missing example file: {file_path.relative_to(ROOT)}")
    return errors


def validate_readme_references() -> list[str]:
    """Verifica referencias minimas a ejemplos y scripts de validacion."""
    errors: list[str] = []
    readme_path = ROOT / "README.md"
    content = readme_path.read_text(encoding="utf-8")

    required_snippets = [
        "examples/python/",
        "examples/curl/",
        "examples/powershell/",
        "scripts/docs/validate_docs.py",
        "scripts/docs/validate_links.py",
        "scripts/docs/validate_examples.py",
    ]

    for snippet in required_snippets:
        if snippet not in content:
            errors.append(f"README is missing reference: {snippet}")

    return errors


def main() -> int:
    """Ejecuta validacion basica de ejemplos y referencias."""
    errors = []
    errors.extend(validate_required_files())
    errors.extend(validate_readme_references())

    if errors:
        print("Documentation example validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Examples and README references are consistent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
