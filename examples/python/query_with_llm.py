"""Ejemplo de consulta con sintesis LLM."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

BASE_URL = "http://127.0.0.1:8000"


def post_json(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Envía un POST JSON y retorna el response parseado."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    """Ejecuta query con LLM para un repo ya ingerido."""
    payload = {
        "repo_id": "mall",
        "query": "cuales son los controller del modulo mall-admin",
        "top_n": 60,
        "top_k": 15,
    }

    try:
        result = post_json("/query", payload)
    except urllib.error.HTTPError as exc:
        print(f"Error HTTP: {exc.code}")
        print(exc.read().decode("utf-8"))
        return 1

    print("Respuesta:\n")
    print(result.get("answer", ""))
    print("\nCitas:")
    for citation in result.get("citations", [])[:5]:
        path = citation.get("path", "?")
        start = citation.get("start_line", 0)
        end = citation.get("end_line", 0)
        print(f"- {path}:{start}-{end}")

    print("\nDiagnostics:")
    print(json.dumps(result.get("diagnostics", {}), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
