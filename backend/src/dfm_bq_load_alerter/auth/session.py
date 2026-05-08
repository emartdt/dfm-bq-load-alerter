"""세션 쿠키 기반 인증 dependency.

세션에는 user dict 만 보관(+ logout 용 id_token). access/refresh 토큰은
저장하지 않는다 — Keycloak 보호 자원 API 를 호출하지 않으므로 access_token
이 필요 없고, 세션 만료는 SessionMiddleware 의 cookie max-age 로 관리한다.
모든 토큰을 담으면 4KB 쿠키 한계를 넘겨 브라우저가 silent drop 한다.
"""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request, status


def _get_user(request: Request) -> dict[str, Any] | None:
    user = request.session.get("user")
    if not isinstance(user, dict):
        return None
    return user


async def get_current_user(request: Request) -> dict[str, Any]:
    user = _get_user(request)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return user


# TODO(rbac): 역할 기반 인가가 필요해지면 require_admin 만 role=='admin' 검사로
# 분기. 현재 스펙은 "로그인=admin" 이므로 셋 다 동일.
require_user = get_current_user
require_admin = get_current_user
