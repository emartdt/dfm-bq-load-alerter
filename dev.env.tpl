# 로컬 개발용 환경변수 템플릿 (op run / op inject 가 읽음).
#
# 사용법:
#   ./scripts/dev-backend.sh       (이 파일을 op 가 자동 주입)
#
# 1password 사전 등록 항목 (vault=Shinsegae):
#   [dfm] dev : dfm-bq-load-alerter
#     - postgres_dsn      : 로컬 PG 또는 cloud-sql-auth-proxy(localhost:5432) 용
#                           postgresql+asyncpg://USER:PASS@HOST:PORT/DB
#     - bootstrap_token   : 로컬 BO API 호출용 임의 토큰 (운영 토큰 재사용 금지)
#
# 평문 노출 금지 — 본 파일은 항상 op:// 참조만 두고 git 에 그대로 커밋.

DFM_ALERT_POSTGRES_DSN=op://Shinsegae/[dfm] dev : dfm-bq-load-alerter/postgres_dsn
DFM_ALERT_BOOTSTRAP_TOKEN=op://Shinsegae/[dfm] dev : dfm-bq-load-alerter/bootstrap_token

# 로컬에서는 cron 미가동 (스케줄러가 reload 시마다 깨어나면 dev 잡음)
DFM_ALERT_SCHEDULER_ENABLED=false

DFM_ALERT_ENVIRONMENT=development
DFM_ALERT_LOG_LEVEL=DEBUG

# 정적 파일은 frontend dev server 가 별도로 서빙 → 백엔드는 mount 안 해도 됨
DFM_ALERT_STATIC_DIR=/tmp/dfm-bq-load-alerter-empty-static

# BigQuery 연동은 로컬에서 보통 비활성. 필요 시 아래 두 줄 주석 해제 +
# 1password 에 sa_key.json 파일 항목 추가 후 op read 로 임시 파일 주입.
# DFM_ALERT_BQ_PROJECT_ID=op://Shinsegae/[dfm] dev : dfm-bq-load-alerter/bq_project_id
# DFM_ALERT_BQ_DATASET_LIST=op://Shinsegae/[dfm] dev : dfm-bq-load-alerter/bq_dataset_list
