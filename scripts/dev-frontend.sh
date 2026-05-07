#!/usr/bin/env bash
# 로컬 개발용 프론트엔드 실행 (Vite dev server, HMR).
# 환경변수 의존성 없음 — /api/* 와 /healthz 는 vite.config.ts 의 proxy 가
# localhost:8000 (백엔드) 으로 전달한다.
#
# 사용법:
#   ./scripts/dev-frontend.sh                # 기본: localhost:5173
#
# 사전 조건:
#   - Node 22 LTS + npm
#   - frontend/ 에 npm install 1회 실행되어 있어야 함

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${REPO_ROOT}/frontend"

if [[ ! -d node_modules ]]; then
  echo "→ node_modules 가 없어 npm install 자동 실행"
  npm install --no-audit --no-fund
fi

exec npm run dev -- --host 0.0.0.0
