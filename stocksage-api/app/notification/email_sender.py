"""SMTP email sender for task notifications."""

from __future__ import annotations

import asyncio
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from functools import partial

from app.config import settings

logger = logging.getLogger(__name__)


def _send_smtp(to: str, subject: str, html_body: str) -> None:
    """Blocking SMTP send — runs in a thread pool."""
    msg = MIMEMultipart("alternative")
    msg["From"] = settings.REPORT_EMAIL_SENDER
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP_SSL(
        settings.REPORT_EMAIL_SMTP_HOST,
        settings.REPORT_EMAIL_SMTP_PORT,
        timeout=30,
    ) as server:
        server.login(settings.REPORT_EMAIL_USER, settings.REPORT_EMAIL_PASSWORD)
        server.sendmail(settings.REPORT_EMAIL_SENDER, [to], msg.as_string())


async def send_email(
    subject: str,
    html_body: str,
    to: str | None = None,
) -> None:
    """Send an HTML email asynchronously (runs SMTP in executor).

    Args:
        subject: Email subject line.
        html_body: HTML content.
        to: Recipient address. Falls back to REPORT_EMAIL_DEFAULT_TO.
    """
    if not settings.REPORT_EMAIL_ENABLED:
        return

    recipient = to or settings.REPORT_EMAIL_DEFAULT_TO
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, partial(_send_smtp, recipient, subject, html_body))
    logger.info("Email sent to %s: %s", recipient, subject)
