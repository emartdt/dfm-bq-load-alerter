"""tables: 조건 OR 토글 + 유입 시간 임계치, alert_policy: 유입 기본 임계치.

요구의 "조건 종류 (OR 로 설정 가능)" 와 "유입 시간 비교" 를 위한 컬럼.

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-07
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tables",
        sa.Column(
            "cond_buffer_load",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.add_column(
        "tables",
        sa.Column(
            "cond_delta_rowcount",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.add_column(
        "tables",
        sa.Column(
            "cond_inflow_time_drift",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "tables",
        sa.Column(
            "inflow_drift_threshold_minutes",
            sa.Integer(),
            nullable=True,
        ),
    )
    op.add_column(
        "alert_policy",
        sa.Column(
            "default_inflow_drift_minutes",
            sa.Integer(),
            nullable=False,
            server_default="60",
        ),
    )


def downgrade() -> None:
    op.drop_column("alert_policy", "default_inflow_drift_minutes")
    op.drop_column("tables", "inflow_drift_threshold_minutes")
    op.drop_column("tables", "cond_inflow_time_drift")
    op.drop_column("tables", "cond_delta_rowcount")
    op.drop_column("tables", "cond_buffer_load")
