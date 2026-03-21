"""Inicia una ingesta y hace polling hasta estado final."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

BASE_URL = "http://127.0.0.1:8000"


def post_json(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Ejecuta un POST JSON y retorna el cuerpo parseado."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def get_json(path: str) -> dict[str, Any]:
    """Ejecuta un GET y retorna JSON parseado."""
    with urllib.request.urlopen(f"{BASE_URL}{path}", timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    """Lanza la ingesta y monitorea progreso hasta finalizar."""
    payload = {
        "provider": "github",
        "repo_url": "https://github.com/macrozheng/mall.git",
        "branch": "main",
    }

    try:
        job = post_json("/repos/ingest", payload)
    except urllib.error.HTTPError as exc:
        print(f"Error HTTP al crear ingesta: {exc.code}")
        print(exc.read().decode("utf-8"))
        return 1

    job_id = job["id"]
    print(f"Job creado: {job_id}")

    while True:
        state = get_json(f"/jobs/{job_id}?logs_tail=20")
        status = state.get("status", "unknown")
        progress = state.get("progress", 0.0)
        print(f"status={status} progress={progress:.2f}")

        if status in {"completed", "partial", "failed"}:
            print(json.dumps(state, indent=2, ensure_ascii=False))
            return 0 if status in {"completed", "partial"} else 2

        time.sleep(1.2)


if __name__ == "__main__":
    raise SystemExit(main())
