"""Outbound mail (Mailer implementations).

Production sends real SMTP mail; dev/tests without SMTP configured log the
message (including the accept link) instead of failing, so the invitation
flow works end-to-end with no mail infrastructure. Mirrors the S3/local-dir
split in app/storage.py.
"""
from __future__ import annotations

from email.message import EmailMessage

from app.logging_config import security_logger


def _header_safe(value: str) -> str:
    """Strip CR/LF (and other header-breaking control chars) from a value
    before it's embedded in an email header. Org/user names are
    user-controlled input; a name containing a newline must never be able to
    inject additional headers into outbound mail."""
    return "".join(ch for ch in value if ch not in "\r\n\x00").strip()


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
        msg["Subject"] = (f"{_header_safe(inviter_name)} invited you to join "
                          f"{_header_safe(org_name)} on VariationIQ")
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

    def send_password_reset(self, *, to_email: str, reset_url: str) -> None:
        import smtplib

        msg = EmailMessage()
        msg["Subject"] = "Reset your VariationIQ password"
        msg["From"] = self.from_addr
        msg["To"] = to_email
        msg.set_content(
            f"Reset your VariationIQ password:\n{reset_url}\n\n"
            f"This link expires in 1 hour. If you didn't request this, you can ignore it — "
            f"your password won't change unless you click the link and set a new one."
        )
        with smtplib.SMTP(self.host, self.port, timeout=10) as smtp:
            if self.use_tls:
                smtp.starttls()
            if self.username and self.password:
                smtp.login(self.username, self.password)
            smtp.send_message(msg)

    def send_account_exists_notice(self, *, to_email: str, login_url: str) -> None:
        """Sent when someone tries to sign up with an email that already has
        an account — the signup response itself is deliberately identical in
        both cases (no user-enumeration signal), so this email is how the
        legitimate owner finds out and gets routed to login/reset."""
        import smtplib

        msg = EmailMessage()
        msg["Subject"] = "You already have a VariationIQ account"
        msg["From"] = self.from_addr
        msg["To"] = to_email
        msg.set_content(
            f"Someone (probably you) tried to create a VariationIQ account with this email, "
            f"but an account already exists.\n\n"
            f"Sign in here:\n{login_url}\n\n"
            f"Forgot your password? Use \"Forgot password?\" on the sign-in page.\n"
            f"If this wasn't you, no action is needed — no new account was created."
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

    def send_password_reset(self, *, to_email: str, reset_url: str) -> None:
        security_logger.info(
            "password reset email (console mailer — no VA_SMTP_HOST configured)",
            extra={
                "event": "password_reset_email_console",
                "to_email": to_email,
                "reset_url": reset_url,
            },
        )

    def send_account_exists_notice(self, *, to_email: str, login_url: str) -> None:
        security_logger.info(
            "account-exists notice email (console mailer — no VA_SMTP_HOST configured)",
            extra={
                "event": "account_exists_email_console",
                "to_email": to_email,
                "login_url": login_url,
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
