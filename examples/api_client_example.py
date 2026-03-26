"""Small client example for ingestion and query endpoints."""

from __future__ import annotations

import requests

BASE_URL = "http://127.0.0.1:8000"


def main() -> None:
    ingest_payload = {
        "source": {
            "source_type": "folder",
            "local_path": "sample_data",
        }
    }
    ingest = requests.post(
        f"{BASE_URL}/sources/ingest",
        json=ingest_payload,
        timeout=30,
    )
    ingest.raise_for_status()
    print("Ingest:", ingest.json())

    query_payload = {"question": "Who works on Project Atlas?", "hops": 2}
    response = requests.post(
        f"{BASE_URL}/query",
        json=query_payload,
        timeout=30,
    )
    response.raise_for_status()
    print("Query:", response.json())


if __name__ == "__main__":
    main()
