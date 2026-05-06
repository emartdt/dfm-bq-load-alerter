# dfm-bq-load-alerter

DFM(datafabric-manager) 시스템에서 BigQuery 적재(load) 작업 상태를 모니터링하고 이상 상황을 알리는 컴포넌트.

> ℹ️ **초기 스캐폴딩 단계입니다.** 본 README는 1차 초기화로 작성되었으며, 실제 동작·실행 방법·의존성·배포 절차는 코드가 추가되는 시점에 보강합니다.

## 목적 (예정)

- BigQuery load job(스트리밍/배치 적재)의 실패·지연·이상 패턴 감지
- 장애 알림 채널(예: Slack, 사내 알림 시스템 등)로 통보
- DFM 운영 자동화 체계(`datafabric-script`, `datafabric-dag-plugins`)와의 연동

## 위치

- DFM 문서 허브: [`dfm-doc`](https://github.com/emartdt/dfm-doc) — 이 리포지토리는 `repos/dfm-bq-load-alerter/` 경로에 git submodule로 마운트됩니다.
- 카테고리·역할은 [`architecture/repos-overview.md`](https://github.com/emartdt/dfm-doc/blob/main/architecture/repos-overview.md)에서 관리됩니다.

## TODO

- [ ] 모니터링 대상 BigQuery 프로젝트/데이터셋 범위 정의
- [ ] 알림 트리거 조건(실패율, 지연 임계치 등) 명세
- [ ] 배포 형태 결정 (Cloud Run / Cloud Functions / Kubernetes CronJob 등)
- [ ] 시크릿 관리 방식 (Vault, GCP Secret Manager 등) 결정
- [ ] DFM 문서(`architecture/`, `runbook/`) 작성

## 라이선스 / 소유

본 리포지토리는 DFM 운영 도구의 일부로, 사내 운영 컴포넌트 정책을 따릅니다.
