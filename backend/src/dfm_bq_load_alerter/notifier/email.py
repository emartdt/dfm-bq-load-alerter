"""SMTP relay sender (aiosmtplib).

Settings used:
- smtp_host / smtp_port / smtp_use_starttls
- smtp_user / smtp_password (omitted = no SMTP AUTH)
- smtp_from_addr (envelope sender + From: header)
- smtp_local_hostname (EHLO/HELO hostname; empty = aiosmtplib default)
"""
from __future__ import annotations

import asyncio
import logging
import socket
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

    send_kwargs: dict[str, object] = {
        "hostname": settings.smtp_host,
        "port": settings.smtp_port,
        "start_tls": settings.smtp_use_starttls,
        # aiosmtplib 기본 timeout(60s)은 '명령당'이라 전송 전체는 무한정
        # 늘어질 수 있다. 명령당 상한을 짧게 명시한다.
        "timeout": settings.smtp_command_timeout_seconds,
        # local_hostname 미지정 시 aiosmtplib이 socket.getfqdn()을 동기
        # 호출해 DNS 장애 시 이벤트 루프 전체가 멈춘다. 항상 명시한다.
        "local_hostname": settings.smtp_local_hostname or socket.gethostname(),
    }
    # Only attempt SMTP AUTH when both credentials are present. Otherwise
    # aiosmtplib calls login() and fails with "No suitable authentication
    # method found." against unauthenticated internal relays.
    auth_enabled = bool(settings.smtp_user and settings.smtp_password)
    if auth_enabled:
        send_kwargs["username"] = settings.smtp_user
        send_kwargs["password"] = settings.smtp_password

    log.info(
        "smtp send: host=%s port=%s to=%d subject=%s starttls=%s auth=%s local_hostname=%s",
        settings.smtp_host,
        settings.smtp_port,
        len(to),
        subject,
        settings.smtp_use_starttls,
        "on" if auth_enabled else "off",
        send_kwargs["local_hostname"],
    )
    # 명령당 timeout이 있어도 (명령 수 × timeout)만큼 누적될 수 있으므로
    # 전송 1회 전체에 상한을 둔다. 초과 시 TimeoutError가 전파되고
    # dispatcher가 failed 이벤트로 기록한다.
    async with asyncio.timeout(settings.smtp_total_timeout_seconds):
        await aiosmtplib.send(message, **send_kwargs)
