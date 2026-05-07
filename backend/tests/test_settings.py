"""Settings 검증."""
from __future__ import annotations

import importlib

import pytest


def _reload_settings():
    import dfm_bq_load_alerter.settings as mod
    importlib.reload(mod)
    return mod


def test_oidc_fields_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DFM_ALERT_OIDC_ISSUER", raising=False)
    with pytest.raises(Exception):
        _reload_settings()


def test_session_secret_key_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DFM_ALERT_SESSION_SECRET_KEY", raising=False)
    with pytest.raises(Exception):
        _reload_settings()


def test_default_session_max_age_seconds() -> None:
    mod = _reload_settings()
    assert mod.settings.session_max_age_seconds == 28800


def test_no_bootstrap_token_field() -> None:
    mod = _reload_settings()
    assert not hasattr(mod.settings, "bootstrap_token")


def test_no_is_oidc_enabled_property() -> None:
    mod = _reload_settings()
    assert not hasattr(mod.settings, "is_oidc_enabled")
