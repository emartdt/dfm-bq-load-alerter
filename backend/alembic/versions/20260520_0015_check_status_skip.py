"""check_status_enum: insufficient_history 제거 → skip 추가.

사양 정렬: 오늘 적재 미완료 + 검증 시각이 batch_time+buffer 이전인 경우를
SKIP 으로 표기하기 위해 enum 을 재정의한다. 기존 insufficient_history 행은
사용자가 사전에 정리하기로 합의되어 있어 데이터 변환은 수행하지 않는다.

PostgreSQL 의 enum 은 값 삭제를 지원하지 않으므로 새 타입을 만들고
컬럼 타입을 교체한 뒤 구 타입을 DROP 한다.

Revision ID: 0015
Revises: 0014
Create Date: 2026-05-20
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE TYPE check_status_enum_new AS ENUM ('ok', 'fail', 'skip')")
    op.execute(
        "ALTER TABLE check_snapshots "
        "ALTER COLUMN status TYPE check_status_enum_new "
        "USING status::text::check_status_enum_new"
    )
    op.execute("DROP TYPE check_status_enum")
    op.execute("ALTER TYPE check_status_enum_new RENAME TO check_status_enum")
    op.execute(
        "COMMENT ON COLUMN check_snapshots.status IS "
        "'체크 결과. ok=정상, fail=실패, "
        "skip=마감(batch_time+buffer) 이전 미적재로 판정 보류.'"
    )


def downgrade() -> None:
    op.execute(
        "CREATE TYPE check_status_enum_old AS ENUM "
        "('ok', 'fail', 'insufficient_history')"
    )
    # skip 행이 있으면 cast 가 실패하므로 사전 정리가 필요하다는 사실을
    # 마이그레이션이 명시적으로 드러내도록 그대로 둔다.
    op.execute(
        "ALTER TABLE check_snapshots "
        "ALTER COLUMN status TYPE check_status_enum_old "
        "USING status::text::check_status_enum_old"
    )
    op.execute("DROP TYPE check_status_enum")
    op.execute("ALTER TYPE check_status_enum_old RENAME TO check_status_enum")
    op.execute(
        "COMMENT ON COLUMN check_snapshots.status IS "
        "'체크 결과. ok=정상, fail=실패, "
        "insufficient_history=비교 가능 이력 부족.'"
    )
