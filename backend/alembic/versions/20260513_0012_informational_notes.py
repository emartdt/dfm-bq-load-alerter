"""check_snapshots: add informational_notes column

FAIL 판정과 무관한 운영 안내(예: 이전 배치 기록 부재로 증감률 비교 생략) 를
``failure_reasons`` 와 분리해 별도 컬럼으로 영속화한다. 알람 템플릿에서
색상/아이콘으로 구분 렌더하기 위함.

Revision ID: 0012
Revises: 0011
Create Date: 2026-05-13
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "check_snapshots",
        sa.Column(
            "informational_notes",
            JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
            comment=(
                "FAIL 판정과 무관한 운영 안내 메시지 목록 (JSONB 배열). "
                "예: ['이전 배치 기록 없음 - 증감률 비교 생략']. 알람 템플릿에서 "
                "failure_reasons(빨강) 과 시각적으로 구분 렌더된다."
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column("check_snapshots", "informational_notes")
