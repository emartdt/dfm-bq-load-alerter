"""SMTP relay sender (aiosmtplib).

Settings used:
- smtp_host / smtp_port / smtp_use_starttls
- smtp_user / smtp_password (omitted = no SMTP AUTH)
- smtp_from_addr (envelope sender + From: header)
"""
from __future__ import annotations

import logging
from email.message import EmailMessage

import aiosmtplib

from dfm_bq_load_alerter.settings import settings

log = logging.getLogger(__name__)


class EmailNotConfiguredError(RuntimeError):
    """SMTP host or sender not set; caller should treat the channel as disabled."""


async def send_email(*, to: list[str], subject: str, html: str) -> None:
    if not settings.smtp_host or not settings.smtp_from_addr:
        raise EmailNotConfiguredError("DFM_ALERT_SMTP_HOST/FROM_ADDR not configured")
    if not to:
        raise ValueError("recipient list is empty")

    message = EmailMessage()
    message["From"] = settings.smtp_from_addr
    message["To"] = ", ".join(to)
    message["Subject"] = subject
    message.set_content("HTML email — please use a compatible mail client.")
    message.add_alternative(html, subtype="html")

    log.info("smtp send: host=%s to=%d subject=%s", settings.smtp_host, len(to), subject)
    await aiosmtplib.send(
        message,
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        start_tls=settings.smtp_use_starttls,
        username=settings.smtp_user or None,
        password=settings.smtp_password or None,
    )
