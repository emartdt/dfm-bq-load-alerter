"""Teams Incoming Webhook POST.

All transport-level failures (DNS, connect timeout, read timeout, TLS errors)
are wrapped in `TeamsPostError` so the caller (dispatcher) can record a
failed AlertEvent without bubbling up to a 500. The dispatcher catches
`TeamsPostError` only — un-wrapped httpx exceptions used to escape and
break the endpoint, see https://github.com/emartdt/dfm-bq-load-alerter PR fix.
"""
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
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(webhook_url, json=payload)
    except httpx.RequestError as exc:
        raise TeamsPostError(
            f"Teams webhook request failed ({type(exc).__name__}): {exc}"
        ) from exc
    if response.status_code >= 400:
        raise TeamsPostError(
            f"Teams webhook returned {response.status_code}: {response.text[:200]}"
        )
