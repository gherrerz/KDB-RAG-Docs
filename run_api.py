"""Run FastAPI backend with Uvicorn."""

from __future__ import annotations

import uvicorn


if __name__ == "__main__":
    uvicorn.run("coderag.api.server:app", host="127.0.0.1", port=8000)
