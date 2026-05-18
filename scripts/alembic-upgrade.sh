#!/usr/bin/env bash
# Alembic 마이그레이션 실행 스크립트.
#
# 사용법:
#   ./scripts/alembic-upgrade.sh dev                 # 로컬 dev DB 에 upgrade head
#   ./scripts/alembic-upgrade.sh prod                # 운영 DB 에 upgrade head (확인 프롬프트)
#   ./scripts/alembic-upgrade.sh dev current         # dev 현재 리비전 표시
#   ./scripts/alembic-upgrade.sh prod history        # prod 마이그레이션 히스토리
#
# dev:
#   - DSN 출처: 1password (vault=Shinsegae, item=dfm-dev-bq-load-alerter, field=postgres_dsn)
#   - DB: dfm_bq_load_alerter_dev
#   - dev.env.tpl 의 op:// 참조를 op run 으로 주입한다 — 평문 DSN 이 디스크에 남지 않는다.
#
# prod:
#   - DSN 출처: K8s Secret `dfm-bq-load-alerter-postgres` (datafabric-alert ns, onprem-prd ctx).
#     운영 Pod 가 사용하는 것과 동일한 시크릿 → DSN 재구성 실수를 방지한다.
#   - DB: dfm_bq_load_alerter (Cloud SQL)
#   - 실행 전 명시적 'yes' 입력을 요구한다.
#
# 전제 조건:
#   - uv 설치
#   - dev: 1password CLI(op) signin 완료, dev.env.tpl 존재
#   - prod: kubectl + onprem-prd 컨텍스트 권한, datafabric-alert ns 접근 권한

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_DIR="${REPO_ROOT}/backend"
ENV_TPL="${REPO_ROOT}/dev.env.tpl"

PROD_CONTEXT="${PROD_CONTEXT:-onprem-prd}"
PROD_NAMESPACE="${PROD_NAMESPACE:-datafabric-alert}"
PROD_SECRET="${PROD_SECRET:-dfm-bq-load-alerter-postgres}"
PROD_SECRET_KEY="${PROD_SECRET_KEY:-DFM_ALERT_POSTGRES_DSN}"

usage() {
  sed -n '2,15p' "$0"
  exit 1
}

[[ $# -ge 1 ]] || usage
TARGET="$1"
shift

# 알렘빅 서브커맨드 — 미지정 시 'upgrade head'
if [[ $# -eq 0 ]]; then
  ALEMBIC_ARGS=(upgrade head)
else
  ALEMBIC_ARGS=("$@")
fi

command -v uv >/dev/null || { echo "ERROR: uv 미설치" >&2; exit 1; }
[[ -d "${BACKEND_DIR}" ]] || { echo "ERROR: backend 디렉토리 없음: ${BACKEND_DIR}" >&2; exit 1; }

# Settings() 가 OIDC/세션 키를 필수로 검증하지만 alembic 은 실제로 사용하지 않는다.
# 검증만 통과하면 충분하므로 더미 placeholder 로 채운다. 운영/개발 모두 동일.
export DFM_ALERT_OIDC_ISSUER="${DFM_ALERT_OIDC_ISSUER:-https://alembic.local.invalid/realms/dummy}"
export DFM_ALERT_OIDC_CLIENT_ID="${DFM_ALERT_OIDC_CLIENT_ID:-alembic-dummy}"
export DFM_ALERT_OIDC_CLIENT_SECRET="${DFM_ALERT_OIDC_CLIENT_SECRET:-alembic-dummy-secret}"
export DFM_ALERT_SESSION_SECRET_KEY="${DFM_ALERT_SESSION_SECRET_KEY:-$(printf '0%.0s' {1..64})}"

run_dev() {
  command -v op >/dev/null || { echo "ERROR: 1password CLI(op) 미설치" >&2; exit 1; }
  [[ -f "${ENV_TPL}" ]] || { echo "ERROR: ${ENV_TPL} 누락" >&2; exit 1; }

  echo "→ target: dev  (dfm_bq_load_alerter_dev via 1password)"
  echo "→ alembic ${ALEMBIC_ARGS[*]}"
  (
    cd "${BACKEND_DIR}"
    exec op run --env-file="${ENV_TPL}" -- \
      uv run alembic "${ALEMBIC_ARGS[@]}"
  )
}

run_prod() {
  command -v kubectl >/dev/null || { echo "ERROR: kubectl 미설치" >&2; exit 1; }

  echo "→ target: prod (dfm_bq_load_alerter on Cloud SQL via k8s secret)"
  echo "    context   : ${PROD_CONTEXT}"
  echo "    namespace : ${PROD_NAMESPACE}"
  echo "    secret    : ${PROD_SECRET} (key=${PROD_SECRET_KEY})"
  echo "    alembic   : ${ALEMBIC_ARGS[*]}"
  echo

  # 변경 명령일 때만 확인 프롬프트 (read-only 서브커맨드는 생략)
  case "${ALEMBIC_ARGS[0]:-}" in
    upgrade|downgrade|stamp|merge|revision)
      read -r -p "운영 DB 에 '${ALEMBIC_ARGS[*]}' 적용. 진행하려면 'yes' 입력: " ans
      [[ "${ans}" == "yes" ]] || { echo "취소됨." >&2; exit 1; }
      ;;
  esac

  # K8s Secret 에서 DSN 추출 (base64 decode). 변수에만 담고 export 시 자식에만 전달.
  local dsn
  dsn="$(kubectl --context "${PROD_CONTEXT}" -n "${PROD_NAMESPACE}" get secret \
    "${PROD_SECRET}" -o jsonpath="{.data.${PROD_SECRET_KEY}}" 2>/dev/null | base64 -d)"
  [[ -n "${dsn}" ]] || {
    echo "ERROR: K8s Secret ${PROD_SECRET}/${PROD_SECRET_KEY} 조회 실패" >&2
    exit 1
  }

  (
    cd "${BACKEND_DIR}"
    DFM_ALERT_POSTGRES_DSN="${dsn}" exec uv run alembic "${ALEMBIC_ARGS[@]}"
  )
}

case "${TARGET}" in
  dev) run_dev ;;
  prod) run_prod ;;
  -h|--help|help) usage ;;
  *)
    echo "ERROR: target 은 dev | prod 만 지원: '${TARGET}'" >&2
    usage
    ;;
esac
