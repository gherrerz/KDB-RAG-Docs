"""Ejecuta todas las validaciones de documentacion del repositorio."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run_step(script_path: Path) -> int:
    """Ejecuta un script de validacion y retorna su codigo de salida."""
    command = [sys.executable, str(script_path)]
    result = subprocess.run(command, cwd=ROOT, check=False)
    return result.returncode


def main() -> int:
    """Corre validadores de links y ejemplos en secuencia."""
    scripts = [
        ROOT / "scripts/docs/validate_examples.py",
        ROOT / "scripts/docs/validate_links.py",
    ]

    for script in scripts:
        if not script.exists():
            print(f"Missing validation script: {script.relative_to(ROOT)}")
            return 1

    for script in scripts:
        print(f"Running: {script.relative_to(ROOT)}")
        exit_code = run_step(script)
        if exit_code != 0:
            return exit_code

    print("All documentation validations passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
