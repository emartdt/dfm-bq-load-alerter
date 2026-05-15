"""alert_policy.cleanup_time 컬럼 추가 — 이력 정리 잡 실행 시각.

이력 보관일 수(retention_days)에 따른 cleanup 잡의 실행 시각을 정책으로
제어할 수 있도록 한다. 기본값 03:00 KST.

Revision ID: 0014
Revises: 0013
Create Date: 2026-05-15
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "alert_policy",
        sa.Column(
            "cleanup_time",
            sa.Time(),
            nullable=False,
            server_default="03:00",
            comment=(
                "이력 정리(cleanup) 잡의 실행 시각 (KST). "
                "retention_days 보다 오래된 check_snapshots/alert_events 를 삭제한다."
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column("alert_policy", "cleanup_time")
