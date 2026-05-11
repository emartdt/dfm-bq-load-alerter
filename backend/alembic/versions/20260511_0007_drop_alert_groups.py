"""drop alert_groups domain — remove per-group routing.

요구사항 변경: 그룹 단위 알람 채널 라우팅 제거.
이후 모든 알람은 active=true 인 수신자/Webhook 전체(글로벌 풀)로 송신된다.
테이블별 알람 조건 설정은 `tables.cond_*` 컬럼으로 유지된다.

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-11
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("idx_tables_group_id", table_name="tables")
    op.drop_constraint("tables_group_id_fkey", "tables", type_="foreignkey")
    op.drop_column("tables", "group_id")
    op.drop_table("alert_group_webhooks")
    op.drop_table("alert_group_recipients")
    op.drop_table("alert_groups")


def downgrade() -> None:
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
