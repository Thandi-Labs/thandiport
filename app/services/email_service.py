import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib

from app.config import settings

logger = logging.getLogger(__name__)

# ── Brand constants ────────────────────────────────────────────────────────────
_COLOR_BG = "#f0f4f8"
_COLOR_CARD = "#ffffff"
_COLOR_HEADER_FROM = "#0d1b2a"
_COLOR_HEADER_TO = "#1b3a5c"
_COLOR_ACCENT = "#3b82f6"
_COLOR_ACCENT_HOVER = "#2563eb"
_COLOR_TEXT = "#1e293b"
_COLOR_MUTED = "#64748b"
_COLOR_BORDER = "#e2e8f0"
_COLOR_WARNING_BG = "#fff7ed"
_COLOR_WARNING_BORDER = "#fed7aa"
_COLOR_WARNING_TEXT = "#9a3412"


def _base_template(title: str, body_html: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>{title}</title>
</head>
<body style="margin:0;padding:0;background-color:{_COLOR_BG};font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
    <tr>
      <td align="center" style="padding:40px 16px;">
        <table role="presentation" width="100%" style="max-width:580px;" cellspacing="0" cellpadding="0" border="0">

          <!-- Header -->
          <tr>
            <td style="background:linear-gradient(135deg,{_COLOR_HEADER_FROM} 0%,{_COLOR_HEADER_TO} 100%);border-radius:12px 12px 0 0;padding:32px 40px;text-align:center;">
              <p style="margin:0;font-size:11px;font-weight:700;letter-spacing:3px;text-transform:uppercase;color:rgba(255,255,255,0.5);">THANDILABS</p>
              <h1 style="margin:8px 0 0;font-size:22px;font-weight:700;color:#ffffff;letter-spacing:-0.3px;">thandiport</h1>
              <p style="margin:6px 0 0;font-size:12px;color:rgba(255,255,255,0.45);">Identity &amp; Access Management</p>
            </td>
          </tr>

          <!-- Body card -->
          <tr>
            <td style="background:{_COLOR_CARD};padding:40px;border-left:1px solid {_COLOR_BORDER};border-right:1px solid {_COLOR_BORDER};">
              {body_html}
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background:{_COLOR_BG};border-radius:0 0 12px 12px;border:1px solid {_COLOR_BORDER};border-top:none;padding:24px 40px;text-align:center;">
              <p style="margin:0;font-size:12px;color:{_COLOR_MUTED};">
                This email was sent by <strong>Thandilabs</strong>. If you did not request this, you can safely ignore it.
              </p>
              <p style="margin:8px 0 0;font-size:11px;color:{_COLOR_BORDER};">
                &copy; {_year()} Thandilabs. All rights reserved.
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _year() -> int:
    from datetime import UTC, datetime
    return datetime.now(UTC).year


def _button(text: str, url: str) -> str:
    return f"""
<table role="presentation" cellspacing="0" cellpadding="0" border="0" style="margin:28px auto 0;">
  <tr>
    <td style="border-radius:8px;background:{_COLOR_ACCENT};">
      <a href="{url}" target="_blank"
         style="display:inline-block;padding:14px 32px;font-size:15px;font-weight:600;
                color:#ffffff;text-decoration:none;letter-spacing:0.2px;border-radius:8px;">
        {text}
      </a>
    </td>
  </tr>
</table>"""


def _divider() -> str:
    return f'<hr style="border:none;border-top:1px solid {_COLOR_BORDER};margin:28px 0;" />'


# ── Email builders ─────────────────────────────────────────────────────────────

def _build_reset_email(username: str, reset_url: str) -> str:
    body = f"""
      <h2 style="margin:0 0 8px;font-size:22px;font-weight:700;color:{_COLOR_TEXT};">
        Reset your password
      </h2>
      <p style="margin:0 0 20px;font-size:15px;line-height:1.6;color:{_COLOR_MUTED};">
        Hi <strong>{username}</strong>, we received a request to reset the password for your
        Thandilabs account. Click the button below to choose a new one.
      </p>

      {_button("Reset My Password", reset_url)}

      {_divider()}

      <div style="background:{_COLOR_WARNING_BG};border:1px solid {_COLOR_WARNING_BORDER};
                  border-radius:8px;padding:16px 20px;">
        <p style="margin:0;font-size:13px;line-height:1.6;color:{_COLOR_WARNING_TEXT};">
          ⚠️ &nbsp;<strong>This link expires in 30 minutes.</strong> If you did not request a
          password reset, please ignore this email — your password will not change.
        </p>
      </div>

      {_divider()}

      <p style="margin:0;font-size:13px;color:{_COLOR_MUTED};">
        If the button above doesn't work, copy and paste this URL into your browser:
      </p>
      <p style="margin:8px 0 0;font-size:12px;word-break:break-all;
                color:{_COLOR_ACCENT};font-family:monospace;">
        {reset_url}
      </p>
    """
    return _base_template("Reset your Thandilabs password", body)


def _build_password_changed_email(username: str) -> str:
    from datetime import UTC, datetime
    timestamp = datetime.now(UTC).strftime("%B %d, %Y at %H:%M UTC")
    body = f"""
      <h2 style="margin:0 0 8px;font-size:22px;font-weight:700;color:{_COLOR_TEXT};">
        Password changed
      </h2>
      <p style="margin:0 0 20px;font-size:15px;line-height:1.6;color:{_COLOR_MUTED};">
        Hi <strong>{username}</strong>, this is a confirmation that the password for your
        Thandilabs account was successfully changed.
      </p>

      <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:16px 20px;">
        <p style="margin:0;font-size:13px;line-height:1.6;color:#166534;">
          ✅ &nbsp;Password updated on <strong>{timestamp}</strong>
        </p>
      </div>

      {_divider()}

      <div style="background:{_COLOR_WARNING_BG};border:1px solid {_COLOR_WARNING_BORDER};
                  border-radius:8px;padding:16px 20px;">
        <p style="margin:0;font-size:13px;line-height:1.6;color:{_COLOR_WARNING_TEXT};">
          🔒 &nbsp;<strong>Didn't make this change?</strong> Contact support immediately or use
          the forgot-password flow to regain control of your account.
        </p>
      </div>
    """
    return _base_template("Your Thandilabs password was changed", body)


# ── Public API ─────────────────────────────────────────────────────────────────

async def send_password_reset_email(to_email: str, username: str, reset_token: str) -> None:
    reset_url = f"{settings.FRONTEND_URL}/reset-password?token={reset_token}"
    html = _build_reset_email(username, reset_url)
    await _send(
        to=to_email,
        subject="Reset your Thandilabs password",
        html=html,
    )


async def send_password_changed_email(to_email: str, username: str) -> None:
    html = _build_password_changed_email(username)
    await _send(
        to=to_email,
        subject="Your Thandilabs password was changed",
        html=html,
    )


async def _send(to: str, subject: str, html: str) -> None:
    if not settings.SMTP_ENABLED:
        logger.info("SMTP disabled — skipping email to %s | subject: %s", to, subject)
        return

    message = MIMEMultipart("alternative")
    message["From"] = f"{settings.SMTP_FROM_NAME} <{settings.SMTP_FROM_EMAIL}>"
    message["To"] = to
    message["Subject"] = subject
    message.attach(MIMEText(html, "html", "utf-8"))

    try:
        await aiosmtplib.send(
            message,
            hostname=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USER or None,
            password=settings.SMTP_PASSWORD or None,
            use_tls=settings.SMTP_USE_TLS,
            start_tls=settings.SMTP_START_TLS,
        )
        logger.info("Email sent to %s | subject: %s", to, subject)
    except Exception:
        logger.exception("Failed to send email to %s | subject: %s", to, subject)
