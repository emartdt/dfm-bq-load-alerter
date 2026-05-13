"""Build alert/report messages — HTML for SMTP, Adaptive Card JSON for Teams.

Rev 5 (모던 카드 템플릿): 각 테이블을 카드 단위로 표현하여 프로젝트·데이터셋·
테이블·배치 시각·이전/오늘 유입 시각·ROW COUNT·증감(Δrows, Δ%)을 한눈에
파악할 수 있도록 구성한다. Teams 측은 Adaptive Card v1.5 의 Container +
ColumnSet 으로 동일한 정보 구조를 재현한다.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from jinja2 import Environment, select_autoescape

KST = ZoneInfo("Asia/Seoul")

ALERT_SUBJECT_PREFIX = "[DFM 빅쿼리 적재 알리미]"
"""모든 알람/테스트 메시지의 제목·본문 헤더에 공통으로 붙는 접두어."""

_env = Environment(autoescape=select_autoescape(["html", "xml"]))


def _to_kst(dt: datetime) -> str:
    return dt.astimezone(KST).strftime("%Y-%m-%d %H:%M:%S")


def _fmt_time(t: time | None) -> str:
    return t.strftime("%H:%M") if t is not None else "-"


def _fmt_count(n: int | None) -> str:
    return f"{n:,}" if n is not None else "-"


def _signed_count(n: int | None) -> str:
    if n is None:
        return "-"
    sign = "+" if n > 0 else ""
    return f"{sign}{n:,}"


def _signed_percent(p: float | None) -> str:
    if p is None:
        return "-"
    sign = "+" if p > 0 else ""
    return f"{sign}{p:.2f}%"


_env.filters["kst"] = _to_kst
_env.filters["fmt_count"] = _fmt_count
_env.filters["signed_count"] = _signed_count
_env.filters["signed_percent"] = _signed_percent
_env.filters["fmt_time"] = _fmt_time
_env.globals["kst"] = _to_kst


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
    note: str | None = None
    today_last_modified: datetime | None = None
    yesterday_last_modified: datetime | None = None
    project: str | None = None
    batch_time: time | None = None
    informational_notes: list[str] | None = None

    @property
    def fqn(self) -> str:
        """Project.dataset.table 또는 dataset.table — 카드 헤더 식별자."""
        parts = [self.project, self.dataset, self.table_name]
        return ".".join(p for p in parts if p)

    @property
    def delta_count(self) -> int | None:
        if self.today_row_count is None or self.yesterday_row_count is None:
            return None
        return self.today_row_count - self.yesterday_row_count


_STATUS_META = {
    "fail": {"label": "FAIL", "bg": "#fdecea", "fg": "#c62828", "accent": "#c62828"},
    "ok": {"label": "OK", "bg": "#e8f5e9", "fg": "#2e7d32", "accent": "#2e7d32"},
    "insufficient_history": {
        "label": "INSUFFICIENT",
        "bg": "#fff4e5",
        "fg": "#b26a00",
        "accent": "#f57c00",
    },
}


def _delta_color(p: float | None) -> str:
    if p is None:
        return "#6b7280"
    if p > 0:
        return "#2e7d32"
    if p < 0:
        return "#c62828"
    return "#6b7280"


_env.globals["status_meta"] = _STATUS_META
_env.globals["delta_color"] = _delta_color


_HTML_TEMPLATE = _env.from_string(
    """<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8"><title>{{ subject }}</title></head>
<body style="margin:0;padding:24px;background:#f5f6f8;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','Apple SD Gothic Neo','Malgun Gothic',sans-serif;color:#1f2937;">

{% macro render_card(r, status) -%}
{% set meta = status_meta[status] %}
<table role="presentation" cellspacing="0" cellpadding="0" border="0" style="width:100%;background:#ffffff;border-radius:12px;box-shadow:0 1px 3px rgba(0,0,0,0.05);margin-bottom:12px;border-left:4px solid {{ meta.accent }};">
<tr><td style="padding:16px 20px;">

  <table role="presentation" cellspacing="0" cellpadding="0" border="0" style="width:100%;">
  <tr>
    <td style="font-size:15px;font-weight:700;color:#111827;word-break:break-all;">
      {% if r.project %}<span style="color:#6b7280;font-weight:500;">{{ r.project }}.</span>{% endif %}{{ r.dataset }}.<span style="color:{{ meta.accent }};">{{ r.table_name }}</span>
    </td>
    <td align="right" style="white-space:nowrap;padding-left:8px;">
      <span style="display:inline-block;padding:3px 10px;border-radius:999px;font-size:11px;font-weight:700;background:{{ meta.bg }};color:{{ meta.fg }};">{{ meta.label }}</span>
    </td>
  </tr>
  </table>

  <div style="font-size:12px;color:#6b7280;margin-top:6px;">
    배치 시각 <strong style="color:#374151;">{{ r.batch_time|fmt_time }}</strong>
    {% if r.expected_check_time %}· 점검 윈도우 기준 {{ kst(r.expected_check_time) }} KST{% endif %}
  </div>

  <table role="presentation" cellspacing="0" cellpadding="0" border="0" style="width:100%;margin-top:14px;border-collapse:separate;border-spacing:8px 0;">
  <tr>
    <td style="width:50%;background:#f9fafb;border-radius:8px;padding:12px 14px;vertical-align:top;">
      <div style="font-size:11px;color:#6b7280;text-transform:uppercase;letter-spacing:0.04em;">이전 배치</div>
      <div style="font-size:18px;font-weight:700;color:#111827;margin-top:2px;">{{ r.yesterday_row_count|fmt_count }} <span style="font-size:11px;font-weight:500;color:#6b7280;">rows</span></div>
      <div style="font-size:11px;color:#6b7280;margin-top:4px;">{% if r.yesterday_last_modified %}유입 {{ kst(r.yesterday_last_modified) }}{% else %}유입 시각 없음{% endif %}</div>
    </td>
    <td style="width:50%;background:#f9fafb;border-radius:8px;padding:12px 14px;vertical-align:top;">
      <div style="font-size:11px;color:#6b7280;text-transform:uppercase;letter-spacing:0.04em;">금일 배치</div>
      <div style="font-size:18px;font-weight:700;color:#111827;margin-top:2px;">{{ r.today_row_count|fmt_count }} <span style="font-size:11px;font-weight:500;color:#6b7280;">rows</span></div>
      <div style="font-size:11px;color:#6b7280;margin-top:4px;">{% if r.today_last_modified %}유입 {{ kst(r.today_last_modified) }}{% else %}유입 시각 없음{% endif %}</div>
    </td>
  </tr>
  </table>

  <div style="margin-top:12px;padding:10px 14px;background:#f3f4f6;border-radius:8px;display:block;">
    <table role="presentation" cellspacing="0" cellpadding="0" border="0" style="width:100%;">
    <tr>
      <td style="font-size:12px;color:#6b7280;">증감</td>
      <td align="right" style="font-size:14px;font-weight:700;color:{{ delta_color(r.delta_percent_vs_yesterday) }};">
        Δ {{ r.delta_count|signed_count }} rows · {{ r.delta_percent_vs_yesterday|signed_percent }}
      </td>
    </tr>
    </table>
  </div>

  {% if r.failure_reasons %}
  <div style="margin-top:12px;">
    <div style="font-size:11px;color:#6b7280;text-transform:uppercase;letter-spacing:0.04em;margin-bottom:6px;">실패 사유</div>
    {% for reason in r.failure_reasons %}<span style="display:inline-block;padding:3px 9px;border-radius:6px;font-size:11px;font-weight:600;background:#fdecea;color:#c62828;margin-right:6px;margin-bottom:4px;">⚠ {{ reason }}</span>{% endfor %}
  </div>
  {% endif %}

  {% if r.informational_notes %}
  <div style="margin-top:12px;">
    <div style="font-size:11px;color:#6b7280;text-transform:uppercase;letter-spacing:0.04em;margin-bottom:6px;">참고</div>
    {% for info in r.informational_notes %}<span style="display:inline-block;padding:3px 9px;border-radius:6px;font-size:11px;font-weight:600;background:#e0f2fe;color:#075985;margin-right:6px;margin-bottom:4px;">ⓘ {{ info }}</span>{% endfor %}
  </div>
  {% endif %}

  {% if r.note %}
  <div style="margin-top:10px;padding:8px 12px;background:#fffbeb;border-left:3px solid #f59e0b;border-radius:4px;font-size:12px;color:#78350f;">📝 {{ r.note }}</div>
  {% endif %}

</td></tr></table>
{%- endmacro %}

<div style="max-width:760px;margin:0 auto;">

  <div style="background:#ffffff;border-radius:12px;padding:20px 24px;box-shadow:0 1px 3px rgba(0,0,0,0.06);margin-bottom:16px;border-left:6px solid {{ banner_accent }};">
    <div style="font-size:13px;color:#6b7280;letter-spacing:0.04em;text-transform:uppercase;">{{ trigger_label }}</div>
    <div style="font-size:22px;font-weight:700;margin-top:4px;">{{ subject }}</div>
    <div style="font-size:13px;color:#6b7280;margin-top:8px;">
      예정 점검 {{ expected_kst }} KST · 실측 점검 {{ actual_kst }} KST
    </div>
    <div style="margin-top:12px;">
      {% if fail_rows %}<span style="display:inline-block;padding:4px 10px;border-radius:999px;font-size:12px;font-weight:600;background:#fdecea;color:#c62828;margin-right:6px;">FAIL {{ fail_rows|length }}</span>{% endif %}
      {% if insufficient_rows %}<span style="display:inline-block;padding:4px 10px;border-radius:999px;font-size:12px;font-weight:600;background:#fff4e5;color:#b26a00;margin-right:6px;">INSUFFICIENT {{ insufficient_rows|length }}</span>{% endif %}
      {% if ok_rows and trigger_kind == "report" %}<span style="display:inline-block;padding:4px 10px;border-radius:999px;font-size:12px;font-weight:600;background:#e8f5e9;color:#2e7d32;">OK {{ ok_rows|length }}</span>{% endif %}
    </div>
  </div>

  {% if fail_rows %}
  <h3 style="margin:24px 4px 12px;color:#c62828;font-size:15px;letter-spacing:0.02em;">FAIL ({{ fail_rows|length }})</h3>
  {% for r in fail_rows %}{{ render_card(r, "fail") }}{% endfor %}
  {% endif %}

  {% if insufficient_rows %}
  <h3 style="margin:24px 4px 12px;color:#b26a00;font-size:15px;letter-spacing:0.02em;">INSUFFICIENT HISTORY ({{ insufficient_rows|length }})</h3>
  {% for r in insufficient_rows %}{{ render_card(r, "insufficient_history") }}{% endfor %}
  {% endif %}

  {% if ok_rows and trigger_kind == "report" %}
  <h3 style="margin:24px 4px 12px;color:#2e7d32;font-size:15px;letter-spacing:0.02em;">OK ({{ ok_rows|length }})</h3>
  {% for r in ok_rows %}{{ render_card(r, "ok") }}{% endfor %}
  {% endif %}

  <p style="font-size:11px;color:#9ca3af;text-align:center;margin-top:24px;">dfm-bq-load-alerter</p>
</div>
</body></html>"""
)


def _bucket_rows(
    rows: list[TemplateRow],
) -> tuple[list[TemplateRow], list[TemplateRow], list[TemplateRow]]:
    fail = [r for r in rows if r.status == "fail"]
    insufficient = [r for r in rows if r.status == "insufficient_history"]
    ok = [r for r in rows if r.status == "ok"]
    return fail, insufficient, ok


def build_email_subject(*, trigger_kind: str, fail_count: int, expected: datetime) -> str:
    if trigger_kind == "report":
        return f"{ALERT_SUBJECT_PREFIX} 일일 리포트 ({_to_kst(expected)})"
    return f"{ALERT_SUBJECT_PREFIX} 점검 실패 {fail_count}건 ({_to_kst(expected)})"


def build_email_html(
    *, trigger_kind: str, expected: datetime, actual: datetime, rows: list[TemplateRow]
) -> tuple[str, str]:
    fail, insufficient, ok = _bucket_rows(rows)
    subject = build_email_subject(
        trigger_kind=trigger_kind, fail_count=len(fail), expected=expected
    )
    if fail:
        banner_accent = "#c62828"
    elif insufficient:
        banner_accent = "#f57c00"
    else:
        banner_accent = "#2e7d32"
    trigger_label = "일일 리포트" if trigger_kind == "report" else "점검 알림"
    html = _HTML_TEMPLATE.render(
        subject=subject,
        trigger_kind=trigger_kind,
        trigger_label=trigger_label,
        banner_accent=banner_accent,
        expected_kst=_to_kst(expected),
        actual_kst=_to_kst(actual),
        fail_rows=fail,
        insufficient_rows=insufficient,
        ok_rows=ok,
    )
    return subject, html


def _card_title_columns(r: TemplateRow, status: str) -> dict[str, Any]:
    meta = _STATUS_META[status]
    project_prefix = f"{r.project}." if r.project else ""
    return {
        "type": "ColumnSet",
        "columns": [
            {
                "type": "Column",
                "width": "stretch",
                "items": [
                    {
                        "type": "TextBlock",
                        "text": f"{project_prefix}{r.dataset}.{r.table_name}",
                        "weight": "Bolder",
                        "wrap": True,
                    }
                ],
            },
            {
                "type": "Column",
                "width": "auto",
                "items": [
                    {
                        "type": "TextBlock",
                        "text": meta["label"],
                        "weight": "Bolder",
                        "color": "Attention"
                        if status == "fail"
                        else ("Warning" if status == "insufficient_history" else "Good"),
                        "horizontalAlignment": "Right",
                    }
                ],
            },
        ],
    }


def _card_compare_columns(r: TemplateRow) -> dict[str, Any]:
    def _side(label: str, count: int | None, ts: datetime | None) -> dict[str, Any]:
        return {
            "type": "Column",
            "width": "stretch",
            "style": "emphasis",
            "items": [
                {
                    "type": "TextBlock",
                    "text": label,
                    "isSubtle": True,
                    "size": "Small",
                    "spacing": "None",
                },
                {
                    "type": "TextBlock",
                    "text": f"**{_fmt_count(count)}** rows",
                    "size": "Medium",
                    "spacing": "None",
                    "wrap": True,
                },
                {
                    "type": "TextBlock",
                    "text": f"유입 {_to_kst(ts)}" if ts is not None else "유입 시각 없음",
                    "isSubtle": True,
                    "size": "Small",
                    "spacing": "None",
                    "wrap": True,
                },
            ],
        }

    return {
        "type": "ColumnSet",
        "spacing": "Small",
        "columns": [
            _side("이전 배치", r.yesterday_row_count, r.yesterday_last_modified),
            _side("금일 배치", r.today_row_count, r.today_last_modified),
        ],
    }


def _card_meta_line(r: TemplateRow) -> dict[str, Any]:
    """이메일의 '배치 시각 HH:MM · 점검 윈도우 기준 ... KST' 라인과 동치."""
    parts = [f"배치 시각 **{_fmt_time(r.batch_time)}**"]
    if r.expected_check_time is not None:
        parts.append(f"점검 윈도우 기준 {_to_kst(r.expected_check_time)} KST")
    return {
        "type": "TextBlock",
        "text": " · ".join(parts),
        "isSubtle": True,
        "size": "Small",
        "spacing": "Small",
        "wrap": True,
    }


def _card_delta_line(r: TemplateRow) -> dict[str, Any]:
    """이메일의 '증감 Δ ±N rows · ±X.XX%' 단일 박스에 대응하는 단일 라인."""
    p = r.delta_percent_vs_yesterday
    if p is None:
        color = "Default"
    elif p > 0:
        color = "Good"
    elif p < 0:
        color = "Attention"
    else:
        color = "Default"
    return {
        "type": "TextBlock",
        "text": (
            f"증감  **Δ {_signed_count(r.delta_count)} rows · "
            f"{_signed_percent(r.delta_percent_vs_yesterday)}**"
        ),
        "color": color,
        "weight": "Bolder",
        "spacing": "Small",
        "wrap": True,
    }


def _build_card_container(r: TemplateRow, status: str) -> dict[str, Any]:
    container_style = (
        "attention"
        if status == "fail"
        else ("warning" if status == "insufficient_history" else "good")
    )
    items: list[dict[str, Any]] = [
        _card_title_columns(r, status),
        _card_meta_line(r),
        _card_compare_columns(r),
        _card_delta_line(r),
    ]
    if r.failure_reasons:
        items.append(
            {
                "type": "TextBlock",
                "text": "**실패 사유**  "
                + "  ".join(f"⚠ {reason}" for reason in r.failure_reasons),
                "color": "Attention",
                "weight": "Bolder",
                "size": "Small",
                "wrap": True,
                "spacing": "Small",
            }
        )
    if r.informational_notes:
        items.append(
            {
                "type": "TextBlock",
                "text": "**참고**  "
                + "  ".join(f"ⓘ {info}" for info in r.informational_notes),
                "color": "Accent",
                "weight": "Bolder",
                "size": "Small",
                "wrap": True,
                "spacing": "Small",
            }
        )
    if r.note:
        items.append(
            {
                "type": "TextBlock",
                "text": f"📝 {r.note}",
                "isSubtle": True,
                "size": "Small",
                "wrap": True,
                "spacing": "Small",
            }
        )
    return {
        "type": "Container",
        "style": container_style,
        "bleed": False,
        "spacing": "Medium",
        "items": items,
    }


def _pill_columns(
    fail_count: int, insufficient_count: int, ok_count: int, trigger_kind: str
) -> dict[str, Any] | None:
    """이메일 헤더의 상태 pill 행과 동치 — Container.style 로 색상을 표현한다."""
    cols: list[dict[str, Any]] = []

    def _pill(label: str, count: int, style: str) -> dict[str, Any]:
        return {
            "type": "Column",
            "width": "auto",
            "style": style,
            "items": [
                {
                    "type": "TextBlock",
                    "text": f"{label}  {count}",
                    "weight": "Bolder",
                    "size": "Small",
                    "spacing": "None",
                }
            ],
        }

    if fail_count:
        cols.append(_pill("FAIL", fail_count, "attention"))
    if insufficient_count:
        cols.append(_pill("INSUFFICIENT", insufficient_count, "warning"))
    if ok_count and trigger_kind == "report":
        cols.append(_pill("OK", ok_count, "good"))
    if not cols:
        return None
    return {"type": "ColumnSet", "spacing": "Small", "columns": cols}


def build_teams_card(
    *, trigger_kind: str, expected: datetime, actual: datetime, rows: list[TemplateRow]
) -> dict[str, Any]:
    """Build an Adaptive Card v1.5 payload suitable for an Incoming Webhook.

    레이아웃은 이메일 HTML 과 동치 — 헤더(트리거 라벨 + 제목 + 예정/실측 KST + 상태 pill)
    이후 카드별 (제목 + 상태 + 배치 메타 라인 + 2단 비교 + 단일 증감 라인 + 사유/노트).
    """
    fail, insufficient, ok = _bucket_rows(rows)
    summary = build_email_subject(
        trigger_kind=trigger_kind, fail_count=len(fail), expected=expected
    )
    trigger_label = "일일 리포트" if trigger_kind == "report" else "점검 알림"

    body: list[dict[str, Any]] = [
        {
            "type": "TextBlock",
            "text": trigger_label,
            "isSubtle": True,
            "size": "Small",
            "spacing": "None",
        },
        {
            "type": "TextBlock",
            "size": "Large",
            "weight": "Bolder",
            "text": summary,
            "color": "Attention" if fail else "Good",
            "wrap": True,
            "spacing": "Small",
        },
        {
            "type": "TextBlock",
            "isSubtle": True,
            "size": "Small",
            "spacing": "Small",
            "text": f"예정 점검 {_to_kst(expected)} KST · 실측 점검 {_to_kst(actual)} KST",
            "wrap": True,
        },
    ]
    pill_row = _pill_columns(len(fail), len(insufficient), len(ok), trigger_kind)
    if pill_row is not None:
        body.append(pill_row)

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
        for r in fail:
            body.append(_build_card_container(r, "fail"))

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
        for r in insufficient:
            body.append(_build_card_container(r, "insufficient_history"))

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
        for r in ok:
            body.append(_build_card_container(r, "ok"))

    return {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.5",
                    # Teams 전용 확장: 채팅창 폭에 맞춰 카드 전체 폭으로 렌더.
                    # 기본 stage 폭(~520px) 에서는 ColumnSet 이 좁아 보이는 문제 회피.
                    "msteams": {"width": "Full"},
                    "body": body,
                },
            }
        ],
    }
