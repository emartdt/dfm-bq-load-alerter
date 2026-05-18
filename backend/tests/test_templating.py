from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from dfm_bq_load_alerter.bq.templating import (
    KST,
    TEMPLATE_MAX_CHARS,
    ConditionQueryTemplateError,
    build_query_context,
    render_condition_query,
)


def _now(year: int, month: int, day: int, hour: int = 7, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=KST)


def test_raw_sql_without_placeholders_passes_through() -> None:
    sql = "SELECT COUNT(*) FROM `p.d.t` WHERE flag = TRUE"
    assert render_condition_query(sql, now_kst=_now(2026, 5, 18)) == sql


def test_today_and_yesterday_substitution_uses_kst() -> None:
    template = (
        "SELECT COUNT(*) FROM `p.d.t` "
        "WHERE DATE(load_dt) BETWEEN DATE('{{ yesterday }}') AND DATE('{{ today }}')"
    )
    rendered = render_condition_query(template, now_kst=_now(2026, 5, 18))
    assert "DATE('2026-05-17')" in rendered
    assert "DATE('2026-05-18')" in rendered


def test_now_variable_is_kst_aware_datetime() -> None:
    template = "-- {{ now.tzinfo }}\nSELECT 1"
    rendered = render_condition_query(template, now_kst=_now(2026, 5, 18, 9, 30))
    # tz comparison via repr: zoneinfo.ZoneInfo('Asia/Seoul')
    assert "Asia/Seoul" in rendered


def test_days_ago_helper() -> None:
    template = "SELECT 1 FROM `p.d.t` WHERE DATE(load_dt) >= DATE('{{ days_ago(7) }}')"
    rendered = render_condition_query(template, now_kst=_now(2026, 5, 18))
    assert "DATE('2026-05-11')" in rendered


def test_months_ago_helper_handles_month_end_clamp() -> None:
    # 3월 31일 → 1개월 전은 2월 말일 (윤년 아님 → 28일)
    template = "{{ months_ago(1) }}"
    rendered = render_condition_query(template, now_kst=_now(2026, 3, 31))
    assert rendered.strip() == "2026-02-28"


def test_months_ago_wraps_year_boundary() -> None:
    template = "{{ months_ago(2) }}"
    rendered = render_condition_query(template, now_kst=_now(2026, 1, 15))
    assert rendered.strip() == "2025-11-15"


def test_strftime_filter_on_date() -> None:
    template = "{{ today.strftime('%Y%m%d') }}"
    rendered = render_condition_query(template, now_kst=_now(2026, 5, 18))
    assert rendered.strip() == "20260518"


def test_undefined_variable_raises() -> None:
    template = "SELECT 1 WHERE {{ unknown_var }}"
    with pytest.raises(ConditionQueryTemplateError):
        render_condition_query(template, now_kst=_now(2026, 5, 18))


def test_template_syntax_error_raises() -> None:
    template = "SELECT 1 WHERE {{ today "
    with pytest.raises(ConditionQueryTemplateError):
        render_condition_query(template, now_kst=_now(2026, 5, 18))


def test_negative_days_ago_rejected() -> None:
    template = "{{ days_ago(-1) }}"
    with pytest.raises(ConditionQueryTemplateError):
        render_condition_query(template, now_kst=_now(2026, 5, 18))


def test_negative_months_ago_rejected() -> None:
    template = "{{ months_ago(-1) }}"
    with pytest.raises(ConditionQueryTemplateError):
        render_condition_query(template, now_kst=_now(2026, 5, 18))


def test_sandbox_blocks_attribute_traversal() -> None:
    """Jinja2 SandboxedEnvironment 는 `__class__` 같은 위험 속성 접근을 차단."""
    template = "{{ today.__class__.__mro__ }}"
    with pytest.raises(ConditionQueryTemplateError):
        render_condition_query(template, now_kst=_now(2026, 5, 18))


def test_template_too_long_rejected() -> None:
    template = "-- " + ("x" * TEMPLATE_MAX_CHARS) + "\nSELECT 1"
    with pytest.raises(ConditionQueryTemplateError):
        render_condition_query(template)


def test_naive_datetime_treated_as_kst() -> None:
    naive = datetime(2026, 5, 18, 7, 0)
    ctx = build_query_context(naive)
    assert ctx["today"].isoformat() == "2026-05-18"
    # 7AM KST 는 KST 기준 같은 날
    assert str(ctx["now"]).endswith("Asia/Seoul'") or "+09:00" in str(ctx["now"])


def test_utc_midnight_maps_to_kst_morning() -> None:
    utc_midnight = datetime(2026, 5, 18, 0, 0, tzinfo=ZoneInfo("UTC"))
    ctx = build_query_context(utc_midnight)
    # 2026-05-18 00:00 UTC = 2026-05-18 09:00 KST → today=05-18
    assert ctx["today"].isoformat() == "2026-05-18"


def test_build_query_context_default_uses_now() -> None:
    """now_kst=None 이면 호출 시각이 들어가야 한다 (스모크)."""
    ctx = build_query_context()
    assert ctx["today"] is not None
    assert ctx["yesterday"] is not None
