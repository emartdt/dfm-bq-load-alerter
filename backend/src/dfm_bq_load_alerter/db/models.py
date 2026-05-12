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

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        comment="테이블 PK (자동 증가).",
    )
    project_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment=(
            "BigQuery 프로젝트 ID. NULL → settings.bq_project_id 폴백. "
            "GCP project ID 형식 (소문자/숫자/하이픈, 6~30자)."
        ),
    )
    dataset: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="모니터링 대상 BigQuery 데이터셋 이름.",
    )
    table_name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="모니터링 대상 BigQuery 테이블 이름 (dataset 내에서 유일).",
    )
    frequency: Mapped[Frequency] = mapped_column(
        Enum(Frequency, name="frequency_enum"),
        nullable=False,
        comment="적재 주기. daily=매일, monthly=매월(batch_day_of_month로 일자 지정).",
    )
    batch_time: Mapped[time] = mapped_column(
        Time,
        nullable=False,
        comment="예정 적재 시각 (KST). 체크 슬롯 계산의 기준이 되는 시각.",
    )
    buffer_minutes: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment=(
            "체크 윈도우 끝점을 batch_time + buffer_minutes 로 결정 (KST). "
            "NULL → alert_policy.default_buffer_minutes 적용."
        ),
    )
    batch_day_of_month: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="월 단위 적재일 (1~31). frequency=monthly 일 때만 의미를 가짐.",
    )
    delta_threshold_percent: Mapped[float | None] = mapped_column(
        Numeric(5, 2),
        nullable=True,
        comment=(
            "행 수 변화율 FAIL 임계치(%, 절대값 기준). "
            "NULL 이면 alert_policy.default_threshold_percent 적용."
        ),
    )
    condition_query: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment=(
            "사용자 정의 SQL 조건식 (BigQuery 표준 SQL). "
            "쿼리 결과가 1행 이상이면 FAIL 로 판정."
        ),
    )
    note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="운영자 메모. 알림 메일/Teams 카드 템플릿에 노출됨 (한국어 권장).",
    )
    cond_buffer_load: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        comment=(
            "버퍼 내 미적재/행 수 0 조건 활성화 여부. "
            "true 이면 deadline 기반 미적재·row_count=0 조건을 평가, false 이면 해당 조건을 무시."
        ),
    )
    cond_delta_rowcount: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        comment="전일/전월 대비 행 수 변화율 임계치 조건 활성화 여부.",
    )
    active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="모니터링 활성화 여부. false 이면 스케줄러 체크 대상에서 제외.",
    )
    ack_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="알림 일시 정지(ack) 만료 시각. 현재 시각 < ack_until 이면 알림 억제.",
    )
    ack_by_user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("bo_users.id", ondelete="SET NULL"),
        nullable=True,
        comment="ack 를 설정한 BO 사용자 FK (감사 추적용).",
    )
    latest_etl_row_count: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        comment=(
            "최근 체크에서 관측된 BigQuery 테이블 행 수. "
            "체크 실행 시 metadata.row_count 로 갱신되며, "
            "조회 실패/미수행 시에는 갱신하지 않는다 (이전 값 유지)."
        ),
    )
    latest_etl_datetime: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment=(
            "최근 체크에서 관측된 BigQuery 테이블의 최종 수정 시각. "
            "체크 실행 시 metadata.last_modified 로 갱신되며, "
            "조회 실패/미수행 시에는 갱신하지 않는다 (이전 값 유지)."
        ),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="레코드 생성 시각 (UTC).",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="레코드 마지막 수정 시각 (UTC).",
    )

    snapshots: Mapped[list[CheckSnapshot]] = relationship(
        back_populates="table", cascade="all,delete-orphan"
    )


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

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        comment="스냅샷 PK (자동 증가).",
    )
    table_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tables.id", ondelete="CASCADE"),
        nullable=False,
        comment="대상 테이블 FK. 테이블 삭제 시 함께 삭제됨.",
    )
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="실제 체크가 수행된 시각 (UTC).",
    )
    expected_check_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment=(
            "본 체크가 처리하기로 예정된 슬롯 시각. "
            "스케줄 슬롯 단위로 동일 슬롯의 중복 체크를 식별할 때 사용."
        ),
    )
    row_count: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        comment="BigQuery 메타데이터로 조회한 행 수. NULL = 조회 실패/미수행.",
    )
    last_modified: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="BigQuery 테이블의 last_modified 메타데이터 (마지막 변경 시각).",
    )
    status: Mapped[CheckStatus] = mapped_column(
        Enum(CheckStatus, name="check_status_enum"),
        nullable=False,
        comment="체크 결과. ok=정상, fail=실패, insufficient_history=비교 가능 이력 부족.",
    )
    failure_reasons: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
        comment="실패 사유 코드 목록 (JSONB 배열). 예: ['not_loaded','row_count_zero'].",
    )
    delta_percent_vs_yesterday: Mapped[float | None] = mapped_column(
        Numeric(8, 2),
        nullable=True,
        comment="전일(또는 전월) 대비 행 수 변화율(%). 음수=감소, 양수=증가.",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="레코드 생성 시각 (UTC).",
    )

    table: Mapped[Table] = relationship(back_populates="snapshots")


class AlertRecipient(Base):
    __tablename__ = "alert_recipients"
    __table_args__ = (UniqueConstraint("email", name="uq_alert_recipients_email"),)

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        comment="이메일 수신자 PK (자동 증가).",
    )
    email: Mapped[str] = mapped_column(
        String(254),
        nullable=False,
        comment="수신자 이메일 주소 (전역 유일, RFC 5321 최대 길이 254).",
    )
    name: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        comment="수신자 표시 이름 (메일 To 헤더 표기용).",
    )
    active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="수신자 활성화 여부. false 이면 송신 대상에서 제외.",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="레코드 생성 시각 (UTC).",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="레코드 마지막 수정 시각 (UTC).",
    )


class TeamsWebhook(Base):
    __tablename__ = "teams_webhooks"
    __table_args__ = (UniqueConstraint("name", name="uq_teams_webhooks_name"),)

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        comment="Teams Webhook PK (자동 증가).",
    )
    name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="Webhook 식별 이름 (전역 유일, 운영자 식별용).",
    )
    webhook_url: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment=(
            "Teams Incoming Webhook URL. 자격 증명으로 취급 — "
            "API 응답 시 반드시 마스킹 후 반환할 것."
        ),
    )
    active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Webhook 활성화 여부. false 이면 송신 대상에서 제외.",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="레코드 생성 시각 (UTC).",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="레코드 마지막 수정 시각 (UTC).",
    )


class AlertEvent(Base):
    __tablename__ = "alert_events"
    __table_args__ = (
        Index("idx_alert_events_status_sent", "status", "sent_at"),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        comment="알림 이벤트 PK (자동 증가).",
    )
    snapshot_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("check_snapshots.id", ondelete="SET NULL"),
        nullable=True,
        comment=(
            "관련 체크 스냅샷 FK. 스냅샷이 삭제되어도 이벤트 이력은 보존하기 위해 SET NULL. "
            "report 트리거 등 스냅샷과 무관한 이벤트는 NULL."
        ),
    )
    trigger_kind: Mapped[TriggerKind] = mapped_column(
        Enum(TriggerKind, name="trigger_kind_enum"),
        nullable=False,
        comment="이벤트 발생 계기. check=정기 체크, report=일일 리포트, ack=ack 동작.",
    )
    channel: Mapped[Channel] = mapped_column(
        Enum(Channel, name="channel_enum"),
        nullable=False,
        comment="송신 채널. email=이메일, teams=Teams Webhook, ack=ack 동작 자체.",
    )
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="실제 송신 시도 시각 (UTC).",
    )
    payload_summary: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="송신한 페이로드 요약 (제목/대상/대표 사유 등). 디버깅 및 사후 추적용.",
    )
    status: Mapped[EventStatus] = mapped_column(
        Enum(EventStatus, name="event_status_enum"),
        nullable=False,
        comment="송신 결과. sent=성공, failed=실패, skipped=정책상 미송신.",
    )
    error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="status=failed 일 때 실패 사유/예외 메시지.",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="레코드 생성 시각 (UTC).",
    )


class ReportRun(Base):
    __tablename__ = "report_runs"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        comment="리포트 실행 PK (자동 증가).",
    )
    run_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="일일 리포트 실행 시각 (UTC).",
    )
    status_summary: Mapped[dict[str, int]] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
        comment=(
            "상태별 테이블 카운트 요약 (JSONB). "
            '예: {"ok": 12, "fail": 3, "insufficient_history": 1}.'
        ),
    )
    sent_to: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        server_default="[]",
        comment="실제 리포트가 송신된 수신처 목록 (JSONB 문자열 배열, 이메일 또는 Webhook 이름).",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="레코드 생성 시각 (UTC).",
    )


class BOUser(Base):
    __tablename__ = "bo_users"
    __table_args__ = (
        UniqueConstraint("keycloak_subject", name="uq_bo_users_keycloak_subject"),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        comment="BO(백오피스) 사용자 PK (자동 증가).",
    )
    keycloak_subject: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Keycloak OIDC sub 클레임 값 (사용자 고유 식별자, 전역 유일).",
    )
    email: Mapped[str | None] = mapped_column(
        String(254),
        nullable=True,
        comment="Keycloak 프로필에서 동기화한 이메일 주소.",
    )
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role_enum"),
        nullable=False,
        default=UserRole.viewer,
        comment="권한 역할. admin=관리(쓰기), viewer=조회 전용. 기본값 viewer.",
    )
    last_login: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="마지막 로그인 성공 시각 (UTC).",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="레코드 생성 시각 (최초 로그인 시각, UTC).",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="레코드 마지막 수정 시각 (UTC).",
    )


class AlertPolicy(Base):
    __tablename__ = "alert_policy"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_alert_policy_singleton"),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        default=1,
        comment="단일 행 보장 PK. 항상 1 (CHECK 제약으로 강제).",
    )
    check_times: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        server_default='["06:00","07:00","08:00","08:20","08:40","09:00"]',
        comment='정기 체크 실행 시각 목록 (JSONB, KST "HH:MM" 문자열 배열).',
    )
    report_time: Mapped[time] = mapped_column(
        Time,
        nullable=False,
        comment="일일 리포트 송신 시각 (KST).",
    )
    dedup_strategy: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="every-hour-resend",
        comment=(
            "중복 알림 방지 전략 코드. "
            "기본 'every-hour-resend' (FAIL 지속 시 시간당 1회 재발송)."
        ),
    )
    default_threshold_percent: Mapped[float] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        default=25.0,
        comment=(
            "전역 기본 행 수 변화율 임계치(%). "
            "테이블별 delta_threshold_percent 가 NULL 일 때 적용."
        ),
    )
    retention_days: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=90,
        comment="check_snapshots/alert_events 보관 일수. 이전 데이터는 정리 작업으로 삭제됨.",
    )
    condition_query_max_bytes: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=104857600,
        comment="사용자 정의 condition_query 의 BigQuery 처리 바이트 상한. 기본 100MiB(104857600).",
    )
    default_buffer_minutes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=30,
        server_default="30",
        comment=(
            "버퍼(분) 전역 기본값. 테이블별 buffer_minutes 가 NULL 일 때 적용. "
            "체크 윈도우 끝점 = batch_time + 이 값."
        ),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="정책 마지막 수정 시각 (UTC).",
    )


class SystemWarning(Base):
    __tablename__ = "system_warnings"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        comment="시스템 경고 PK (자동 증가).",
    )
    severity: Mapped[WarningSeverity] = mapped_column(
        Enum(WarningSeverity, name="warning_severity_enum"),
        nullable=False,
        comment="경고 심각도. info=정보, warning=주의, error=오류.",
    )
    category: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="경고 분류 코드 (예: 'bq_quota', 'smtp_failure', 'leader_lost').",
    )
    message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="운영자에게 노출될 경고 메시지 본문.",
    )
    context: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        server_default="{}",
        comment="추가 컨텍스트 (JSONB). 디버깅용 구조화 데이터.",
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="경고 발생 시각 (UTC).",
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="경고 해소 시각 (UTC). NULL 이면 미해소 상태.",
    )


class BqQueryLog(Base):
    __tablename__ = "bq_query_log"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        comment="BigQuery 쿼리 실행 로그 PK (자동 증가).",
    )
    table_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("tables.id", ondelete="SET NULL"),
        nullable=True,
        comment="관련 테이블 FK. 테이블 삭제 시 로그는 보존(NULL 처리).",
    )
    query_kind: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="쿼리 종류 코드 (예: 'metadata', 'condition_query', 'rowcount').",
    )
    bytes_processed: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
        comment="BigQuery 가 처리한 바이트 수. NULL = 미수집/실패.",
    )
    executed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="쿼리 실행 시각 (UTC).",
    )
    note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="쿼리에 대한 부가 메모 (사용 목적, 트리거 등).",
    )
