"""Shared test fixtures."""
from __future__ import annotations

import os

import pytest

# Ensure OIDC/session env vars are present at collection time (before any
# module imports trigger Settings() instantiation). Tests that need to
# delete these vars use monkeypatch.delenv() in combination with the
# autouse fixture below.
os.environ.setdefault("DFM_ALERT_OIDC_ISSUER", "https://iam.example.test/realms/TEST")
os.environ.setdefault("DFM_ALERT_OIDC_CLIENT_ID", "test-client")
os.environ.setdefault("DFM_ALERT_OIDC_CLIENT_SECRET", "test-secret")
os.environ.setdefault("DFM_ALERT_SESSION_SECRET_KEY", "0" * 64)
os.environ.setdefault("DFM_ALERT_SCHEDULER_ENABLED", "false")
os.environ.setdefault("DFM_ALERT_ENVIRONMENT", "development")


@pytest.fixture(autouse=True)
def _oidc_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """모든 테스트에 OIDC/세션 dummy env 주입."""
    monkeypatch.setenv("DFM_ALERT_OIDC_ISSUER", "https://iam.example.test/realms/TEST")
    monkeypatch.setenv("DFM_ALERT_OIDC_CLIENT_ID", "test-client")
    monkeypatch.setenv("DFM_ALERT_OIDC_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv("DFM_ALERT_SESSION_SECRET_KEY", "0" * 64)
    monkeypatch.setenv("DFM_ALERT_SCHEDULER_ENABLED", "false")
    monkeypatch.setenv("DFM_ALERT_ENVIRONMENT", "development")
