"""teams_webhooks: replace secret_ref with webhook_url

The BO API (PR-A) registers Teams webhooks directly. The pre-PR-A
``secret_ref`` env-var indirection had no callers (no row in
``teams_webhooks`` ever existed in production), so this revision is a
clean column swap rather than a data migration.

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-07
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "teams_webhooks",
        sa.Column("webhook_url", sa.Text(), nullable=True),
    )
    # No live rows yet; backfill is a no-op. Enforce NOT NULL afterwards.
    op.execute(
        "UPDATE teams_webhooks SET webhook_url = '' WHERE webhook_url IS NULL"
    )
    op.alter_column("teams_webhooks", "webhook_url", nullable=False)
    op.drop_column("teams_webhooks", "secret_ref")


def downgrade() -> None:
    op.add_column(
        "teams_webhooks",
        sa.Column(
            "secret_ref",
            sa.String(length=253),
            nullable=False,
            server_default="",
        ),
    )
    op.alter_column("teams_webhooks", "secret_ref", server_default=None)
    op.drop_column("teams_webhooks", "webhook_url")
