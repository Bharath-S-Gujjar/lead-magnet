"""Communication provider abstraction layer.

Defines base provider interface and safe local dry-run communication providers.
"""

from datetime import datetime, timezone
import uuid


class CommunicationProvider:
    """Base abstract communication provider class."""

    def send_email(self, recipient, subject, body, metadata=None):
        raise NotImplementedError("send_email must be implemented by subclass")

    def send_sms(self, recipient, body, metadata=None):
        raise NotImplementedError("send_sms must be implemented by subclass")

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

    def send_sms(self, recipient, body, metadata=None):
        msg_id = f"dry-run-sms-{uuid.uuid4().hex[:12]}"
        return {
            "success": True,
            "provider": "dry_run",
            "provider_message_id": msg_id,
            "channel": "sms",
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

    def send_sms(self, recipient, body, metadata=None):
        return {
            "success": False,
            "provider": "failing_mock",
            "provider_message_id": None,
            "error": self.error_message,
            "channel": "sms",
        }

    def send_whatsapp(self, recipient, body, metadata=None):
        return {
            "success": False,
            "provider": "failing_mock",
            "provider_message_id": None,
            "error": self.error_message,
            "channel": "whatsapp",
        }


def get_communication_provider(provider_name="dry_run"):
    """Factory function returning configured communication provider instance."""
    if provider_name == "dry_run":
        return DryRunCommunicationProvider()
    elif provider_name == "failing_mock":
        return FailingCommunicationProvider()
    else:
        # Default fallback to dry-run for safety
        return DryRunCommunicationProvider()
