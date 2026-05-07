"""OIDC client (Keycloak) — Authlib 기반."""
from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlencode

import httpx
from authlib.integrations.starlette_client import OAuth, StarletteOAuth2App
from fastapi import Request

from dfm_bq_load_alerter.settings import settings

_oauth = OAuth()
_oauth.register(
    name="keycloak",
    server_metadata_url=(
        f"{settings.oidc_issuer.rstrip('/')}/.well-known/openid-configuration"
    ),
    client_id=settings.oidc_client_id,
    client_secret=settings.oidc_client_secret,
    client_kwargs={"scope": "openid email profile"},
)


def keycloak() -> StarletteOAuth2App:
    client = _oauth.keycloak  # type: ignore[attr-defined]
    assert client is not None
    return client


def _resolve_redirect_uri(request: Request) -> str:
    if settings.oidc_redirect_uri:
        return settings.oidc_redirect_uri
    return str(request.url_for("auth_callback"))


def _resolve_post_logout_redirect_uri(request: Request) -> str:
    if settings.oidc_post_logout_redirect_uri:
        return settings.oidc_post_logout_redirect_uri
    return f"{request.url.scheme}://{request.url.netloc}/"


async def authorize_redirect(request: Request):
    return await keycloak().authorize_redirect(
        request, _resolve_redirect_uri(request)
    )


async def fetch_token(request: Request) -> dict[str, Any]:
    return await keycloak().authorize_access_token(request)


async def refresh_access_token(refresh_token: str) -> dict[str, Any] | None:
    metadata = await keycloak().load_server_metadata()
    token_endpoint = metadata["token_endpoint"]
    async with httpx.AsyncClient(timeout=10.0) as http:
        try:
            resp = await http.post(
                token_endpoint,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": settings.oidc_client_id,
                    "client_secret": settings.oidc_client_secret,
                },
            )
        except httpx.HTTPError:
            return None
    if resp.status_code != 200:
        return None
    payload = resp.json()
    if "access_token" not in payload:
        return None
    return payload


async def build_logout_url(id_token: str | None, request: Request) -> str:
    metadata = await keycloak().load_server_metadata()
    end_session = metadata.get("end_session_endpoint")
    if not end_session:
        return _resolve_post_logout_redirect_uri(request)
    params: dict[str, str] = {
        "post_logout_redirect_uri": _resolve_post_logout_redirect_uri(request),
        "client_id": settings.oidc_client_id,
    }
    if id_token:
        params["id_token_hint"] = id_token
    return f"{end_session}?{urlencode(params)}"


def expires_at_from_token(token: dict[str, Any]) -> int:
    if "expires_at" in token:
        return int(token["expires_at"])
    if "expires_in" in token:
        return int(time.time()) + int(token["expires_in"])
    return int(time.time()) + 300
