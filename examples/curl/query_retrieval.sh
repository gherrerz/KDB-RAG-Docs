#!/usr/bin/env bash
set -euo pipefail

BASE_URL="http://127.0.0.1:8000"

curl -sS -X POST "$BASE_URL/query/retrieval" \
  -H "Content-Type: application/json" \
  -d '{
    "repo_id": "mall",
    "query": "donde esta la configuracion de neo4j",
    "top_n": 60,
    "top_k": 15,
    "include_context": false
  }' | jq .
