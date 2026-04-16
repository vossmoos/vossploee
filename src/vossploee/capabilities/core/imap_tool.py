from __future__ import annotations

import asyncio
import base64
import smtplib
from email.message import EmailMessage
from email.policy import SMTP
from os import getenv

from dotenv import load_dotenv

from vossploee.capabilities.capability_settings import load_capability_settings

# Only this address may receive mail from this tool (hard limit).
_ALLOWED_RECIPIENT = "aol@vossmoos.de"


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
    subject: str,
    body: str,
) -> str:
    msg = EmailMessage(policy=SMTP)
    msg["Subject"] = subject.strip() or "(no subject)"
    msg["From"] = user
    msg["To"] = _ALLOWED_RECIPIENT
    msg.set_content(body, subtype="plain", charset="utf-8")

    with smtplib.SMTP_SSL(smtp_host, smtp_port) as smtp:
        _smtp_login_plain_utf8(smtp, user, password)
        smtp.send_message(msg)

    return (
        f"Email sent via SMTP {smtp_host}:{smtp_port} SSL to {_ALLOWED_RECIPIENT!r} "
        f"(subject: {msg['Subject']!r})."
    )


async def imap_send_mail(subject: str, body: str) -> str:
    """Send one email to the fixed allowed recipient using SMTP (SSL) from core capability config.

    Outgoing mail uses ``[imap].smtp_host`` / ``smtp_port`` in ``core/config.toml``. Credentials
    use the env var names in that section. IMAP host/port in config are not used by this action.
    """
    load_dotenv()
    cfg = load_capability_settings("core").imap
    if cfg is None:
        return "Mail is not configured for the core capability (missing [imap] in core/config.toml)."

    user = getenv(cfg.user_env, "") or ""
    password = getenv(cfg.password_env, "") or ""
    user, password = user.strip(), password.strip()
    if not user or not password:
        return (
            "Mail credentials missing: set the environment variables named in core/config.toml "
            f"([imap].user_env / [imap].password_env), currently {cfg.user_env!r} and "
            f"{cfg.password_env!r}, e.g. in `.env`."
        )

    if not (body or "").strip():
        return "Email body must not be empty."

    try:
        return await asyncio.to_thread(
            _send_mail_sync,
            smtp_host=cfg.smtp_host,
            smtp_port=cfg.smtp_port,
            user=user,
            password=password,
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
