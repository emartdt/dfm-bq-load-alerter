# 커스텀 row_count 쿼리 템플레이팅 설계

작성일: 2026-05-18
대상 영역: `tables.condition_query` (BigQuery 사용자 정의 row_count SQL)

## 1. 배경

`tables.condition_query` 는 사용자가 직접 작성한 SELECT/WITH SQL 로 BigQuery `__TABLES__.row_count` 를 대체해 row_count 를 산출하는 기능이다. 일자 컬럼을 가진 테이블에서 "오늘 들어온 행 수만 카운트" 와 같은 요구가 있으나, 현재는 SQL 안에 날짜가 하드코딩되어야 해 운영자가 매일 쿼리를 갱신해야 한다.

본 변경은 condition_query 에 **Jinja2 기반 일자 변수 치환** 기능을 도입해, 동일 SQL 이 매 실행 시점의 KST 날짜를 기반으로 다른 필터로 실행되도록 만든다.

## 2. 목표 및 비목표

### 목표
- `tables.condition_query` 에 Jinja2 템플릿 문법(`{{ ... }}`, `{% ... %}`) 사용 허용
- KST(Asia/Seoul) 기준 일자 관련 변수/헬퍼를 안전한 컨텍스트로 노출
- 저장 시점 사전 검증, 실행 시점 안전한 렌더링 및 기존 보안 검증과의 결합
- 운영자가 UI 에서 "오늘 기준" 렌더 결과를 미리 확인할 수 있는 경로 제공
- 템플릿 문법을 쓰지 않는 기존 SQL 의 동작과 결과는 동일 (하위 호환)

### 비목표
- DB 스키마 변경. `condition_query` 컬럼은 그대로 사용한다.
- 시간 단위/주 단위/사용자 정의 함수 등 변수 셋 확장 (필요 시 후속)
- 멀티 행/멀티 컬럼 결과 허용. 기존 "1행 1정수 컬럼" 계약은 유지한다.
- 알림 본문/이메일 템플릿과의 변수 공유

## 3. 사용자 시나리오

운영자는 다음과 같은 SQL 을 한 번 등록한다.

```sql
SELECT COUNT(*) FROM `proj.ds.t`
WHERE DATE(load_dt) = DATE('{{ today }}')
```

이후 매일 실행 시점에 `{{ today }}` 는 KST 기준 그날의 `YYYY-MM-DD` 로 자동 치환된다. 별도 운영 작업 없이 동일 SQL 이 매일 다른 조건으로 row_count 를 산출한다.

추가 예시:
- 전일 파티션: `WHERE _PARTITIONDATE = DATE('{{ yesterday }}')`
- 1주일 누적: `WHERE DATE(load_dt) >= DATE('{{ days_ago(7) }}')`
- 포맷 변환: `WHERE partition_id = '{{ today.strftime("%Y%m%d") }}'`

## 4. 컴포넌트 및 변경 범위

### 4.1 새 모듈: `backend/src/dfm_bq_load_alerter/bq/templating.py`
- `build_query_context(now_kst: datetime) -> dict`: 변수 컨텍스트 생성
- `render_condition_query(template: str, *, now_kst: datetime | None = None) -> str`: SandboxedEnvironment 로 렌더, 실패 시 `ConditionQueryError` 발생
- 의존 노출 변수:
  - `today` (`date`, KST)
  - `yesterday` (`date`, KST)
  - `now` (`datetime`, KST)
  - `days_ago(n: int) -> date`
  - `months_ago(n: int) -> date`
- 모듈 내부에서 `jinja2.sandbox.SandboxedEnvironment(autoescape=False)` 인스턴스를 단일 생성 후 재사용

### 4.2 `backend/src/dfm_bq_load_alerter/bq/metadata.py`
- `run_condition_query` 진입 시 가장 먼저 `render_condition_query(query)` 호출
- 렌더 결과를 기존 `_validate_condition_query` 에 전달
- 렌더 실패는 `ConditionQueryError` 로 일관 처리 (호출부 변경 없음)
- `__TABLES__` 경로 등 기존 동작은 변동 없음

### 4.3 신규 API: 쿼리 미리보기
- 경로: `POST /api/tables/condition-query/preview`
- 요청 바디: `{ "query": "..." }`
- 동작:
  1. `render_condition_query(query)` 로 KST 오늘 기준 렌더
  2. `_validate_condition_query` 통과 여부 확인
  3. BigQuery dry-run 으로 처리 바이트 추정 (`condition_query_max_bytes` 와 비교)
- 응답:
  ```json
  {
    "rendered_sql": "...",
    "total_bytes_processed": 12345,
    "max_bytes": 104857600,
    "exceeds_budget": false
  }
  ```
- 실패 시: 4xx + `{ "error": "...메시지..." }`
- 권한: 기존 테이블 편집 권한과 동일

### 4.4 저장 시점 검증
- 테이블 생성/수정 API(`POST/PATCH /api/tables/...`) 에서 `condition_query` 가 비어있지 않은 경우:
  - `render_condition_query` 로 오늘 기준 1회 렌더
  - 렌더 결과에 `_validate_condition_query` 적용
  - 실패 시 422 응답
- dry-run 은 저장 시 호출하지 않음 (네트워크 비용/지연 회피, 미리보기 버튼에서 명시적으로 수행)

### 4.5 프론트엔드 `frontend/src/pages/Tables.tsx`
- `condition_query` textarea 하단에 다음 변경:
  - `field-hint` 보강: 사용 가능한 변수 (`{{ today }}`, `{{ yesterday }}`, `{{ days_ago(n) }}`, `{{ months_ago(n) }}`, `{{ now }}`) 및 KST 기준 안내
  - placeholder 를 템플릿 예시로 교체
  - "렌더 미리보기" 버튼 추가 → 클릭 시 `/api/tables/condition-query/preview` 호출 → 결과(렌더된 SQL, 처리 바이트, 예산 초과 경고)를 textarea 바로 아래 인라인 영역(`<pre>` 블록 + 메타 정보)에 표시
- 신규 API 호출은 `frontend/src/api/tables.ts` 에 함수 추가

## 5. 데이터 흐름

```
[운영자 입력 (raw template)]
        │
        ▼
[저장 API: PATCH /api/tables/{id}]
        ├── render_condition_query(today) ─┐
        │                                  ▼
        │                          [_validate_condition_query]
        │                                  │
        │ (모두 통과)                       │
        ▼                                  │
[DB: tables.condition_query (raw template 저장)]
                                           
[스케줄러 실행 시점]
        │
        ▼
[checks.runner → fetch_metadata(row_count_query=...)]
        │
        ▼
[run_condition_query]
        ├── render_condition_query(now_kst)
        ├── _validate_condition_query (렌더 결과 대상)
        ├── BigQuery dry-run (byte budget)
        └── BigQuery execute → scalar int
```

## 6. 보안 고려사항

- **샌드박스**: Jinja2 `SandboxedEnvironment` 사용으로 임의 속성 접근/호출 차단
- **변수 타입**: 노출 변수는 모두 `date` 또는 `datetime`. 사용자 입력 문자열을 변수로 노출하지 않으므로 SQL 인젝션 표면 없음
- **금지 키워드**: 렌더 *결과* 에 대해 기존 `_validate_condition_query` 적용 → 템플릿으로 우회 시도 시 차단
- **autoescape**: SQL 용도이므로 비활성. 단, 변수 값에는 사용자 입력이 섞이지 않으므로 안전
- **렌더 시간 한도**: Jinja2 의 무한 루프 가능성은 SandboxedEnvironment 가 제한하지 않으므로, 템플릿 길이 상한(예: 10KB) 을 저장 API 에서 강제. 실행 시점에도 동일 한도 재확인

## 7. 오류 처리

| 상황 | 처리 |
|------|------|
| Jinja2 `TemplateSyntaxError` | `ConditionQueryError("템플릿 문법 오류: ...")` |
| 존재하지 않는 변수 참조 | `ConditionQueryError("정의되지 않은 변수: ...")` (StrictUndefined) |
| 렌더 결과가 빈 문자열 | 기존 검증에서 "비어 있습니다" 로 잡힘 |
| 렌더 결과에 forbidden 키워드 | 기존 검증에서 차단 |
| `days_ago(-1)` 등 비정상 인수 | `ConditionQueryError("days_ago 인수는 0 이상의 정수여야 합니다")` |
| 템플릿 길이 한도 초과 | 저장 API 422 / 실행 시 `ConditionQueryError` |

실행 시점 실패는 기존 알림 파이프와 동일하게 처리되어 `condition_query` 실패 사유로 기록된다.

## 8. 테스트 계획

`backend/tests/test_bq_metadata.py` 및 신규 `backend/tests/test_templating.py`:

- 단위 테스트 (`templating.py`):
  - `today/yesterday/now` 가 KST 기준인지
  - `days_ago(7)`, `months_ago(1)` 결과 검증
  - `strftime` 필터 동작
  - 미정의 변수 참조 시 예외
  - 문법 오류 시 예외
  - 템플릿 미사용 (raw SQL) 시 입력 그대로 반환
  - SandboxedEnvironment 가 `__class__` 등 위험 속성 접근 차단

- 통합 테스트 (`test_bq_metadata.py`):
  - 템플릿 + 기존 validate/dry-run/execute 통합 흐름
  - 템플릿 렌더 후 forbidden 키워드 (`DROP` 등) 발생 시 차단
  - 하위 호환: 기존 평문 SQL 테스트 케이스가 변경 없이 통과

- 프론트엔드:
  - 미리보기 API 호출/표시는 수동 검증 (UI 테스트 인프라 부재)

## 9. 롤아웃

- DB 마이그레이션 없음 → 즉시 배포 가능
- 기존 등록된 condition_query 는 `{{ }}` 미사용이므로 동작 변동 없음 (회귀 위험 낮음)
- 출시 후 운영 가이드(`docs/`) 에 사용 예 1페이지 추가

## 10. 향후 확장

- 시각 단위 변수 (`hour`, `now_minus_minutes(n)`)
- 정책별 타임존 변경 (현재 KST 고정)
- 알림 본문 템플릿과 변수 셋 통일
