"""
Email sender module using Gmail SMTP.

This module handles sending emails via Gmail's SMTP server.
Requires Gmail app-specific password (not your regular Gmail password).
"""

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr, make_msgid
from typing import Optional
from datetime import datetime
from dotenv import load_dotenv
from loguru import logger

# Load environment variables
load_dotenv()

# Gmail SMTP Configuration
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")


class EmailSendError(Exception):
    """Custom exception for email sending errors."""

    pass


def send_email(
    to_email: str,
    subject: str,
    html_body: str,
    plain_body: Optional[str] = None,
    from_name: str = "Recipe Recommender",
) -> str:
    """
    Send an email via Gmail SMTP.

    Args:
        to_email: Recipient email address
        subject: Email subject line
        html_body: HTML content of the email
        plain_body: Plain text version (optional, will be auto-generated if not provided)
        from_name: Display name for sender

    Returns:
        Message-ID for tracking replies

    Raises:
        EmailSendError: If email sending fails
    """
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        raise EmailSendError(
            "Gmail credentials not configured. Please set GMAIL_ADDRESS and GMAIL_APP_PASSWORD in .env"
        )

    # Create message
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = formataddr((from_name, GMAIL_ADDRESS))
    msg["To"] = to_email
    msg["Date"] = formataddr((None, datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S +0000")))

    # Generate unique Message-ID for tracking replies
    message_id = make_msgid(domain=GMAIL_ADDRESS.split("@")[1])
    msg["Message-ID"] = message_id

    # Create plain text version if not provided
    if plain_body is None:
        # Simple HTML to text conversion
        import re
        plain_body = re.sub("<[^<]+?>", "", html_body)

    # Attach both plain and HTML versions
    part1 = MIMEText(plain_body, "plain")
    part2 = MIMEText(html_body, "html")
    msg.attach(part1)
    msg.attach(part2)

    try:
        # Connect to Gmail SMTP server
        logger.debug(f"Connecting to {SMTP_SERVER}:{SMTP_PORT}")
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()

            # Login
            logger.debug(f"Logging in as {GMAIL_ADDRESS}")
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)

            # Send email
            logger.debug(f"Sending email to {to_email}")
            server.send_message(msg)

        logger.info(f"Email sent successfully to {to_email}: {subject}")
        logger.debug(f"Message-ID: {message_id}")
        return message_id

    except smtplib.SMTPAuthenticationError as e:
        logger.error(f"SMTP Authentication failed: {e}")
        raise EmailSendError(
            "Gmail authentication failed. Check your GMAIL_APP_PASSWORD. "
            "You need an app-specific password, not your regular Gmail password."
        )
    except smtplib.SMTPException as e:
        logger.error(f"SMTP error: {e}")
        raise EmailSendError(f"Failed to send email: {e}")
    except Exception as e:
        logger.error(f"Unexpected error sending email: {e}")
        raise EmailSendError(f"Unexpected error: {e}")


def send_test_email(to_email: Optional[str] = None) -> None:
    """
    Send a test email to verify SMTP configuration.

    Args:
        to_email: Recipient email (defaults to USER_EMAIL from .env)
    """
    if to_email is None:
        to_email = os.getenv("USER_EMAIL")

    if not to_email:
        print("Error: No email address provided and USER_EMAIL not set in .env")
        return

    subject = "Test Email from Recipe Recommender"
    html_body = """
    <html>
      <head></head>
      <body>
        <h2>🎉 Email System Test</h2>
        <p>Hello!</p>
        <p>This is a test email from your Recipe Recommender system.</p>
        <p>If you're reading this, your email configuration is working correctly!</p>
        <hr>
        <p style="color: #666; font-size: 12px;">
          Sent from Recipe Recommender<br>
          Powered by Spoonacular API
        </p>
      </body>
    </html>
    """

    try:
        message_id = send_email(to_email, subject, html_body)
        print(f"✅ Test email sent successfully to {to_email}")
        print(f"📧 Message-ID: {message_id}")
        print("\nCheck your inbox!")
    except EmailSendError as e:
        print(f"❌ Failed to send test email: {e}")


if __name__ == "__main__":
    # Test the email sender
    logger.add("logs/email_test.log", rotation="1 day")

    print("Testing Email Sender...")
    print("-" * 50)
    print("\nTo use Gmail SMTP, you need:")
    print("1. Enable 2-Factor Authentication on your Gmail account")
    print("2. Generate an app-specific password:")
    print("   https://myaccount.google.com/apppasswords")
    print("3. Add it to your .env file as GMAIL_APP_PASSWORD")
    print("-" * 50)
    print()

    send_test_email()
