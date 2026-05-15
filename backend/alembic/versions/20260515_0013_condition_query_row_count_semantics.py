"""tables.condition_query: redefine as custom row_count SQL

기존 코멘트는 "쿼리 결과가 1행 이상이면 FAIL" 이었으나 실제 코드 경로에서
사용되지 않은 미구현 컬럼이었다. 이번 변경으로 의미를 재정의한다:
사용자 정의 SQL 이 주어지면 그 결과(단일 행/단일 정수 컬럼)를 row_count 로
사용한다. NULL 이면 기존대로 `__TABLES__.row_count` 를 사용.

Revision ID: 0013
Revises: 0012
Create Date: 2026-05-15
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


NEW_COMMENT = (
    "사용자 정의 row_count 산출 SQL (BigQuery 표준 SQL). "
    "NULL 이면 __TABLES__.row_count 를 사용. 값이 있으면 SELECT/WITH 로 시작하는 "
    "단일 행·단일 정수 컬럼 쿼리를 실행해 그 결과를 row_count 로 사용한다. "
    "alert_policy.condition_query_max_bytes 처리량 상한 적용."
)
OLD_COMMENT = (
    "사용자 정의 SQL 조건식 (BigQuery 표준 SQL). "
    "쿼리 결과가 1행 이상이면 FAIL 로 판정."
)


def upgrade() -> None:
    op.alter_column(
        "tables",
        "condition_query",
        existing_type=sa.Text(),
        existing_nullable=True,
        comment=NEW_COMMENT,
    )


def downgrade() -> None:
    op.alter_column(
        "tables",
        "condition_query",
        existing_type=sa.Text(),
        existing_nullable=True,
        comment=OLD_COMMENT,
    )
