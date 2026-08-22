"""Outbound email helper — Gmail SMTP, generic SMTP, Resend, or local mail drop."""

from __future__ import annotations

import json
import os
import smtplib
import ssl
import urllib.error
import urllib.request
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formataddr, parseaddr
from pathlib import Path
from typing import Any


def _mail_dir() -> Path:
    root = Path(__file__).resolve().parent.parent / "uploads" / "mail"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _drop_local(to: str, subject: str, html_body: str, text_body: str, reason: str = "") -> None:
    payload = {
        "to": to,
        "subject": subject,
        "html": html_body,
        "text": text_body,
        "reason": reason,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    path = _mail_dir() / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')}.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def email_config_status() -> dict[str, Any]:
    """Safe status for ops — never includes secrets."""
    gmail_user = (os.environ.get("GMAIL_USER") or os.environ.get("SMTP_USER") or "").strip()
    gmail_pass = (os.environ.get("GMAIL_APP_PASSWORD") or os.environ.get("SMTP_PASSWORD") or "").strip()
    smtp_host = (os.environ.get("SMTP_HOST") or "").strip()
    resend = bool((os.environ.get("RESEND_API_KEY") or "").strip())
    gmail_ready = bool(gmail_user and gmail_pass)
    smtp_ready = bool(smtp_host and gmail_user and gmail_pass) or gmail_ready
    provider = "none"
    if resend:
        provider = "resend"
    elif gmail_ready or (smtp_host and "gmail" in smtp_host.lower()):
        provider = "gmail"
    elif smtp_host:
        provider = "smtp"
    return {
        "configured": bool(resend or smtp_ready),
        "provider": provider,
        "smtp_host": smtp_host or ("smtp.gmail.com" if gmail_ready else ""),
        "from_hint": (os.environ.get("SMTP_FROM") or os.environ.get("EMAIL_FROM") or gmail_user or ""),
        "gmail_user_set": bool(gmail_user),
        "gmail_password_set": bool(gmail_pass),
    }


def _from_address(login_user: str) -> str:
    """Gmail requires From to match the authenticated account (or a verified alias)."""
    configured = (os.environ.get("SMTP_FROM") or os.environ.get("EMAIL_FROM") or "").strip()
    name, addr = parseaddr(configured)
    login = login_user.strip().lower()
    if addr and addr.lower() == login:
        return configured if name else formataddr(("BUILD FORCES", addr))
    if login:
        return formataddr(("BUILD FORCES", login))
    return configured or "BUILD FORCES <noreply@buildforces.com>"


def _send_resend(to: str, subject: str, html_body: str, text_body: str, api_key: str) -> None:
    from_addr = os.environ.get("EMAIL_FROM") or os.environ.get("SMTP_FROM") or "BUILD FORCES <noreply@buildforces.com>"
    body = json.dumps(
        {
            "from": from_addr,
            "to": [to],
            "subject": subject,
            "html": html_body,
            "text": text_body,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        if resp.status >= 300:
            raise RuntimeError(f"Resend HTTP {resp.status}")


def _send_smtp(to: str, subject: str, html_body: str, text_body: str) -> None:
    # Prefer explicit Gmail env vars, then generic SMTP.
    user = (
        os.environ.get("GMAIL_USER")
        or os.environ.get("SMTP_USER")
        or ""
    ).strip()
    # App passwords are often pasted with spaces — strip them.
    password = (
        os.environ.get("GMAIL_APP_PASSWORD")
        or os.environ.get("SMTP_PASSWORD")
        or ""
    ).replace(" ", "").strip()
    host = (os.environ.get("SMTP_HOST") or "").strip()
    if not host and user and password:
        host = "smtp.gmail.com"
    port = int(os.environ.get("SMTP_PORT") or ("587" if host else "0") or "587")
    if not host:
        raise RuntimeError("SMTP_HOST / Gmail not configured")
    if not user or not password:
        raise RuntimeError("SMTP_USER/GMAIL_USER and SMTP_PASSWORD/GMAIL_APP_PASSWORD are required")

    from_addr = _from_address(user)
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to
    msg["Reply-To"] = from_addr
    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")

    context = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=30, context=context) as server:
            server.login(user, password)
            server.send_message(msg)
        return

    with smtplib.SMTP(host, port, timeout=30) as server:
        server.ehlo()
        server.starttls(context=context)
        server.ehlo()
        server.login(user, password)
        server.send_message(msg)


def send_email(to: str, subject: str, html_body: str, text_body: str | None = None) -> dict[str, Any]:
    """Send email. Returns {sent: bool, reason?: str, provider?: str}."""
    text = text_body or subject
    to = (to or "").strip().lower()
    if not to:
        return {"sent": False, "reason": "missing_recipient"}

    resend_key = (os.environ.get("RESEND_API_KEY") or "").strip()
    gmail_user = (os.environ.get("GMAIL_USER") or os.environ.get("SMTP_USER") or "").strip()
    gmail_pass = (os.environ.get("GMAIL_APP_PASSWORD") or os.environ.get("SMTP_PASSWORD") or "").strip()
    smtp_host = (os.environ.get("SMTP_HOST") or "").strip()
    can_smtp = bool(smtp_host or (gmail_user and gmail_pass))

    try:
        if resend_key:
            _send_resend(to, subject, html_body, text, resend_key)
            return {"sent": True, "provider": "resend"}
        if can_smtp:
            _send_smtp(to, subject, html_body, text)
            provider = "gmail" if (not smtp_host or "gmail" in smtp_host.lower()) else "smtp"
            return {"sent": True, "provider": provider}
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, RuntimeError, smtplib.SMTPException) as exc:
        _drop_local(to, subject, html_body, text, reason=str(exc))
        return {"sent": False, "reason": str(exc)}

    _drop_local(to, subject, html_body, text, reason="email_not_configured")
    return {"sent": False, "reason": "email_not_configured"}


def password_reset_email_html(reset_url: str) -> str:
    return f"""<!DOCTYPE html>
<html><body style="font-family:Arial,Helvetica,sans-serif;color:#0f172a;line-height:1.5;margin:0;padding:24px;background:#f8f7fc">
  <div style="max-width:560px;margin:0 auto;background:#fff;border-radius:16px;padding:28px;border:1px solid #e9e5f5">
    <p style="margin:0 0 8px;font-size:12px;font-weight:700;letter-spacing:.14em;color:#7c3aed">BUILD FORCES</p>
    <h1 style="margin:0 0 12px;font-size:22px">Reset your password</h1>
    <p style="margin:0 0 18px">You asked to reset your BUILD FORCES password. Use the button below. This link expires in 1 hour.</p>
    <p style="margin:0 0 18px">
      <a href="{reset_url}" style="display:inline-block;background:#7c3aed;color:#fff;padding:12px 18px;border-radius:10px;text-decoration:none;font-weight:600">Reset password</a>
    </p>
    <p style="margin:0 0 8px;font-size:13px;color:#64748b">Or copy this link:</p>
    <p style="margin:0;word-break:break-all;font-size:12px;color:#475569">{reset_url}</p>
    <p style="margin:18px 0 0;font-size:13px;color:#64748b">If you did not request this, you can ignore this email.</p>
  </div>
</body></html>"""
