# 로컬 개발용 환경변수 템플릿 (op run 이 읽음).
#
# 사용법: ./scripts/dev-up.sh
#
# 1password 사전 등록 항목 (vault=Shinsegae):
#   dfm-dev-bq-load-alerter
#     - postgres_dsn      : postgresql+asyncpg://USER:PASS@HOST:PORT/DB
#   [dfm] keycloak: dfm-bq-load-alerter
#     - client_id, client_secret, session_secret_key
#       (대괄호 때문에 op:// 참조 불가 — dev-up.sh가 op item get으로 직접 export)
#
# 평문 노출 금지 — 본 파일은 항상 op:// 참조만.

DFM_ALERT_POSTGRES_DSN=op://Shinsegae/dfm-dev-bq-load-alerter/postgres_dsn

DFM_ALERT_OIDC_ISSUER=https://iam.shinsegae.ai/auth/realms/SHINSEGAE.AI
DFM_ALERT_OIDC_REDIRECT_URI=http://localhost:5173/auth/callback
DFM_ALERT_OIDC_POST_LOGOUT_REDIRECT_URI=http://localhost:5173/

# 로컬에서는 cron 미가동 (스케줄러가 reload 시마다 깨어나면 dev 잡음)
DFM_ALERT_SCHEDULER_ENABLED=false

# 로컬은 단일 프로세스라 PG advisory lock 기반 leader election 불필요.
# false 로 두면 lock 경합 없이 곧바로 스케줄러를 띄운다.
DFM_ALERT_LEADER_ELECTION_ENABLED=false

DFM_ALERT_ENVIRONMENT=development
DFM_ALERT_LOG_LEVEL=DEBUG

# dev 에서는 vite dev server (:5173) 가 React 자산을 모두 서빙한다.
DFM_ALERT_STATIC_DIR=/nonexistent/dfm-bq-load-alerter-dev

# BigQuery 연동은 로컬에서 보통 비활성.
DFM_ALERT_BQ_PROJECT_ID=op://Shinsegae/dfm-dev-bq-load-alerter/bq_project_id

# 로컬 SMTP — Mailpit 등 캡처용 컨테이너로 발송 경로만 검증.
#   docker run -d --rm --name mailpit -p 1025:1025 -p 8025:8025 axllent/mailpit
#   수신함: http://localhost:8025
# 실제 릴레이로 보내려면 host/port/user/password 를 사내 SMTP 값으로 교체.
DFM_ALERT_SMTP_HOST=10.253.12.132
DFM_ALERT_SMTP_PORT=25
DFM_ALERT_SMTP_USE_STARTTLS=false
DFM_ALERT_SMTP_FROM_ADDR=dfm-alert@shinsegae.ai
