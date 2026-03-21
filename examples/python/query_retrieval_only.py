"""Ejemplo de consulta retrieval-only sin sintesis LLM."""

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
    """Ejecuta consulta retrieval-only para revisar evidencia."""
    payload = {
        "repo_id": "mall",
        "query": "donde esta la configuracion de neo4j",
        "top_n": 60,
        "top_k": 15,
        "include_context": False,
    }

    try:
        result = post_json("/query/retrieval", payload)
    except urllib.error.HTTPError as exc:
        print(f"Error HTTP: {exc.code}")
        print(exc.read().decode("utf-8"))
        return 1

    print("Resumen:\n")
    print(result.get("answer", ""))

    print("\nTop chunks:")
    for chunk in result.get("chunks", [])[:5]:
        path = chunk.get("path", "?")
        start = chunk.get("start_line", 0)
        end = chunk.get("end_line", 0)
        score = chunk.get("score", 0.0)
        print(f"- {path}:{start}-{end} score={score:.4f}")

    print("\nStatistics:")
    print(json.dumps(result.get("statistics", {}), indent=2, ensure_ascii=False))
    print("\nDiagnostics:")
    print(json.dumps(result.get("diagnostics", {}), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
