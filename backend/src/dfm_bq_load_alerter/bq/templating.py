"""Jinja2 기반 condition_query 템플레이팅.

`tables.condition_query` 에 저장된 SQL 안에서 KST 기준 일자 변수를 치환해,
"매일 다른 날짜 필터로 같은 SQL 을 실행" 요구를 지원한다.

사용 가능한 변수/헬퍼:
- `today`      : 오늘 (KST `date`)
- `yesterday`  : 어제 (KST `date`)
- `now`        : 현재 (KST `datetime`)
- `days_ago(n)`   : n 일 전 `date`
- `months_ago(n)` : n 개월 전 `date` (단순 30일 단위가 아닌 calendar 단위)

보안:
- `jinja2.sandbox.SandboxedEnvironment` 사용 → 임의 속성/메서드 접근 차단
- 미정의 변수 참조는 `StrictUndefined` 로 즉시 예외
- 노출 변수는 모두 `date`/`datetime` 객체. 사용자 입력 문자열은 컨텍스트에
  들어가지 않으므로 추가 인젝션 표면 없음
- 렌더 결과 SQL 은 호출 측에서 `_validate_condition_query` 로 다시 검증되어야
  forbidden 키워드 (DML/DDL) 우회를 차단할 수 있다.

길이 한도:
- 템플릿 본문이 `TEMPLATE_MAX_CHARS` 를 넘으면 `ConditionQueryError`.
- 렌더 결과 길이는 호출 측 validate 단계에서 별도 제어하지 않음(기존 정책 유지).
"""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from jinja2 import StrictUndefined, TemplateError
from jinja2.sandbox import SandboxedEnvironment

KST = ZoneInfo("Asia/Seoul")

# 운영 안전망: 무한 길이 템플릿 방지 (실용 가용한 SQL 은 수 KB 를 넘지 않음).
TEMPLATE_MAX_CHARS = 10_000


class ConditionQueryTemplateError(ValueError):
    """Jinja2 렌더 실패. 호출 측에서 `ConditionQueryError` 로 래핑된다."""


_env = SandboxedEnvironment(
    autoescape=False,
    undefined=StrictUndefined,
    keep_trailing_newline=True,
)


def _months_ago(now_date: date, n: int) -> date:
    if not isinstance(n, int) or isinstance(n, bool) or n < 0:
        raise ConditionQueryTemplateError(
            "months_ago 인수는 0 이상의 정수여야 합니다."
        )
    year = now_date.year
    month = now_date.month - n
    while month <= 0:
        month += 12
        year -= 1
    # 말일(예: 1/31 → 2/28) 보정: 해당 월의 마지막 날로 클램프.
    day = min(now_date.day, _last_day_of_month(year, month))
    return date(year, month, day)


def _days_ago(now_date: date, n: int) -> date:
    if not isinstance(n, int) or isinstance(n, bool) or n < 0:
        raise ConditionQueryTemplateError(
            "days_ago 인수는 0 이상의 정수여야 합니다."
        )
    from datetime import timedelta

    return now_date - timedelta(days=n)


def _last_day_of_month(year: int, month: int) -> int:
    from calendar import monthrange

    return monthrange(year, month)[1]


def build_query_context(now_kst: datetime | None = None) -> dict[str, object]:
    """KST 기준 현재 시각을 받아 Jinja2 컨텍스트를 만든다.

    `now_kst=None` 이면 호출 시각 기준 KST `now()` 를 사용한다.
    """
    if now_kst is None:
        now_kst = datetime.now(tz=KST)
    elif now_kst.tzinfo is None:
        now_kst = now_kst.replace(tzinfo=KST)
    today = now_kst.date()
    return {
        "today": today,
        "yesterday": _days_ago(today, 1),
        "now": now_kst,
        "days_ago": lambda n: _days_ago(today, n),
        "months_ago": lambda n: _months_ago(today, n),
    }


def render_condition_query(
    template: str, *, now_kst: datetime | None = None
) -> str:
    """템플릿 본문을 KST 변수로 렌더링한다.

    `{{ }}` / `{% %}` 를 사용하지 않는 평문 SQL 은 그대로 반환된다 (하위 호환).
    Jinja2 문법/변수 오류는 `ConditionQueryTemplateError` 로 변환된다.
    """
    if len(template) > TEMPLATE_MAX_CHARS:
        raise ConditionQueryTemplateError(
            f"condition_query 템플릿 길이가 한도({TEMPLATE_MAX_CHARS}자)를 초과합니다."
        )
    try:
        compiled = _env.from_string(template)
        return compiled.render(build_query_context(now_kst))
    except ConditionQueryTemplateError:
        raise
    except TemplateError as exc:
        raise ConditionQueryTemplateError(
            f"condition_query 템플릿 렌더 실패: {exc}"
        ) from exc
    except Exception as exc:  # noqa: BLE001 — sandbox SecurityError 등 포괄
        raise ConditionQueryTemplateError(
            f"condition_query 템플릿 렌더 중 오류: {exc}"
        ) from exc
