"""세션 쿠키 기반 인증 dependency."""
from __future__ import annotations

import time
from typing import Any

from fastapi import HTTPException, Request, Response, status

from dfm_bq_load_alerter.auth import oidc

REFRESH_THRESHOLD_SECONDS = 300


def _clear_session(request: Request) -> None:
    request.session.clear()


def _get_tokens(request: Request) -> dict[str, Any] | None:
    tokens = request.session.get("tokens")
    if not isinstance(tokens, dict):
        return None
    return tokens


def _get_user(request: Request) -> dict[str, Any] | None:
    user = request.session.get("user")
    if not isinstance(user, dict):
        return None
    return user


async def get_current_user(request: Request, response: Response) -> dict[str, Any]:
    user = _get_user(request)
    tokens = _get_tokens(request)

    if user is None or tokens is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    expires_at = int(tokens.get("expires_at", 0))
    if expires_at - int(time.time()) < REFRESH_THRESHOLD_SECONDS:
        refresh_token = tokens.get("refresh_token")
        if not refresh_token:
            _clear_session(request)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session expired",
            )
        new_token = await oidc.refresh_access_token(refresh_token)
        if new_token is None:
            _clear_session(request)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session refresh failed",
            )
        tokens["access_token"] = new_token["access_token"]
        if "refresh_token" in new_token:
            tokens["refresh_token"] = new_token["refresh_token"]
        if "id_token" in new_token:
            tokens["id_token"] = new_token["id_token"]
        tokens["expires_at"] = oidc.expires_at_from_token(new_token)
        request.session["tokens"] = tokens

    return user


require_user = get_current_user
require_admin = get_current_user
