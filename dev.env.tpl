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

DFM_ALERT_OIDC_ISSUER=https://iam.shinsegae.ai/realms/SHINSEGAE.AI
DFM_ALERT_OIDC_REDIRECT_URI=http://localhost:5173/auth/callback
DFM_ALERT_OIDC_POST_LOGOUT_REDIRECT_URI=http://localhost:5173/

# 로컬에서는 cron 미가동 (스케줄러가 reload 시마다 깨어나면 dev 잡음)
DFM_ALERT_SCHEDULER_ENABLED=false

DFM_ALERT_ENVIRONMENT=development
DFM_ALERT_LOG_LEVEL=DEBUG

# dev 에서는 vite dev server (:5173) 가 React 자산을 모두 서빙한다.
DFM_ALERT_STATIC_DIR=/nonexistent/dfm-bq-load-alerter-dev

# BigQuery 연동은 로컬에서 보통 비활성.
# DFM_ALERT_BQ_PROJECT_ID=op://Shinsegae/dfm-dev-bq-load-alerter/bq_project_id
# DFM_ALERT_BQ_DATASET_LIST=op://Shinsegae/dfm-dev-bq-load-alerter/bq_dataset_list
