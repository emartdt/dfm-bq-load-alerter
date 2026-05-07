"""webhooks API: pure helpers + router smoke."""
from __future__ import annotations

from datetime import UTC, datetime

from dfm_bq_load_alerter.api.webhooks import WebhookOut, _mask
from dfm_bq_load_alerter.db.models import TeamsWebhook


def test_mask_empty() -> None:
    assert _mask("") == ""


def test_mask_long_url_hides_middle_token() -> None:
    url = "https://outlook.office.com/webhook/abcdef1234567890/IncomingWebhook/xyz"
    masked = _mask(url)
    # Host preserved
    assert masked.startswith("https://outlook.office.com/")
    # Random middle (the credential) must be gone
    assert "abcdef1234567890" not in masked
    # Ellipsis indicates redaction occurred
    assert "…" in masked


def test_mask_short_path_full_redaction() -> None:
    masked = _mask("https://shorturl.example/x")
    assert masked.startswith("https://shorturl.example/")
    assert "x" not in masked.removeprefix("https://shorturl.example/")


def test_webhook_out_never_returns_raw_url() -> None:
    """WebhookOut serialisation must not expose the cleartext URL."""
    hook = TeamsWebhook(
        id=1,
        name="ops-room",
        webhook_url=(
            "https://outlook.office.com/webhook/SECRETTOKEN_DO_NOT_LEAK/IncomingWebhook"
        ),
        active=True,
        created_at=datetime.now(tz=UTC),
        updated_at=datetime.now(tz=UTC),
    )
    out = WebhookOut.from_model(hook)
    serialised = out.model_dump_json()
    assert "SECRETTOKEN_DO_NOT_LEAK" not in serialised
    # The masked field must not contain the literal name 'webhook_url' as a key
    assert "webhook_url_masked" in serialised
    assert "\"webhook_url\":" not in serialised


def test_webhooks_router_registered() -> None:
    """The /api/webhooks routes are mounted on the FastAPI app."""
    from dfm_bq_load_alerter.main import app

    paths = {route.path for route in app.routes}  # type: ignore[attr-defined]
    assert "/api/webhooks" in paths
    assert "/api/webhooks/{webhook_id}" in paths
    assert "/api/webhooks/{webhook_id}/test" in paths
