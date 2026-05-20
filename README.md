# dfm-bq-load-alerter

DFM(datafabric-manager) 시스템에서 BigQuery 적재(load) 작업 상태를 모니터링하고 이상 상황을 알리는 웹 서비스.

> ℹ️ **MVP 스캐폴드 단계입니다.** 백엔드/프론트엔드/Helm/CI 의 골격만 존재하며, 실제 BigQuery 연동·알림 채널은 미구현입니다.

## 구성

- **Backend**: Python 3.13 + FastAPI ([`backend/`](backend/))
- **Frontend**: TypeScript + React 19 + Vite ([`frontend/`](frontend/))
- **Container**: 단일 멀티스테이지 이미지 — frontend 빌드 산출물을 FastAPI 가 정적 서빙 ([`Dockerfile`](Dockerfile))
- **Helm chart**: [`charts/dfm-bq-load-alerter/`](charts/dfm-bq-load-alerter/)
- **CI/CD**: GitHub Actions ([`.github/workflows/`](.github/workflows/))

```
.
├── backend/
│   ├── pyproject.toml
│   ├── src/dfm_bq_load_alerter/
│   │   ├── main.py            # FastAPI app + SPA fallback
│   │   ├── settings.py
│   │   └── api/
│   │       ├── health.py      # GET /healthz
│   │       └── alerts.py      # GET /api/alerts (mock)
│   └── tests/test_health.py
├── frontend/
│   ├── package.json           # React 19 + TS + Vite
│   └── src/{main.tsx,App.tsx,App.css}
├── charts/dfm-bq-load-alerter/
│   ├── Chart.yaml / values.yaml
│   └── templates/{deployment,service,ingress,serviceaccount}.yaml
├── .github/workflows/
│   ├── ci.yml                 # PR/push → lint, test, docker build
│   └── release.yml            # release published → push image + helm upgrade
├── Dockerfile                 # node22 → python3.13 멀티스테이지
└── .dockerignore
```

## 엔드포인트

| Method | Path | 설명 |
|--------|------|------|
| GET | `/healthz` | 헬스 체크 |
| GET | `/api/version` | 앱 버전 |
| GET | `/api/alerts` | 알림 목록 (현재 mock 데이터) |
| GET | `/` 외 SPA 경로 | React SPA 라우팅 (정적 파일) |

## 배포

- **클러스터**: `onprem-prd` (Rancher RKE2)
- **네임스페이스**: `datafabric-alert`
- **URL**: <https://dfm-alert.shinsegae.ai>
- **IngressClass**: `nginx`
- **TLS**: 와일드카드 시크릿 `tls-wildcard-shinsegae-ai-2026` 재사용 (`datafabric-alert` 네임스페이스에 동일 시크릿이 존재해야 함)

### 릴리스 플로우 (`scripts/release.sh`)

GH-hosted runner 가 사내 Rancher API 에 도달할 수 없어 이미지 빌드와 클러스터 배포가 분리되며, 그 외 단계는 `scripts/release.sh` 가 한 번에 자동화한다.

```bash
./scripts/release.sh 0.9.0           # 정식 실행 (각 단계 confirm 프롬프트 포함)
./scripts/release.sh 0.9.0 --yes     # 프롬프트 자동 yes
./scripts/release.sh 0.9.0 --dry-run # 명령만 출력
./scripts/release.sh 0.9.0 --start-from migrate  # 특정 단계부터 재개
```

스크립트는 **멱등** — 중도 실패 후 동일 명령으로 재실행하면 이미 끝난 단계는 자동 skip 한다.

| 단계 | 동작 | 멱등 키 |
|------|------|---------|
| **1. bump** | `chore/release-vX.Y.Z` 브랜치에서 `backend/pyproject.toml`, `frontend/package.json` 버전을 X.Y.Z 로 올린 뒤 `dev` 로 머지(merge commit) | dev 의 두 버전 파일이 이미 X.Y.Z 면 skip |
| **2. pr1** | `dev → main` 릴리스 PR 생성·CI 대기·merge commit 머지 | dev 가 main 의 ancestor 이고 main 도 X.Y.Z 면 skip |
| **3. migrate** | 운영 DB(Cloud SQL `dfm_bq_load_alerter`) 에 `alembic upgrade head` 적용 | alembic 자체가 멱등 |
| **4. release** | `vX.Y.Z` 태그 + GitHub Release 생성 → `release.yml` 이 GCP Artifact Registry 로 이미지 push | 태그가 이미 존재하면 skip |
| **5. deploy** | (수동) 사내망 단말에서 `./scripts/deploy.sh X.Y.Z` 로 클러스터 적용 | — |

> ⚠️ **버전 bump 는 반드시 dev 에서 먼저** 한다. 과거에는 dev→main 머지 후 main 에 직접 bump PR 을 올렸지만, 그 커밋이 dev 로 역방향 머지되지 않아 다음 릴리스 PR 의 버전 파일이 매번 충돌했다. dev-first bump 와 함께 GitHub 리포지토리 설정에서 **squash merge 를 비활성화** 하여(merge commit 전용) dev↔main 사이 history 도 일치하도록 운영한다.

상세 — [`docs/deployment.md`](docs/deployment.md), 사후 작업 — [`scripts/deploy.sh`](scripts/deploy.sh).

### 필요한 GitHub Secrets / Variables (이미지 푸시용)

| 종류 | 이름 | 용도 |
|------|------|------|
| secret | `GCP_SA_KEY` | Artifact Registry push 권한 SA JSON 키 |
| variable | `AR_HOST` | 예: `asia-northeast3-docker.pkg.dev` |
| variable | `AR_PROJECT` | GCP 프로젝트 ID |
| variable | `AR_REPO` | Artifact Registry 리포지토리 이름 |

## 로컬 개발

### Backend

```bash
cd backend
uv pip install --system ".[dev]"
uvicorn dfm_bq_load_alerter.main:app --reload --port 8000
```

테스트:

```bash
cd backend && pytest -q
```

### Frontend

```bash
cd frontend
npm install
npm run dev          # http://localhost:5173 — /api, /healthz 는 :8000 프록시
```

### 단일 이미지 빌드 & 실행

```bash
docker build -t dfm-bq-load-alerter:dev .
docker run --rm -p 8000:8000 dfm-bq-load-alerter:dev
# http://localhost:8000
```

## 위치

- DFM 문서 허브: [`dfm-doc`](https://github.com/emartdt/dfm-doc) — 이 리포지토리는 `repos/dfm-bq-load-alerter/` 경로에 git submodule 로 마운트됨
- 카테고리·역할: [`architecture/repos-overview.md`](https://github.com/emartdt/dfm-doc/blob/main/architecture/repos-overview.md)

## 라이선스 / 소유

본 리포지토리는 DFM 운영 도구의 일부로, 사내 운영 컴포넌트 정책을 따릅니다.
