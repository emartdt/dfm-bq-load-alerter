"""순수 알람 발송 채널 테스트 API.

BigQuery 점검(run-now) / 일일 리포트(report-now)와 무관하게, 등록된
SMTP 설정과 Teams Incoming Webhook이 실제로 도달하는지만 빠르게 확인
하기 위한 엔드포인트. 더미 본문을 만들어 활성 수신자·webhook 으로
1회 송신한 뒤 채널별 결과(sent/failed/skipped)를 그대로 반환한다.
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from dfm_bq_load_alerter.auth import require_admin
from dfm_bq_load_alerter.db.models import AlertRecipient, TeamsWebhook
from dfm_bq_load_alerter.db.session import get_session
from dfm_bq_load_alerter.notifier.email import (
    EmailNotConfiguredError,
    send_email,
)
from dfm_bq_load_alerter.notifier.teams import TeamsPostError, post_teams_card

router = APIRouter(prefix="/api/notifier", tags=["notifier"])
KST = ZoneInfo("Asia/Seoul")


class TestSendIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recipient_ids: list[int] | None = Field(
        default=None,
        description="지정 시 해당 AlertRecipient ID 로만 발송. 빈 값/생략 시 활성 수신자 전체.",
    )
    webhook_ids: list[int] | None = Field(
        default=None,
        description="지정 시 해당 TeamsWebhook ID 로만 발송. 빈 값/생략 시 활성 웹훅 전체.",
    )
    message: str | None = Field(
        default=None,
        max_length=500,
        description="본문에 함께 표시할 사용자 메모(선택).",
    )


class TestSendResult(BaseModel):
    channel: Literal["email", "teams"]
    target: str
    status: Literal["sent", "failed", "skipped"]
    detail: str | None = None


class TestSendResponse(BaseModel):
    triggered_at: datetime
    results: list[TestSendResult]
    sent: int
    failed: int
    skipped: int


def _build_email_body(now: datetime, message: str | None) -> tuple[str, str]:
    ts = now.astimezone(KST).strftime("%Y-%m-%d %H:%M:%S")
    subject = f"[DFM Alert] 채널 발송 테스트 ({ts} KST)"
    note_html = (
        f'<p style="color:#444;">메모: {message}</p>' if message else ""
    )
    html = (
        '<!DOCTYPE html><html lang="ko"><body '
        'style="font-family:system-ui,-apple-system,\'Segoe UI\',sans-serif;color:#1a1a1a;">'
        f'<h2>DFM Alert 채널 발송 테스트</h2>'
        f'<p>이 메일은 SMTP 설정 검증용으로 발송된 더미 메시지입니다.</p>'
        f'<p>발송 시각(KST): <b>{ts}</b></p>'
        f'{note_html}'
        '<hr><p style="font-size:12px;color:#888;">dfm-bq-load-alerter · /api/notifier/test-send</p>'
        '</body></html>'
    )
    return subject, html


def _build_teams_card(now: datetime, message: str | None) -> dict:
    ts = now.astimezone(KST).strftime("%Y-%m-%d %H:%M:%S")
    body: list[dict] = [
        {
            "type": "TextBlock",
            "size": "Large",
            "weight": "Bolder",
            "text": "[DFM Alert] 채널 발송 테스트",
        },
        {
            "type": "TextBlock",
            "isSubtle": True,
            "spacing": "None",
            "text": f"발송 시각(KST): {ts}",
        },
        {
            "type": "TextBlock",
            "wrap": True,
            "text": "이 카드는 Teams Incoming Webhook 검증용 더미 메시지입니다.",
        },
    ]
    if message:
        body.append(
            {
                "type": "TextBlock",
                "wrap": True,
                "isSubtle": True,
                "text": f"메모: {message}",
            }
        )
    return {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.5",
                    "body": body,
                },
            }
        ],
    }


@router.post("/test-send", response_model=TestSendResponse)
async def test_send(
    session: Annotated[AsyncSession, Depends(get_session)],
    _principal: Annotated[dict, Depends(require_admin)],
    payload: TestSendIn | None = None,
) -> TestSendResponse:
    """이메일/Teams 채널 발송이 실제로 도달하는지 검증.

    - 입력: AlertRecipient / TeamsWebhook ID 목록 및 메모. 모두 DB 등록값만 사용.
            미지정 시 active=True 인 자원 전부.
    - 출력: 채널별 송신 결과. AlertEvent 테이블에는 적재하지 않는다.
    """
    payload = payload or TestSendIn()
    now = datetime.now(tz=KST)
    subject, html = _build_email_body(now, payload.message)
    card = _build_teams_card(now, payload.message)
    results: list[TestSendResult] = []

    # Resolve email recipients — DB(AlertRecipient)만 참조
    if payload.recipient_ids:
        stmt = select(AlertRecipient.email).where(
            AlertRecipient.id.in_(payload.recipient_ids)
        )
    else:
        stmt = select(AlertRecipient.email).where(AlertRecipient.active.is_(True))
    recipients = list((await session.execute(stmt)).scalars().all())

    if not recipients:
        results.append(
            TestSendResult(
                channel="email",
                target="(none)",
                status="skipped",
                detail="활성 수신자가 없습니다.",
            )
        )
    else:
        target_label = ", ".join(recipients)
        try:
            await send_email(to=recipients, subject=subject, html=html)
            results.append(
                TestSendResult(channel="email", target=target_label, status="sent")
            )
        except EmailNotConfiguredError as exc:
            results.append(
                TestSendResult(
                    channel="email",
                    target=target_label,
                    status="skipped",
                    detail=str(exc),
                )
            )
        except Exception as exc:  # noqa: BLE001 — surface to caller
            results.append(
                TestSendResult(
                    channel="email",
                    target=target_label,
                    status="failed",
                    detail=f"{type(exc).__name__}: {exc}",
                )
            )

    # Resolve Teams webhooks
    stmt = select(TeamsWebhook).where(TeamsWebhook.active.is_(True))
    if payload.webhook_ids:
        stmt = select(TeamsWebhook).where(TeamsWebhook.id.in_(payload.webhook_ids))
    webhooks = (await session.execute(stmt)).scalars().all()

    if not webhooks:
        results.append(
            TestSendResult(
                channel="teams",
                target="(none)",
                status="skipped",
                detail="대상 웹훅이 없습니다.",
            )
        )
    else:
        for hook in webhooks:
            if not hook.webhook_url:
                results.append(
                    TestSendResult(
                        channel="teams",
                        target=hook.name,
                        status="skipped",
                        detail="webhook_url is empty",
                    )
                )
                continue
            try:
                await post_teams_card(webhook_url=hook.webhook_url, payload=card)
                results.append(
                    TestSendResult(channel="teams", target=hook.name, status="sent")
                )
            except TeamsPostError as exc:
                results.append(
                    TestSendResult(
                        channel="teams",
                        target=hook.name,
                        status="failed",
                        detail=str(exc),
                    )
                )

    sent = sum(1 for r in results if r.status == "sent")
    failed = sum(1 for r in results if r.status == "failed")
    skipped = sum(1 for r in results if r.status == "skipped")
    return TestSendResponse(
        triggered_at=now,
        results=results,
        sent=sent,
        failed=failed,
        skipped=skipped,
    )
