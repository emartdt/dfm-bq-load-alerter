"""Teams Incoming Webhook POST."""
from __future__ import annotations

import logging
from typing import Any

import httpx

log = logging.getLogger(__name__)


class TeamsPostError(RuntimeError):
    pass


async def post_teams_card(*, webhook_url: str, payload: dict[str, Any]) -> None:
    if not webhook_url:
        raise ValueError("webhook_url is empty")
    log.info("teams webhook POST")
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(webhook_url, json=payload)
    if response.status_code >= 400:
        raise TeamsPostError(
            f"Teams webhook returned {response.status_code}: {response.text[:200]}"
        )
