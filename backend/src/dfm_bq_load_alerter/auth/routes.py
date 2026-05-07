"""인증 라우터."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from dfm_bq_load_alerter.auth import oidc
from dfm_bq_load_alerter.auth.session import get_current_user
from dfm_bq_load_alerter.db.bo_users import upsert_login
from dfm_bq_load_alerter.db.session import get_session

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

    await upsert_login(session, keycloak_subject=sub, email=email)

    request.session["user"] = {"sub": sub, "email": email, "name": name}
    request.session["tokens"] = {
        "access_token": token["access_token"],
        "refresh_token": token.get("refresh_token"),
        "id_token": token.get("id_token"),
        "expires_at": oidc.expires_at_from_token(token),
    }

    return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)


@router.post("/logout", name="auth_logout")
async def logout(request: Request) -> RedirectResponse:
    tokens = request.session.get("tokens") or {}
    id_token = tokens.get("id_token")
    request.session.clear()
    logout_url = await oidc.build_logout_url(id_token, request)
    return RedirectResponse(url=logout_url, status_code=status.HTTP_302_FOUND)


@router.get("/me")
async def me(user: dict = Depends(get_current_user)) -> dict[str, Any]:
    return {"sub": user["sub"], "email": user.get("email"), "name": user.get("name")}
