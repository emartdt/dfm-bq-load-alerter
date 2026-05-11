"""모든 테이블/컬럼에 한국어 COMMENT 부여.

models.py 의 SQLAlchemy `comment=` 정의를 PostgreSQL `COMMENT ON COLUMN` 으로 동기화.
psql `\\d+` / 데이터 카탈로그 도구에서 컬럼 의미를 즉시 확인할 수 있게 함.

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-11
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# (table, column, comment) — 모델 정의와 1:1 동기화.
COLUMN_COMMENTS: list[tuple[str, str, str]] = [
    # tables
    ("tables", "id", "테이블 PK (자동 증가)."),
    ("tables", "dataset", "모니터링 대상 BigQuery 데이터셋 이름."),
    ("tables", "table_name", "모니터링 대상 BigQuery 테이블 이름 (dataset 내에서 유일)."),
    ("tables", "frequency", "적재 주기. daily=매일, monthly=매월(batch_day_of_month로 일자 지정)."),
    ("tables", "batch_time", "예정 적재 시각 (KST). 체크 슬롯 계산의 기준이 되는 시각."),
    ("tables", "deadline_time", "적재 마감 시각 (KST). 이 시각 이후로도 미적재 시 FAIL 후보가 됨."),
    (
        "tables",
        "batch_day_of_month",
        "월 단위 적재일 (1~31). frequency=monthly 일 때만 의미를 가짐.",
    ),
    (
        "tables",
        "delta_threshold_percent",
        "행 수 변화율 FAIL 임계치(%, 절대값 기준). "
        "NULL 이면 alert_policy.default_threshold_percent 적용.",
    ),
    (
        "tables",
        "condition_query",
        "사용자 정의 SQL 조건식 (BigQuery 표준 SQL). "
        "쿼리 결과가 1행 이상이면 FAIL 로 판정.",
    ),
    ("tables", "note", "운영자 메모. 알림 메일/Teams 카드 템플릿에 노출됨 (한국어 권장)."),
    (
        "tables",
        "cond_buffer_load",
        "버퍼 내 미적재/행 수 0 조건 활성화 여부. "
        "true 이면 deadline 기반 미적재·row_count=0 조건을 평가, false 이면 해당 조건을 무시.",
    ),
    (
        "tables",
        "cond_delta_rowcount",
        "전일/전월 대비 행 수 변화율 임계치 조건 활성화 여부.",
    ),
    (
        "tables",
        "cond_inflow_time_drift",
        "유입 시각 드리프트 조건 활성화 여부. "
        "true 이면 오늘 last_modified 시각과 전일 시각 차이를 "
        "inflow_drift_threshold_minutes "
        "(없으면 alert_policy.default_inflow_drift_minutes) 와 비교.",
    ),
    (
        "tables",
        "inflow_drift_threshold_minutes",
        "테이블별 유입 시각 드리프트 임계치(분). NULL 이면 alert_policy 기본값을 사용.",
    ),
    ("tables", "active", "모니터링 활성화 여부. false 이면 스케줄러 체크 대상에서 제외."),
    (
        "tables",
        "group_id",
        "소속 알림 그룹. NULL → 전역 기본 채널(활성 수신자/Webhook 전체) 로 송신, "
        "값이 있으면 해당 그룹의 채널로만 송신.",
    ),
    (
        "tables",
        "ack_until",
        "알림 일시 정지(ack) 만료 시각. 현재 시각 < ack_until 이면 알림 억제.",
    ),
    ("tables", "ack_by_user_id", "ack 를 설정한 BO 사용자 FK (감사 추적용)."),
    ("tables", "created_at", "레코드 생성 시각 (UTC)."),
    ("tables", "updated_at", "레코드 마지막 수정 시각 (UTC)."),
    # check_snapshots
    ("check_snapshots", "id", "스냅샷 PK (자동 증가)."),
    ("check_snapshots", "table_id", "대상 테이블 FK. 테이블 삭제 시 함께 삭제됨."),
    ("check_snapshots", "checked_at", "실제 체크가 수행된 시각 (UTC)."),
    (
        "check_snapshots",
        "expected_check_time",
        "본 체크가 처리하기로 예정된 슬롯 시각. "
        "스케줄 슬롯 단위로 동일 슬롯의 중복 체크를 식별할 때 사용.",
    ),
    (
        "check_snapshots",
        "row_count",
        "BigQuery 메타데이터로 조회한 행 수. NULL = 조회 실패/미수행.",
    ),
    (
        "check_snapshots",
        "last_modified",
        "BigQuery 테이블의 last_modified 메타데이터 (마지막 변경 시각).",
    ),
    (
        "check_snapshots",
        "status",
        "체크 결과. ok=정상, fail=실패, insufficient_history=비교 가능 이력 부족.",
    ),
    (
        "check_snapshots",
        "failure_reasons",
        "실패 사유 코드 목록 (JSONB 배열). 예: ['not_loaded','row_count_zero'].",
    ),
    (
        "check_snapshots",
        "delta_percent_vs_yesterday",
        "전일(또는 전월) 대비 행 수 변화율(%). 음수=감소, 양수=증가.",
    ),
    ("check_snapshots", "created_at", "레코드 생성 시각 (UTC)."),
    # alert_groups
    ("alert_groups", "id", "알림 그룹 PK (자동 증가)."),
    ("alert_groups", "name", "알림 그룹 식별 이름 (전역 유일)."),
    ("alert_groups", "description", "알림 그룹 설명/용도 메모."),
    ("alert_groups", "active", "알림 그룹 사용 여부. false 이면 송신 대상에서 제외."),
    ("alert_groups", "created_at", "레코드 생성 시각 (UTC)."),
    ("alert_groups", "updated_at", "레코드 마지막 수정 시각 (UTC)."),
    # alert_group_recipients
    (
        "alert_group_recipients",
        "group_id",
        "알림 그룹 FK (alert_groups.id). 그룹 삭제 시 매핑 삭제.",
    ),
    (
        "alert_group_recipients",
        "recipient_id",
        "이메일 수신자 FK (alert_recipients.id). 수신자 삭제 시 매핑 삭제.",
    ),
    # alert_group_webhooks
    (
        "alert_group_webhooks",
        "group_id",
        "알림 그룹 FK (alert_groups.id). 그룹 삭제 시 매핑 삭제.",
    ),
    (
        "alert_group_webhooks",
        "webhook_id",
        "Teams Webhook FK (teams_webhooks.id). Webhook 삭제 시 매핑 삭제.",
    ),
    # alert_recipients
    ("alert_recipients", "id", "이메일 수신자 PK (자동 증가)."),
    (
        "alert_recipients",
        "email",
        "수신자 이메일 주소 (전역 유일, RFC 5321 최대 길이 254).",
    ),
    ("alert_recipients", "name", "수신자 표시 이름 (메일 To 헤더 표기용)."),
    (
        "alert_recipients",
        "active",
        "수신자 활성화 여부. false 이면 송신 대상에서 제외.",
    ),
    ("alert_recipients", "created_at", "레코드 생성 시각 (UTC)."),
    ("alert_recipients", "updated_at", "레코드 마지막 수정 시각 (UTC)."),
    # teams_webhooks
    ("teams_webhooks", "id", "Teams Webhook PK (자동 증가)."),
    ("teams_webhooks", "name", "Webhook 식별 이름 (전역 유일, 운영자 식별용)."),
    (
        "teams_webhooks",
        "webhook_url",
        "Teams Incoming Webhook URL. 자격 증명으로 취급 — "
        "API 응답 시 반드시 마스킹 후 반환할 것.",
    ),
    (
        "teams_webhooks",
        "active",
        "Webhook 활성화 여부. false 이면 송신 대상에서 제외.",
    ),
    ("teams_webhooks", "created_at", "레코드 생성 시각 (UTC)."),
    ("teams_webhooks", "updated_at", "레코드 마지막 수정 시각 (UTC)."),
    # alert_events
    ("alert_events", "id", "알림 이벤트 PK (자동 증가)."),
    (
        "alert_events",
        "snapshot_id",
        "관련 체크 스냅샷 FK. 스냅샷이 삭제되어도 이벤트 이력은 보존하기 위해 SET NULL. "
        "report 트리거 등 스냅샷과 무관한 이벤트는 NULL.",
    ),
    (
        "alert_events",
        "trigger_kind",
        "이벤트 발생 계기. check=정기 체크, report=일일 리포트, ack=ack 동작.",
    ),
    (
        "alert_events",
        "channel",
        "송신 채널. email=이메일, teams=Teams Webhook, ack=ack 동작 자체.",
    ),
    ("alert_events", "sent_at", "실제 송신 시도 시각 (UTC)."),
    (
        "alert_events",
        "payload_summary",
        "송신한 페이로드 요약 (제목/대상/대표 사유 등). 디버깅 및 사후 추적용.",
    ),
    (
        "alert_events",
        "status",
        "송신 결과. sent=성공, failed=실패, skipped=정책상 미송신.",
    ),
    ("alert_events", "error", "status=failed 일 때 실패 사유/예외 메시지."),
    ("alert_events", "created_at", "레코드 생성 시각 (UTC)."),
    # report_runs
    ("report_runs", "id", "리포트 실행 PK (자동 증가)."),
    ("report_runs", "run_at", "일일 리포트 실행 시각 (UTC)."),
    (
        "report_runs",
        "status_summary",
        '상태별 테이블 카운트 요약 (JSONB). 예: {"ok": 12, "fail": 3, "insufficient_history": 1}.',
    ),
    (
        "report_runs",
        "sent_to",
        "실제 리포트가 송신된 수신처 목록 (JSONB 문자열 배열, 이메일 또는 Webhook 이름).",
    ),
    ("report_runs", "created_at", "레코드 생성 시각 (UTC)."),
    # bo_users
    ("bo_users", "id", "BO(백오피스) 사용자 PK (자동 증가)."),
    (
        "bo_users",
        "keycloak_subject",
        "Keycloak OIDC sub 클레임 값 (사용자 고유 식별자, 전역 유일).",
    ),
    ("bo_users", "email", "Keycloak 프로필에서 동기화한 이메일 주소."),
    (
        "bo_users",
        "role",
        "권한 역할. admin=관리(쓰기), viewer=조회 전용. 기본값 viewer.",
    ),
    ("bo_users", "last_login", "마지막 로그인 성공 시각 (UTC)."),
    ("bo_users", "created_at", "레코드 생성 시각 (최초 로그인 시각, UTC)."),
    ("bo_users", "updated_at", "레코드 마지막 수정 시각 (UTC)."),
    # alert_policy
    ("alert_policy", "id", "단일 행 보장 PK. 항상 1 (CHECK 제약으로 강제)."),
    (
        "alert_policy",
        "check_times",
        '정기 체크 실행 시각 목록 (JSONB, KST "HH:MM" 문자열 배열).',
    ),
    ("alert_policy", "report_time", "일일 리포트 송신 시각 (KST)."),
    (
        "alert_policy",
        "dedup_strategy",
        "중복 알림 방지 전략 코드. 기본 'every-hour-resend' (FAIL 지속 시 시간당 1회 재발송).",
    ),
    (
        "alert_policy",
        "default_threshold_percent",
        "전역 기본 행 수 변화율 임계치(%). 테이블별 delta_threshold_percent 가 NULL 일 때 적용.",
    ),
    (
        "alert_policy",
        "retention_days",
        "check_snapshots/alert_events 보관 일수. 이전 데이터는 정리 작업으로 삭제됨.",
    ),
    (
        "alert_policy",
        "condition_query_max_bytes",
        "사용자 정의 condition_query 의 BigQuery 처리 바이트 상한. 기본 100MiB(104857600).",
    ),
    (
        "alert_policy",
        "default_inflow_drift_minutes",
        "유입 시각 드리프트 전역 기본 임계치(분). "
        "테이블별 inflow_drift_threshold_minutes 가 NULL 일 때 적용.",
    ),
    ("alert_policy", "updated_at", "정책 마지막 수정 시각 (UTC)."),
    # system_warnings
    ("system_warnings", "id", "시스템 경고 PK (자동 증가)."),
    (
        "system_warnings",
        "severity",
        "경고 심각도. info=정보, warning=주의, error=오류.",
    ),
    (
        "system_warnings",
        "category",
        "경고 분류 코드 (예: 'bq_quota', 'smtp_failure', 'leader_lost').",
    ),
    ("system_warnings", "message", "운영자에게 노출될 경고 메시지 본문."),
    (
        "system_warnings",
        "context",
        "추가 컨텍스트 (JSONB). 디버깅용 구조화 데이터.",
    ),
    ("system_warnings", "occurred_at", "경고 발생 시각 (UTC)."),
    (
        "system_warnings",
        "resolved_at",
        "경고 해소 시각 (UTC). NULL 이면 미해소 상태.",
    ),
    # bq_query_log
    ("bq_query_log", "id", "BigQuery 쿼리 실행 로그 PK (자동 증가)."),
    (
        "bq_query_log",
        "table_id",
        "관련 테이블 FK. 테이블 삭제 시 로그는 보존(NULL 처리).",
    ),
    (
        "bq_query_log",
        "query_kind",
        "쿼리 종류 코드 (예: 'metadata', 'condition_query', 'rowcount').",
    ),
    (
        "bq_query_log",
        "bytes_processed",
        "BigQuery 가 처리한 바이트 수. NULL = 미수집/실패.",
    ),
    ("bq_query_log", "executed_at", "쿼리 실행 시각 (UTC)."),
    ("bq_query_log", "note", "쿼리에 대한 부가 메모 (사용 목적, 트리거 등)."),
]


def upgrade() -> None:
    bind = op.get_bind()
    for table, column, comment in COLUMN_COMMENTS:
        escaped = comment.replace("'", "''")
        bind.exec_driver_sql(
            f"COMMENT ON COLUMN {table}.{column} IS '{escaped}'"
        )


def downgrade() -> None:
    bind = op.get_bind()
    for table, column, _ in COLUMN_COMMENTS:
        bind.exec_driver_sql(f"COMMENT ON COLUMN {table}.{column} IS NULL")
