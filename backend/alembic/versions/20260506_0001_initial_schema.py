"""initial schema for v0.2.x

Tables: tables, check_snapshots, alert_recipients, teams_webhooks, alert_events,
report_runs, bo_users, alert_policy, system_warnings, bq_query_log.

Revision ID: 0001
Revises:
Create Date: 2026-05-06

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    frequency_enum = sa.Enum("daily", "monthly", name="frequency_enum")
    check_status_enum = sa.Enum("ok", "fail", "insufficient_history", name="check_status_enum")
    trigger_kind_enum = sa.Enum("check", "report", "ack", name="trigger_kind_enum")
    channel_enum = sa.Enum("email", "teams", "ack", name="channel_enum")
    event_status_enum = sa.Enum("sent", "failed", "skipped", name="event_status_enum")
    user_role_enum = sa.Enum("admin", "viewer", name="user_role_enum")
    warning_severity_enum = sa.Enum("info", "warning", "error", name="warning_severity_enum")

    bind = op.get_bind()
    for e in (
        frequency_enum,
        check_status_enum,
        trigger_kind_enum,
        channel_enum,
        event_status_enum,
        user_role_enum,
        warning_severity_enum,
    ):
        e.create(bind, checkfirst=True)

    op.create_table(
        "bo_users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("keycloak_subject", sa.String(255), nullable=False),
        sa.Column("email", sa.String(254), nullable=True),
        sa.Column("role", user_role_enum, nullable=False, server_default="viewer"),
        sa.Column("last_login", sa.DateTime(timezone=True), nullable=True),
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
        sa.UniqueConstraint("keycloak_subject", name="uq_bo_users_keycloak_subject"),
    )

    op.create_table(
        "tables",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("dataset", sa.String(128), nullable=False),
        sa.Column("table_name", sa.String(128), nullable=False),
        sa.Column("frequency", frequency_enum, nullable=False),
        sa.Column("batch_time", sa.Time, nullable=False),
        sa.Column("deadline_time", sa.Time, nullable=False),
        sa.Column("batch_day_of_month", sa.Integer, nullable=True),
        sa.Column("delta_threshold_percent", sa.Numeric(5, 2), nullable=True),
        sa.Column("condition_query", sa.Text, nullable=True),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("ack_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "ack_by_user_id",
            sa.Integer,
            sa.ForeignKey("bo_users.id", ondelete="SET NULL"),
            nullable=True,
        ),
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
        sa.UniqueConstraint("dataset", "table_name", name="uq_tables_dataset_table"),
        sa.CheckConstraint(
            "frequency = 'monthly' OR batch_day_of_month IS NULL",
            name="ck_tables_monthly_dom",
        ),
        sa.CheckConstraint(
            "delta_threshold_percent IS NULL OR "
            "(delta_threshold_percent > 0 AND delta_threshold_percent <= 100)",
            name="ck_tables_delta_range",
        ),
    )

    op.create_table(
        "check_snapshots",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "table_id",
            sa.Integer,
            sa.ForeignKey("tables.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expected_check_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("row_count", sa.BigInteger, nullable=True),
        sa.Column("last_modified", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", check_status_enum, nullable=False),
        sa.Column(
            "failure_reasons",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("delta_percent_vs_yesterday", sa.Numeric(8, 2), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_check_snapshots_table_time",
        "check_snapshots",
        ["table_id", "checked_at"],
    )

    op.create_table(
        "alert_recipients",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("name", sa.String(128), nullable=True),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
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
        sa.UniqueConstraint("email", name="uq_alert_recipients_email"),
    )

    op.create_table(
        "teams_webhooks",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("secret_ref", sa.String(253), nullable=False),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
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
        sa.UniqueConstraint("name", name="uq_teams_webhooks_name"),
    )

    op.create_table(
        "alert_events",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "snapshot_id",
            sa.Integer,
            sa.ForeignKey("check_snapshots.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("trigger_kind", trigger_kind_enum, nullable=False),
        sa.Column("channel", channel_enum, nullable=False),
        sa.Column(
            "sent_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("payload_summary", sa.Text, nullable=True),
        sa.Column("status", event_status_enum, nullable=False),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_alert_events_status_sent", "alert_events", ["status", "sent_at"]
    )

    op.create_table(
        "report_runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "run_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "status_summary",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "sent_to",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "alert_policy",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "check_times",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text(
                """'["06:00","07:00","08:00","08:20","08:40","09:00"]'::jsonb"""
            ),
        ),
        sa.Column("report_time", sa.Time, nullable=False, server_default=sa.text("'07:45'")),
        sa.Column(
            "dedup_strategy",
            sa.String(32),
            nullable=False,
            server_default="every-hour-resend",
        ),
        sa.Column(
            "default_threshold_percent",
            sa.Numeric(5, 2),
            nullable=False,
            server_default="25.0",
        ),
        sa.Column("retention_days", sa.Integer, nullable=False, server_default="90"),
        sa.Column(
            "condition_query_max_bytes",
            sa.BigInteger,
            nullable=False,
            server_default="104857600",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("id = 1", name="ck_alert_policy_singleton"),
    )
    op.execute(
        """
        INSERT INTO alert_policy (id, report_time)
        VALUES (1, '07:45')
        ON CONFLICT DO NOTHING
        """
    )

    op.create_table(
        "system_warnings",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("severity", warning_severity_enum, nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column(
            "context",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "bq_query_log",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "table_id",
            sa.Integer,
            sa.ForeignKey("tables.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("query_kind", sa.String(32), nullable=False),
        sa.Column("bytes_processed", sa.BigInteger, nullable=True),
        sa.Column(
            "executed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("note", sa.Text, nullable=True),
    )


def downgrade() -> None:
    op.drop_table("bq_query_log")
    op.drop_table("system_warnings")
    op.drop_table("alert_policy")
    op.drop_table("report_runs")
    op.drop_index("idx_alert_events_status_sent", table_name="alert_events")
    op.drop_table("alert_events")
    op.drop_table("teams_webhooks")
    op.drop_table("alert_recipients")
    op.drop_index("idx_check_snapshots_table_time", table_name="check_snapshots")
    op.drop_table("check_snapshots")
    op.drop_table("tables")
    op.drop_table("bo_users")

    bind = op.get_bind()
    for name in (
        "warning_severity_enum",
        "user_role_enum",
        "event_status_enum",
        "channel_enum",
        "trigger_kind_enum",
        "check_status_enum",
        "frequency_enum",
    ):
        sa.Enum(name=name).drop(bind, checkfirst=True)
