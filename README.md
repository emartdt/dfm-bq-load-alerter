<div align="center">

# dfm-bq-load-alerter

**DFM(datafabric-manager) BigQuery 적재 모니터링 & 알림 서비스**

BigQuery에 일/월 단위로 적재되는 배치 테이블의 적재 완료 여부, 행 수 0 여부, 증감률 이상치를 자동으로 점검하고 Email / Microsoft Teams 채널로 알림을 발송합니다.

[![CI](https://github.com/emartdt/dfm-bq-load-alerter/actions/workflows/ci.yml/badge.svg)](https://github.com/emartdt/dfm-bq-load-alerter/actions/workflows/ci.yml)
[![Release](https://github.com/emartdt/dfm-bq-load-alerter/actions/workflows/release.yml/badge.svg)](https://github.com/emartdt/dfm-bq-load-alerter/actions/workflows/release.yml)
![python](https://img.shields.io/badge/python-3.13-blue?logo=python&logoColor=white)
![fastapi](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)
![react](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)
![vite](https://img.shields.io/badge/Vite-6-646CFF?logo=vite&logoColor=white)
![helm](https://img.shields.io/badge/Helm-chart-0F1689?logo=helm&logoColor=white)
![license](https://img.shields.io/badge/license-Proprietary-lightgrey)

[기능](#-기능) · [아키텍처](#-아키텍처) · [빠른 시작](#-빠른-시작) · [설정](#-설정-환경변수) · [API](#-api-레퍼런스) · [배포](#-배포) · [개발 가이드](#-개발-가이드)

</div>

---

## 📋 목차

- [기능](#-기능)
- [아키텍처](#-아키텍처)
- [기술 스택](#-기술-스택)
- [프로젝트 구조](#-프로젝트-구조)
- [빠른 시작](#-빠른-시작)
- [설정 (환경변수)](#-설정-환경변수)
- [상태 판정 로직](#-상태-판정-로직)
- [API 레퍼런스](#-api-레퍼런스)
- [화면](#-화면-frontend-routes)
- [배포](#-배포)
- [릴리스 플로우](#-릴리스-플로우)
- [개발 가이드](#-개발-가이드)
- [기여](#-기여)
- [라이선스](#-라이선스)

---

## ✨ 기능

- **자동 점검 스케줄러** — APScheduler 기반 cron 작업으로 BigQuery 테이블 상태를 정기 점검 (daily / monthly).
- **상태 판정 엔진** — 적재 완료 여부 · `ROW COUNT = 0` · 전 배치 대비 증감률 이상치를 OR 조합으로 판정 (`ok` / `fail` / `skip`).
- **유연한 임계치 정책** — 그룹/테이블별 기본 증감률 임계치(default `25%`) override, 시간 기반/품질 기반 조건 개별 토글.
- **글로벌 리포트** — 매일 정해진 시각(예: 07:45)에 전체 적재 현황을 일괄 발송, 그 외 시간대는 실패 시에만 알람.
- **멀티 채널 알림** — Email (SMTP relay) + Microsoft Teams (Incoming Webhook), 수신자/Webhook BO에서 CRUD.
- **백오피스 UI** — React 19 SPA. 테이블/수신자/Webhook/정책/이력/통계 대시보드.
- **이력 & 통계** — 점검 스냅샷·이벤트·일/월별 성공률·테이블별 성공률 차트.
- **인증/인가** — Keycloak OIDC 기반 SSO, 서버 세션 쿠키 (`itsdangerous` 서명, 8h 기본).
- **HA-Ready 단일 인스턴스** — PostgreSQL advisory lock 기반 leader election, 다중 Pod 환경에서도 cron 1회 보장.
- **사내 프록시 우회** — 외부 인터넷이 막힌 사내 K8s 클러스터에서 Teams Webhook · Google APIs 호출을 위한 forward proxy 설정 내장.
- **자동 마이그레이션** — Helm `migrate-job` 이 release 시 `alembic upgrade head` 선실행.

---

## 🏗 아키텍처

```mermaid
flowchart LR
    subgraph User["👤 사용자"]
        Browser[Browser SPA]
        Ops[Ops Email/Teams]
    end

    subgraph K8s["☸️ K8s (onprem-prd / datafabric-alert)"]
        subgraph Pod["Pod: dfm-bq-load-alerter"]
            FastAPI[FastAPI<br/>uvicorn :8000]
            Sched[APScheduler<br/>+ Leader Lock]
            Static[React SPA<br/>static files]
        end
        Ing[Ingress<br/>nginx + TLS]
    end

    subgraph External["외부/사내"]
        BQ[(BigQuery)]
        PG[(Cloud SQL<br/>PostgreSQL)]
        KC[Keycloak<br/>OIDC]
        SMTP[SMTP Relay]
        Teams[Teams Webhook]
        Proxy[Forward Proxy<br/>proxy.shinsegae.ai]
    end

    Browser -->|HTTPS| Ing
    Ing --> FastAPI
    FastAPI --> Static
    FastAPI -->|OIDC| KC
    FastAPI <--> PG
    Sched <--> PG
    Sched -->|쿼리| BQ
    Sched -->|판정 결과| Ops
    Sched -.via.-> Proxy
    Proxy --> Teams
    Proxy --> BQ
    FastAPI -->|메일| SMTP
```

### 핵심 컴포넌트

| 컴포넌트 | 디렉토리 | 역할 |
|----------|----------|------|
| `main` | `backend/src/dfm_bq_load_alerter/main.py` | FastAPI 앱 부팅, lifespan, 라우터 등록, SPA fallback |
| `api/*` | `backend/src/dfm_bq_load_alerter/api/` | REST 엔드포인트 (tables/recipients/webhooks/checks/history/policy/notifier) |
| `auth/*` | `backend/src/dfm_bq_load_alerter/auth/` | Keycloak OIDC, 세션, 권한 가드 |
| `bq/*` | `backend/src/dfm_bq_load_alerter/bq/` | BigQuery 클라이언트, 메타데이터 조회, 쿼리 템플릿 |
| `checks/*` | `backend/src/dfm_bq_load_alerter/checks/` | 상태 판정 엔진 (`engine.py`), runner |
| `notifier/*` | `backend/src/dfm_bq_load_alerter/notifier/` | Email/Teams dispatcher + Jinja2 템플릿 |
| `scheduler/*` | `backend/src/dfm_bq_load_alerter/scheduler/` | APScheduler 셋업, 동적 잡 등록, PG advisory leader |
| `db/*` | `backend/src/dfm_bq_load_alerter/db/` | SQLAlchemy 비동기 엔진, 세션, ORM 모델 |

---

## 🛠 기술 스택

### Backend (Python 3.13)

| 영역 | 라이브러리 / 버전 |
|------|------------------|
| 웹 프레임워크 | FastAPI 0.115, uvicorn 0.32 |
| 데이터 검증 | pydantic 2.9, pydantic-settings 2.6 |
| ORM / 마이그레이션 | SQLAlchemy 2.0 (async), asyncpg 0.30, alembic 1.13 |
| Cloud SQL | cloud-sql-python-connector 1.12 |
| 스케줄러 | APScheduler 3.10 (asyncio) |
| BigQuery | google-cloud-bigquery 3.25 |
| 알림 | aiosmtplib 3.0, httpx 0.27, jinja2 3.1 |
| 인증 | authlib 1.3, python-jose 3.3, itsdangerous 2.2 |
| 캐싱 | cachetools 5.5 |
| 개발 도구 | ruff 0.7, mypy 1.13, pytest 8.3, pytest-asyncio 0.24, freezegun 1.5 |

### Frontend (Node 22)

| 영역 | 라이브러리 / 버전 |
|------|------------------|
| 프레임워크 | React 19 + TypeScript 5.7 |
| 빌드 | Vite 6 |
| 라우팅 | react-router-dom 7 |
| HTTP | axios 1.7 |
| Lint | ESLint 9 + typescript-eslint 8 |

### 인프라

| 영역 | 스택 |
|------|------|
| 컨테이너 | Docker (멀티스테이지: `node:22-alpine` → `python:3.13-slim` + `uv`) |
| 오케스트레이션 | Kubernetes (Rancher RKE2) + Helm chart |
| Ingress | nginx ingress controller + wildcard TLS |
| 이미지 레지스트리 | GCP Artifact Registry (`asia-northeast3`) |
| CI/CD | GitHub Actions |
| DB (운영) | Cloud SQL (PostgreSQL) |
| 인증 (운영) | Keycloak (`iam.shinsegae.ai`) |

---

## 📁 프로젝트 구조

```
dfm-bq-load-alerter/
├── backend/                            # Python 3.13 + FastAPI
│   ├── pyproject.toml                  # 의존성 / 빌드 / ruff / pytest 설정
│   ├── alembic.ini
│   ├── alembic/versions/               # DB 스키마 마이그레이션
│   ├── src/dfm_bq_load_alerter/
│   │   ├── main.py                     # FastAPI app + lifespan + SPA fallback
│   │   ├── settings.py                 # pydantic-settings (DFM_ALERT_* env)
│   │   ├── api/                        # REST 엔드포인트 (tables/recipients/...)
│   │   ├── auth/                       # OIDC (Keycloak) + 세션
│   │   ├── bq/                         # BigQuery client/metadata/templating
│   │   ├── checks/                     # 상태 판정 엔진 + runner
│   │   ├── db/                         # SQLAlchemy + 모델
│   │   ├── notifier/                   # Email / Teams + 템플릿
│   │   └── scheduler/                  # APScheduler + leader election
│   └── tests/                          # pytest (한국어 함수명 정책)
├── frontend/                           # React 19 + Vite 6 + TS
│   ├── package.json
│   ├── vite.config.ts                  # /api, /healthz, /auth 프록시 → :8000
│   └── src/
│       ├── App.tsx                     # 라우터 + ProtectedRoute + Layout
│       ├── api/                        # axios 클라이언트별
│       ├── auth/                       # AuthContext / ProtectedRoute
│       ├── components/                 # Header, BarChart, LineChart
│       └── pages/                      # Home / Tables / Recipients / Webhooks / History / Policy / Login
├── charts/dfm-bq-load-alerter/         # Helm chart
│   ├── Chart.yaml / values.yaml
│   └── templates/{deployment,service,ingress,serviceaccount,migrate-job,_helpers,NOTES}.{yaml,tpl,txt}
├── scripts/
│   ├── dev-up.sh / dev-down.sh         # 로컬 백·프 동시 실행/정지
│   ├── dev-restart.sh
│   ├── alembic-upgrade.sh              # 운영/스테이징 DB 마이그레이션 실행
│   ├── release.sh                      # 5단계 릴리스 자동화 (멱등)
│   ├── deploy.sh                       # helm upgrade (사내망 단말)
│   ├── bigquery/                       # BQ 메타데이터 비교/시드
│   ├── diff-batch-config.sql
│   └── expected-batch-config.json
├── docs/
│   ├── deployment.md                   # 배포 절차 상세
│   ├── dev-setup.md                    # 로컬 개발 셋업
│   └── 요구사항.md                     # 도메인 요구사항 통합본
├── .github/workflows/
│   ├── ci.yml                          # PR/push → ruff + pytest + npm build + docker build
│   └── release.yml                     # release published → AR push
├── Dockerfile                          # 멀티스테이지 (node22 → python3.13-slim)
├── dev.env.tpl                         # 1password op:// 참조 템플릿
└── README.md
```

---

## 🚀 빠른 시작

### 사전 조건

| 도구 | 버전 | 설치 |
|------|------|------|
| `op` (1password CLI) | 2.x+ | `brew install --cask 1password-cli` |
| `uv` (Python 패키지 매니저) | 0.5+ | `brew install uv` |
| Node.js | 22 LTS | `brew install node@22` |
| PostgreSQL | 15+ 접근 경로 | Cloud SQL Auth Proxy 또는 로컬 PG |

1password 데스크톱 앱 + CLI 통합 인증(`op signin`) 완료 필요.

### 1. 1password 항목 등록 (최초 1회)

vault: **Shinsegae** / 항목명: **`dfm-dev-bq-load-alerter`** — `postgres_dsn`, `bq_project_id`, 기타 시크릿 필드.
세부 필드 목록은 [`docs/dev-setup.md`](docs/dev-setup.md) 참고.

### 2. 의존성 설치 (최초 1회)

```bash
# Backend
cd backend && uv sync --frozen --extra dev

# Frontend
cd ../frontend && npm install
```

### 3. 실행

```bash
./scripts/dev-up.sh
# Backend  → http://localhost:8000/healthz   (logs: .dev/backend.log)
# Frontend → http://localhost:5173/          (logs: .dev/frontend.log)

# 정지
./scripts/dev-down.sh
```

`op run` 이 `dev.env.tpl` 의 `op://` 참조를 백엔드 자식 프로세스에만 환경변수로 주입합니다 — **평문 시크릿이 디스크에 저장되지 않습니다**.

브라우저에서 `http://localhost:5173` 접속 → Keycloak 로그인 → BO 진입.

### 4. 마이그레이션 (최초 1회)

```bash
cd backend && op run --env-file=../dev.env.tpl -- uv run alembic upgrade head
```

### 5. 단일 이미지 빌드 (선택)

```bash
docker build -t dfm-bq-load-alerter:dev .
docker run --rm -p 8000:8000 \
  -e DFM_ALERT_POSTGRES_DSN=... \
  -e DFM_ALERT_OIDC_ISSUER=... \
  -e DFM_ALERT_OIDC_CLIENT_ID=... \
  -e DFM_ALERT_OIDC_CLIENT_SECRET=... \
  -e DFM_ALERT_SESSION_SECRET_KEY=... \
  dfm-bq-load-alerter:dev
# → http://localhost:8000
```

상세 가이드는 [`docs/dev-setup.md`](docs/dev-setup.md).

---

## ⚙️ 설정 (환경변수)

모든 설정은 `DFM_ALERT_*` prefix 환경변수로 주입합니다. pydantic-settings 가 자동 파싱.

### 필수 (없으면 부팅 실패)

| 변수 | 설명 |
|------|------|
| `DFM_ALERT_OIDC_ISSUER` | Keycloak realm issuer URL |
| `DFM_ALERT_OIDC_CLIENT_ID` | OIDC 클라이언트 ID |
| `DFM_ALERT_OIDC_CLIENT_SECRET` | OIDC 클라이언트 시크릿 |
| `DFM_ALERT_SESSION_SECRET_KEY` | 세션 쿠키 서명 키 (32바이트 hex 권장) |

### 자주 사용

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `DFM_ALERT_POSTGRES_DSN` | `""` | `postgresql+asyncpg://user:pass@host:5432/dbname` |
| `DFM_ALERT_POSTGRES_SESSION_TIMEZONE` | `Asia/Seoul` | PG 세션 TZ |
| `DFM_ALERT_ENVIRONMENT` | `production` | `development` / `staging` / `production` |
| `DFM_ALERT_LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` / ... |
| `DFM_ALERT_SCHEDULER_ENABLED` | `true` | cron 활성화 |
| `DFM_ALERT_LEADER_ELECTION_ENABLED` | `true` | PG advisory lock (멀티 Pod 환경) |
| `DFM_ALERT_LEADER_PING_SECONDS` | `30` | leader heartbeat 주기 (5–300) |
| `DFM_ALERT_SCHEDULER_TIMEZONE` | `Asia/Seoul` | APScheduler TZ |
| `DFM_ALERT_DEFAULT_THRESHOLD_PERCENT` | `25.0` | 기본 증감률 임계치 (%) |
| `DFM_ALERT_RETENTION_DAYS` | `90` | 스냅샷/이력 보관 기간 |
| `DFM_ALERT_STATIC_DIR` | `/app/static` | React 빌드 산출물 경로 |
| `DFM_ALERT_SESSION_MAX_AGE_SECONDS` | `28800` | 세션 만료 (8h) |

### BigQuery

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `DFM_ALERT_BQ_PROJECT_ID` | `""` | GCP 프로젝트 ID (운영 스크립트·smoke 테스트용. 테이블 점검은 테이블별 `project_id` 필수 입력값 사용) |
| `DFM_ALERT_BQ_DATASET_LIST` | `""` | 쉼표 구분 데이터셋 (UI 드롭다운용) |
| `DFM_ALERT_BQ_CREDENTIALS_PATH` | `/var/secrets/bq-sa/key.json` | BQ SA 키 JSON 경로 |
| `DFM_ALERT_BQ_MAX_CONCURRENCY` | `5` | BQ 조회 동시 실행 한도 (1–64) |
| `DFM_ALERT_CONDITION_QUERY_MAX_BYTES` | `104857600` | 사용자 정의 condition SQL 의 스캔 바이트 상한 (100 MiB) |

### SMTP

| 변수 | 기본값 |
|------|--------|
| `DFM_ALERT_SMTP_HOST` / `_PORT` / `_USER` / `_PASSWORD` | `""` / `587` / `""` / `""` |
| `DFM_ALERT_SMTP_FROM_ADDR` | `""` |
| `DFM_ALERT_SMTP_USE_STARTTLS` | `true` |
| `DFM_ALERT_SMTP_LOCAL_HOSTNAME` | `""` |

### Teams 발송 튜닝

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `DFM_ALERT_TEAMS_CHUNK_DELAY_SECONDS` | `5.0` | 분할 전송 사이 지연 (rate-limit 회피, 0–60) |

전체 목록과 검증 로직은 [`backend/src/dfm_bq_load_alerter/settings.py`](backend/src/dfm_bq_load_alerter/settings.py) 참조.

---

## 🧮 상태 판정 로직

매 cron tick 마다 각 등록 테이블에 대해 다음 트리를 평가합니다 (`backend/src/dfm_bq_load_alerter/checks/engine.py`):

```
오늘 일자로 적재 완료
├─ row count = 0                                    → fail
└─ row count > 0
   ├─ 이전 배치 스냅샷 있음
   │  ├─ 증감률 ≥ 임계치                            → fail
   │  └─ 증감률 < 임계치                            → ok
   └─ 이전 배치 스냅샷 없음                         → ok

오늘 일자로 적재 미완료
├─ 현재 시각 < 배치예상시간 + 버퍼                  → skip
└─ 현재 시각 ≥ 배치예상시간 + 버퍼                  → fail
```

| 상태 | 의미 | 알림 |
|------|------|------|
| `ok`   | 정상 적재 | 글로벌 리포트에만 포함 |
| `fail` | 적재 실패 / 행 0 / 증감 이상치 / 지연 초과 | 즉시 알림 |
| `skip` | 아직 적재 시간 전 (버퍼 안쪽) | 알림 없음 |

조건은 그룹/테이블 단위로 활성/비활성 가능하며, 임계치(`DFM_ALERT_DEFAULT_THRESHOLD_PERCENT`) 는 정책 페이지에서 override 합니다. 도메인 요구사항 전체는 [`docs/요구사항.md`](docs/요구사항.md) 참조.

---

## 📡 API 레퍼런스

전체 OpenAPI 스펙은 부팅 후 [`/docs`](http://localhost:8000/docs) 에서 인터랙티브 확인.

### Public

| Method | Path | 설명 |
|--------|------|------|
| GET | `/healthz` | 헬스 체크 (DB 연결 포함) |
| GET | `/api/version` | 앱 버전 |
| GET | `/{*}` | SPA fallback (`/api`, `/auth`, `/healthz`, `/assets` 제외) |

### Auth (Keycloak OIDC)

| Method | Path | 설명 |
|--------|------|------|
| GET | `/auth/login` | OIDC 로그인 시작 |
| GET | `/auth/callback` | OIDC 콜백 |
| POST | `/auth/logout` | 로그아웃 (세션 제거) |
| GET | `/auth/me` | 현재 사용자 정보 |

### Tables

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/tables` | 등록된 BQ 테이블 목록 |
| POST | `/api/tables` | 신규 등록 |
| GET | `/api/tables/{id}` | 단건 조회 |
| PATCH | `/api/tables/{id}` | 부분 수정 |
| DELETE | `/api/tables/{id}` | 삭제 |
| POST | `/api/tables/import` | BQ 메타데이터로 일괄 import |
| POST | `/api/tables/{id}/condition/preview` | 사용자 condition SQL dry-run |

### Recipients · Webhooks

| Method | Path |
|--------|------|
| GET/POST/GET/PATCH/DELETE | `/api/recipients[/{id}]` |
| POST | `/api/recipients/{id}/test` — 테스트 메일 발송 |
| GET/POST/PATCH/DELETE | `/api/webhooks[/{id}]` |
| POST | `/api/webhooks/{id}/test` — 테스트 Teams 메시지 발송 |

### Checks

| Method | Path | 설명 |
|--------|------|------|
| POST | `/api/checks/run-now` | 점검 즉시 실행 (테이블/그룹 지정) |
| POST | `/api/checks/report-now` | 글로벌 리포트 즉시 발송 |

### History · Stats

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/history/snapshots` | 점검 스냅샷 페이징 |
| GET | `/api/history/events` | 이벤트(알림 발송 기록) 페이징 |
| GET | `/api/history/stats/daily` | 일별 성공/실패 집계 |
| GET | `/api/history/stats/monthly` | 월별 집계 |
| GET | `/api/history/stats/table-success-rate` | 테이블별 성공률 |

### Policy · Notifier

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/policy` | 글로벌 정책 조회 |
| PATCH | `/api/policy` | 정책 수정 (임계치, 리텐션, 글로벌 리포트 시각 등) |
| POST | `/api/notifier/test-send` | 임의 본문으로 채널 테스트 |

---

## 🖥 화면 (Frontend Routes)

| Path | 페이지 | 권한 |
|------|--------|------|
| `/login` | Keycloak 로그인 진입점 | Public |
| `/` | Home — 대시보드 (오늘 현황·차트) | 로그인 |
| `/tables` | BQ 테이블 CRUD | 로그인 |
| `/recipients` | 이메일 수신자 관리 | 로그인 |
| `/webhooks` | Teams Webhook 관리 | 로그인 |
| `/history` | 점검 이력 / 이벤트 조회 | 로그인 |
| `/policy` | 전역 정책 (임계치, 리텐션, 글로벌 리포트 시각) | 로그인 |

`ProtectedRoute` (frontend/src/auth/ProtectedRoute.tsx) 가 세션 미인증 시 `/login` 으로 리다이렉트합니다.

---

## 🚢 배포

### 환경 정보

| 항목 | 값 |
|------|----|
| 클러스터 | `onprem-prd` (Rancher RKE2) |
| 네임스페이스 | `datafabric-alert` |
| 외부 URL | <https://dfm-alert.shinsegae.ai> |
| IngressClass | `nginx` |
| TLS | 와일드카드 시크릿 `tls-wildcard-shinsegae-ai-2026` |
| 이미지 레지스트리 | GCP Artifact Registry (`asia-northeast3-docker.pkg.dev`) |

### 사전 시크릿 (최초 1회)

`datafabric-alert` 네임스페이스에 다음 두 시크릿이 있어야 합니다:

| 이름 | 용도 |
|------|------|
| `tls-wildcard-shinsegae-ai-2026` | ingress wildcard TLS |
| `asia-gcr-global-secret` | Artifact Registry image pull |

복제 절차는 [`docs/deployment.md`](docs/deployment.md) 참조.

### 일반 배포 (사내 단말)

```bash
./scripts/deploy.sh 0.10.2                   # helm upgrade
./scripts/deploy.sh 0.10.2 --dry-run         # 적용 전 변경 확인
./scripts/deploy.sh 0.10.2 --set replicaCount=2
```

### 롤백 / 관측

```bash
helm --kube-context onprem-prd -n datafabric-alert rollback dfm-bq-load-alerter
kubectl --context onprem-prd -n datafabric-alert get all
kubectl --context onprem-prd -n datafabric-alert logs deploy/dfm-bq-load-alerter -f
```

배포 두 단계가 **이미지 빌드(외부 GH Runner) ↔ 클러스터 적용(사내 단말)** 으로 분리되어 있는 이유와 후속 ArgoCD 도입 TODO 는 [`docs/deployment.md`](docs/deployment.md) 참조.

---

## 🔁 릴리스 플로우

`scripts/release.sh` 한 번으로 5단계를 자동화합니다 (각 단계 confirm 프롬프트). **멱등** — 중단 후 동일 명령으로 재실행하면 끝난 단계는 자동 skip.

```bash
./scripts/release.sh 0.10.2                  # 정식 실행
./scripts/release.sh 0.10.2 --yes            # 프롬프트 자동 yes
./scripts/release.sh 0.10.2 --dry-run        # 명령만 출력
./scripts/release.sh 0.10.2 --start-from migrate   # 특정 단계부터 재개
```

| # | 단계 | 동작 | 멱등 키 |
|---|------|------|---------|
| 1 | **bump** | `chore/release-vX.Y.Z` 브랜치에서 `backend/pyproject.toml`, `frontend/package.json` 버전을 X.Y.Z 로 올린 뒤 `dev` 로 merge commit 머지 | dev 의 두 버전 파일이 이미 X.Y.Z |
| 2 | **pr1** | `dev → main` 릴리스 PR 생성·CI 대기·merge commit 머지 | dev 가 main 의 ancestor 이고 main 도 X.Y.Z |
| 3 | **migrate** | 운영 Cloud SQL 에 `alembic upgrade head` 적용 | alembic 자체가 멱등 |
| 4 | **release** | `vX.Y.Z` 태그 + GitHub Release 생성 → `release.yml` 이 Artifact Registry 로 이미지 push | 태그 존재 |
| 5 | **deploy** | (수동) 사내 단말에서 `./scripts/deploy.sh X.Y.Z` 로 helm upgrade | — |

> ⚠️ **버전 bump 는 반드시 dev 에서 먼저.** 과거 main 직접 bump 후 dev 로 역머지되지 않아 다음 릴리스 PR 의 버전 파일이 매번 충돌. dev-first bump 와 함께 GitHub 저장소 설정에서 **squash merge 비활성화**(merge commit 전용) 하여 dev↔main history 를 일치 운영.

### 필요한 GitHub Secrets / Variables

| 종류 | 이름 | 용도 |
|------|------|------|
| secret | `GCP_SA_KEY` | Artifact Registry push 권한 SA JSON 키 |
| variable | `AR_HOST` | 예: `asia-northeast3-docker.pkg.dev` |
| variable | `AR_PROJECT` | GCP 프로젝트 ID |
| variable | `AR_REPO` | Artifact Registry 리포 이름 |

---

## 🧑‍💻 개발 가이드

### 테스트

```bash
# Backend
cd backend && op run --env-file=../dev.env.tpl -- uv run pytest -q

# Frontend
cd frontend && npm run lint && npm run build
```

> 테스트 함수명은 한국어 표기를 허용합니다 (`tests/*.py` 의 N802 면제). 단위 테스트는 `freezegun` + `pytest-postgresql` 로 시간/DB 픽스처를 격리합니다.

### Lint / Type Check

```bash
cd backend && uv run ruff check .            # 라인 100자, py313 target
cd frontend && npm run lint                  # ESLint 9 + typescript-eslint
```

### 마이그레이션 추가

```bash
cd backend && op run --env-file=../dev.env.tpl -- \
  uv run alembic revision --autogenerate -m "add foo"
op run --env-file=../dev.env.tpl -- uv run alembic upgrade head
```

`backend/alembic/versions/` 의 파일명 컨벤션: `YYYYMMDD_NNNN_short_description.py`.

### 디렉토리 컨벤션

- **백엔드 라우터는 반드시 SPA fallback 보다 먼저 등록** (`main.py` 의 `_BACKEND_PREFIXES` C2 guard).
- **백엔드 API prefix**: `/api/<resource>`, 인증: `/auth/<action>`, 헬스: `/healthz`.
- 한국어 우선 (커밋 메시지·문서·런북). 코드 식별자/주석은 영문 유지.
- 다이어그램은 Mermaid 우선 (텍스트 diff 가능).

---

## 🤝 기여

이 저장소는 **DFM 문서 허브 [`dfm-doc`](https://github.com/emartdt/dfm-doc)** 에 `repos/dfm-bq-load-alerter/` 경로로 git submodule 마운트되어 운영됩니다. 카테고리·역할 매핑은 [`architecture/repos-overview.md`](https://github.com/emartdt/dfm-doc/blob/main/architecture/repos-overview.md) 참고.

### 작업 흐름

1. `dev` 에서 feature 브랜치 분기
2. 로컬에서 `./scripts/dev-up.sh` 로 검증
3. PR → `dev` 머지 (CI 통과 필수)
4. 릴리스 시점에 `./scripts/release.sh X.Y.Z` 로 5단계 자동화

### 커밋 메시지

[Conventional Commits](https://www.conventionalcommits.org/) 권장. 예시: `fix(engine): preserve sign in delta percent calculations`.

---

## 📄 라이선스

Proprietary — 본 리포지토리는 DFM 운영 도구의 일부로 사내 운영 컴포넌트 정책을 따릅니다. 외부 배포·공개를 금합니다.

---

<div align="center">

**문의** · DFM Platform Team

</div>
