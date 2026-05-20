## 아키텍처
- backend: python3.13 + fastapi
- frontend: reactJS
- database: cloudSQL(pgsql)
- auth: Keycloak

## 요구사항 정리

### 관리 대상 테이블 타입
- daily
- monthly

### 테이블 상태 판별 논리식

- 오늘 일자로 적재 완료 되어 있을 경우
    - 현재 row count가 0일 경우 → 실패
    - row count가 0이 아닌 경우
        - 이전 배치 스냅샷이 있는 경우 (증감 비교 대상이 있는 경우)
            - 증감률이 역치 이상: 실패
            - 증감률이 역치 미만: 성공
        - 이전 배치 스냅샷이 없는 경우
            - 성공
- 오늘 일자로 적재 완료 안된경우
    - 현재 시간 < 배치예상시간 + 버퍼
        - SKIP
    - 배치예상시간 + 버퍼 < 현재 시간
        - 실패

### 점검 상태 값
- ok
- fail
- skip