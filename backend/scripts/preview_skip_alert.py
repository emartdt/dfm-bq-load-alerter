"""SKIP 상태의 점검/리포트 알림 본문을 파일로 렌더해 눈으로 확인한다.

DB·SMTP·Teams Webhook 없이 동작한다. dispatcher 의 필터링
(check·report 모두 SKIP 제외) 효과를 실제 HTML/Teams 카드 페이로드로
시각화한다.

사용법:
    uv run python scripts/preview_skip_alert.py

출력 경로 (`/tmp/skip_preview/`):
    - check.html / report.html  — 이메일 본문 (브라우저로 열어 확인)
    - check_teams.json / report_teams.json  — Adaptive Card 페이로드
"""
from __future__ import annotations

import json
import os
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

# Settings() 가 import 시점에 인스턴스화되므로 dummy env 주입.
os.environ.setdefault("DFM_ALERT_OIDC_ISSUER", "https://example.test/realms/TEST")
os.environ.setdefault("DFM_ALERT_OIDC_CLIENT_ID", "preview-client")
os.environ.setdefault("DFM_ALERT_OIDC_CLIENT_SECRET", "preview-secret")
os.environ.setdefault("DFM_ALERT_SESSION_SECRET_KEY", "0" * 64)
os.environ.setdefault("DFM_ALERT_SCHEDULER_ENABLED", "false")
os.environ.setdefault("DFM_ALERT_ENVIRONMENT", "development")

from dfm_bq_load_alerter.db.models import CheckStatus  # noqa: E402
from dfm_bq_load_alerter.notifier.dispatcher import (  # noqa: E402
    DispatchSnapshot,
    _to_template_row,
)
from dfm_bq_load_alerter.notifier.template import (  # noqa: E402
    build_email_html,
    build_teams_cards,
)

KST = ZoneInfo("Asia/Seoul")
NOW = datetime(2026, 5, 20, 5, 0, tzinfo=KST)


def _snap(
    status: CheckStatus,
    *,
    table: str,
    failure_reasons: list[str] | None = None,
    today_row_count: int | None = 950,
    today_last_modified: datetime | None = None,
) -> DispatchSnapshot:
    return DispatchSnapshot(
        snapshot_id=None,
        dataset="bw",
        table_name=table,
        expected_check_time=NOW,
        actual_check_time=NOW,
        yesterday_row_count=1000,
        today_row_count=today_row_count,
        delta_percent_vs_yesterday=-5.0 if today_row_count else None,
        status=status,
        failure_reasons=failure_reasons or [],
        today_last_modified=today_last_modified,
        yesterday_last_modified=datetime(2026, 5, 19, 5, 0, tzinfo=KST),
        project="dfm",
        batch_time=time(5, 0),
        informational_notes=[],
        buffer_minutes=30,
    )


SNAPSHOTS = [
    _snap(
        CheckStatus.fail,
        table="ORDER_FAIL",
        failure_reasons=["오늘 미적재"],
        today_row_count=None,
    ),
    _snap(
        CheckStatus.skip,
        table="ORDER_PENDING",
        today_row_count=None,
    ),
    _snap(
        CheckStatus.ok,
        table="ORDER_OK",
        today_last_modified=datetime(2026, 5, 20, 4, 50, tzinfo=KST),
    ),
]


def main() -> None:
    out_dir = Path("/tmp/skip_preview")
    out_dir.mkdir(parents=True, exist_ok=True)

    for trigger in ("check", "report"):
        # dispatcher.dispatch() 의 필터링 규칙을 그대로 재현 — check·report
        # 모두 SKIP 은 본문에서 제외한다.
        filtered = [s for s in SNAPSHOTS if s.status != CheckStatus.skip]
        rows = [_to_template_row(s) for s in filtered]

        subject, html = build_email_html(
            trigger_kind=trigger, expected=NOW, actual=NOW, rows=rows
        )
        html_path = out_dir / f"{trigger}.html"
        html_path.write_text(html, encoding="utf-8")

        teams_cards = build_teams_cards(
            trigger_kind=trigger, expected=NOW, actual=NOW, rows=rows
        )
        teams_path = out_dir / f"{trigger}_teams.json"
        teams_path.write_text(
            json.dumps(teams_cards, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        status_breakdown = {
            "fail": sum(1 for s in filtered if s.status == CheckStatus.fail),
            "skip": sum(1 for s in filtered if s.status == CheckStatus.skip),
            "ok": sum(1 for s in filtered if s.status == CheckStatus.ok),
        }
        print(
            f"[{trigger}] {subject}\n"
            f"  본문 카드 status 분포: {status_breakdown}\n"
            f"  email html : {html_path}\n"
            f"  teams card : {teams_path}\n"
        )


if __name__ == "__main__":
    main()
