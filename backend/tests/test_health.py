from fastapi.testclient import TestClient

from dfm_bq_load_alerter.main import app

client = TestClient(app)


def test_healthz() -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_version() -> None:
    response = client.get("/api/version")
    assert response.status_code == 200
    assert "version" in response.json()


def test_alerts_returns_list() -> None:
    response = client.get("/api/alerts")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
