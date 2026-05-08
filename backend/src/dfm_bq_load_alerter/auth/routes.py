"""인증 라우터."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from dfm_bq_load_alerter.auth import oidc
from dfm_bq_load_alerter.auth.session import get_current_user
from dfm_bq_load_alerter.db.bo_users import upsert_login
from dfm_bq_load_alerter.db.session import get_session

log = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login", name="auth_login")
async def login(request: Request) -> Any:
    return await oidc.authorize_redirect(request)


@router.get("/callback", name="auth_callback")
async def callback(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> RedirectResponse:
    try:
        token = await oidc.fetch_token(request)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OIDC callback failed: {exc}",
        ) from exc

    userinfo = token.get("userinfo") or {}
    sub = userinfo.get("sub")
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="id_token missing 'sub' claim",
        )

    email = userinfo.get("email")
    name = userinfo.get("name") or userinfo.get("preferred_username")

    # bo_users 기록은 best-effort. 추적 실패가 로그인 자체를 막아선 안 됨.
    try:
        await upsert_login(session, keycloak_subject=sub, email=email)
    except Exception:  # noqa: BLE001
        log.exception("upsert_login failed for sub=%s; continuing login", sub)

    # 세션에는 user 와 id_token(로그아웃 hint) 만 보관.
    # access_token / refresh_token 은 보관하지 않는다 — Keycloak 보호 자원
    # API 를 호출하지 않고, 세션 만료는 쿠키 max-age 로 관리하기 때문.
    # JWT 3개를 모두 담으면 4KB 쿠키 한계를 넘겨 브라우저가 silent drop.
    request.session["user"] = {"sub": sub, "email": email, "name": name}
    request.session["id_token"] = token.get("id_token")

    return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)


@router.post("/logout", name="auth_logout")
async def logout(request: Request) -> RedirectResponse:
    id_token = request.session.get("id_token")
    request.session.clear()
    logout_url = await oidc.build_logout_url(id_token, request)
    return RedirectResponse(url=logout_url, status_code=status.HTTP_302_FOUND)


@router.get("/me")
async def me(user: dict = Depends(get_current_user)) -> dict[str, Any]:
    return {"sub": user["sub"], "email": user.get("email"), "name": user.get("name")}
