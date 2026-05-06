from fastapi import Depends, FastAPI, status
from fastapi.testclient import TestClient

from dfm_bq_load_alerter.auth import require_admin


def _build_app() -> FastAPI:
    app = FastAPI()

    @app.get("/admin")
    def admin(_principal: dict = Depends(require_admin)):
        return {"ok": True}

    return app


def test_no_token_yields_401(monkeypatch) -> None:
    monkeypatch.setattr(
        "dfm_bq_load_alerter.auth.bootstrap.settings.bootstrap_token",
        "secret-xyz",
        raising=False,
    )
    monkeypatch.setattr(
        "dfm_bq_load_alerter.auth.bootstrap.settings.oidc_issuer", "", raising=False
    )
    monkeypatch.setattr(
        "dfm_bq_load_alerter.auth.bootstrap.settings.oidc_client_id", "", raising=False
    )

    app = _build_app()
    with TestClient(app) as client:
        resp = client.get("/admin")
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED


def test_correct_token_yields_200(monkeypatch) -> None:
    monkeypatch.setattr(
        "dfm_bq_load_alerter.auth.bootstrap.settings.bootstrap_token",
        "secret-xyz",
        raising=False,
    )
    monkeypatch.setattr(
        "dfm_bq_load_alerter.auth.bootstrap.settings.oidc_issuer", "", raising=False
    )
    monkeypatch.setattr(
        "dfm_bq_load_alerter.auth.bootstrap.settings.oidc_client_id", "", raising=False
    )

    app = _build_app()
    with TestClient(app) as client:
        resp = client.get("/admin", headers={"Authorization": "Bearer secret-xyz"})
    assert resp.status_code == status.HTTP_200_OK


def test_wrong_token_yields_401(monkeypatch) -> None:
    monkeypatch.setattr(
        "dfm_bq_load_alerter.auth.bootstrap.settings.bootstrap_token",
        "secret-xyz",
        raising=False,
    )
    monkeypatch.setattr(
        "dfm_bq_load_alerter.auth.bootstrap.settings.oidc_issuer", "", raising=False
    )
    monkeypatch.setattr(
        "dfm_bq_load_alerter.auth.bootstrap.settings.oidc_client_id", "", raising=False
    )

    app = _build_app()
    with TestClient(app) as client:
        resp = client.get("/admin", headers={"Authorization": "Bearer wrong"})
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED


def test_oidc_configured_yields_503(monkeypatch) -> None:
    """Bootstrap dependency refuses to operate once OIDC is configured."""
    monkeypatch.setattr(
        "dfm_bq_load_alerter.auth.bootstrap.settings.bootstrap_token",
        "secret-xyz",
        raising=False,
    )
    monkeypatch.setattr(
        "dfm_bq_load_alerter.auth.bootstrap.settings.oidc_issuer",
        "https://idp.example.com/realms/dfm",
        raising=False,
    )
    monkeypatch.setattr(
        "dfm_bq_load_alerter.auth.bootstrap.settings.oidc_client_id",
        "dfm-alerter",
        raising=False,
    )

    app = _build_app()
    with TestClient(app) as client:
        resp = client.get("/admin", headers={"Authorization": "Bearer secret-xyz"})
    assert resp.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


def test_no_token_configured_yields_401(monkeypatch) -> None:
    """If bootstrap_token is empty, the endpoint refuses all requests."""
    monkeypatch.setattr(
        "dfm_bq_load_alerter.auth.bootstrap.settings.bootstrap_token", "", raising=False
    )
    monkeypatch.setattr(
        "dfm_bq_load_alerter.auth.bootstrap.settings.oidc_issuer", "", raising=False
    )
    monkeypatch.setattr(
        "dfm_bq_load_alerter.auth.bootstrap.settings.oidc_client_id", "", raising=False
    )

    app = _build_app()
    with TestClient(app) as client:
        resp = client.get("/admin", headers={"Authorization": "Bearer anything"})
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED
