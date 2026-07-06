# 이메일 전송 timeout + job deadline 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 이메일 전송과 스케줄러 job에 실행 시간 상한을 부여해, 한 번의 무한/장기 대기가 알람 기능 전체를 영구 마비시키는 구조를 제거한다.

**Architecture:** (1) `send_email`에 aiosmtplib 명령당 timeout(10s)과 전송 전체 상한(60s, `asyncio.timeout`)을 명시하고 `local_hostname`을 항상 전달해 이벤트 루프 블로킹(`socket.getfqdn`)을 우회한다. (2) 각 job 본문을 `asyncio.timeout(600s)` 래퍼로 감싸고, 초과 시 새 DB 세션으로 `alert_events`에 failed 이벤트를 기록한다(기존 `channel=email` enum 재사용 — 마이그레이션 없음). (3) APScheduler `max_instances`를 1→2로 올려 2차 방어를 둔다.

**Tech Stack:** Python 3.13, FastAPI, APScheduler 3.10, aiosmtplib 3.0, SQLAlchemy 2.0 async, pytest + pytest-asyncio(명시적 `@pytest.mark.asyncio` 마커 사용)

**Spec:** `docs/superpowers/specs/2026-07-06-job-timeout-design.md`

## Global Constraints

- 작업 브랜치: `charge` (이미 생성됨, main에서 분기)
- 모든 명령은 `/Users/224749/dt/src/dfm-bq-load-alerter/backend` 디렉토리에서 실행
- 테스트 실행: `.venv/bin/pytest` (Task 0에서 생성; `uv`는 이 머신에 없음)
- 의존성 추가/변경 금지 — aiosmtplib==3.0 그대로, timeout은 호출부에서 지정
- DB 마이그레이션 금지 (사용자 결정) — 기존 `Channel.email` enum 값 재사용
- ruff line-length 100, 테스트 docstring/주석은 한국어 우선 (CLAUDE.md 정책)
- 커밋 메시지는 저장소 관례를 따름: `type(scope): 한국어 설명` + `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`
- 기존 테스트를 깨뜨리면 안 됨. 단, `tests/test_email.py::test_send_email_invokes_aiosmtplib_with_starttls`는 동작 변경(local_hostname 항상 전달)에 맞춰 **수정 대상**이다 — Task 2에 포함

---

### Task 0: 개발 환경 준비 + 베이스라인 확인

**Files:** 없음 (환경만)

**Interfaces:**
- Produces: `backend/.venv` — 이후 모든 Task가 `.venv/bin/pytest`를 사용

- [ ] **Step 1: venv 생성 및 의존성 설치**

```bash
cd /Users/224749/dt/src/dfm-bq-load-alerter/backend
/usr/local/bin/python3.13 -m venv .venv
.venv/bin/pip install -q -e '.[dev]'
```

Expected: 오류 없이 설치 완료 (`pip list`에 aiosmtplib 3.0.0, pytest 8.3.x 표시)

- [ ] **Step 2: 이번 변경과 관련된 테스트 파일의 베이스라인 통과 확인**

```bash
.venv/bin/pytest tests/test_email.py tests/test_scheduler_jobs.py tests/test_scheduler_setup.py tests/test_settings.py -q
```

Expected: 전부 PASS. (PostgreSQL 바이너리가 필요한 것은 `test_alembic.py` 등 다른 파일이므로 여기서는 무관. 만약 여기서 실패하는 테스트가 있으면 **작업을 멈추고 사용자에게 보고** — 우리 변경 전부터 깨져 있는 것.)

- [ ] **Step 3: `.venv`가 gitignore에 있는지 확인**

```bash
git check-ignore .venv && echo ignored
```

Expected: `ignored` 출력. (아니면 커밋 시 `backend/.venv`를 절대 add하지 않도록 주의하고, `.gitignore`에 `backend/.venv/` 한 줄을 추가해 Task 1 커밋에 포함)

---

### Task 1: settings에 timeout 설정 3개 추가

**Files:**
- Modify: `src/dfm_bq_load_alerter/settings.py` (`teams_chunk_delay_seconds` 필드 바로 아래)
- Test: `tests/test_settings.py`

**Interfaces:**
- Produces: `settings.smtp_command_timeout_seconds: float` (기본 10.0), `settings.smtp_total_timeout_seconds: float` (기본 60.0), `settings.job_timeout_seconds: int` (기본 600) — Task 2, 3이 사용

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_settings.py` 파일 끝에 추가:

```python
def test_timeout_기본값() -> None:
    """SMTP/job timeout 설정 기본값 — spec 2026-07-06-job-timeout-design.md."""
    mod = _reload_settings()
    assert mod.settings.smtp_command_timeout_seconds == 10.0
    assert mod.settings.smtp_total_timeout_seconds == 60.0
    assert mod.settings.job_timeout_seconds == 600
```

- [ ] **Step 2: 실패 확인**

```bash
.venv/bin/pytest tests/test_settings.py::test_timeout_기본값 -v
```

Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'smtp_command_timeout_seconds'`

- [ ] **Step 3: 구현**

`src/dfm_bq_load_alerter/settings.py`의 `teams_chunk_delay_seconds` 필드 정의 바로 아래에 추가:

```python
    # 이메일/job 실행 시간 상한. 무한 대기로 스케줄러 슬롯이 영구 점유되는
    # 것을 막는다 (spec: 2026-07-06-job-timeout-design.md).
    smtp_command_timeout_seconds: float = Field(default=10.0, ge=1.0, le=300.0)
    smtp_total_timeout_seconds: float = Field(default=60.0, ge=5.0, le=600.0)
    job_timeout_seconds: int = Field(default=600, ge=30, le=3600)
```

- [ ] **Step 4: 통과 확인**

```bash
.venv/bin/pytest tests/test_settings.py -q
```

Expected: 전부 PASS

- [ ] **Step 5: 커밋**

```bash
git add src/dfm_bq_load_alerter/settings.py tests/test_settings.py
git commit -m "feat(settings): SMTP/job timeout 설정 추가

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: send_email에 명령당 timeout + 전체 상한 + local_hostname 상시 전달

**Files:**
- Modify: `src/dfm_bq_load_alerter/notifier/email.py`
- Test: `tests/test_email.py` (기존 테스트 1개 수정 + 신규 2개)

**Interfaces:**
- Consumes: Task 1의 `settings.smtp_command_timeout_seconds`, `settings.smtp_total_timeout_seconds`
- Produces: `send_email(*, to, subject, html)` — 시그니처 불변. 전송이 `smtp_total_timeout_seconds`를 넘으면 `TimeoutError` 전파(내장 예외). dispatcher는 이미 `except Exception`으로 잡아 failed 이벤트를 기록하므로 **dispatcher 변경 없음**

- [ ] **Step 1: 기존 테스트 수정 + 신규 실패 테스트 2개 작성**

`tests/test_email.py` — 먼저 파일 상단 import에 추가:

```python
import asyncio
import socket
```

`test_send_email_invokes_aiosmtplib_with_starttls`의 마지막 두 줄(주석 포함)을 다음으로 교체:

```python
    # local_hostname 미설정 시에도 항상 전달한다 — aiosmtplib이 내부에서
    # socket.getfqdn()을 동기 호출해 이벤트 루프를 블록하는 경로를 차단.
    assert kwargs["local_hostname"] == socket.gethostname()
    assert kwargs["timeout"] == email_module.settings.smtp_command_timeout_seconds
```

파일 끝에 신규 테스트 2개 추가:

```python
@pytest.mark.asyncio
async def test_send_email_전송_전체가_상한을_넘으면_TimeoutError(monkeypatch) -> None:
    """aiosmtplib의 명령당 timeout으로도 못 막는 누적 지연을 전체 상한이 끊는다."""
    monkeypatch.setattr(email_module.settings, "smtp_host", "smtp.example.com", raising=False)
    monkeypatch.setattr(email_module.settings, "smtp_from_addr", "alerts@dfm.local", raising=False)
    monkeypatch.setattr(
        email_module.settings, "smtp_total_timeout_seconds", 0.05, raising=False
    )

    async def _hangs_forever(*args, **kwargs):
        await asyncio.sleep(30)

    monkeypatch.setattr(email_module.aiosmtplib, "send", _hangs_forever)

    with pytest.raises(TimeoutError):
        await send_email(to=["a@example.com"], subject="s", html="<b>h</b>")


@pytest.mark.asyncio
async def test_send_email_명령당_timeout을_aiosmtplib에_전달(monkeypatch) -> None:
    monkeypatch.setattr(email_module.settings, "smtp_host", "smtp.example.com", raising=False)
    monkeypatch.setattr(email_module.settings, "smtp_from_addr", "alerts@dfm.local", raising=False)
    monkeypatch.setattr(
        email_module.settings, "smtp_command_timeout_seconds", 7.5, raising=False
    )

    sent = AsyncMock()
    monkeypatch.setattr(email_module.aiosmtplib, "send", sent)

    await send_email(to=["a@example.com"], subject="s", html="<b>h</b>")

    assert sent.await_args.kwargs["timeout"] == 7.5
```

- [ ] **Step 2: 실패 확인**

```bash
.venv/bin/pytest tests/test_email.py -v
```

Expected: 신규 2개 FAIL (`KeyError: 'timeout'` / TimeoutError 미발생), 수정한 starttls 테스트 FAIL (`KeyError: 'local_hostname'`). 나머지 기존 테스트는 PASS 유지.

- [ ] **Step 3: 구현**

`src/dfm_bq_load_alerter/notifier/email.py` 수정.

import 블록에 추가 (`import logging` 위/아래 알파벳순):

```python
import asyncio
import socket
```

`send_kwargs` 정의(38–42행)를 다음으로 교체:

```python
    send_kwargs: dict[str, object] = {
        "hostname": settings.smtp_host,
        "port": settings.smtp_port,
        "start_tls": settings.smtp_use_starttls,
        # aiosmtplib 기본 timeout(60s)은 '명령당'이라 전송 전체는 무한정
        # 늘어질 수 있다. 명령당 상한을 짧게 명시한다.
        "timeout": settings.smtp_command_timeout_seconds,
        # local_hostname 미지정 시 aiosmtplib이 socket.getfqdn()을 동기
        # 호출해 DNS 장애 시 이벤트 루프 전체가 멈춘다. 항상 명시한다.
        "local_hostname": settings.smtp_local_hostname or socket.gethostname(),
    }
```

기존의 `if settings.smtp_local_hostname:` 두 줄(50–51행)은 **삭제** (위에서 항상 설정하므로).

마지막 줄 `await aiosmtplib.send(message, **send_kwargs)`를 다음으로 교체:

```python
    # 명령당 timeout이 있어도 (명령 수 × timeout)만큼 누적될 수 있으므로
    # 전송 1회 전체에 상한을 둔다. 초과 시 TimeoutError가 전파되고
    # dispatcher가 failed 이벤트로 기록한다.
    async with asyncio.timeout(settings.smtp_total_timeout_seconds):
        await aiosmtplib.send(message, **send_kwargs)
```

log.info의 `settings.smtp_local_hostname or "(default)"` 인자는 `send_kwargs["local_hostname"]`로 교체.

- [ ] **Step 4: 통과 확인**

```bash
.venv/bin/pytest tests/test_email.py tests/test_dispatcher.py -q
```

Expected: 전부 PASS (dispatcher 테스트로 예외 경로 회귀 확인)

- [ ] **Step 5: 커밋**

```bash
git add src/dfm_bq_load_alerter/notifier/email.py tests/test_email.py
git commit -m "fix(email): 전송 timeout 명시 + local_hostname 상시 전달로 이벤트 루프 블로킹 제거

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: 스케줄러 job에 전체 deadline 래퍼 적용

**Files:**
- Modify: `src/dfm_bq_load_alerter/scheduler/jobs.py`
- Test: `tests/test_scheduler_jobs.py`

**Interfaces:**
- Consumes: Task 1의 `settings.job_timeout_seconds`
- Produces:
  - `check_at(job_id: str, moment: time) -> None` / `report_745(moment: time = time(7, 45)) -> None` — 시그니처 불변 (setup.py의 등록 코드 무변경)
  - `cleanup_history(now: datetime | None = None) -> dict[str, int | str] | None` — timeout 시 `None` 반환 (기존 호출자는 스케줄러뿐이라 반환값 미사용)
  - 내부: `_run_with_deadline(job_id: str, body: Coroutine[Any, Any, T], trigger_kind: TriggerKind | None) -> T | None`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_scheduler_jobs.py` — 상단 import에 추가:

```python
import asyncio

from dfm_bq_load_alerter.db.models import (
    AlertEvent,
    Channel,
    EventStatus,
    TriggerKind,
)
```

파일 끝에 추가:

```python
def _make_timeout_session():
    """deadline 초과 기록용 세션 mock — add는 동기 메서드이므로 MagicMock."""
    fake_session = AsyncMock()
    fake_session.add = MagicMock()
    fake_session.commit = AsyncMock()
    fake_session.__aenter__ = AsyncMock(return_value=fake_session)
    fake_session.__aexit__ = AsyncMock(return_value=None)
    return fake_session


@pytest.mark.asyncio
async def test_check_at_deadline_초과시_failed_이벤트_기록(monkeypatch) -> None:
    """job이 job_timeout_seconds를 넘기면 예외 없이 종료하고 alert_events에 남긴다."""
    fake_session = _make_timeout_session()
    monkeypatch.setattr(
        "dfm_bq_load_alerter.scheduler.jobs.sessionmaker_factory",
        MagicMock(return_value=MagicMock(return_value=fake_session)),
    )
    monkeypatch.setattr(
        "dfm_bq_load_alerter.scheduler.jobs.settings.job_timeout_seconds",
        0.05,
        raising=False,
    )

    async def slow_run_checks(*args, **kwargs):
        await asyncio.sleep(30)

    monkeypatch.setattr(
        "dfm_bq_load_alerter.scheduler.jobs.run_checks", slow_run_checks
    )

    # TimeoutError가 밖으로 새면 안 된다 (APScheduler 슬롯 보호가 목적)
    await check_at("check-0800", time(8, 0))

    fake_session.add.assert_called_once()
    event = fake_session.add.call_args.args[0]
    assert isinstance(event, AlertEvent)
    assert event.trigger_kind == TriggerKind.check
    assert event.channel == Channel.email
    assert event.status == EventStatus.failed
    assert event.payload_summary == "job timeout · check-0800"
    assert "deadline exceeded" in event.error
    fake_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_report_745_deadline_초과시_report_트리거로_기록(monkeypatch) -> None:
    fake_session = _make_timeout_session()
    monkeypatch.setattr(
        "dfm_bq_load_alerter.scheduler.jobs.sessionmaker_factory",
        MagicMock(return_value=MagicMock(return_value=fake_session)),
    )
    monkeypatch.setattr(
        "dfm_bq_load_alerter.scheduler.jobs.settings.job_timeout_seconds",
        0.05,
        raising=False,
    )

    async def slow_run_checks(*args, **kwargs):
        await asyncio.sleep(30)

    monkeypatch.setattr(
        "dfm_bq_load_alerter.scheduler.jobs.run_checks", slow_run_checks
    )

    await report_745()

    event = fake_session.add.call_args.args[0]
    assert event.trigger_kind == TriggerKind.report
    assert event.payload_summary == "job timeout · report-0745"


@pytest.mark.asyncio
async def test_cleanup_history_deadline_초과시_DB기록_없이_None_반환(monkeypatch) -> None:
    """cleanup은 알람과 무관하므로 timeout 시 로그만 남긴다 (spec 결정)."""
    fake_session = _make_timeout_session()

    async def slow_get(*args, **kwargs):
        await asyncio.sleep(30)

    fake_session.get = slow_get
    monkeypatch.setattr(
        "dfm_bq_load_alerter.scheduler.jobs.sessionmaker_factory",
        MagicMock(return_value=MagicMock(return_value=fake_session)),
    )
    monkeypatch.setattr(
        "dfm_bq_load_alerter.scheduler.jobs.settings.job_timeout_seconds",
        0.05,
        raising=False,
    )

    result = await cleanup_history(now=datetime(2026, 5, 15, 3, 0, tzinfo=KST))

    assert result is None
    fake_session.add.assert_not_called()


@pytest.mark.asyncio
async def test_deadline_이벤트_기록_실패해도_예외를_삼킨다(monkeypatch, caplog) -> None:
    """timeout 기록용 세션 생성 자체가 실패해도 job은 조용히 끝나야 한다."""
    call_count = 0
    fake_session = _make_timeout_session()

    def failing_factory():
        nonlocal call_count
        call_count += 1
        if call_count >= 2:  # 두 번째(기록용) 세션 생성에서 실패
            raise RuntimeError("db down")
        return fake_session

    monkeypatch.setattr(
        "dfm_bq_load_alerter.scheduler.jobs.sessionmaker_factory",
        MagicMock(return_value=failing_factory),
    )
    monkeypatch.setattr(
        "dfm_bq_load_alerter.scheduler.jobs.settings.job_timeout_seconds",
        0.05,
        raising=False,
    )

    async def slow_run_checks(*args, **kwargs):
        await asyncio.sleep(30)

    monkeypatch.setattr(
        "dfm_bq_load_alerter.scheduler.jobs.run_checks", slow_run_checks
    )

    await check_at("check-0800", time(8, 0))  # 예외가 나오면 테스트 실패

    assert "failed to record job-timeout event" in caplog.text
```

- [ ] **Step 2: 실패 확인**

```bash
.venv/bin/pytest tests/test_scheduler_jobs.py -v
```

Expected: 신규 4개가 FAIL (TimeoutError가 그대로 전파되거나 30초 sleep 대신 즉시 실패). 기존 테스트는 PASS 유지.
주의: 신규 테스트가 30초씩 걸리며 "통과"처럼 보이면 안 된다 — deadline 미구현 상태에서는 `asyncio.sleep(30)`을 기다리므로, 빠르게 FAIL하지 않고 오래 걸리면 Ctrl-C 없이 완주하지 말고 구현으로 넘어간다 (`--timeout` 플러그인은 없음).

- [ ] **Step 3: 구현**

`src/dfm_bq_load_alerter/scheduler/jobs.py` 수정.

import 블록 교체/추가:

```python
import asyncio
import logging
from collections.abc import Coroutine
from datetime import UTC, datetime, time, timedelta
from typing import Any, TypeVar
from zoneinfo import ZoneInfo

from sqlalchemy import delete

from dfm_bq_load_alerter.checks import run_checks
from dfm_bq_load_alerter.db.models import (
    AlertEvent,
    AlertPolicy,
    Channel,
    CheckSnapshot,
    EventStatus,
    TriggerKind,
)
from dfm_bq_load_alerter.db.session import sessionmaker_factory
from dfm_bq_load_alerter.notifier.dispatcher import build_dispatch_snapshots, dispatch
from dfm_bq_load_alerter.settings import settings

log = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")
T = TypeVar("T")
```

`_expected_check_datetime` 아래에 래퍼 2개 추가:

```python
async def _record_job_timeout(job_id: str, trigger_kind: TriggerKind) -> None:
    """deadline 초과를 alert_events에 남긴다 (best-effort, 새 세션).

    channel enum에 시스템용 값이 없어 email을 재사용한다 — 마이그레이션을
    피하기 위한 결정(spec 참고). payload_summary 접두사로 구분한다.
    """
    try:
        sm = sessionmaker_factory()
        async with sm() as session:
            session.add(
                AlertEvent(
                    snapshot_id=None,
                    trigger_kind=trigger_kind,
                    channel=Channel.email,
                    status=EventStatus.failed,
                    payload_summary=f"job timeout · {job_id}",
                    error=(
                        f"job deadline exceeded ({settings.job_timeout_seconds}s)"
                    ),
                )
            )
            await session.commit()
    except Exception:  # noqa: BLE001 — 기록 실패가 job을 더 죽이면 안 된다
        log.exception("[%s] failed to record job-timeout event", job_id)


async def _run_with_deadline(
    job_id: str,
    body: Coroutine[Any, Any, T],
    trigger_kind: TriggerKind | None,
) -> T | None:
    """job 본문을 settings.job_timeout_seconds 상한으로 실행.

    초과 시 본문을 취소(진행 중 세션은 롤백)하고, trigger_kind가 있으면
    failed 이벤트를 남긴다. 예외를 밖으로 내보내지 않아 APScheduler의
    max_instances 슬롯이 무한 점유되는 일을 막는다.
    """
    try:
        async with asyncio.timeout(settings.job_timeout_seconds):
            return await body
    except TimeoutError:
        log.error(
            "[%s] job deadline exceeded (%ss); run aborted, snapshots rolled back",
            job_id,
            settings.job_timeout_seconds,
        )
        if trigger_kind is not None:
            await _record_job_timeout(job_id, trigger_kind)
        return None
```

기존 `check_at`을 다음으로 교체 (본문은 `_check_at_body`로 이동, 로직 무변경):

```python
async def check_at(job_id: str, moment: time) -> None:
    """Run all active table checks for a single cron trigger.

    Notification semantics: trigger='check' — bundled email+Teams send when
    one or more snapshots are FAIL; otherwise no message.
    """
    await _run_with_deadline(job_id, _check_at_body(job_id, moment), TriggerKind.check)


async def _check_at_body(job_id: str, moment: time) -> None:
    actual = datetime.now(tz=KST)
    expected = _expected_check_datetime(moment, now=actual)
    log.info(
        "[%s] cron fired (expected=%s actual=%s)",
        job_id,
        expected.isoformat(timespec="seconds"),
        actual.isoformat(timespec="seconds"),
    )

    sm = sessionmaker_factory()
    async with sm() as session:
        snapshots = await run_checks(
            session, expected_check_time=expected, actual_check_time=actual
        )
        dispatch_rows = await build_dispatch_snapshots(session, snapshots)
        sent = await dispatch(
            session,
            snapshots=dispatch_rows,
            trigger_kind="check",
            expected=expected,
            actual=actual,
        )
        await session.commit()
    log.info("[%s] cron complete: snapshots=%d events=%d", job_id, len(snapshots), sent)
```

같은 방식으로 `report_745` 교체 (기존 본문을 `_report_745_body(moment)`로 그대로 이동):

```python
async def report_745(moment: time = time(7, 45)) -> None:
    """Daily summary report at 07:45 KST.

    Notification semantics: trigger='report' — always sends once even if
    every table is OK. Includes OK / INSUFFICIENT_HISTORY sections.
    """
    await _run_with_deadline(
        "report-0745", _report_745_body(moment), TriggerKind.report
    )
```

(`_report_745_body`는 기존 `report_745` 본문 71–98행을 그대로 옮긴다.)

`cleanup_history` 교체 (기존 본문을 `_cleanup_history_body(now)`로 그대로 이동, docstring은 공개 함수에 유지):

```python
async def cleanup_history(now: datetime | None = None) -> dict[str, int | str] | None:
    """Delete check_snapshots/alert_events older than policy.retention_days.

    Reads ``alert_policy.retention_days`` each run so policy changes take
    effect on the next cleanup tick without a redeploy. Falls back to
    ``settings.retention_days`` when the policy row is absent.
    deadline 초과 시 None을 반환한다 (알람과 무관하므로 DB 기록은 생략).
    """
    return await _run_with_deadline(
        "cleanup-history", _cleanup_history_body(now), None
    )
```

- [ ] **Step 4: 통과 확인**

```bash
.venv/bin/pytest tests/test_scheduler_jobs.py -q
```

Expected: 전부 PASS, 신규 4개는 각각 0.1초 내외로 종료 (30초 걸리면 deadline 미작동)

- [ ] **Step 5: 커밋**

```bash
git add src/dfm_bq_load_alerter/scheduler/jobs.py tests/test_scheduler_jobs.py
git commit -m "feat(scheduler): job 전체 deadline 래퍼 추가 — 무한 대기로 인한 알람 마비 방지

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: max_instances 1 → 2 (2차 방어)

**Files:**
- Modify: `src/dfm_bq_load_alerter/scheduler/setup.py:62-65`
- Test: `tests/test_scheduler_setup.py`

**Interfaces:**
- Consumes: 없음 (Task 3과 독립이지만, deadline이 1차 방어라는 전제로 값 2를 선택)

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_scheduler_setup.py` 파일 끝에 추가:

```python
def test_모든_job이_max_instances_2로_등록된다() -> None:
    """deadline(1차 방어)이 실패해도 다음 firing이 skip되지 않게 하는 2차 방어."""
    scheduler = build_scheduler()
    register_jobs(scheduler)
    for job in scheduler.get_jobs():
        assert job.max_instances == 2, job.id
```

- [ ] **Step 2: 실패 확인**

```bash
.venv/bin/pytest "tests/test_scheduler_setup.py::test_모든_job이_max_instances_2로_등록된다" -v
```

Expected: FAIL — `assert 1 == 2`

- [ ] **Step 3: 구현**

`src/dfm_bq_load_alerter/scheduler/setup.py`의 `job_defaults`를 교체:

```python
        job_defaults={
            "coalesce": True,
            # job 본문에 deadline(_run_with_deadline)이 있어 슬롯이 영구
            # 점유될 일은 없지만, deadline 회귀 시에도 다음 firing이
            # skip되지 않도록 1개 여유를 둔다. 값을 키우면 동일 알람이
            # 중복 발송될 수 있으므로 2를 유지할 것.
            "max_instances": 2,
        },
```

- [ ] **Step 4: 통과 확인**

```bash
.venv/bin/pytest tests/test_scheduler_setup.py -q
```

Expected: 전부 PASS

- [ ] **Step 5: 커밋**

```bash
git add src/dfm_bq_load_alerter/scheduler/setup.py tests/test_scheduler_setup.py
git commit -m "feat(scheduler): max_instances 2로 상향 — deadline 회귀 대비 2차 방어

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: 전체 검증 (lint + 전체 테스트)

**Files:** 없음 (검증만; ruff 지적 시 해당 파일 수정)

- [ ] **Step 1: ruff**

```bash
.venv/bin/ruff check src tests
```

Expected: `All checks passed!` — 지적이 있으면 수정 후 `style: ruff 지적 수정` 커밋

- [ ] **Step 2: 전체 테스트**

```bash
.venv/bin/pytest -q
```

Expected: 이번 변경 관련 파일 전부 PASS. PostgreSQL 바이너리 부재로 `test_alembic.py` 등 인프라 의존 테스트가 error/skip 되는 경우, **Task 0 베이스라인과 동일한 실패 목록인지 비교**해 신규 실패가 없음을 확인하고 결과를 사용자에게 보고.

- [ ] **Step 3: 스펙 대비 최종 확인**

spec의 "오류 처리 요약" 표 5개 시나리오가 각각 테스트로 커버되는지 대조:
- SMTP 명령 timeout 전달 → `test_send_email_명령당_timeout을_aiosmtplib에_전달`
- 전송 전체 상한 → `test_send_email_전송_전체가_상한을_넘으면_TimeoutError`
- job deadline + 기록 → `test_check_at_deadline_초과시_failed_이벤트_기록`, `test_report_745_deadline_초과시_report_트리거로_기록`
- 기록 실패 시 삼킴 → `test_deadline_이벤트_기록_실패해도_예외를_삼킨다`
- local_hostname 상시 전달 → 수정된 `test_send_email_invokes_aiosmtplib_with_starttls`
