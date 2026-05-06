from fastapi.testclient import TestClient

from dfm_bq_load_alerter.main import app


def test_healthz_no_db_configured(monkeypatch) -> None:
    monkeypatch.setattr(
        "dfm_bq_load_alerter.api.health.settings.postgres_dsn", "", raising=False
    )
    with TestClient(app) as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["db"] == "not-configured"


def test_version() -> None:
    with TestClient(app) as client:
        response = client.get("/api/version")
    assert response.status_code == 200
    assert "version" in response.json()


def test_alerts_returns_list() -> None:
    with TestClient(app) as client:
        response = client.get("/api/alerts")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_spa_fallback_does_not_intercept_api_paths(tmp_path, monkeypatch) -> None:
    """C2 guard: SPA fallback must NOT swallow /api/*, /auth/*, /assets/* paths."""
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<html><body>SPA</body></html>")
    assets = static_dir / "assets"
    assets.mkdir()

    monkeypatch.setattr(
        "dfm_bq_load_alerter.main.settings.static_dir", static_dir, raising=False
    )

    from dfm_bq_load_alerter import main as main_module
    importlib_reload = __import__("importlib").reload
    importlib_reload(main_module)

    with TestClient(main_module.app) as client:
        # Unknown /api path → backend 404 (not SPA fallback)
        response = client.get("/api/does-not-exist")
        assert response.status_code == 404

        # Unknown /auth path → backend 404 (not SPA fallback)
        response = client.get("/auth/callback")
        assert response.status_code == 404

        # Non-prefix path → SPA index.html
        response = client.get("/dashboard")
        assert response.status_code == 200
        assert "SPA" in response.text
