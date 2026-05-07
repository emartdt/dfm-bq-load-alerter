#!/usr/bin/env bash
# 로컬 개발 환경 기동: backend(uvicorn --reload) + frontend(vite) 동시 실행.
# 두 프로세스 모두 백그라운드. 로그는 .dev/{backend,frontend}.log,
# PID 는 .dev/{backend,frontend}.pid 에 보관. 정지는 ./scripts/dev-down.sh.
#
# 사용법:
#   ./scripts/dev-up.sh                  # 기본 backend :8000, frontend :5173
#   BACKEND_PORT=9000 ./scripts/dev-up.sh
#
# 사전 조건:
#   - 1password CLI(op) signin 완료
#   - 1password vault `Shinsegae` 의 dfm-dev-bq-load-alerter (postgres_dsn,
#     bootstrap_token) 등록 — docs/dev-setup.md 참조
#   - uv / npm 설치
#   - frontend/node_modules 미존재 시 자동 npm install

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEV_DIR="${REPO_ROOT}/.dev"
ENV_TPL="${REPO_ROOT}/dev.env.tpl"
BACKEND_PORT="${BACKEND_PORT:-8000}"

command -v op >/dev/null || { echo "ERROR: 1password CLI(op) 미설치" >&2; exit 1; }
command -v uv >/dev/null || { echo "ERROR: uv 미설치" >&2; exit 1; }
command -v npm >/dev/null || { echo "ERROR: npm 미설치" >&2; exit 1; }

[[ -f "${ENV_TPL}" ]] || { echo "ERROR: ${ENV_TPL} 누락" >&2; exit 1; }

mkdir -p "${DEV_DIR}"

# 이미 떠 있는 프로세스 점검 — 중복 기동 차단
for proc in backend frontend; do
  pidfile="${DEV_DIR}/${proc}.pid"
  if [[ -f "${pidfile}" ]] && kill -0 "$(cat "${pidfile}")" 2>/dev/null; then
    echo "ERROR: ${proc} already running (PID $(cat "${pidfile}"))." >&2
    echo "       Run ./scripts/dev-down.sh first." >&2
    exit 1
  fi
  rm -f "${pidfile}"
done

if [[ ! -d "${REPO_ROOT}/frontend/node_modules" ]]; then
  echo "→ frontend node_modules 가 없어 npm install 자동 실행"
  (cd "${REPO_ROOT}/frontend" && npm install --no-audit --no-fund)
fi

echo "→ backend uvicorn :${BACKEND_PORT} (logs: .dev/backend.log)"
(
  cd "${REPO_ROOT}/backend"
  exec op run --env-file="${ENV_TPL}" -- \
    uv run uvicorn dfm_bq_load_alerter.main:app \
      --host 0.0.0.0 --port "${BACKEND_PORT}" --reload --reload-dir src
) > "${DEV_DIR}/backend.log" 2>&1 &
echo $! > "${DEV_DIR}/backend.pid"

echo "→ frontend vite :5173 (logs: .dev/frontend.log)"
(
  cd "${REPO_ROOT}/frontend"
  exec npm run dev -- --host 0.0.0.0
) > "${DEV_DIR}/frontend.log" 2>&1 &
echo $! > "${DEV_DIR}/frontend.pid"

cat <<EOF

기동 완료.
  Backend  → http://localhost:${BACKEND_PORT}/healthz   (PID $(cat "${DEV_DIR}/backend.pid"))
  Frontend → http://localhost:5173/                       (PID $(cat "${DEV_DIR}/frontend.pid"))

로그 따라가기:
  tail -f .dev/backend.log
  tail -f .dev/frontend.log

정지:
  ./scripts/dev-down.sh
EOF
