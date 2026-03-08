"""
Email Service for sending transactional emails.

Supports:
- Password reset emails
- Team invitation emails
- SMTP configuration for all editions (Hostinger for SaaS, custom for Enterprise)
"""

import logging
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from dataclasses import dataclass

from ..core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class EmailResult:
    """Result of an email send operation."""
    success: bool
    message: str
    error: Optional[str] = None


class EmailService:
    """
    Email service for sending transactional emails via SMTP.

    Supports TLS (port 587) and SSL (port 465) connections.
    """

    def __init__(self):
        """Initialize email service with configuration from settings."""
        self.host = settings.SMTP_HOST
        self.port = settings.SMTP_PORT
        self.user = settings.SMTP_USER
        self.password = settings.SMTP_PASSWORD
        self.from_email = settings.SMTP_FROM_EMAIL or settings.SMTP_USER
        self.from_name = settings.SMTP_FROM_NAME
        self.use_tls = settings.SMTP_USE_TLS
        self.use_ssl = settings.SMTP_USE_SSL

    @property
    def is_configured(self) -> bool:
        """Check if SMTP is properly configured."""
        return bool(self.host and self.user and self.password)

    def _create_message(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        text_body: Optional[str] = None
    ) -> MIMEMultipart:
        """Create a MIME message with HTML and optional plain text."""
        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = f"{self.from_name} <{self.from_email}>"
        message["To"] = to_email

        # Add plain text version (fallback)
        if text_body:
            message.attach(MIMEText(text_body, "plain", "utf-8"))

        # Add HTML version
        message.attach(MIMEText(html_body, "html", "utf-8"))

        return message

    def send_email(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        text_body: Optional[str] = None
    ) -> EmailResult:
        """
        Send an email via SMTP.

        Args:
            to_email: Recipient email address
            subject: Email subject
            html_body: HTML content
            text_body: Optional plain text content (fallback)

        Returns:
            EmailResult with success status
        """
        if not self.is_configured:
            logger.warning("SMTP not configured, skipping email send")
            return EmailResult(
                success=False,
                message="SMTP not configured",
                error="SMTP_HOST, SMTP_USER, or SMTP_PASSWORD not set"
            )

        try:
            message = self._create_message(to_email, subject, html_body, text_body)

            # Choose connection type based on configuration
            if self.use_ssl:
                # SSL connection (typically port 465)
                context = ssl.create_default_context()
                with smtplib.SMTP_SSL(self.host, self.port, context=context) as server:
                    server.login(self.user, self.password)
                    server.sendmail(self.from_email, to_email, message.as_string())
            else:
                # TLS connection (typically port 587)
                with smtplib.SMTP(self.host, self.port) as server:
                    if self.use_tls:
                        context = ssl.create_default_context()
                        server.starttls(context=context)
                    server.login(self.user, self.password)
                    server.sendmail(self.from_email, to_email, message.as_string())

            logger.info(f"Email sent successfully to {to_email}: {subject}")
            return EmailResult(success=True, message="Email sent successfully")

        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"SMTP authentication failed: {e}")
            return EmailResult(
                success=False,
                message="Authentication failed",
                error=str(e)
            )
        except smtplib.SMTPException as e:
            logger.error(f"SMTP error sending email to {to_email}: {e}")
            return EmailResult(
                success=False,
                message="Failed to send email",
                error=str(e)
            )
        except Exception as e:
            logger.exception(f"Unexpected error sending email to {to_email}: {e}")
            return EmailResult(
                success=False,
                message="Unexpected error",
                error=str(e)
            )

    # =========================================================================
    # Password Reset Emails
    # =========================================================================

    def send_password_reset_email(
        self,
        to_email: str,
        reset_link: str,
        user_name: Optional[str] = None,
        expires_hours: int = 24
    ) -> EmailResult:
        """
        Send a password reset email.

        Args:
            to_email: User's email address
            reset_link: Full URL for password reset (includes token)
            user_name: Optional user's display name
            expires_hours: Token expiration time in hours

        Returns:
            EmailResult with success status
        """
        subject = "Reset your BigMCP password"

        greeting = f"Hi {user_name}," if user_name else "Hi,"

        html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Reset your password</title>
</head>
<body style="font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #171717; max-width: 600px; margin: 0 auto; padding: 20px; background-color: #FAFAFA;">
    <div style="background: #D97757; padding: 30px; border-radius: 10px 10px 0 0; text-align: center;">
        <h1 style="color: white; margin: 0; font-size: 28px; font-weight: 700;">BigMCP</h1>
    </div>

    <div style="background: #ffffff; padding: 30px; border: 1px solid #E5E5E5; border-top: none; border-radius: 0 0 10px 10px;">
        <p style="font-size: 16px; color: #525252;">{greeting}</p>

        <p style="font-size: 16px; color: #525252;">We received a request to reset your password. Click the button below to create a new password:</p>

        <div style="text-align: center; margin: 30px 0;">
            <a href="{reset_link}" style="background: #D97757; color: white; padding: 14px 30px; text-decoration: none; border-radius: 6px; font-size: 16px; font-weight: 600; display: inline-block; box-shadow: 0 4px 14px 0 rgba(217, 119, 87, 0.39);">Reset Password</a>
        </div>

        <p style="font-size: 14px; color: #525252;">This link will expire in {expires_hours} hours.</p>

        <p style="font-size: 14px; color: #525252;">If you didn't request this password reset, you can safely ignore this email. Your password will remain unchanged.</p>

        <hr style="border: none; border-top: 1px solid #E5E5E5; margin: 30px 0;">

        <p style="font-size: 12px; color: #737373;">If the button doesn't work, copy and paste this link into your browser:</p>
        <p style="font-size: 12px; color: #D97757; word-break: break-all;">{reset_link}</p>
    </div>

    <div style="text-align: center; padding: 20px; color: #737373; font-size: 12px;">
        <p>&copy; BigMCP - MCP Server Management Platform</p>
    </div>
</body>
</html>
"""

        text_body = f"""
{greeting}

We received a request to reset your password.

Click the link below to create a new password:
{reset_link}

This link will expire in {expires_hours} hours.

If you didn't request this password reset, you can safely ignore this email.

---
BigMCP - MCP Server Management Platform
"""

        return self.send_email(to_email, subject, html_body, text_body)

    # =========================================================================
    # Team Invitation Emails
    # =========================================================================

    def send_invitation_email(
        self,
        to_email: str,
        invitation_link: str,
        organization_name: str,
        inviter_name: Optional[str] = None,
        role: str = "member",
        message: Optional[str] = None,
        expires_days: int = 7
    ) -> EmailResult:
        """
        Send a team invitation email.

        Args:
            to_email: Invitee's email address
            invitation_link: Full URL to accept invitation (includes token)
            organization_name: Name of the organization
            inviter_name: Name of the person who sent the invitation
            role: Role being offered (member, admin)
            message: Optional personal message from inviter
            expires_days: Invitation expiration time in days

        Returns:
            EmailResult with success status
        """
        subject = f"You've been invited to join {organization_name} on BigMCP"

        inviter_text = f"{inviter_name} has" if inviter_name else "You have been"
        role_display = "an admin" if role == "admin" else "a team member"

        message_section = ""
        message_text = ""
        if message:
            message_section = f"""
        <div style="background: #FEF3C7; padding: 15px; border-radius: 6px; margin: 20px 0; border-left: 4px solid #D97757;">
            <p style="margin: 0; font-style: italic; color: #555;">"{message}"</p>
            {f'<p style="margin: 10px 0 0 0; color: #888; font-size: 14px;">- {inviter_name}</p>' if inviter_name else ''}
        </div>
"""
            message_text = f'\nPersonal message: "{message}"'

        html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Team Invitation</title>
</head>
<body style="font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #171717; max-width: 600px; margin: 0 auto; padding: 20px; background-color: #FAFAFA;">
    <div style="background: #D97757; padding: 30px; border-radius: 10px 10px 0 0; text-align: center;">
        <h1 style="color: white; margin: 0; font-size: 28px; font-weight: 700;">BigMCP</h1>
    </div>

    <div style="background: #ffffff; padding: 30px; border: 1px solid #E5E5E5; border-top: none; border-radius: 0 0 10px 10px;">
        <h2 style="color: #171717; margin-top: 0; font-weight: 600;">You're invited!</h2>

        <p style="font-size: 16px; color: #525252;">{inviter_text} invited you to join <strong style="color: #171717;">{organization_name}</strong> as {role_display}.</p>

        {message_section}

        <div style="text-align: center; margin: 30px 0;">
            <a href="{invitation_link}" style="background: #D97757; color: white; padding: 14px 30px; text-decoration: none; border-radius: 6px; font-size: 16px; font-weight: 600; display: inline-block; box-shadow: 0 4px 14px 0 rgba(217, 119, 87, 0.39);">Accept Invitation</a>
        </div>

        <p style="font-size: 14px; color: #525252;">This invitation will expire in {expires_days} days.</p>

        <hr style="border: none; border-top: 1px solid #E5E5E5; margin: 30px 0;">

        <p style="font-size: 12px; color: #737373;">If you don't know who sent this invitation or don't want to join, you can safely ignore this email.</p>

        <p style="font-size: 12px; color: #737373;">If the button doesn't work, copy and paste this link into your browser:</p>
        <p style="font-size: 12px; color: #D97757; word-break: break-all;">{invitation_link}</p>
    </div>

    <div style="text-align: center; padding: 20px; color: #737373; font-size: 12px;">
        <p>&copy; BigMCP - MCP Server Management Platform</p>
    </div>
</body>
</html>
"""

        text_body = f"""
You're invited!

{inviter_text} invited you to join {organization_name} as {role_display}.
{message_text}

Click the link below to accept the invitation:
{invitation_link}

This invitation will expire in {expires_days} days.

If you don't know who sent this invitation, you can safely ignore this email.

---
BigMCP - MCP Server Management Platform
"""

        return self.send_email(to_email, subject, html_body, text_body)

    # =========================================================================
    # Email Verification Emails
    # =========================================================================

    def send_verification_email(
        self,
        to_email: str,
        verification_link: str,
        user_name: Optional[str] = None,
        expires_hours: int = 48
    ) -> EmailResult:
        """
        Send an email verification email.

        Args:
            to_email: User's email address
            verification_link: Full URL for email verification (includes token)
            user_name: Optional user's display name
            expires_hours: Token expiration time in hours

        Returns:
            EmailResult with success status
        """
        subject = "Verify your BigMCP email address"

        greeting = f"Hi {user_name}," if user_name else "Hi,"

        html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Verify your email</title>
</head>
<body style="font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #171717; max-width: 600px; margin: 0 auto; padding: 20px; background-color: #FAFAFA;">
    <div style="background: #D97757; padding: 30px; border-radius: 10px 10px 0 0; text-align: center;">
        <h1 style="color: white; margin: 0; font-size: 28px; font-weight: 700;">BigMCP</h1>
    </div>

    <div style="background: #ffffff; padding: 30px; border: 1px solid #E5E5E5; border-top: none; border-radius: 0 0 10px 10px;">
        <h2 style="color: #171717; margin-top: 0; font-weight: 600;">Welcome to BigMCP!</h2>

        <p style="font-size: 16px; color: #525252;">{greeting}</p>

        <p style="font-size: 16px; color: #525252;">Thanks for signing up! Please verify your email address by clicking the button below:</p>

        <div style="text-align: center; margin: 30px 0;">
            <a href="{verification_link}" style="background: #D97757; color: white; padding: 14px 30px; text-decoration: none; border-radius: 6px; font-size: 16px; font-weight: 600; display: inline-block; box-shadow: 0 4px 14px 0 rgba(217, 119, 87, 0.39);">Verify Email</a>
        </div>

        <p style="font-size: 14px; color: #525252;">This link will expire in {expires_hours} hours.</p>

        <p style="font-size: 14px; color: #525252;">If you didn't create an account on BigMCP, you can safely ignore this email.</p>

        <hr style="border: none; border-top: 1px solid #E5E5E5; margin: 30px 0;">

        <p style="font-size: 12px; color: #737373;">If the button doesn't work, copy and paste this link into your browser:</p>
        <p style="font-size: 12px; color: #D97757; word-break: break-all;">{verification_link}</p>
    </div>

    <div style="text-align: center; padding: 20px; color: #737373; font-size: 12px;">
        <p>&copy; BigMCP - MCP Server Management Platform</p>
    </div>
</body>
</html>
"""

        text_body = f"""
{greeting}

Welcome to BigMCP!

Thanks for signing up! Please verify your email address by clicking the link below:
{verification_link}

This link will expire in {expires_hours} hours.

If you didn't create an account on BigMCP, you can safely ignore this email.

---
BigMCP - MCP Server Management Platform
"""

        return self.send_email(to_email, subject, html_body, text_body)


# Singleton instance
_email_service: Optional[EmailService] = None


def get_email_service() -> EmailService:
    """Get the email service singleton."""
    global _email_service
    if _email_service is None:
        _email_service = EmailService()
    return _email_service
