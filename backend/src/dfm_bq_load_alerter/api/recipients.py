from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from dfm_bq_load_alerter.auth import require_admin
from dfm_bq_load_alerter.db.models import AlertRecipient
from dfm_bq_load_alerter.db.session import get_session

router = APIRouter(prefix="/api/recipients", tags=["recipients"])


class RecipientIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    name: str | None = Field(default=None, max_length=128)
    active: bool = True


class RecipientPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr | None = None
    name: str | None = Field(default=None, max_length=128)
    active: bool | None = None


class RecipientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    name: str | None
    active: bool
    created_at: datetime
    updated_at: datetime


@router.get("", response_model=list[RecipientOut])
async def list_recipients(
    session: AsyncSession = Depends(get_session),
    _principal: dict = Depends(require_admin),
) -> list[AlertRecipient]:
    rows = (
        await session.execute(select(AlertRecipient).order_by(AlertRecipient.email))
    ).scalars().all()
    return list(rows)


@router.post("", response_model=RecipientOut, status_code=status.HTTP_201_CREATED)
async def create_recipient(
    payload: RecipientIn,
    session: AsyncSession = Depends(get_session),
    _principal: dict = Depends(require_admin),
) -> AlertRecipient:
    recipient = AlertRecipient(**payload.model_dump())
    session.add(recipient)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"email must be unique: {payload.email}",
        ) from exc
    await session.refresh(recipient)
    return recipient


@router.get("/{recipient_id}", response_model=RecipientOut)
async def get_recipient(
    recipient_id: int,
    session: AsyncSession = Depends(get_session),
    _principal: dict = Depends(require_admin),
) -> AlertRecipient:
    recipient = await session.get(AlertRecipient, recipient_id)
    if recipient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return recipient


@router.patch("/{recipient_id}", response_model=RecipientOut)
async def update_recipient(
    recipient_id: int,
    payload: RecipientPatch,
    session: AsyncSession = Depends(get_session),
    _principal: dict = Depends(require_admin),
) -> AlertRecipient:
    recipient = await session.get(AlertRecipient, recipient_id)
    if recipient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(recipient, key, value)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="email already in use",
        ) from exc
    await session.refresh(recipient)
    return recipient


@router.delete(
    "/{recipient_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_recipient(
    recipient_id: int,
    session: AsyncSession = Depends(get_session),
    _principal: dict = Depends(require_admin),
) -> None:
    recipient = await session.get(AlertRecipient, recipient_id)
    if recipient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    await session.delete(recipient)
    await session.commit()
