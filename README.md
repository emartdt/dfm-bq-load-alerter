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

### 릴리스 플로우

1. `main` 에 머지 후 GitHub UI 에서 `vX.Y.Z` 태그로 release publish
2. `.github/workflows/release.yml` 이 자동 실행:
   - GCP Artifact Registry 로 이미지 push (`<host>/<project>/<repo>/dfm-bq-load-alerter:vX.Y.Z`)
   - `helm upgrade --install` 으로 onprem-prd 클러스터에 배포

### 필요한 GitHub Secrets / Variables

| 종류 | 이름 | 용도 |
|------|------|------|
| secret | `GCP_SA_KEY` | Artifact Registry push 권한 SA JSON 키 |
| secret | `KUBE_CONFIG` | onprem-prd kubeconfig (base64 인코딩) |
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

## TODO (MVP 이후)

- [ ] 실제 BigQuery load job 모니터링 로직 (`google-cloud-bigquery` SDK)
- [ ] 알림 채널 연동 (Slack / 사내 알림 시스템)
- [ ] 알림 임계치·정책 설정 UI
- [ ] 인증 (FreeIPA/OIDC SSO) — 현재 무인증
- [ ] Helm chart 를 `datafabric-appcatalog-charts` 로 이전
- [ ] 와일드카드 TLS 시크릿 자동 복제 메커니즘 (reflector 등)
- [ ] DFM 문서 작성 (`architecture/dfm-bq-load-alerter.md`, `runbook/`)
- [ ] 관측성: Prometheus `/metrics`, 구조화 로그
- [ ] e2e 테스트

## 위치

- DFM 문서 허브: [`dfm-doc`](https://github.com/emartdt/dfm-doc) — 이 리포지토리는 `repos/dfm-bq-load-alerter/` 경로에 git submodule 로 마운트됨
- 카테고리·역할: [`architecture/repos-overview.md`](https://github.com/emartdt/dfm-doc/blob/main/architecture/repos-overview.md)

## 라이선스 / 소유

본 리포지토리는 DFM 운영 도구의 일부로, 사내 운영 컴포넌트 정책을 따릅니다.
