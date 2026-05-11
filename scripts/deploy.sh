#!/usr/bin/env bash
# 사내망에서 onprem-prd 클러스터의 datafabric-alert 네임스페이스로
# dfm-bq-load-alerter 를 배포한다.
#
# 사용법:
#   scripts/deploy.sh                # latest 태그 사용
#   scripts/deploy.sh 0.1.0          # 특정 버전
#   scripts/deploy.sh 0.1.0 --dry-run  # 변경 미리 보기
#
# 전제 조건:
#   - kubectl context onprem-prd 가 설정되어 있고 접근 권한이 있다
#   - helm v3 설치
#   - charts/dfm-bq-load-alerter/ 가 존재 (이 repo 의 charts 디렉토리)
#   - 네임스페이스 datafabric-alert 에 와일드카드 TLS 시크릿
#     `tls-wildcard-shinsegae-ai-2026` 이 이미 존재 (없으면 docs/deployment.md 참조)

set -euo pipefail

VERSION="${1:-latest}"
shift || true
EXTRA_ARGS=("$@")

CONTEXT="${KUBE_CONTEXT:-onprem-prd}"
NAMESPACE="${NAMESPACE:-datafabric-alert}"
RELEASE_NAME="${RELEASE_NAME:-dfm-bq-load-alerter}"
IMAGE_HOST="${AR_HOST:-asia-northeast3-docker.pkg.dev}"
IMAGE_PROJECT="${AR_PROJECT:-emart-datafabric}"
IMAGE_REPO="${AR_REPO:-container-registry}"
IMAGE="${IMAGE_HOST}/${IMAGE_PROJECT}/${IMAGE_REPO}/dfm-bq-load-alerter"

CHART_PATH="$(cd "$(dirname "$0")/.." && pwd)/charts/dfm-bq-load-alerter"

if [[ ! -d "${CHART_PATH}" ]]; then
  echo "ERROR: chart 경로를 찾지 못함: ${CHART_PATH}" >&2
  exit 1
fi

command -v kubectl >/dev/null || { echo "ERROR: kubectl 미설치" >&2; exit 1; }
command -v helm >/dev/null || { echo "ERROR: helm 미설치" >&2; exit 1; }

echo "→ context: ${CONTEXT}"
echo "→ namespace: ${NAMESPACE}"
echo "→ release: ${RELEASE_NAME}"
echo "→ image: ${IMAGE}:${VERSION}"
echo

# 네임스페이스 보장 (이미 있으면 그대로)
kubectl --context "${CONTEXT}" get ns "${NAMESPACE}" >/dev/null 2>&1 \
  || kubectl --context "${CONTEXT}" create ns "${NAMESPACE}"

# TLS 시크릿 사전 점검 (없으면 안내만 하고 진행은 사용자 판단)
if ! kubectl --context "${CONTEXT}" -n "${NAMESPACE}" get secret tls-wildcard-shinsegae-ai-2026 >/dev/null 2>&1; then
  echo "WARN: ${NAMESPACE} 네임스페이스에 와일드카드 TLS 시크릿이 없습니다." >&2
  echo "      datafabric-platform 네임스페이스에서 복제 절차는 docs/deployment.md 참조." >&2
fi

# 운영(onprem-prd) 전용 시크릿 참조 — 이름이 바뀌면 함께 갱신할 것.
SMTP_SECRET="${SMTP_SECRET:-dfm-bq-load-alerter-smtp}"
TEAMS_DEFAULT_WEBHOOK_SECRET="${TEAMS_DEFAULT_WEBHOOK_SECRET:-dfm-bq-load-alerter-teams-default}"

helm upgrade --install "${RELEASE_NAME}" "${CHART_PATH}" \
  --kube-context "${CONTEXT}" \
  --namespace "${NAMESPACE}" \
  --set image.repository="${IMAGE}" \
  --set image.tag="${VERSION}" \
  --set smtp.secretRef="${SMTP_SECRET}" \
  --set teams.defaultWebhookSecretRef="${TEAMS_DEFAULT_WEBHOOK_SECRET}" \
  --wait --timeout 5m \
  ${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}

echo
echo "→ rollout 검증:"
kubectl --context "${CONTEXT}" -n "${NAMESPACE}" rollout status \
  deploy/"${RELEASE_NAME}" --timeout=3m
