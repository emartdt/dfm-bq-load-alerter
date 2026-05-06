from datetime import datetime
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


def test_teams_card_structure_minimum() -> None:
    rows = [_row("fail", failure_reasons=["delta_exceeded"])]
    card = build_teams_card(
        trigger_kind="check", expected=NOW, actual=NOW, rows=rows
    )
    assert card["type"] == "message"
    attachment = card["attachments"][0]
    assert attachment["contentType"] == "application/vnd.microsoft.card.adaptive"
    body_kinds = {b["type"] for b in attachment["content"]["body"]}
    assert "TextBlock" in body_kinds
    assert "FactSet" in body_kinds


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
