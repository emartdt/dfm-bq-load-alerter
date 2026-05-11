"""buffer_minutes 도입 — deadline_time / inflow_drift 조건 제거.

요구사항 변경:
  - tables.deadline_time 제거. 대신 tables.buffer_minutes 도입 (NULL → 정책 기본값).
    체크 윈도우 = [batch_time, batch_time + buffer_minutes].
  - 유입 시각 드리프트 조건 (cond_inflow_time_drift, inflow_drift_threshold_minutes)
    제거. 알람 조건은 (버퍼 내 미적재 / row_count=0) 와 (Δ% 임계치) 두 종류만 남는다.
  - alert_policy.default_inflow_drift_minutes 제거.
    대신 default_buffer_minutes (기본 30) 도입.

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-11
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # tables: + buffer_minutes, - deadline_time, - cond_inflow_time_drift,
    #         - inflow_drift_threshold_minutes
    op.add_column(
        "tables",
        sa.Column(
            "buffer_minutes",
            sa.Integer(),
            nullable=True,
            comment=(
                "체크 윈도우 끝점을 batch_time + buffer_minutes 로 결정. "
                "NULL → alert_policy.default_buffer_minutes 적용 (기본 30분)."
            ),
        ),
    )
    op.drop_column("tables", "deadline_time")
    op.drop_column("tables", "cond_inflow_time_drift")
    op.drop_column("tables", "inflow_drift_threshold_minutes")

    # alert_policy: + default_buffer_minutes, - default_inflow_drift_minutes
    op.add_column(
        "alert_policy",
        sa.Column(
            "default_buffer_minutes",
            sa.Integer(),
            nullable=False,
            server_default="30",
            comment=(
                "버퍼(분) 전역 기본값. 테이블별 buffer_minutes 가 NULL 일 때 적용. "
                "체크 윈도우 끝점 = batch_time + 이 값."
            ),
        ),
    )
    op.drop_column("alert_policy", "default_inflow_drift_minutes")


def downgrade() -> None:
    op.add_column(
        "alert_policy",
        sa.Column(
            "default_inflow_drift_minutes",
            sa.Integer(),
            nullable=False,
            server_default="60",
        ),
    )
    op.drop_column("alert_policy", "default_buffer_minutes")

    op.add_column(
        "tables",
        sa.Column(
            "inflow_drift_threshold_minutes",
            sa.Integer(),
            nullable=True,
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
            "deadline_time",
            sa.Time(),
            nullable=False,
            server_default="09:00",
        ),
    )
    op.drop_column("tables", "buffer_minutes")
