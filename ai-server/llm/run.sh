#!/usr/bin/env bash
# STT·LLM 서버 실행 (같은 LAN의 Spring·Pi·Vision이 접근할 수 있도록 0.0.0.0 바인딩)
cd "$(dirname "$0")"
source .venv/bin/activate 2>/dev/null
uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8001}
