"""tables.latest_etl_row_count 도입 — 최근 관측 행 수 캐시.

각 체크 실행 시 fetch_metadata 의 row_count 로 갱신되어,
Tables 페이지에서 마지막으로 관측된 ETL 행 수를 즉시 노출한다.
metadata.row_count 가 NULL 이면 기존 값을 유지한다.

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-11
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tables",
        sa.Column(
            "latest_etl_row_count",
            sa.BigInteger(),
            nullable=True,
            comment=(
                "최근 체크에서 관측된 BigQuery 테이블 행 수. "
                "체크 실행 시 metadata.row_count 로 갱신되며, "
                "조회 실패/미수행 시에는 갱신하지 않는다 (이전 값 유지)."
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column("tables", "latest_etl_row_count")
