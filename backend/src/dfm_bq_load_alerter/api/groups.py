"""알람 그룹 CRUD + 멤버(수신자/웹훅/테이블) 관리 API.

그룹은 알림 채널을 묶는 단위다. tables.group_id 가 가리키는 그룹의 채널
(이메일 수신자 + Teams 웹훅) 로만 알림이 전달된다. 그룹 미지정 테이블은
기존 글로벌 동작(모든 active 수신자/웹훅).

멤버십은 `PUT` 으로 전체 집합을 교체한다. 부분 변경(POST/DELETE) 보다
프런트가 단순해지고 동시 편집 충돌 시 후-쓰기-우선 의 동작이 명확해진다.
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from dfm_bq_load_alerter.auth import require_admin
from dfm_bq_load_alerter.db.models import (
    AlertGroup,
    AlertGroupRecipient,
    AlertGroupWebhook,
    AlertRecipient,
    Table,
    TeamsWebhook,
)
from dfm_bq_load_alerter.db.session import get_session

router = APIRouter(prefix="/api/groups", tags=["groups"])


class GroupIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    active: bool = True


class GroupPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    active: bool | None = None


class GroupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    active: bool
    table_count: int
    recipient_count: int
    webhook_count: int
    created_at: datetime
    updated_at: datetime


class IdSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ids: list[int] = Field(default_factory=list)


async def _build_group_out(session: AsyncSession, group: AlertGroup) -> GroupOut:
    table_count = (
        await session.execute(
            select(func.count(Table.id)).where(Table.group_id == group.id)
        )
    ).scalar_one()
    recipient_count = (
        await session.execute(
            select(func.count(AlertGroupRecipient.recipient_id)).where(
                AlertGroupRecipient.group_id == group.id
            )
        )
    ).scalar_one()
    webhook_count = (
        await session.execute(
            select(func.count(AlertGroupWebhook.webhook_id)).where(
                AlertGroupWebhook.group_id == group.id
            )
        )
    ).scalar_one()
    return GroupOut(
        id=group.id,
        name=group.name,
        description=group.description,
        active=group.active,
        table_count=table_count,
        recipient_count=recipient_count,
        webhook_count=webhook_count,
        created_at=group.created_at,
        updated_at=group.updated_at,
    )


@router.get("", response_model=list[GroupOut])
async def list_groups(
    session: Annotated[AsyncSession, Depends(get_session)],
    _principal: Annotated[dict, Depends(require_admin)],
) -> list[GroupOut]:
    rows = (
        await session.execute(select(AlertGroup).order_by(AlertGroup.name))
    ).scalars().all()
    return [await _build_group_out(session, g) for g in rows]


@router.post("", response_model=GroupOut, status_code=status.HTTP_201_CREATED)
async def create_group(
    payload: GroupIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    _principal: Annotated[dict, Depends(require_admin)],
) -> GroupOut:
    group = AlertGroup(**payload.model_dump())
    session.add(group)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"name must be unique: {payload.name}",
        ) from exc
    await session.refresh(group)
    return await _build_group_out(session, group)


@router.get("/{group_id}", response_model=GroupOut)
async def get_group(
    group_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    _principal: Annotated[dict, Depends(require_admin)],
) -> GroupOut:
    group = await session.get(AlertGroup, group_id)
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return await _build_group_out(session, group)


@router.patch("/{group_id}", response_model=GroupOut)
async def update_group(
    group_id: int,
    payload: GroupPatch,
    session: Annotated[AsyncSession, Depends(get_session)],
    _principal: Annotated[dict, Depends(require_admin)],
) -> GroupOut:
    group = await session.get(AlertGroup, group_id)
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(group, key, value)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="name already in use",
        ) from exc
    await session.refresh(group)
    return await _build_group_out(session, group)


@router.delete(
    "/{group_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_group(
    group_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    _principal: Annotated[dict, Depends(require_admin)],
) -> None:
    group = await session.get(AlertGroup, group_id)
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    # tables.group_id → NULL via ON DELETE SET NULL; memberships cascade.
    await session.delete(group)
    await session.commit()


# --- Membership ----------------------------------------------------------

class MemberIds(BaseModel):
    """Membership response: ordered list of FK ids."""

    ids: list[int]


@router.get("/{group_id}/recipients", response_model=MemberIds)
async def list_group_recipients(
    group_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    _principal: Annotated[dict, Depends(require_admin)],
) -> MemberIds:
    if await session.get(AlertGroup, group_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    ids = (
        await session.execute(
            select(AlertGroupRecipient.recipient_id)
            .where(AlertGroupRecipient.group_id == group_id)
            .order_by(AlertGroupRecipient.recipient_id)
        )
    ).scalars().all()
    return MemberIds(ids=list(ids))


@router.put("/{group_id}/recipients", response_model=MemberIds)
async def replace_group_recipients(
    group_id: int,
    payload: IdSet,
    session: Annotated[AsyncSession, Depends(get_session)],
    _principal: Annotated[dict, Depends(require_admin)],
) -> MemberIds:
    if await session.get(AlertGroup, group_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    requested = sorted(set(payload.ids))
    if requested:
        existing = (
            await session.execute(
                select(AlertRecipient.id).where(AlertRecipient.id.in_(requested))
            )
        ).scalars().all()
        missing = set(requested) - set(existing)
        if missing:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"unknown recipient_id(s): {sorted(missing)}",
            )
    await session.execute(
        delete(AlertGroupRecipient).where(AlertGroupRecipient.group_id == group_id)
    )
    for rid in requested:
        session.add(AlertGroupRecipient(group_id=group_id, recipient_id=rid))
    await session.commit()
    return MemberIds(ids=requested)


@router.get("/{group_id}/webhooks", response_model=MemberIds)
async def list_group_webhooks(
    group_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    _principal: Annotated[dict, Depends(require_admin)],
) -> MemberIds:
    if await session.get(AlertGroup, group_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    ids = (
        await session.execute(
            select(AlertGroupWebhook.webhook_id)
            .where(AlertGroupWebhook.group_id == group_id)
            .order_by(AlertGroupWebhook.webhook_id)
        )
    ).scalars().all()
    return MemberIds(ids=list(ids))


@router.put("/{group_id}/webhooks", response_model=MemberIds)
async def replace_group_webhooks(
    group_id: int,
    payload: IdSet,
    session: Annotated[AsyncSession, Depends(get_session)],
    _principal: Annotated[dict, Depends(require_admin)],
) -> MemberIds:
    if await session.get(AlertGroup, group_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    requested = sorted(set(payload.ids))
    if requested:
        existing = (
            await session.execute(
                select(TeamsWebhook.id).where(TeamsWebhook.id.in_(requested))
            )
        ).scalars().all()
        missing = set(requested) - set(existing)
        if missing:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"unknown webhook_id(s): {sorted(missing)}",
            )
    await session.execute(
        delete(AlertGroupWebhook).where(AlertGroupWebhook.group_id == group_id)
    )
    for wid in requested:
        session.add(AlertGroupWebhook(group_id=group_id, webhook_id=wid))
    await session.commit()
    return MemberIds(ids=requested)


@router.get("/{group_id}/tables", response_model=MemberIds)
async def list_group_tables(
    group_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    _principal: Annotated[dict, Depends(require_admin)],
) -> MemberIds:
    if await session.get(AlertGroup, group_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    ids = (
        await session.execute(
            select(Table.id).where(Table.group_id == group_id).order_by(Table.id)
        )
    ).scalars().all()
    return MemberIds(ids=list(ids))


@router.put("/{group_id}/tables", response_model=MemberIds)
async def replace_group_tables(
    group_id: int,
    payload: IdSet,
    session: Annotated[AsyncSession, Depends(get_session)],
    _principal: Annotated[dict, Depends(require_admin)],
) -> MemberIds:
    """그룹의 테이블 멤버십을 전체 교체.

    이전 그룹에 있던 테이블이지만 이번 payload 에 없는 테이블은 group_id 가
    NULL 로 reset 된다 (해당 테이블만; 다른 그룹과는 무관).
    """
    if await session.get(AlertGroup, group_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    requested = sorted(set(payload.ids))
    if requested:
        existing = (
            await session.execute(
                select(Table.id).where(Table.id.in_(requested))
            )
        ).scalars().all()
        missing = set(requested) - set(existing)
        if missing:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"unknown table_id(s): {sorted(missing)}",
            )
    # Reset previously-assigned tables not in the new set.
    rows = (
        await session.execute(
            select(Table).where(Table.group_id == group_id)
        )
    ).scalars().all()
    for t in rows:
        if t.id not in requested:
            t.group_id = None
    # Assign newly-requested tables.
    if requested:
        rows = (
            await session.execute(
                select(Table).where(Table.id.in_(requested))
            )
        ).scalars().all()
        for t in rows:
            t.group_id = group_id
    await session.commit()
    return MemberIds(ids=requested)
