"""tables.note column for memo (PR-C).

Adds a free-form note column on each table — operators document context
(예: "월말 결산 BW 적재", "ETL 작업자: data-platform") that the alert
template surfaces alongside the failure reason. The deadline-aware
evaluation logic uses existing `deadline_time`; no schema change required
for that part.

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-07
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tables", sa.Column("note", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("tables", "note")
