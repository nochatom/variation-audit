"""Outbound mail (Mailer implementations).

Production sends real SMTP mail; dev/tests without SMTP configured log the
message (including the accept link) instead of failing, so the invitation
flow works end-to-end with no mail infrastructure. Mirrors the S3/local-dir
split in app/storage.py.
"""
from __future__ import annotations

from email.message import EmailMessage

from app.logging_config import security_logger


class SmtpMailer:
    """Sends mail via SMTP (STARTTLS by default)."""

    def __init__(self, host: str, port: int, *, username: str | None,
                 password: str | None, use_tls: bool, from_addr: str):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.use_tls = use_tls
        self.from_addr = from_addr

    def send_invitation(self, *, to_email: str, org_name: str,
                        inviter_name: str, accept_url: str) -> None:
        import smtplib  # imported lazily so non-SMTP deployments needn't touch it

        msg = EmailMessage()
        msg["Subject"] = f"{inviter_name} invited you to join {org_name} on VariationIQ"
        msg["From"] = self.from_addr
        msg["To"] = to_email
        msg.set_content(
            f"{inviter_name} has invited you to join {org_name} on VariationIQ.\n\n"
            f"Accept the invitation:\n{accept_url}\n\n"
            f"This link expires in 7 days. If you weren't expecting this, you can ignore it."
        )
        with smtplib.SMTP(self.host, self.port, timeout=10) as smtp:
            if self.use_tls:
                smtp.starttls()
            if self.username and self.password:
                smtp.login(self.username, self.password)
            smtp.send_message(msg)


class ConsoleMailer:
    """Logs the invitation instead of sending it. Dev/test fallback when no
    SMTP host is configured — the accept link is retrievable from logs."""

    def send_invitation(self, *, to_email: str, org_name: str,
                        inviter_name: str, accept_url: str) -> None:
        security_logger.info(
            "invitation email (console mailer — no VA_SMTP_HOST configured)",
            extra={
                "event": "invitation_email_console",
                "to_email": to_email,
                "org_name": org_name,
                "inviter_name": inviter_name,
                "accept_url": accept_url,
            },
        )


def build_mailer():
    """Pick a mailer from settings: SMTP if configured, else console/log."""
    from app.config import get_settings

    s = get_settings()
    if s.smtp_host:
        return SmtpMailer(
            s.smtp_host, s.smtp_port,
            username=s.smtp_username, password=s.smtp_password,
            use_tls=s.smtp_use_tls, from_addr=s.smtp_from,
        )
    return ConsoleMailer()


def get_mailer():
    """FastAPI dependency yielding the mailer (overridable in tests)."""
    return build_mailer()
