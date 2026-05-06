# 배포 가이드

`dfm-bq-load-alerter` 의 운영 배포는 **두 단계**로 분리되어 있다.

| 단계 | 어디서 | 무엇을 |
|------|--------|--------|
| 1. 이미지 빌드·푸시 | GitHub Actions (사외) | release publish 시 자동 — Artifact Registry 로 push |
| 2. 클러스터 배포 | 사내망 (수동) | `scripts/deploy.sh` 로 helm upgrade |

GitHub-hosted runner 가 사내 Rancher API(`rancher.shinsegae.ai`, 10.253.71.x) 에 도달할 수 없어 helm 단계를 분리했다. 추후 셀프-호스티드 러너 또는 GitOps(ArgoCD/Flux)로 자동화 예정.

## 사전 조건

- `kubectl` v1.28+, `helm` v3+ 설치
- `~/.kube/config` 에 `onprem-prd` context (Rancher 토큰 인증)
- 사내망 접속 가능 (VPN 또는 사내 단말)
- 대상 네임스페이스: `datafabric-alert`

### 사전 복제 시크릿 (최초 1회)

`datafabric-alert` 네임스페이스에 다음 두 시크릿이 존재해야 한다. 둘 다 `datafabric-platform` 네임스페이스에서 동일 이름으로 운영 중이므로 그대로 복제.

| 이름 | 용도 |
|------|------|
| `tls-wildcard-shinsegae-ai-2026` | ingress 와일드카드 TLS |
| `asia-gcr-global-secret` | Artifact Registry image pull (`asia-northeast3-docker.pkg.dev`) |

```bash
for s in tls-wildcard-shinsegae-ai-2026 asia-gcr-global-secret; do
  kubectl --context onprem-prd -n datafabric-platform get secret "$s" -o yaml \
    | grep -v '^\s*namespace:' \
    | sed 's/^\(metadata:\)$/\1\n  namespace: datafabric-alert/' \
    | kubectl --context onprem-prd apply -f -
done
```

> 시크릿 만료/갱신 시 동일 절차 반복. 자동 동기화는 후속 작업(reflector 등) TODO.

## 일반 배포

GitHub release 가 publish 되면 GH Actions 가 이미지를 Artifact Registry 로 push 한다. 사내 단말에서:

```bash
./scripts/deploy.sh 0.1.0
```

원하면 옵션 추가:

```bash
# 변경 미리 보기 (실제 적용 안 함)
./scripts/deploy.sh 0.1.0 --dry-run

# replicas 조정
./scripts/deploy.sh 0.1.0 --set replicaCount=2

# values 파일 오버라이드
./scripts/deploy.sh 0.1.0 -f overrides.yaml
```

`latest` 태그를 쓰는 것도 가능하지만, 운영에서는 항상 명시적 버전을 권장.

## 롤백

```bash
helm --kube-context onprem-prd -n datafabric-alert rollback dfm-bq-load-alerter
```

## 관측 명령

```bash
kubectl --context onprem-prd -n datafabric-alert get all
kubectl --context onprem-prd -n datafabric-alert logs deploy/dfm-bq-load-alerter -f
kubectl --context onprem-prd -n datafabric-alert describe ingress dfm-bq-load-alerter
```

## 환경 변수 / 오버라이드

`deploy.sh` 가 사용하는 기본값 (env 로 변경 가능):

| 변수 | 기본값 |
|------|--------|
| `KUBE_CONTEXT` | `onprem-prd` |
| `NAMESPACE` | `datafabric-alert` |
| `RELEASE_NAME` | `dfm-bq-load-alerter` |
| `AR_HOST` | `asia-northeast3-docker.pkg.dev` |
| `AR_PROJECT` | `emart-datafabric` |
| `AR_REPO` | `container-registry` |

## TODO

- [ ] 사내 셀프-호스티드 러너 또는 ArgoCD 도입으로 helm 단계 재자동화
- [ ] `scripts/deploy.sh` 의 dry-run 출력 형식 표준화
- [ ] 배포 직후 헬스 체크(curl `/healthz`) 추가
