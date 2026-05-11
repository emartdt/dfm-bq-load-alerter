"""tables.project_id 도입 — 테이블별 BigQuery 프로젝트 지정.

NULL → settings.bq_project_id (환경변수 DFM_ALERT_BQ_PROJECT_ID) 가 폴백.
값이 있으면 해당 프로젝트의 BigQuery 클라이언트로 메타데이터를 조회한다.

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-11
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tables",
        sa.Column(
            "project_id",
            sa.String(64),
            nullable=True,
            comment=(
                "BigQuery 프로젝트 ID. NULL → settings.bq_project_id 폴백. "
                "GCP project ID 형식 (소문자/숫자/하이픈, 6~30자)."
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column("tables", "project_id")
