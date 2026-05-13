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
    monkeypatch.setattr(email_module.settings, "smtp_local_hostname", "", raising=False)

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
    # local_hostname is omitted when empty so aiosmtplib uses its default
    assert "local_hostname" not in kwargs


@pytest.mark.asyncio
async def test_send_email_passes_local_hostname_when_set(monkeypatch) -> None:
    monkeypatch.setattr(email_module.settings, "smtp_host", "smtp.example.com", raising=False)
    monkeypatch.setattr(email_module.settings, "smtp_port", 25, raising=False)
    monkeypatch.setattr(email_module.settings, "smtp_user", "", raising=False)
    monkeypatch.setattr(email_module.settings, "smtp_password", "", raising=False)
    monkeypatch.setattr(email_module.settings, "smtp_from_addr", "alerts@dfm.local", raising=False)
    monkeypatch.setattr(email_module.settings, "smtp_use_starttls", False, raising=False)
    monkeypatch.setattr(
        email_module.settings, "smtp_local_hostname", "alerter.dfm.local", raising=False
    )

    sent = AsyncMock()
    monkeypatch.setattr(email_module.aiosmtplib, "send", sent)

    await send_email(to=["a@example.com"], subject="hi", html="<b>h</b>")

    kwargs = sent.await_args.kwargs
    assert kwargs["local_hostname"] == "alerter.dfm.local"
    assert kwargs["start_tls"] is False
    # 자격 증명이 비어 있으면 AUTH를 시도하지 않도록 키 자체를 전달하지 않음.
    assert "username" not in kwargs
    assert "password" not in kwargs


@pytest.mark.asyncio
async def test_send_email_skips_auth_when_only_user_set(monkeypatch) -> None:
    """user만 채워지고 password가 비어 있으면 AUTH를 시도하지 않는다.

    운영 환경에서 내부 릴레이(email.shinsegae.ai:25) 대상으로 user/password가
    실수로 설정되었을 때 ``No suitable authentication method found.`` 가 발생
    하던 회귀를 막기 위한 가드.
    """
    monkeypatch.setattr(email_module.settings, "smtp_host", "smtp.example.com", raising=False)
    monkeypatch.setattr(email_module.settings, "smtp_port", 25, raising=False)
    monkeypatch.setattr(email_module.settings, "smtp_user", "AE0E100028@example.com", raising=False)
    monkeypatch.setattr(email_module.settings, "smtp_password", "", raising=False)
    monkeypatch.setattr(email_module.settings, "smtp_from_addr", "alerts@dfm.local", raising=False)
    monkeypatch.setattr(email_module.settings, "smtp_use_starttls", False, raising=False)
    monkeypatch.setattr(email_module.settings, "smtp_local_hostname", "", raising=False)

    sent = AsyncMock()
    monkeypatch.setattr(email_module.aiosmtplib, "send", sent)

    await send_email(to=["a@example.com"], subject="hi", html="<b>h</b>")

    kwargs = sent.await_args.kwargs
    assert "username" not in kwargs
    assert "password" not in kwargs
