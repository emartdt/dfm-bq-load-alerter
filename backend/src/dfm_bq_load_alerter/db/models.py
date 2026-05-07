from __future__ import annotations

import enum
from datetime import datetime, time

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from dfm_bq_load_alerter.db.base import Base


class Frequency(enum.StrEnum):
    daily = "daily"
    monthly = "monthly"


class CheckStatus(enum.StrEnum):
    ok = "ok"
    fail = "fail"
    insufficient_history = "insufficient_history"


class TriggerKind(enum.StrEnum):
    check = "check"
    report = "report"
    ack = "ack"


class Channel(enum.StrEnum):
    email = "email"
    teams = "teams"
    ack = "ack"


class EventStatus(enum.StrEnum):
    sent = "sent"
    failed = "failed"
    skipped = "skipped"


class UserRole(enum.StrEnum):
    admin = "admin"
    viewer = "viewer"


class WarningSeverity(enum.StrEnum):
    info = "info"
    warning = "warning"
    error = "error"


class Table(Base):
    __tablename__ = "tables"
    __table_args__ = (
        UniqueConstraint("dataset", "table_name", name="uq_tables_dataset_table"),
        CheckConstraint(
            "frequency = 'monthly' OR batch_day_of_month IS NULL",
            name="ck_tables_monthly_dom",
        ),
        CheckConstraint(
            "delta_threshold_percent IS NULL OR "
            "(delta_threshold_percent > 0 AND delta_threshold_percent <= 100)",
            name="ck_tables_delta_range",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dataset: Mapped[str] = mapped_column(String(128), nullable=False)
    table_name: Mapped[str] = mapped_column(String(128), nullable=False)
    frequency: Mapped[Frequency] = mapped_column(
        Enum(Frequency, name="frequency_enum"), nullable=False
    )
    batch_time: Mapped[time] = mapped_column(Time, nullable=False)
    deadline_time: Mapped[time] = mapped_column(Time, nullable=False)
    batch_day_of_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    delta_threshold_percent: Mapped[float | None] = mapped_column(
        Numeric(5, 2), nullable=True
    )
    condition_query: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Operator memo surfaced in alert templates (KR text 권장).",
    )
    cond_buffer_load: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        comment=(
            "When true: deadline-aware not-loaded / row_count_zero conditions "
            "are evaluated. False → those conditions are suppressed."
        ),
    )
    cond_delta_rowcount: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        comment="When true: delta_percent_vs_yesterday/last-month threshold check is applied.",
    )
    cond_inflow_time_drift: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment=(
            "When true: today's last_modified clock-time vs yesterday's is "
            "compared against `inflow_drift_threshold_minutes` "
            "(falls back to alert_policy.default_inflow_drift_minutes)."
        ),
    )
    inflow_drift_threshold_minutes: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Per-table override for inflow drift threshold (minutes).",
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    group_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("alert_groups.id", ondelete="SET NULL"),
        nullable=True,
        comment=(
            "Optional alert group. NULL → global default channels (all active "
            "recipients/webhooks). Set → only the group's channels receive "
            "alerts for this table."
        ),
    )
    ack_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ack_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("bo_users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    snapshots: Mapped[list[CheckSnapshot]] = relationship(
        back_populates="table", cascade="all,delete-orphan"
    )
    group: Mapped[AlertGroup | None] = relationship(back_populates="tables")


class CheckSnapshot(Base):
    __tablename__ = "check_snapshots"
    __table_args__ = (
        Index(
            "idx_check_snapshots_table_time",
            "table_id",
            "checked_at",
            postgresql_using="btree",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    table_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tables.id", ondelete="CASCADE"), nullable=False
    )
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expected_check_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    row_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_modified: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[CheckStatus] = mapped_column(
        Enum(CheckStatus, name="check_status_enum"), nullable=False
    )
    failure_reasons: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    delta_percent_vs_yesterday: Mapped[float | None] = mapped_column(
        Numeric(8, 2), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    table: Mapped[Table] = relationship(back_populates="snapshots")


class AlertGroup(Base):
    """Logical grouping of tables that share notification channels.

    Tables with `group_id` set route alerts to the channels (email recipients +
    Teams webhooks) attached to this group. Tables without `group_id` use the
    global default — all active recipients/webhooks. The dispatcher buckets
    snapshots per group and sends one bundled message to each bucket's
    channels (rev 3 P0 — required for "그룹별로 알람 채널 설정 가능").
    """

    __tablename__ = "alert_groups"
    __table_args__ = (UniqueConstraint("name", name="uq_alert_groups_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    tables: Mapped[list[Table]] = relationship(back_populates="group")
    recipients: Mapped[list[AlertRecipient]] = relationship(
        secondary="alert_group_recipients", back_populates="groups"
    )
    webhooks: Mapped[list[TeamsWebhook]] = relationship(
        secondary="alert_group_webhooks", back_populates="groups"
    )


class AlertGroupRecipient(Base):
    __tablename__ = "alert_group_recipients"

    group_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("alert_groups.id", ondelete="CASCADE"),
        primary_key=True,
    )
    recipient_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("alert_recipients.id", ondelete="CASCADE"),
        primary_key=True,
    )


class AlertGroupWebhook(Base):
    __tablename__ = "alert_group_webhooks"

    group_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("alert_groups.id", ondelete="CASCADE"),
        primary_key=True,
    )
    webhook_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("teams_webhooks.id", ondelete="CASCADE"),
        primary_key=True,
    )


class AlertRecipient(Base):
    __tablename__ = "alert_recipients"
    __table_args__ = (UniqueConstraint("email", name="uq_alert_recipients_email"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    groups: Mapped[list[AlertGroup]] = relationship(
        secondary="alert_group_recipients", back_populates="recipients"
    )


class TeamsWebhook(Base):
    __tablename__ = "teams_webhooks"
    __table_args__ = (UniqueConstraint("name", name="uq_teams_webhooks_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    webhook_url: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment=(
            "Incoming webhook URL. Treated as a credential — API responses "
            "MUST mask the value before returning to clients."
        ),
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    groups: Mapped[list[AlertGroup]] = relationship(
        secondary="alert_group_webhooks", back_populates="webhooks"
    )


class AlertEvent(Base):
    __tablename__ = "alert_events"
    __table_args__ = (
        Index("idx_alert_events_status_sent", "status", "sent_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("check_snapshots.id", ondelete="SET NULL"), nullable=True
    )
    trigger_kind: Mapped[TriggerKind] = mapped_column(
        Enum(TriggerKind, name="trigger_kind_enum"), nullable=False
    )
    channel: Mapped[Channel] = mapped_column(
        Enum(Channel, name="channel_enum"), nullable=False
    )
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    payload_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[EventStatus] = mapped_column(
        Enum(EventStatus, name="event_status_enum"), nullable=False
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ReportRun(Base):
    __tablename__ = "report_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    status_summary: Mapped[dict[str, int]] = mapped_column(
        JSONB, nullable=False, server_default="{}"
    )
    sent_to: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default="[]")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class BOUser(Base):
    __tablename__ = "bo_users"
    __table_args__ = (
        UniqueConstraint("keycloak_subject", name="uq_bo_users_keycloak_subject"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    keycloak_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role_enum"), nullable=False, default=UserRole.viewer
    )
    last_login: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class AlertPolicy(Base):
    __tablename__ = "alert_policy"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_alert_policy_singleton"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    check_times: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        server_default='["06:00","07:00","08:00","08:20","08:40","09:00"]',
    )
    report_time: Mapped[time] = mapped_column(Time, nullable=False)
    dedup_strategy: Mapped[str] = mapped_column(
        String(32), nullable=False, default="every-hour-resend"
    )
    default_threshold_percent: Mapped[float] = mapped_column(
        Numeric(5, 2), nullable=False, default=25.0
    )
    retention_days: Mapped[int] = mapped_column(Integer, nullable=False, default=90)
    condition_query_max_bytes: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=104857600
    )
    default_inflow_drift_minutes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=60,
        server_default="60",
        comment=(
            "System-wide default for `cond_inflow_time_drift` threshold. "
            "Per-table value (`tables.inflow_drift_threshold_minutes`) "
            "overrides when set."
        ),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class SystemWarning(Base):
    __tablename__ = "system_warnings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    severity: Mapped[WarningSeverity] = mapped_column(
        Enum(WarningSeverity, name="warning_severity_enum"), nullable=False
    )
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class BqQueryLog(Base):
    __tablename__ = "bq_query_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    table_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("tables.id", ondelete="SET NULL"), nullable=True
    )
    query_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    bytes_processed: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
