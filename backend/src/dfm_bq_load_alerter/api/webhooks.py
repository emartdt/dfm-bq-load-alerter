"""Teams Incoming Webhook 등록 / 관리 API.

webhook_url 은 발신 자격 증명에 해당하므로 응답에서는 항상 마스킹된 값을
돌려준다. 변경(POST/PATCH) 시에만 평문 URL 을 받는다.
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, HttpUrl
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from dfm_bq_load_alerter.auth import require_admin
from dfm_bq_load_alerter.db.models import TeamsWebhook
from dfm_bq_load_alerter.db.session import get_session
from dfm_bq_load_alerter.notifier.teams import TeamsPostError, post_teams_card
from dfm_bq_load_alerter.notifier.template import ALERT_SUBJECT_PREFIX

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


def _mask(url: str) -> str:
    """Return a non-reversible preview of a webhook URL.

    Format: ``https://host/<first8>…<last4>``. Empty input → empty string.
    """
    if not url:
        return ""
    schemehost, _, path = url.partition("/")
    if not path and "://" in url:
        # url was just scheme://host
        return url
    base = url.split("://", 1)
    if len(base) == 2:
        scheme = base[0] + "://"
        rest = base[1]
    else:
        scheme = ""
        rest = url
    host, _, tail = rest.partition("/")
    if len(tail) <= 12:
        return f"{scheme}{host}/{'*' * len(tail)}"
    return f"{scheme}{host}/{tail[:8]}…{tail[-4:]}"


class WebhookIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    webhook_url: HttpUrl
    active: bool = True


class WebhookPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=128)
    webhook_url: HttpUrl | None = None
    active: bool | None = None


class WebhookOut(BaseModel):
    id: int
    name: str
    webhook_url_masked: str
    active: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, hook: TeamsWebhook) -> WebhookOut:
        return cls(
            id=hook.id,
            name=hook.name,
            webhook_url_masked=_mask(hook.webhook_url),
            active=hook.active,
            created_at=hook.created_at,
            updated_at=hook.updated_at,
        )


@router.get("", response_model=list[WebhookOut])
async def list_webhooks(
    session: Annotated[AsyncSession, Depends(get_session)],
    _principal: Annotated[dict, Depends(require_admin)],
) -> list[WebhookOut]:
    rows = (
        await session.execute(select(TeamsWebhook).order_by(TeamsWebhook.name))
    ).scalars().all()
    return [WebhookOut.from_model(r) for r in rows]


@router.post("", response_model=WebhookOut, status_code=status.HTTP_201_CREATED)
async def create_webhook(
    payload: WebhookIn,
    session: Annotated[AsyncSession, Depends(get_session)],
    _principal: Annotated[dict, Depends(require_admin)],
) -> WebhookOut:
    hook = TeamsWebhook(
        name=payload.name,
        webhook_url=str(payload.webhook_url),
        active=payload.active,
    )
    session.add(hook)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"name must be unique: {payload.name}",
        ) from exc
    await session.refresh(hook)
    return WebhookOut.from_model(hook)


@router.patch("/{webhook_id}", response_model=WebhookOut)
async def update_webhook(
    webhook_id: int,
    payload: WebhookPatch,
    session: Annotated[AsyncSession, Depends(get_session)],
    _principal: Annotated[dict, Depends(require_admin)],
) -> WebhookOut:
    hook = await session.get(TeamsWebhook, webhook_id)
    if hook is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    updates = payload.model_dump(exclude_unset=True)
    if "webhook_url" in updates and updates["webhook_url"] is not None:
        updates["webhook_url"] = str(updates["webhook_url"])
    for key, value in updates.items():
        setattr(hook, key, value)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="name already in use",
        ) from exc
    await session.refresh(hook)
    return WebhookOut.from_model(hook)


@router.delete(
    "/{webhook_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_webhook(
    webhook_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    _principal: Annotated[dict, Depends(require_admin)],
) -> None:
    hook = await session.get(TeamsWebhook, webhook_id)
    if hook is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    await session.delete(hook)
    await session.commit()


class WebhookTestResult(BaseModel):
    ok: bool
    detail: str


@router.post("/{webhook_id}/test", response_model=WebhookTestResult)
async def test_webhook(
    webhook_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    _principal: Annotated[dict, Depends(require_admin)],
) -> WebhookTestResult:
    """등록된 webhook URL 로 테스트 카드를 1회 송신해 연결 상태를 확인."""
    hook = await session.get(TeamsWebhook, webhook_id)
    if hook is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if not hook.webhook_url:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="webhook_url is empty",
        )
    payload = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.5",
                    "body": [
                        {
                            "type": "TextBlock",
                            "size": "Large",
                            "weight": "Bolder",
                            "text": f"{ALERT_SUBJECT_PREFIX} Webhook 연결 테스트",
                        },
                        {
                            "type": "TextBlock",
                            "isSubtle": True,
                            "text": (
                                f"name={hook.name} · {datetime.now().isoformat(timespec='seconds')}"
                            ),
                        },
                    ],
                },
            }
        ],
    }
    try:
        await post_teams_card(webhook_url=hook.webhook_url, payload=payload)
    except TeamsPostError as exc:
        return WebhookTestResult(ok=False, detail=str(exc))
    return WebhookTestResult(ok=True, detail="sent")
