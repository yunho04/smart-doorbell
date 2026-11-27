#!/usr/bin/env bash
# 통합 테스트 시뮬레이터 실행기: 가상환경 준비 → 의존성 설치 → 시나리오 실행.
# 사용: ./integration-tests/run.sh [--scenario delivery ...] [--keep-backend] (전체 옵션: --help)
set -euo pipefail
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"
if [ ! -x .venv/bin/python ]; then
  echo "[setup] 가상환경 생성: integration-tests/.venv"
  "$PYTHON" -m venv .venv
fi
if [ ! -f .venv/.deps-installed ] || [ requirements.txt -nt .venv/.deps-installed ]; then
  echo "[setup] 의존성 설치 (requirements.txt)"
  .venv/bin/python -m pip install --quiet --disable-pip-version-check -r requirements.txt
  touch .venv/.deps-installed
fi
exec .venv/bin/python -m doorbell_sim "$@"
