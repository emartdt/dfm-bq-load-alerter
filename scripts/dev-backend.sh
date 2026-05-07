#!/usr/bin/env bash
# 로컬 개발용 백엔드 실행. 1password CLI(op) 로 dev.env.tpl 의 op:// 참조를
# 실제 값으로 주입한 뒤 uvicorn --reload 를 띄운다.
#
# 사용법:
#   ./scripts/dev-backend.sh                 # 기본: 0.0.0.0:8000
#   PORT=9000 ./scripts/dev-backend.sh       # 포트 변경
#
# 사전 조건:
#   - op CLI 설치 + `op signin` 또는 데스크톱 앱과 통합 인증 완료
#   - 1password vault `Shinsegae` 에 [dfm] dev : dfm-bq-load-alerter 등록
#   - backend/ 에 uv.lock 존재 (uv sync 1회 실행되어 있어야 함)
#   - PG 가 로컬에서 접근 가능 (Cloud SQL Auth Proxy 또는 로컬 PG)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_TPL="${REPO_ROOT}/dev.env.tpl"
PORT="${PORT:-8000}"

command -v op >/dev/null || {
  echo "ERROR: 1password CLI(op) 미설치. https://developer.1password.com/docs/cli/" >&2
  exit 1
}
command -v uv >/dev/null || {
  echo "ERROR: uv 미설치. https://docs.astral.sh/uv/" >&2
  exit 1
}

if [[ ! -f "${ENV_TPL}" ]]; then
  echo "ERROR: ${ENV_TPL} 누락" >&2
  exit 1
fi

cd "${REPO_ROOT}/backend"

# `op run --env-file` 은 자식 프로세스에 평문 환경변수를 주입한 뒤 자동 정리.
# uvicorn --reload 가 실행되는 동안만 평문이 메모리에 존재.
exec op run --env-file="${ENV_TPL}" -- \
  uv run uvicorn dfm_bq_load_alerter.main:app \
    --host 0.0.0.0 --port "${PORT}" --reload --reload-dir src
