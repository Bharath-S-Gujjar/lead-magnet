"""Communication provider abstraction layer.

Defines base provider interface, safe dry-run providers, and production providers
for email (Gmail SMTP) and WhatsApp (Business API).

Channels supported: EMAIL, WHATSAPP.
NO SMS — explicitly removed per product requirement.
"""

from datetime import datetime, timezone
import os
import smtplib
import uuid
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

try:
    import requests as _requests_lib
except ImportError:
    _requests_lib = None


class CommunicationProvider:
    """Base abstract communication provider class."""

    def send_email(self, recipient, subject, body, metadata=None):
        raise NotImplementedError("send_email must be implemented by subclass")

    def send_whatsapp(self, recipient, body, metadata=None):
        raise NotImplementedError("send_whatsapp must be implemented by subclass")


class DryRunCommunicationProvider(CommunicationProvider):
    """Local safe communication provider that records dry-run dispatches without network calls."""

    def send_email(self, recipient, subject, body, metadata=None):
        msg_id = f"dry-run-email-{uuid.uuid4().hex[:12]}"
        return {
            "success": True,
            "provider": "dry_run",
            "provider_message_id": msg_id,
            "channel": "email",
            "recipient": recipient,
            "dispatched_at": datetime.now(timezone.utc).isoformat(),
        }

    def send_whatsapp(self, recipient, body, metadata=None):
        msg_id = f"dry-run-whatsapp-{uuid.uuid4().hex[:12]}"
        return {
            "success": True,
            "provider": "dry_run",
            "provider_message_id": msg_id,
            "channel": "whatsapp",
            "recipient": recipient,
            "dispatched_at": datetime.now(timezone.utc).isoformat(),
        }


class FailingCommunicationProvider(CommunicationProvider):
    """Mock provider that simulates communication failure for testing error handling."""

    def __init__(self, error_message="Simulated provider failure"):
        self.error_message = error_message

    def send_email(self, recipient, subject, body, metadata=None):
        return {
            "success": False,
            "provider": "failing_mock",
            "provider_message_id": None,
            "error": self.error_message,
            "channel": "email",
        }

    def send_whatsapp(self, recipient, body, metadata=None):
        return {
            "success": False,
            "provider": "failing_mock",
            "provider_message_id": None,
            "error": self.error_message,
            "channel": "whatsapp",
        }


class GmailSMTPProvider(CommunicationProvider):
    """Production Gmail-compatible SMTP email provider.

    Credentials MUST come from environment variables:
        SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, SMTP_FROM_EMAIL

    Does NOT hardcode credentials. Fails gracefully if env vars are missing.
    """

    def __init__(self):
        self.host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.port = int(os.getenv("SMTP_PORT", "587"))
        self.username = os.getenv("SMTP_USERNAME", "")
        self.password = os.getenv("SMTP_PASSWORD", "")
        self.from_email = os.getenv("SMTP_FROM_EMAIL", "")

    def send_email(self, recipient, subject, body, metadata=None):
        if not self.username or not self.password or not self.from_email:
            return {
                "success": False,
                "provider": "gmail_smtp",
                "provider_message_id": None,
                "error": "SMTP credentials not configured (SMTP_USERNAME, SMTP_PASSWORD, SMTP_FROM_EMAIL required)",
                "channel": "email",
            }

        if not recipient or "@" not in str(recipient):
            return {
                "success": False,
                "provider": "gmail_smtp",
                "provider_message_id": None,
                "error": f"Invalid recipient email: {recipient}",
                "channel": "email",
            }

        try:
            msg = MIMEMultipart()
            msg["From"] = self.from_email
            msg["To"] = recipient
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain"))

            with smtplib.SMTP(self.host, self.port, timeout=30) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(self.username, self.password)
                server.sendmail(self.from_email, recipient, msg.as_string())

            msg_id = f"gmail-smtp-{uuid.uuid4().hex[:12]}"
            return {
                "success": True,
                "provider": "gmail_smtp",
                "provider_message_id": msg_id,
                "channel": "email",
                "recipient": recipient,
                "dispatched_at": datetime.now(timezone.utc).isoformat(),
            }

        except smtplib.SMTPAuthenticationError as e:
            return {
                "success": False,
                "provider": "gmail_smtp",
                "provider_message_id": None,
                "error": f"SMTP authentication failed: {e}",
                "channel": "email",
            }
        except Exception as e:
            return {
                "success": False,
                "provider": "gmail_smtp",
                "provider_message_id": None,
                "error": f"Email delivery failed: {e}",
                "channel": "email",
            }

    def send_whatsapp(self, recipient, body, metadata=None):
        return {
            "success": False,
            "provider": "gmail_smtp",
            "provider_message_id": None,
            "error": "WhatsApp not supported by Gmail SMTP provider",
            "channel": "whatsapp",
        }


class WhatsAppBusinessProvider(CommunicationProvider):
    """Production WhatsApp Business API provider.

    Credentials MUST come from environment variables:
        WHATSAPP_API_URL, WHATSAPP_API_TOKEN, WHATSAPP_PHONE_NUMBER_ID

    Uses the WhatsApp Cloud API for template-based messaging.
    Requires pre-approved message templates in WhatsApp Business Manager.
    """

    def __init__(self):
        self.api_url = os.getenv("WHATSAPP_API_URL", "https://graph.facebook.com/v18.0")
        self.api_token = os.getenv("WHATSAPP_API_TOKEN", "")
        self.phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")

    def send_email(self, recipient, subject, body, metadata=None):
        return {
            "success": False,
            "provider": "whatsapp_business",
            "provider_message_id": None,
            "error": "Email not supported by WhatsApp Business provider",
            "channel": "email",
        }

    def send_whatsapp(self, recipient, body, metadata=None):
        if not self.api_token or not self.phone_number_id:
            return {
                "success": False,
                "provider": "whatsapp_business",
                "provider_message_id": None,
                "error": "WhatsApp Business credentials not configured (WHATSAPP_API_TOKEN, WHATSAPP_PHONE_NUMBER_ID required)",
                "channel": "whatsapp",
            }

        if not recipient or not isinstance(recipient, str) or not recipient.strip():
            return {
                "success": False,
                "provider": "whatsapp_business",
                "provider_message_id": None,
                "error": f"Invalid recipient phone: {recipient}",
                "channel": "whatsapp",
            }

        if _requests_lib is None:
            return {
                "success": False,
                "provider": "whatsapp_business",
                "provider_message_id": None,
                "error": "requests library not available for WhatsApp API calls",
                "channel": "whatsapp",
            }

        url = f"{self.api_url}/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

        # Text message (non-template for simplicity; production should use templates)
        payload = {
            "messaging_product": "whatsapp",
            "to": recipient.strip(),
            "type": "text",
            "text": {"body": body},
        }

        try:
            response = _requests_lib.post(url, json=payload, headers=headers, timeout=30)
            resp_data = response.json() if response.content else {}

            if response.status_code in (200, 201):
                messages = resp_data.get("messages", [])
                msg_id = messages[0].get("id") if messages else f"wa-{uuid.uuid4().hex[:12]}"
                return {
                    "success": True,
                    "provider": "whatsapp_business",
                    "provider_message_id": msg_id,
                    "channel": "whatsapp",
                    "recipient": recipient,
                    "dispatched_at": datetime.now(timezone.utc).isoformat(),
                }
            else:
                error_detail = resp_data.get("error", {}).get("message", f"HTTP {response.status_code}")
                return {
                    "success": False,
                    "provider": "whatsapp_business",
                    "provider_message_id": None,
                    "error": f"WhatsApp API error: {error_detail}",
                    "channel": "whatsapp",
                }

        except Exception as e:
            return {
                "success": False,
                "provider": "whatsapp_business",
                "provider_message_id": None,
                "error": f"WhatsApp delivery failed: {e}",
                "channel": "whatsapp",
            }


def get_communication_provider(provider_name=None):
    """Factory function returning configured communication provider instance.

    Args:
        provider_name (str, optional): Provider name. Auto-detected from env if None.

    Returns:
        CommunicationProvider: Configured provider instance.
    """
    if provider_name is None:
        provider_name = os.getenv("COMMUNICATION_PROVIDER", "dry_run")

    if provider_name == "dry_run":
        return DryRunCommunicationProvider()
    elif provider_name == "failing_mock":
        return FailingCommunicationProvider()
    elif provider_name == "gmail_smtp":
        return GmailSMTPProvider()
    elif provider_name == "whatsapp_business":
        return WhatsAppBusinessProvider()
    else:
        # Default fallback to dry-run for safety
        return DryRunCommunicationProvider()
