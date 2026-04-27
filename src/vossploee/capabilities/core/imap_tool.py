from __future__ import annotations

import asyncio
import base64
import smtplib
from email.message import EmailMessage
from email.policy import SMTP
from os import getenv

from vossploee.config import get_settings


def _smtp_login_plain_utf8(smtp: smtplib.SMTP_SSL, user: str, password: str) -> None:
    """Log in with AUTH PLAIN using UTF-8 for credentials.

    The stdlib :meth:`smtplib.SMTP.login` base64-encodes the SASL PLAIN string with
    ``.encode("ascii")``, which rejects non-ASCII characters in passwords (e.g. ``§``).
    Servers on TLS typically accept UTF-8 octets inside the PLAIN payload.
    """
    smtp.ehlo_or_helo_if_needed()
    if not smtp.has_extn("auth"):
        raise smtplib.SMTPNotSupportedError("SMTP AUTH extension not supported by server.")
    auth_advertised = smtp.esmtp_features.get("auth", "")
    methods = {m.upper() for m in auth_advertised.split()}
    if "PLAIN" not in methods:
        smtp.login(user, password)
        return
    inner = b"\x00" + user.encode("utf-8") + b"\x00" + password.encode("utf-8")
    blob = base64.b64encode(inner).decode("ascii")
    code, resp = smtp.docmd("AUTH", "PLAIN " + blob)
    if code not in (235, 503):
        raise smtplib.SMTPAuthenticationError(code, resp)


def _send_mail_sync(
    *,
    smtp_host: str,
    smtp_port: int,
    user: str,
    password: str,
    recipient: str,
    subject: str,
    body: str,
) -> str:
    msg = EmailMessage(policy=SMTP)
    msg["Subject"] = subject.strip() or "(no subject)"
    msg["From"] = user
    msg["To"] = recipient
    msg.set_content(body, subtype="plain", charset="utf-8")

    with smtplib.SMTP_SSL(smtp_host, smtp_port) as smtp:
        _smtp_login_plain_utf8(smtp, user, password)
        smtp.send_message(msg)

    return f"Email sent via SMTP {smtp_host}:{smtp_port} SSL to {recipient!r} (subject: {msg['Subject']!r})."


async def imap_send_mail(subject: str, body: str, recipient: str) -> str:
    settings = get_settings()
    allowed = {x.lower() for x in settings.channel_email_allowed_senders}
    recipient = (recipient or "").strip().lower()
    if recipient not in allowed:
        return f"Recipient {recipient!r} is not in VOSSPLOEE_CHANNEL_EMAIL_ALLOWED_SENDERS."

    user = getenv(settings.channel_email_user_env, "") or ""
    password = getenv(settings.channel_email_password_env, "") or ""
    user, password = user.strip(), password.strip()
    if not user or not password:
        return (
            "Mail credentials missing in configured env vars "
            f"{settings.channel_email_user_env!r} and {settings.channel_email_password_env!r}."
        )

    if not (body or "").strip():
        return "Email body must not be empty."

    try:
        return await asyncio.to_thread(
            _send_mail_sync,
            smtp_host=settings.channel_email_smtp_host,
            smtp_port=settings.channel_email_smtp_port,
            user=user,
            password=password,
            recipient=recipient,
            subject=subject,
            body=body,
        )
    except smtplib.SMTPException as exc:
        return f"SMTP error while sending: {exc}"
    except UnicodeEncodeError as exc:
        return (
            "Could not encode content for SMTP. If this happened during login, the server may "
            "require ASCII-only passwords; otherwise check subject/body. "
            f"Details: {exc}"
        )
    except OSError as exc:
        return f"Network error while sending: {exc}"
