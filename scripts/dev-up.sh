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
#   - 1password vault `Shinsegae`:
#       dfm-dev-bq-load-alerter (postgres_dsn)
#       [dfm] keycloak: dfm-bq-load-alerter (client_id, client_secret, session_secret_key)
#   - uv / npm 설치
#   - frontend/node_modules 미존재 시 자동 npm install

# bash 안전 모드:
#   -e            : 명령이 실패(비-0 종료코드)하면 즉시 스크립트 종료
#   -u            : 선언되지 않은 변수를 쓰면 에러 (오타 방지)
#   -o pipefail   : 파이프라인 중 한 단계라도 실패하면 전체 실패로 간주
set -euo pipefail

# 스크립트 위치 기준으로 레포 루트 절대경로를 산출 (어느 경로에서 실행해도 동일하게 동작).
#   $0              : 실행된 스크립트 경로
#   dirname "$0"    : 그 디렉토리 (예: ./scripts)
#   cd ... && pwd   : 부모 디렉토리(=레포 루트)로 이동 후 절대경로 출력
#   $( ... )        : 명령 치환 — 내부 명령의 표준출력을 문자열로 사용
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEV_DIR="${REPO_ROOT}/.dev"                 # 로그/PID 파일 보관 디렉토리
ENV_TPL="${REPO_ROOT}/dev.env.tpl"          # op run 이 읽는 환경변수 템플릿 (op:// 참조 포함)
# ${VAR:-default} : VAR 이 비어있거나 없으면 default 사용.
# 따라서 `BACKEND_PORT=9000 ./scripts/dev-up.sh` 처럼 호출 시 환경변수로 덮어쓰기 가능.
BACKEND_PORT="${BACKEND_PORT:-8000}"

# 필수 CLI 존재 확인.
#   command -v X    : X 가 PATH 에 있으면 경로 출력(성공), 없으면 비-0(실패)
#   >/dev/null      : 성공 시 출력되는 경로 문자열을 화면에 띄우지 않도록 버림
#   A || B          : A 가 실패할 때만 B 실행
#   { ...; }        : 같은 셸에서 묶음 실행 (서브셸 아님)
#   >&2             : 표준에러로 출력 — 에러 메시지의 정석
#   exit 1          : 비-0 종료코드로 스크립트 종료
command -v op >/dev/null || { echo "ERROR: 1password CLI(op) 미설치" >&2; exit 1; }
command -v uv >/dev/null || { echo "ERROR: uv 미설치" >&2; exit 1; }
command -v npm >/dev/null || { echo "ERROR: npm 미설치" >&2; exit 1; }

# [[ -f path ]] : 해당 경로가 "일반 파일"로 존재하는지 검사. dev.env.tpl 없으면 즉시 종료.
[[ -f "${ENV_TPL}" ]] || { echo "ERROR: ${ENV_TPL} 누락" >&2; exit 1; }

# mkdir -p : 부모까지 생성, 이미 있어도 에러 없음 (idempotent).
mkdir -p "${DEV_DIR}"

# 이미 떠 있는 프로세스 점검 — 중복 기동 차단
# backend, frontend 두 토큰을 차례로 $proc 에 바인딩하여 동일 검사 반복.
for proc in backend frontend; do
  pidfile="${DEV_DIR}/${proc}.pid"
  if [[ -f "${pidfile}" ]] && kill -0 "$(cat "${pidfile}")" 2>/dev/null; then
    echo "ERROR: ${proc} already running (PID $(cat "${pidfile}"))." >&2
    echo "       Run ./scripts/dev-down.sh first." >&2
    exit 1
  fi
  rm -f "${pidfile}"
done

# frontend 의존성 자동 설치.
#   [[ ! -d path ]] : 디렉토리가 "없으면" 참
#   ( ... )         : 서브셸 — 안에서 cd 해도 바깥 셸의 작업 디렉토리는 안 바뀜
#   --no-audit      : npm 보안 감사 출력 비활성 (속도/로그 정리)
#   --no-fund       : 후원 메시지 비활성
if [[ ! -d "${REPO_ROOT}/frontend/node_modules" ]]; then
  echo "→ frontend node_modules 가 없어 npm install 자동 실행"
  (cd "${REPO_ROOT}/frontend" && npm install --no-audit --no-fund)
fi

echo "→ backend uvicorn :${BACKEND_PORT} (logs: .dev/backend.log)"
# 작은따옴표 '...' : 내부 변수/명령 치환을 하지 않고 문자 그대로 사용.
# 아이템 이름에 공백/대괄호/콜론이 있으므로 그대로 보존하기 위함.
KEYCLOAK_ITEM='[dfm] keycloak: dfm-bq-load-alerter'
# op item get : 1password CLI 로 보관함 아이템의 특정 필드 값을 조회.
#   --vault Shinsegae       : 어느 vault 에서 찾을지
#   --field client_id       : 추출할 필드명
#   --reveal                : 마스킹(••••) 없이 실제 평문 반환 (자동화에서 변수로 받기 위함)
# $( ... ) 로 표준출력을 변수에 캡처.
DFM_ALERT_OIDC_CLIENT_ID="$(op item get "$KEYCLOAK_ITEM" --vault Shinsegae --field client_id --reveal)"
DFM_ALERT_OIDC_CLIENT_SECRET="$(op item get "$KEYCLOAK_ITEM" --vault Shinsegae --field client_secret --reveal)"
DFM_ALERT_SESSION_SECRET_KEY="$(op item get "$KEYCLOAK_ITEM" --vault Shinsegae --field session_secret_key --reveal)"
# export : 변수들을 "자식 프로세스에 상속되는" 환경변수로 승격. 안 하면 uvicorn 이 못 봄.
export DFM_ALERT_OIDC_CLIENT_ID DFM_ALERT_OIDC_CLIENT_SECRET DFM_ALERT_SESSION_SECRET_KEY
# backend 백그라운드 기동.
#   ( ... )                 : 서브셸로 실행 (cd 가 바깥에 영향 없음)
#   exec                    : 현재 셸을 다음 명령으로 "교체" — 중간 셸이 끼지 않아 PID 추적/시그널 전달이 깔끔
#   op run --env-file=...   : dev.env.tpl 의 op:// 참조를 실행 시점에 실제 값으로 치환해 환경변수로 주입
#                             (평문이 디스크에 저장되지 않는 이유)
#   --                      : "옵션 끝" 마커. 뒤의 인자가 op 옵션으로 오해되지 않도록 분리
#   uv run uvicorn ...      : uv 가 관리하는 가상환경에서 uvicorn 실행
#     --host 0.0.0.0        : 모든 네트워크 인터페이스에서 수신 (다른 기기/컨테이너 접근 가능)
#     --port "${BACKEND_PORT}" : 환경변수로 받은 포트
#     --reload              : 코드 변경 시 자동 재시작 (개발용)
#     --reload-dir src      : 감시 대상 디렉토리 한정 (불필요한 재시작 방지)
#   > file                  : 표준출력(1)을 파일로 리다이렉트
#   2>&1                    : 표준에러(2)를 표준출력(1)으로 합침 → 모두 같은 로그 파일로
#                             (순서 중요: `> file 2>&1` 이 맞음)
#   &                       : 백그라운드 실행
(
  cd "${REPO_ROOT}/backend"
  exec op run --env-file="${ENV_TPL}" -- \
    uv run uvicorn dfm_bq_load_alerter.main:app \
      --host 0.0.0.0 --port "${BACKEND_PORT}" --reload --reload-dir src
) > "${DEV_DIR}/backend.log" 2>&1 &
# $! : 직전에 백그라운드(&)로 던진 프로세스의 PID. dev-down.sh 가 이 파일을 읽어 kill 함.
echo $! > "${DEV_DIR}/backend.pid"

echo "→ frontend vite :5173 (logs: .dev/frontend.log)"
# frontend 백그라운드 기동. 구조는 backend 와 동일.
#   npm run dev -- --host 0.0.0.0
#     첫 번째 `--` 는 "이 뒤의 인자는 npm 옵션이 아니라 스크립트(vite)로 그대로 전달" 이라는 표식.
#     덕분에 --host 0.0.0.0 이 vite 옵션으로 정확히 들어가서 LAN 접근 허용됨.
(
  cd "${REPO_ROOT}/frontend"
  exec npm run dev -- --host 0.0.0.0
) > "${DEV_DIR}/frontend.log" 2>&1 &
echo $! > "${DEV_DIR}/frontend.pid"

# here-document: <<EOF ~ EOF 사이 문자열을 cat 의 표준입력으로 전달해 화면 출력.
# 따옴표 없는 <<EOF 이므로 본문 안의 ${...} / $(...) 가 정상적으로 확장됨.
# (확장을 막고 그대로 출력하려면 <<'EOF' 처럼 작은따옴표로 감싸면 됨)
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
