from __future__ import annotations

from datetime import datetime, time

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from dfm_bq_load_alerter.auth import require_admin
from dfm_bq_load_alerter.db.models import Frequency, Table
from dfm_bq_load_alerter.db.session import get_session

router = APIRouter(prefix="/api/tables", tags=["tables"])


class TableIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str | None = Field(default=None, min_length=1, max_length=64)
    dataset: str = Field(min_length=1, max_length=128)
    table_name: str = Field(min_length=1, max_length=128)
    frequency: Frequency
    batch_time: time
    buffer_minutes: int | None = Field(default=None, ge=1, le=1440)
    batch_day_of_month: int | None = Field(default=None, ge=1, le=31)
    delta_threshold_percent: float | None = Field(default=None, gt=0, le=100)
    condition_query: str | None = None
    note: str | None = None
    cond_buffer_load: bool = True
    cond_delta_rowcount: bool = True
    active: bool = True


class TablePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str | None = Field(default=None, min_length=1, max_length=64)
    frequency: Frequency | None = None
    batch_time: time | None = None
    buffer_minutes: int | None = Field(default=None, ge=1, le=1440)
    batch_day_of_month: int | None = Field(default=None, ge=1, le=31)
    delta_threshold_percent: float | None = Field(default=None, gt=0, le=100)
    condition_query: str | None = None
    note: str | None = None
    cond_buffer_load: bool | None = None
    cond_delta_rowcount: bool | None = None
    active: bool | None = None


class TableOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: str | None
    dataset: str
    table_name: str
    frequency: Frequency
    batch_time: time
    buffer_minutes: int | None
    batch_day_of_month: int | None
    delta_threshold_percent: float | None
    condition_query: str | None
    note: str | None
    cond_buffer_load: bool
    cond_delta_rowcount: bool
    active: bool
    latest_etl_row_count: int | None
    latest_etl_datetime: datetime | None
    created_at: datetime
    updated_at: datetime


class BulkTableEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    day: int | None = Field(default=None, ge=1, le=31)
    time: time
    type: Frequency

    @field_validator("time", mode="before")
    @classmethod
    def _zero_pad_hour(cls, value: object) -> object:
        if isinstance(value, str) and len(value) >= 1 and value[1:2] == ":":
            return "0" + value
        return value


class BulkTablesIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset: str = Field(min_length=1, max_length=128)
    project_id: str | None = Field(default=None, min_length=1, max_length=64)
    buffer_minutes: int | None = Field(default=None, ge=1, le=1440)
    tables: dict[str, BulkTableEntry] = Field(min_length=1)


class BulkSkipped(BaseModel):
    table_name: str
    reason: str


class BulkTablesResult(BaseModel):
    created: list[TableOut]
    skipped: list[BulkSkipped]


@router.get("", response_model=list[TableOut])
async def list_tables(
    session: AsyncSession = Depends(get_session),
    _principal: dict = Depends(require_admin),
) -> list[Table]:
    rows = (
        await session.execute(select(Table).order_by(Table.dataset, Table.table_name))
    ).scalars().all()
    return list(rows)


@router.post(
    "/bulk",
    response_model=BulkTablesResult,
    status_code=status.HTTP_201_CREATED,
)
async def bulk_create_tables(
    payload: BulkTablesIn,
    session: AsyncSession = Depends(get_session),
    _principal: dict = Depends(require_admin),
) -> BulkTablesResult:
    """`{table_name: {day, time, type}}` 포맷으로 다건 등록.

    - `type=daily` → `batch_day_of_month`는 무시됨 (NULL 저장).
    - `type=monthly` → `day` 필수.
    - 이미 존재하는 (dataset, table_name) 은 skipped 로 반환되며 다른 행은 계속 등록.
    """
    names = list(payload.tables.keys())
    existing_rows = await session.execute(
        select(Table.table_name).where(
            Table.dataset == payload.dataset,
            Table.table_name.in_(names),
        )
    )
    existing: set[str] = set(existing_rows.scalars().all())

    skipped: list[BulkSkipped] = []
    to_insert: list[Table] = []
    for name, entry in payload.tables.items():
        if name in existing:
            skipped.append(BulkSkipped(table_name=name, reason="already exists"))
            continue
        if entry.type == Frequency.monthly and entry.day is None:
            skipped.append(
                BulkSkipped(
                    table_name=name,
                    reason="batch_day_of_month required for monthly",
                )
            )
            continue
        to_insert.append(
            Table(
                project_id=payload.project_id,
                dataset=payload.dataset,
                table_name=name,
                frequency=entry.type,
                batch_time=entry.time,
                buffer_minutes=payload.buffer_minutes,
                batch_day_of_month=(
                    entry.day if entry.type == Frequency.monthly else None
                ),
            )
        )

    if to_insert:
        session.add_all(to_insert)
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"bulk insert failed: {exc.orig}",
            ) from exc
        for table in to_insert:
            await session.refresh(table)

    return BulkTablesResult(
        created=[TableOut.model_validate(t) for t in to_insert],
        skipped=skipped,
    )


@router.post("", response_model=TableOut, status_code=status.HTTP_201_CREATED)
async def create_table(
    payload: TableIn,
    session: AsyncSession = Depends(get_session),
    _principal: dict = Depends(require_admin),
) -> Table:
    if payload.frequency == Frequency.monthly and payload.batch_day_of_month is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="batch_day_of_month is required for monthly frequency",
        )
    table = Table(**payload.model_dump())
    session.add(table)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"(dataset, table_name) must be unique: {payload.dataset}.{payload.table_name}",
        ) from exc
    await session.refresh(table)
    return table


@router.get("/{table_id}", response_model=TableOut)
async def get_table(
    table_id: int,
    session: AsyncSession = Depends(get_session),
    _principal: dict = Depends(require_admin),
) -> Table:
    table = await session.get(Table, table_id)
    if table is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return table


@router.patch("/{table_id}", response_model=TableOut)
async def update_table(
    table_id: int,
    payload: TablePatch,
    session: AsyncSession = Depends(get_session),
    _principal: dict = Depends(require_admin),
) -> Table:
    table = await session.get(Table, table_id)
    if table is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(table, key, value)
    await session.commit()
    await session.refresh(table)
    return table


@router.delete(
    "/{table_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_table(
    table_id: int,
    session: AsyncSession = Depends(get_session),
    _principal: dict = Depends(require_admin),
) -> None:
    table = await session.get(Table, table_id)
    if table is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    await session.delete(table)
    await session.commit()
