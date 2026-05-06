from unittest.mock import AsyncMock

import pytest

from dfm_bq_load_alerter.notifier import email as email_module
from dfm_bq_load_alerter.notifier.email import (
    EmailNotConfiguredError,
    send_email,
)


@pytest.mark.asyncio
async def test_send_email_raises_when_smtp_host_missing(monkeypatch) -> None:
    monkeypatch.setattr(email_module.settings, "smtp_host", "", raising=False)
    monkeypatch.setattr(email_module.settings, "smtp_from_addr", "x@y", raising=False)
    with pytest.raises(EmailNotConfiguredError):
        await send_email(to=["a@example.com"], subject="s", html="<b>h</b>")


@pytest.mark.asyncio
async def test_send_email_raises_when_from_addr_missing(monkeypatch) -> None:
    monkeypatch.setattr(email_module.settings, "smtp_host", "smtp.example.com", raising=False)
    monkeypatch.setattr(email_module.settings, "smtp_from_addr", "", raising=False)
    with pytest.raises(EmailNotConfiguredError):
        await send_email(to=["a@example.com"], subject="s", html="<b>h</b>")


@pytest.mark.asyncio
async def test_send_email_raises_when_recipient_list_empty(monkeypatch) -> None:
    monkeypatch.setattr(email_module.settings, "smtp_host", "smtp.example.com", raising=False)
    monkeypatch.setattr(email_module.settings, "smtp_from_addr", "x@y", raising=False)
    with pytest.raises(ValueError):
        await send_email(to=[], subject="s", html="<b>h</b>")


@pytest.mark.asyncio
async def test_send_email_invokes_aiosmtplib_with_starttls(monkeypatch) -> None:
    monkeypatch.setattr(email_module.settings, "smtp_host", "smtp.example.com", raising=False)
    monkeypatch.setattr(email_module.settings, "smtp_port", 587, raising=False)
    monkeypatch.setattr(email_module.settings, "smtp_user", "u", raising=False)
    monkeypatch.setattr(email_module.settings, "smtp_password", "p", raising=False)
    monkeypatch.setattr(email_module.settings, "smtp_from_addr", "alerts@dfm.local", raising=False)
    monkeypatch.setattr(email_module.settings, "smtp_use_starttls", True, raising=False)

    sent = AsyncMock()
    monkeypatch.setattr(email_module.aiosmtplib, "send", sent)

    await send_email(to=["a@example.com"], subject="hi", html="<b>h</b>")

    sent.assert_awaited_once()
    kwargs = sent.await_args.kwargs
    assert kwargs["hostname"] == "smtp.example.com"
    assert kwargs["port"] == 587
    assert kwargs["start_tls"] is True
    assert kwargs["username"] == "u"
    assert kwargs["password"] == "p"
