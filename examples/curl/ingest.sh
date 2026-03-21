#!/usr/bin/env bash
set -euo pipefail

BASE_URL="http://127.0.0.1:8000"

curl -sS -X POST "$BASE_URL/repos/ingest" \
  -H "Content-Type: application/json" \
  -d '{
    "provider": "github",
    "repo_url": "https://github.com/macrozheng/mall.git",
    "branch": "main"
  }' | jq .
