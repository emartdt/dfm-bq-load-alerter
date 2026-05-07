# 로컬 개발 환경 셋업

dfm-bq-load-alerter 백엔드(FastAPI) + 프론트엔드(React/Vite) 를 로컬에서 띄우는 절차.
환경변수는 [1password CLI(`op`)](https://developer.1password.com/docs/cli/) 가
`dev.env.tpl` 의 `op://` 참조를 런타임에 실제 값으로 주입한다.
**평문 비밀은 디스크에 절대 저장하지 않는다.**

## 1. 사전 조건

| 도구 | 버전 | 설치 |
|------|------|------|
| `op` (1password CLI) | 2.x+ | `brew install --cask 1password-cli` |
| `uv` (Python 패키지 매니저) | 0.5+ | `brew install uv` |
| Node.js | 22 LTS | `brew install node@22` |
| PostgreSQL 접근 경로 | — | Cloud SQL Auth Proxy 또는 로컬 PG. DSN 한 줄로 표현 가능해야 함. |

`op signin` 으로 1password 데스크톱 앱과 CLI 통합 인증을 완료한 뒤 시작.

## 2. 1password 항목 등록 (최초 1회)

vault: **Shinsegae** / 항목명: **`[dfm] dev : dfm-bq-load-alerter`**

| Field | Type | 값 (예시) |
|-------|------|-----------|
| `postgres_dsn` | Password | `postgresql+asyncpg://dfm_bq_load_alerter:<pass>@127.0.0.1:5432/dfm_bq_load_alerter` |
| `bootstrap_token` | Password | 임의 문자열 32자 이상 — `openssl rand -hex 32` 로 생성. **운영 토큰 재사용 금지.** |

> ℹ️ 운영 시크릿(`[dfm] cloud-sql : dfm-bq-load-alerter`) 는 K8s Secret 동기화 전용. 로컬 dev 는 같은 DB 를 보더라도 별도 사용자/비밀번호를 두는 게 안전 (개발자별 분리, 사고 시 회수 용이).

## 3. 의존성 설치 (최초 1회)

```bash
cd backend
uv sync --frozen --extra dev
cd ../frontend
npm install
```

## 4. 실행

두 개의 터미널이 필요하다.

### 터미널 A — 백엔드 (uvicorn --reload)

```bash
./scripts/dev-backend.sh
# 기본 포트 8000. 변경 시 PORT=9000 ./scripts/dev-backend.sh
```

`op run` 이 `dev.env.tpl` 을 읽어 환경변수를 자식 프로세스(uvicorn)에만 주입.
프로세스 종료 시 평문은 메모리에서 사라진다.

### 터미널 B — 프론트엔드 (Vite dev server)

```bash
./scripts/dev-frontend.sh
# http://localhost:5173 — /api/* 와 /healthz 는 vite proxy 로 백엔드에 전달
```

브라우저에서 `localhost:5173` 접속 → 우측 상단 token 입력란에 1password 의
`bootstrap_token` 값을 붙여 넣으면 admin API 호출 가능.

## 5. 검증 체크리스트

```bash
# 백엔드만 단독으로 동작하는지
curl -s http://localhost:8000/healthz | jq
# {"status": "ok", "db": ...}

# DB 연결까지 살아있는지 (alembic upgrade head 한 번 돌려야 함)
cd backend && op run --env-file=../dev.env.tpl -- uv run alembic upgrade head

# 프론트 → 백엔드 proxy
curl -s http://localhost:5173/api/version
# {"version":"0.1.0"}

# 인증 필요한 admin 엔드포인트
TOKEN=$(op item get "[dfm] dev : dfm-bq-load-alerter" --vault Shinsegae --fields bootstrap_token --reveal)
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/policy | jq
unset TOKEN
```

## 6. 자주 마주치는 함정

- **`op run` 이 `Error retrieving credentials`** — 1password 데스크톱 앱이 잠겨 있거나 CLI 통합 인증 미완료. `op signin` 다시 실행.
- **`could not connect to server`** — Cloud SQL Auth Proxy 가 떠있지 않거나 로컬 PG 가 죽음. `dev.env.tpl` 의 `postgres_dsn` 의 host/port 와 실제 listen 주소 일치 확인.
- **`alembic` migration 누락** — DB 가 비어 있을 때 4번 검증의 `alembic upgrade head` 를 1회 돌려야 모든 새 컬럼/테이블이 생긴다.
- **`/api/*` 가 401** — bootstrap_token 이 매칭 안 됨. 백엔드를 재시작하면 op 가 새 값을 주입하니, 1password 에서 토큰을 바꿨다면 백엔드 프로세스 재시작 필요.
- **scheduler 가 자꾸 깨어남** — `dev.env.tpl` 에 `DFM_ALERT_SCHEDULER_ENABLED=false` 가 들어 있는지 확인.
