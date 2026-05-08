"""OIDC 인증 흐름 통합 테스트."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.responses import RedirectResponse
from fastapi.testclient import TestClient


@pytest.fixture
def app():
    import importlib

    import dfm_bq_load_alerter.main as m
    import dfm_bq_load_alerter.settings as s
    importlib.reload(s)
    importlib.reload(m)

    # Override DB session dependency so OIDC callback tests don't require
    # a configured Postgres engine. upsert_login is patched at the call
    # sites (tests below), so the session value itself is unused.
    from dfm_bq_load_alerter.db.session import get_session

    async def _fake_session():
        yield None

    m.app.dependency_overrides[get_session] = _fake_session
    try:
        yield m.app
    finally:
        m.app.dependency_overrides.clear()


@pytest.fixture
def client(app) -> TestClient:
    return TestClient(app)


def test_login_redirects_to_keycloak(client: TestClient) -> None:
    fake_redirect = "https://iam.example.test/realms/TEST/protocol/openid-connect/auth?state=X"
    with patch(
        "dfm_bq_load_alerter.auth.oidc.authorize_redirect",
        new=AsyncMock(return_value=RedirectResponse(url=fake_redirect, status_code=302)),
    ):
        resp = client.get("/auth/login", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"].startswith("https://iam.example.test/")


def test_callback_sets_session_and_redirects_home(client: TestClient) -> None:
    fake_token = {
        "access_token": "AT",
        "refresh_token": "RT",
        "id_token": "ID",
        "expires_in": 600,
        "userinfo": {"sub": "user-123", "email": "u@ex.com", "name": "U"},
    }
    with patch(
        "dfm_bq_load_alerter.auth.oidc.fetch_token",
        new=AsyncMock(return_value=fake_token),
    ), patch(
        "dfm_bq_load_alerter.auth.routes.upsert_login",
        new=AsyncMock(),
    ):
        resp = client.get("/auth/callback?code=abc&state=xyz", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"] == "/"
    assert "dfm_session" in resp.headers.get("set-cookie", "")


def test_callback_rejects_invalid_token(client: TestClient) -> None:
    with patch(
        "dfm_bq_load_alerter.auth.oidc.fetch_token",
        new=AsyncMock(side_effect=Exception("bad state")),
    ):
        resp = client.get("/auth/callback?code=abc&state=bad", follow_redirects=False)
    assert resp.status_code == 400


def test_callback_rejects_missing_sub(client: TestClient) -> None:
    fake_token = {
        "access_token": "AT",
        "expires_in": 600,
        "userinfo": {"email": "u@ex.com"},
    }
    with patch(
        "dfm_bq_load_alerter.auth.oidc.fetch_token",
        new=AsyncMock(return_value=fake_token),
    ):
        resp = client.get("/auth/callback?code=abc&state=xyz", follow_redirects=False)
    assert resp.status_code == 400


def test_admin_endpoint_requires_session(client: TestClient) -> None:
    resp = client.get("/api/tables")
    assert resp.status_code == 401


def test_me_returns_401_when_anonymous(client: TestClient) -> None:
    resp = client.get("/auth/me")
    assert resp.status_code == 401


def _login_session_cookie(client: TestClient, expires_in: int = 3600) -> None:
    fake_token = {
        "access_token": "AT",
        "refresh_token": "RT",
        "id_token": "ID",
        "expires_in": expires_in,
        "userinfo": {"sub": "user-123", "email": "u@ex.com", "name": "U"},
    }
    with patch(
        "dfm_bq_load_alerter.auth.oidc.fetch_token",
        new=AsyncMock(return_value=fake_token),
    ), patch(
        "dfm_bq_load_alerter.auth.routes.upsert_login",
        new=AsyncMock(),
    ):
        resp = client.get(
            "/auth/callback?code=abc&state=xyz", follow_redirects=False
        )
    assert resp.status_code == 302


def test_me_returns_user_when_authenticated(client: TestClient) -> None:
    _login_session_cookie(client)
    resp = client.get("/auth/me")
    assert resp.status_code == 200
    data = resp.json()
    assert data["sub"] == "user-123"
    assert data["email"] == "u@ex.com"


def test_logout_clears_session_and_redirects_to_keycloak(client: TestClient) -> None:
    _login_session_cookie(client)
    fake_logout_url = "https://iam.example.test/realms/TEST/protocol/openid-connect/logout?id_token_hint=ID"
    with patch(
        "dfm_bq_load_alerter.auth.oidc.build_logout_url",
        new=AsyncMock(return_value=fake_logout_url),
    ):
        resp = client.post("/auth/logout", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["location"].startswith("https://iam.example.test/")
