# 이메일 전송 timeout + job deadline 설계

날짜: 2026-07-06
브랜치: `charge`

## 배경 / 문제

주기 job(check/report)이 알람을 전송하는 구조에서, 한 job 인스턴스가 끝나지
않으면 APScheduler의 `max_instances=1` 때문에 이후 모든 firing이 조용히
skip되어 알람 기능이 영구 마비된다.

조사 결과 (aiosmtplib 3.0.0 소스 확인):

- `aiosmtplib.send()`에는 **명령당 60초** 기본 timeout(`DEFAULT_TIMEOUT = 60`)이
  있어 단일 명령이 무한 대기하지는 않는다. 그러나 전송 **전체**에 대한 상한이
  없어 최악의 경우 `60초 × (약 9개 명령 + 수신자 수)`까지 늘어질 수 있다.
- `smtp_local_hostname` 미설정 시 aiosmtplib이 `socket.getfqdn()`을 **동기**
  호출한다(라이브러리 문서에 명시된 이벤트 루프 블로킹). DNS 장애 시 job뿐
  아니라 FastAPI/health check까지 프로세스 전체가 멈춘다.
- `run_checks`(BigQuery)나 DB 쿼리가 멈추는 경우에 대한 상한도 없다.

## 결정 사항 (사용자 확정)

| 항목 | 결정 |
| --- | --- |
| job 전체 deadline | 600초 (10분, check 간격 20분의 절반), 설정으로 조정 가능 |
| deadline 초과 시 기록 | ERROR 로그 + 새 세션으로 `alert_events`에 failed 행 기록 |
| `max_instances` | 1 → 2 (deadline이 1차 방어, 이건 2차 방어) |
| 접근 방식 | A안: job 래퍼(asyncio.timeout) + 이메일 전송 자체 timeout (계층별 방어) |
| Channel enum | **마이그레이션 없음** — 기존 `channel=email` 재사용, `payload_summary`로 구분 |

## 변경 내용

### 1. `settings.py` — 신규 설정 3개 (`DFM_ALERT_` prefix)

```python
smtp_command_timeout_seconds: float = Field(default=10.0, ge=1.0, le=300.0)
smtp_total_timeout_seconds: float = Field(default=60.0, ge=5.0, le=600.0)
job_timeout_seconds: int = Field(default=600, ge=30, le=3600)
```

### 2. `notifier/email.py`

- `aiosmtplib.send(..., timeout=settings.smtp_command_timeout_seconds)` 명시
  (Teams의 10초 timeout과 일관).
- 전송 전체를 `asyncio.timeout(settings.smtp_total_timeout_seconds)`로 래핑.
  초과 시 `TimeoutError`를 **그대로 전파** — dispatcher의 기존
  `except Exception` 블록이 `alert_events`에 failed로 기록하고 Teams 전송은
  계속 진행된다 (기존 오류 처리 경로 재사용, dispatcher 변경 없음).
- `local_hostname`: `settings.smtp_local_hostname`이 비어 있으면
  `socket.gethostname()`을 전달해 aiosmtplib 내부의 `socket.getfqdn()` 동기
  호출(이벤트 루프 블로킹)을 항상 우회한다.

### 3. `scheduler/jobs.py` — job deadline 래퍼

```python
async def _run_with_deadline(
    job_id: str,
    body: Coroutine,           # job 본문
    trigger_kind: TriggerKind | None,  # None이면 DB 기록 생략 (cleanup)
) -> None: ...
```

- `asyncio.timeout(settings.job_timeout_seconds)`로 본문 실행.
- `TimeoutError` 시:
  1. ERROR 로그 (`job deadline exceeded`).
  2. `trigger_kind`가 있으면 **새 DB 세션**을 열어 `alert_events`에 기록:
     `channel=email`(enum 재사용), `status=failed`,
     `payload_summary="job timeout · {job_id}"`,
     `error="job deadline exceeded ({N}s)"`.
  3. 기록 자체가 실패하면 로그만 남기고 삼킨다 — 래퍼가 job을 더 죽게
     만들면 안 된다.
- 적용: `check_at`(check), `report_745`(report), `cleanup_history`(기록 없음).
- 기존 job 함수 시그니처 유지 — 본문을 내부 코루틴으로 분리하고 래퍼로 감싸
  스케줄러 등록 코드(`setup.py`)는 등록 로직 변경 없음.
- timeout으로 중단된 회차의 스냅샷은 커밋되지 않는다(세션 롤백). 다음 cron이
  다시 체크하므로 부분 커밋보다 안전하다.

### 4. `scheduler/setup.py`

- `job_defaults`의 `max_instances: 1 → 2`.
- 주석으로 이유 명시: deadline 버그/회귀 시에도 다음 firing이 skip되지 않게
  하는 2차 방어. `coalesce=True` 유지.

## 오류 처리 요약

| 시나리오 | 동작 |
| --- | --- |
| SMTP 명령 1개가 10초 초과 | aiosmtplib `SMTPTimeoutError` → dispatcher가 failed 기록, Teams 계속 |
| 이메일 전송 전체 60초 초과 | `TimeoutError` → 동일 |
| job 전체 10분 초과 | 본문 취소 → 로그 + 새 세션으로 failed 이벤트 기록 → job 정상 종료 |
| timeout 이벤트 DB 기록 실패 | 로그만 남기고 종료 |
| DNS 장애 + local_hostname 미설정 | `gethostname()` 사용으로 이벤트 루프 블로킹 자체가 발생하지 않음 |

## 테스트 계획 (TDD — 실패 테스트 먼저)

- `test_email.py`
  - 배너 후 무응답인 fake SMTP 서버 → `smtp_total_timeout_seconds`(테스트에선
    작은 값) 내 `TimeoutError` 발생.
  - `aiosmtplib.send` 호출 kwargs에 `timeout`이 전달되는지 검증.
  - `smtp_local_hostname` 미설정 시 `local_hostname=socket.gethostname()`이
    전달되는지 검증.
- `test_scheduler_jobs.py`
  - `run_checks`를 지연시키는 monkeypatch + `job_timeout_seconds`를 작게 설정
    → job이 예외를 올리지 않고 종료하고, `alert_events`에
    `status=failed` / `payload_summary="job timeout · …"` 행이 남는지 검증.
  - cleanup job timeout 시 DB 기록 없이 로그만 남는지 검증.
- `test_scheduler_setup.py`
  - `job_defaults["max_instances"] == 2` 검증.

## 스코프 제외 (YAGNI)

- Channel enum `system` 값 추가 및 마이그레이션 — 사용자 결정으로 제외.
- Teams 운영 알림(시스템 장애 카드) 발송.
- BigQuery 클라이언트 자체의 세분화된 timeout 튜닝 — job deadline이 상한을
  보장하므로 이번 스코프에서 다루지 않음.
