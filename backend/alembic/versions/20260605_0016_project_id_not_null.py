"""tables.project_id NOT NULL — 폴백 개념 제거 (DPC-1583).

빈 project_id 로 등록된 테이블이 DFM_ALERT_BQ_PROJECT_ID 미설정 환경에서
점검 시점에야 "BigQuery 호출 실패" 로 드러나는 문제를 막기 위해
project_id 를 필수 컬럼으로 전환한다.

기존 NULL 행은 마이그레이션 실행 시점의 DFM_ALERT_BQ_PROJECT_ID 값으로
백필한다. NULL 행이 존재하는데 환경변수가 비어 있으면 명시적으로 실패한다
(운영/개발 DB 모두 2026-06-05 기준 NULL 행 0건 확인됨).

Revision ID: 0016
Revises: 0015
Create Date: 2026-06-05
"""
from __future__ import annotations

import os
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    null_count = conn.execute(
        sa.text("SELECT count(*) FROM tables WHERE project_id IS NULL")
    ).scalar_one()
    if null_count:
        backfill = os.environ.get("DFM_ALERT_BQ_PROJECT_ID", "").strip()
        if not backfill:
            raise RuntimeError(
                f"tables.project_id 가 NULL 인 행이 {null_count}건 있습니다. "
                "백필에 사용할 DFM_ALERT_BQ_PROJECT_ID 를 설정한 뒤 "
                "마이그레이션을 다시 실행하세요."
            )
        conn.execute(
            sa.text(
                "UPDATE tables SET project_id = :project "
                "WHERE project_id IS NULL"
            ),
            {"project": backfill},
        )

    op.alter_column(
        "tables",
        "project_id",
        existing_type=sa.String(64),
        nullable=False,
        comment=(
            "BigQuery 프로젝트 ID (필수). "
            "GCP project ID 형식 (소문자/숫자/하이픈, 6~30자)."
        ),
    )


def downgrade() -> None:
    op.alter_column(
        "tables",
        "project_id",
        existing_type=sa.String(64),
        nullable=True,
        comment=(
            "BigQuery 프로젝트 ID. NULL → settings.bq_project_id 폴백. "
            "GCP project ID 형식 (소문자/숫자/하이픈, 6~30자)."
        ),
    )
