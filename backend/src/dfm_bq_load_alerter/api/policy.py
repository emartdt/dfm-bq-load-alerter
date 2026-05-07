"""Alert Policy 싱글톤 조회/수정 API.

`alert_policy.id = 1` 한 행이 시스템 전역 정책을 보관 (CHECK constraint 가
다른 id 를 막음). 행이 없으면 GET 시점에 기본값으로 생성한다.
"""
from __future__ import annotations

from datetime import datetime, time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from dfm_bq_load_alerter.auth import require_admin
from dfm_bq_load_alerter.db.models import AlertPolicy
from dfm_bq_load_alerter.db.session import get_session

router = APIRouter(prefix="/api/policy", tags=["policy"])


class PolicyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    check_times: list[str]
    report_time: time
    dedup_strategy: str
    default_threshold_percent: float
    retention_days: int
    condition_query_max_bytes: int
    updated_at: datetime


class PolicyPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    check_times: list[str] | None = Field(
        default=None,
        description='HH:MM strings, e.g. ["06:00","07:00","08:00"]',
    )
    report_time: time | None = None
    dedup_strategy: str | None = Field(default=None, max_length=32)
    default_threshold_percent: float | None = Field(default=None, gt=0, le=100)
    retention_days: int | None = Field(default=None, ge=1, le=3650)
    condition_query_max_bytes: int | None = Field(default=None, ge=1024)


def _validate_check_times(values: list[str]) -> None:
    for raw in values:
        try:
            time.fromisoformat(raw)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"invalid check_times entry: {raw!r}",
            ) from exc


async def _get_or_create(session: AsyncSession) -> AlertPolicy:
    policy = await session.get(AlertPolicy, 1)
    if policy is None:
        policy = AlertPolicy(
            id=1,
            check_times=[
                "06:00",
                "07:00",
                "08:00",
                "08:20",
                "08:40",
                "09:00",
            ],
            report_time=time(7, 45),
            dedup_strategy="every-hour-resend",
            default_threshold_percent=25.0,
            retention_days=90,
            condition_query_max_bytes=104857600,
        )
        session.add(policy)
        await session.commit()
        await session.refresh(policy)
    return policy


def _serialize(policy: AlertPolicy) -> PolicyOut:
    return PolicyOut(
        check_times=list(policy.check_times),
        report_time=policy.report_time,
        dedup_strategy=policy.dedup_strategy,
        default_threshold_percent=float(policy.default_threshold_percent),
        retention_days=policy.retention_days,
        condition_query_max_bytes=policy.condition_query_max_bytes,
        updated_at=policy.updated_at,
    )


@router.get("", response_model=PolicyOut)
async def get_policy(
    session: Annotated[AsyncSession, Depends(get_session)],
    _principal: Annotated[dict, Depends(require_admin)],
) -> PolicyOut:
    return _serialize(await _get_or_create(session))


@router.patch("", response_model=PolicyOut)
async def patch_policy(
    payload: PolicyPatch,
    session: Annotated[AsyncSession, Depends(get_session)],
    _principal: Annotated[dict, Depends(require_admin)],
) -> PolicyOut:
    policy = await _get_or_create(session)
    updates = payload.model_dump(exclude_unset=True)
    if "check_times" in updates and updates["check_times"] is not None:
        _validate_check_times(updates["check_times"])
    for key, value in updates.items():
        setattr(policy, key, value)
    await session.commit()
    await session.refresh(policy)
    return _serialize(policy)
