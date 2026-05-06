"""Build alert/report messages — HTML for SMTP, Adaptive Card JSON for Teams.

Content per rev 2 P11: dataset · table · expected/actual check time ·
yesterday/today row_count · delta % · failure reasons. Misfire catch-up
shows expected vs actual side-by-side.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from jinja2 import Environment, select_autoescape

KST = ZoneInfo("Asia/Seoul")

_env = Environment(autoescape=select_autoescape(["html", "xml"]))


@dataclass(frozen=True, slots=True)
class TemplateRow:
    dataset: str
    table_name: str
    expected_check_time: datetime
    actual_check_time: datetime
    yesterday_row_count: int | None
    today_row_count: int | None
    delta_percent_vs_yesterday: float | None
    status: str  # 'ok' | 'fail' | 'insufficient_history'
    failure_reasons: list[str]


_HTML_TEMPLATE = _env.from_string(
    """<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8"><title>{{ subject }}</title></head>
<body style="font-family:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;color:#1a1a1a;">
<h2 style="margin-bottom:0.25rem;">{{ subject }}</h2>
<p style="color:#888;margin-top:0;">trigger: {{ trigger_kind }} · expected={{ expected_kst }} KST · actual={{ actual_kst }} KST</p>

{% if fail_rows %}
<h3 style="color:#c62828;">FAIL ({{ fail_rows|length }})</h3>
<table style="border-collapse:collapse;width:100%;font-size:14px;">
<thead><tr style="background:#fbe9e7;">
  <th style="padding:6px;text-align:left;">Dataset.Table</th>
  <th style="padding:6px;text-align:right;">Yesterday</th>
  <th style="padding:6px;text-align:right;">Today</th>
  <th style="padding:6px;text-align:right;">Δ%</th>
  <th style="padding:6px;text-align:left;">Reasons</th>
</tr></thead>
<tbody>
{% for r in fail_rows %}<tr>
  <td style="padding:6px;border-bottom:1px solid #eee;">{{ r.dataset }}.{{ r.table_name }}</td>
  <td style="padding:6px;text-align:right;border-bottom:1px solid #eee;">{{ "{:,}".format(r.yesterday_row_count) if r.yesterday_row_count is not none else "-" }}</td>
  <td style="padding:6px;text-align:right;border-bottom:1px solid #eee;">{{ "{:,}".format(r.today_row_count) if r.today_row_count is not none else "-" }}</td>
  <td style="padding:6px;text-align:right;border-bottom:1px solid #eee;">{{ "%.2f"|format(r.delta_percent_vs_yesterday) if r.delta_percent_vs_yesterday is not none else "-" }}</td>
  <td style="padding:6px;border-bottom:1px solid #eee;">{{ r.failure_reasons|join(", ") }}</td>
</tr>{% endfor %}
</tbody></table>
{% endif %}

{% if insufficient_rows %}
<h3 style="color:#f57c00;">INSUFFICIENT HISTORY ({{ insufficient_rows|length }})</h3>
<ul>{% for r in insufficient_rows %}<li>{{ r.dataset }}.{{ r.table_name }} (today rows={{ r.today_row_count if r.today_row_count is not none else "-" }})</li>{% endfor %}</ul>
{% endif %}

{% if ok_rows and trigger_kind == "report" %}
<h3 style="color:#2e7d32;">OK ({{ ok_rows|length }})</h3>
<ul>{% for r in ok_rows %}<li>{{ r.dataset }}.{{ r.table_name }} ({{ "{:,}".format(r.today_row_count) if r.today_row_count is not none else "-" }} rows)</li>{% endfor %}</ul>
{% endif %}

<hr><p style="font-size:12px;color:#888;">dfm-bq-load-alerter v0.2.x</p>
</body></html>"""
)


def _to_kst(dt: datetime) -> str:
    return dt.astimezone(KST).strftime("%Y-%m-%d %H:%M:%S")


def _bucket_rows(rows: list[TemplateRow]) -> tuple[list[TemplateRow], list[TemplateRow], list[TemplateRow]]:
    fail = [r for r in rows if r.status == "fail"]
    insufficient = [r for r in rows if r.status == "insufficient_history"]
    ok = [r for r in rows if r.status == "ok"]
    return fail, insufficient, ok


def build_email_subject(*, trigger_kind: str, fail_count: int, expected: datetime) -> str:
    if trigger_kind == "report":
        return f"[DFM Alert] 일일 리포트 ({_to_kst(expected)})"
    return f"[DFM Alert] 점검 실패 {fail_count}건 ({_to_kst(expected)})"


def build_email_html(
    *, trigger_kind: str, expected: datetime, actual: datetime, rows: list[TemplateRow]
) -> tuple[str, str]:
    fail, insufficient, ok = _bucket_rows(rows)
    subject = build_email_subject(
        trigger_kind=trigger_kind, fail_count=len(fail), expected=expected
    )
    html = _HTML_TEMPLATE.render(
        subject=subject,
        trigger_kind=trigger_kind,
        expected_kst=_to_kst(expected),
        actual_kst=_to_kst(actual),
        fail_rows=fail,
        insufficient_rows=insufficient,
        ok_rows=ok,
    )
    return subject, html


def build_teams_card(
    *, trigger_kind: str, expected: datetime, actual: datetime, rows: list[TemplateRow]
) -> dict[str, Any]:
    """Build an Adaptive Card v1.5 payload suitable for an Incoming Webhook."""
    fail, insufficient, ok = _bucket_rows(rows)
    summary = build_email_subject(
        trigger_kind=trigger_kind, fail_count=len(fail), expected=expected
    )

    body: list[dict[str, Any]] = [
        {
            "type": "TextBlock",
            "size": "Large",
            "weight": "Bolder",
            "text": summary,
            "color": "Attention" if fail else "Good",
        },
        {
            "type": "TextBlock",
            "isSubtle": True,
            "spacing": "None",
            "text": f"trigger={trigger_kind} · expected={_to_kst(expected)} · actual={_to_kst(actual)}",
        },
    ]

    if fail:
        body.append(
            {
                "type": "TextBlock",
                "weight": "Bolder",
                "color": "Attention",
                "text": f"FAIL ({len(fail)})",
                "separator": True,
            }
        )
        body.append(
            {
                "type": "FactSet",
                "facts": [
                    {
                        "title": f"{r.dataset}.{r.table_name}",
                        "value": (
                            f"yesterday={r.yesterday_row_count} → today={r.today_row_count}"
                            f" · Δ%={r.delta_percent_vs_yesterday}"
                            f" · {', '.join(r.failure_reasons)}"
                        ),
                    }
                    for r in fail
                ],
            }
        )

    if insufficient:
        body.append(
            {
                "type": "TextBlock",
                "weight": "Bolder",
                "color": "Warning",
                "text": f"INSUFFICIENT HISTORY ({len(insufficient)})",
                "separator": True,
            }
        )
        body.append(
            {
                "type": "FactSet",
                "facts": [
                    {
                        "title": f"{r.dataset}.{r.table_name}",
                        "value": f"today={r.today_row_count}",
                    }
                    for r in insufficient
                ],
            }
        )

    if ok and trigger_kind == "report":
        body.append(
            {
                "type": "TextBlock",
                "weight": "Bolder",
                "color": "Good",
                "text": f"OK ({len(ok)})",
                "separator": True,
            }
        )
        body.append(
            {
                "type": "FactSet",
                "facts": [
                    {
                        "title": f"{r.dataset}.{r.table_name}",
                        "value": f"today={r.today_row_count}",
                    }
                    for r in ok
                ],
            }
        )

    return {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.5",
                    "body": body,
                },
            }
        ],
    }
