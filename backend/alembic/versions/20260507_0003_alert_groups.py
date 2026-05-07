"""alert groups domain — `alert_groups` + member join tables + tables.group_id.

Adds the per-group alert routing structure required by 요구사항의 "그룹별로
알람 채널 설정 가능 / 그룹/테이블 별 세팅 가능". A `tables.group_id` of
NULL keeps the pre-rev3 behaviour (global default channels).

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-07
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "alert_groups",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("name", name="uq_alert_groups_name"),
    )

    op.create_table(
        "alert_group_recipients",
        sa.Column(
            "group_id",
            sa.Integer,
            sa.ForeignKey("alert_groups.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "recipient_id",
            sa.Integer,
            sa.ForeignKey("alert_recipients.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    op.create_table(
        "alert_group_webhooks",
        sa.Column(
            "group_id",
            sa.Integer,
            sa.ForeignKey("alert_groups.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "webhook_id",
            sa.Integer,
            sa.ForeignKey("teams_webhooks.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    op.add_column(
        "tables",
        sa.Column(
            "group_id",
            sa.Integer,
            sa.ForeignKey("alert_groups.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "idx_tables_group_id",
        "tables",
        ["group_id"],
        postgresql_where=sa.text("group_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("idx_tables_group_id", table_name="tables")
    op.drop_column("tables", "group_id")
    op.drop_table("alert_group_webhooks")
    op.drop_table("alert_group_recipients")
    op.drop_table("alert_groups")
