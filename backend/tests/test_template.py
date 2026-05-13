from datetime import datetime, time
from zoneinfo import ZoneInfo

from dfm_bq_load_alerter.notifier.template import (
    TemplateRow,
    build_email_html,
    build_email_subject,
    build_teams_card,
)

KST = ZoneInfo("Asia/Seoul")
NOW = datetime(2026, 5, 6, 9, 0, tzinfo=KST)


def _row(status: str, **overrides) -> TemplateRow:
    base = dict(
        dataset="bw",
        table_name="PZEVENTID",
        expected_check_time=NOW,
        actual_check_time=NOW,
        yesterday_row_count=1000,
        today_row_count=900,
        delta_percent_vs_yesterday=10.0,
        status=status,
        failure_reasons=[],
    )
    base.update(overrides)
    return TemplateRow(**base)


def test_subject_for_check_includes_fail_count() -> None:
    subject = build_email_subject(trigger_kind="check", fail_count=3, expected=NOW)
    assert "점검 실패 3건" in subject
    assert "2026-05-06" in subject


def test_subject_for_report_uses_report_label() -> None:
    subject = build_email_subject(trigger_kind="report", fail_count=0, expected=NOW)
    assert "일일 리포트" in subject


def test_email_html_renders_fail_section_only_when_fails_present() -> None:
    fail_row = _row("fail", failure_reasons=["row_count_zero"], today_row_count=0)
    _, html = build_email_html(
        trigger_kind="check", expected=NOW, actual=NOW, rows=[fail_row]
    )
    assert "FAIL (1)" in html
    assert "row_count_zero" in html
    assert "INSUFFICIENT" not in html


def test_email_html_escapes_dangerous_input() -> None:
    """HTML autoescape must neutralise <script> in dataset/table names."""
    bad = _row("fail", dataset="<script>alert(1)</script>", failure_reasons=["x"])
    _, html = build_email_html(
        trigger_kind="check", expected=NOW, actual=NOW, rows=[bad]
    )
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_email_html_report_includes_ok_section() -> None:
    rows = [_row("ok"), _row("ok", table_name="OTHER")]
    _, html = build_email_html(
        trigger_kind="report", expected=NOW, actual=NOW, rows=rows
    )
    assert "OK (2)" in html


def test_email_html_check_trigger_omits_ok_section() -> None:
    rows = [_row("ok"), _row("fail", failure_reasons=["x"])]
    _, html = build_email_html(
        trigger_kind="check", expected=NOW, actual=NOW, rows=rows
    )
    assert "FAIL" in html
    assert "OK (" not in html


def _collect_types(items) -> set[str]:
    """Adaptive Card body 의 모든 노드 타입 집합 (Container 재귀 포함)."""
    found: set[str] = set()
    for item in items:
        found.add(item.get("type", ""))
        if item.get("type") == "Container":
            found |= _collect_types(item.get("items", []))
        if item.get("type") == "ColumnSet":
            for col in item.get("columns", []):
                found |= _collect_types(col.get("items", []))
    return found


def test_teams_card_structure_minimum() -> None:
    rows = [_row("fail", failure_reasons=["delta_exceeded"])]
    card = build_teams_card(
        trigger_kind="check", expected=NOW, actual=NOW, rows=rows
    )
    assert card["type"] == "message"
    attachment = card["attachments"][0]
    assert attachment["contentType"] == "application/vnd.microsoft.card.adaptive"
    body = attachment["content"]["body"]
    body_kinds = _collect_types(body)
    assert "TextBlock" in body_kinds
    assert "FactSet" in body_kinds  # 카드 컨테이너 안에 위치


def test_teams_card_attention_color_when_fails() -> None:
    rows = [_row("fail", failure_reasons=["x"])]
    card = build_teams_card(
        trigger_kind="check", expected=NOW, actual=NOW, rows=rows
    )
    headline = card["attachments"][0]["content"]["body"][0]
    assert headline["color"] == "Attention"


def test_teams_card_good_color_when_no_fails() -> None:
    rows = [_row("ok")]
    card = build_teams_card(
        trigger_kind="report", expected=NOW, actual=NOW, rows=rows
    )
    headline = card["attachments"][0]["content"]["body"][0]
    assert headline["color"] == "Good"


def test_email_html_includes_project_dataset_table_in_card() -> None:
    """프로젝트 prefix 가 카드 헤더에 노출되어야 한다."""
    row = _row(
        "fail",
        project="bw-prj-001",
        dataset="bw",
        table_name="PZEVENTID",
        failure_reasons=["delta_exceeded"],
    )
    _, html = build_email_html(
        trigger_kind="check", expected=NOW, actual=NOW, rows=[row]
    )
    assert "bw-prj-001" in html
    assert "PZEVENTID" in html
    assert "bw" in html


def test_email_html_includes_batch_time_label() -> None:
    row = _row("fail", batch_time=time(7, 0), failure_reasons=["x"])
    _, html = build_email_html(
        trigger_kind="check", expected=NOW, actual=NOW, rows=[row]
    )
    assert "07:00" in html
    assert "배치 시각" in html


def test_email_html_shows_delta_count_and_percent_with_sign() -> None:
    """오늘 - 어제 = -100, Δ% = -10.00% (부호 포함)."""
    row = _row(
        "fail",
        yesterday_row_count=1000,
        today_row_count=900,
        delta_percent_vs_yesterday=-10.0,
        failure_reasons=["delta_exceeded"],
    )
    _, html = build_email_html(
        trigger_kind="check", expected=NOW, actual=NOW, rows=[row]
    )
    assert "-100" in html
    assert "-10.00%" in html


def test_email_html_shows_previous_batch_load_time() -> None:
    yday = datetime(2026, 5, 5, 6, 58, tzinfo=KST)
    today = datetime(2026, 5, 6, 7, 4, tzinfo=KST)
    row = _row(
        "fail",
        yesterday_last_modified=yday,
        today_last_modified=today,
        failure_reasons=["delta_exceeded"],
    )
    _, html = build_email_html(
        trigger_kind="check", expected=NOW, actual=NOW, rows=[row]
    )
    assert "2026-05-05 06:58:00" in html
    assert "2026-05-06 07:04:00" in html
    assert "이전 배치" in html
    assert "금일 배치" in html


def test_teams_card_fail_container_includes_project_and_batch_time() -> None:
    row = _row(
        "fail",
        project="bw-prj-001",
        batch_time=time(7, 0),
        failure_reasons=["delta_exceeded"],
    )
    card = build_teams_card(
        trigger_kind="check", expected=NOW, actual=NOW, rows=[row]
    )
    body = card["attachments"][0]["content"]["body"]
    container = next(b for b in body if b.get("type") == "Container")
    flat = str(container)
    assert "bw-prj-001.bw.PZEVENTID" in flat
    assert "07:00" in flat


def test_teams_card_includes_delta_facts() -> None:
    row = _row(
        "fail",
        yesterday_row_count=1000,
        today_row_count=900,
        delta_percent_vs_yesterday=-10.0,
        failure_reasons=["delta_exceeded"],
    )
    card = build_teams_card(
        trigger_kind="check", expected=NOW, actual=NOW, rows=[row]
    )
    body = card["attachments"][0]["content"]["body"]
    container = next(b for b in body if b.get("type") == "Container")
    fact_set = next(item for item in container["items"] if item["type"] == "FactSet")
    titles = [f["title"] for f in fact_set["facts"]]
    values = [f["value"] for f in fact_set["facts"]]
    assert "증감 rows" in titles
    assert "증감 %" in titles
    assert "-100" in values
    assert "-10.00%" in values
