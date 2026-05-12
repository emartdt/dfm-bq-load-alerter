"""tables.latest_etl_datetime 도입 — 최근 관측 last_modified 캐시.

각 체크 실행 시 fetch_metadata 의 last_modified 로 갱신되어,
Tables 페이지에서 마지막으로 관측된 BigQuery 테이블 최종 수정 시각을
즉시 노출한다. metadata.last_modified 가 NULL 이면 기존 값을 유지한다.

Revision ID: 0011
Revises: 0010
Create Date: 2026-05-12
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tables",
        sa.Column(
            "latest_etl_datetime",
            sa.DateTime(timezone=True),
            nullable=True,
            comment=(
                "최근 체크에서 관측된 BigQuery 테이블의 최종 수정 시각. "
                "체크 실행 시 metadata.last_modified 로 갱신되며, "
                "조회 실패/미수행 시에는 갱신하지 않는다 (이전 값 유지)."
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column("tables", "latest_etl_datetime")
