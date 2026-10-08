"""Communication provider abstraction layer.

Defines base provider interface, safe dry-run providers, and production providers
for email (Gmail SMTP) and WhatsApp (Business API).

Channels supported: EMAIL, WHATSAPP.
NO SMS — explicitly removed per product requirement.
"""

from datetime import datetime, timezone
import email.utils
import os
import smtplib
import uuid
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Sender display name used in the From header, e.g. "Lead Magnet <noreply@gmail.com>"
# Set SENDER_DISPLAY_NAME in .env to override. Defaults to "Lead Magnet".
SENDER_DISPLAY_NAME = os.getenv("SENDER_DISPLAY_NAME", "Lead Magnet")


def _format_from_address(display_name, email_addr):
    """Return a properly RFC 2822 formatted From address.

    Result: 'Display Name <email@example.com>'
    Falls back to bare email address if display_name is empty.
    """
    name = (display_name or "").strip()
    if name:
        return email.utils.formataddr((name, email_addr))
    return email_addr


def normalize_whatsapp_phone(phone_str):
    """Normalize phone number to Meta WhatsApp Cloud API format (E.164 digits without leading '+').

    Meta WhatsApp Cloud API expects recipient numbers in international format:
        Country code followed by national subscriber number, with no leading zeros,
        dashes, spaces, parentheses, or plus signs.
        Example:
            "+91 98765-43210" -> "919876543210"
            "+1 (555) 123-4567" -> "15551234567"

    Rules:
        - If phone is empty, non-string, or has no digits: returns (None, error_msg).
        - Strips whitespace, hyphens, parentheses, and dots.
        - If phone starts with '+': strips '+' and validates that remaining digits
          form a valid international E.164 number (8 to 15 digits).
        - If phone does NOT start with '+':
          - If 11 to 15 digits: treated as already containing international country code.
          - If 10 digits or fewer: returns (None, error_msg) because country codes
            CANNOT be guessed or inferred from arbitrary national numbers.
    """
    if not phone_str or not isinstance(phone_str, str):
        return None, "Invalid or empty phone number"

    cleaned = phone_str.strip()
    if not cleaned:
        return None, "Invalid or empty phone number"

    has_plus = cleaned.startswith("+")
    digits = "".join(ch for ch in cleaned if ch.isdigit())

    if not digits:
        return None, f"Phone number contains no digits: {phone_str}"

    if has_plus:
        if len(digits) < 8 or len(digits) > 15:
            return None, f"Invalid international phone number length ({len(digits)} digits, expected 8-15): {phone_str}"
        return digits, None

    # No leading plus
    if len(digits) < 11:
        return None, (
            f"Phone number '{phone_str}' lacks international country code. "
            "Meta WhatsApp Cloud API requires country code (e.g. +91XXXXXXXXXX or +1XXXXXXXXXX). "
            "Country code cannot be guessed from arbitrary national numbers."
        )
    elif len(digits) > 15:
        return None, f"Phone number exceeds maximum E.164 length of 15 digits: {phone_str}"

    return digits, None


def _build_html_body(plain_text, store_url=None, campaign_type=None, image_url=None):
    """Generate a clean, minimal HTML email body from plain text.

    Uses a simple table layout. No hidden text, no tracking pixels,
    no invisible links, no deceptive content. Supports optional product image.
    """
    # Escape HTML entities in the plain text
    safe_text = (
        plain_text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    # Convert line breaks to HTML
    html_lines = safe_text.replace("\n\n", "</p><p>").replace("\n", "<br>")
    img_html = (
        f'<div style="text-align:center;margin:18px 0;">'
        f'<img src="{image_url}" alt="Product" style="max-width:280px;height:auto;border-radius:6px;border:1px solid #e0e0e0;display:inline-block;">'
        f'</div>'
        if image_url else ""
    )

    return (
        '<!DOCTYPE html>'
        '<html lang="en">'
        '<head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Lead Magnet</title>'
        '<style>'
        'body{margin:0;padding:0;background:#f5f5f5;font-family:Arial,sans-serif;font-size:15px;color:#222;}'
        '.wrap{max-width:560px;margin:32px auto;background:#fff;border-radius:6px;overflow:hidden;}'
        '.hdr{background:#1a1a2e;padding:20px 28px;}'
        '.hdr span{color:#fff;font-size:18px;font-weight:bold;letter-spacing:.5px;}'
        '.body{padding:28px;}'
        '.body p{margin:0 0 14px;line-height:1.6;}'
        '.footer{padding:16px 28px;background:#f0f0f0;font-size:12px;color:#666;border-top:1px solid #e0e0e0;}'
        '</style>'
        '</head>'
        '<body>'
        '<table width="100%" cellpadding="0" cellspacing="0" border="0"><tr><td align="center" style="padding:16px;">'
        '<div class="wrap">'
        '<div class="hdr"><span>Lead Magnet</span></div>'
        f'<div class="body">{img_html}<p>{html_lines}</p></div>'
        '<div class="footer">'
        'You are receiving this email because you have an account at Lead Magnet.'
        '</div>'
        '</div>'
        '</td></tr></table>'
        '</body></html>'
    )

try:
    import requests as _requests_lib
except ImportError:
    _requests_lib = None


class CommunicationProvider:
    """Base abstract communication provider class."""

    def send_email(self, recipient, subject, body, metadata=None, html_body=None, **kwargs):
        raise NotImplementedError("send_email must be implemented by subclass")

    def send_whatsapp(self, recipient, body, metadata=None):
        raise NotImplementedError("send_whatsapp must be implemented by subclass")


class DryRunCommunicationProvider(CommunicationProvider):
    """Local safe communication provider that records dry-run dispatches without network calls."""

    def send_email(self, recipient, subject, body, metadata=None, html_body=None, **kwargs):
        msg_id = f"dry-run-email-{uuid.uuid4().hex[:12]}"
        img_url = metadata.get("primary_image") or metadata.get("image_url") if isinstance(metadata, dict) else None
        effective_html = html_body if html_body else _build_html_body(body, image_url=img_url)
        return {
            "success": True,
            "provider": "dry_run",
            "provider_message_id": msg_id,
            "channel": "email",
            "recipient": recipient,
            "subject": subject,
            "body": body,
            "html_body": effective_html,
            "metadata": metadata or {},
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

    def send_email(self, recipient, subject, body, metadata=None, html_body=None, **kwargs):
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
        SMTP_HOST, SMTP_PORT, SMTP_USERNAME (or GMAIL_USER),
        SMTP_PASSWORD (or GMAIL_APP_PASSWORD), SMTP_FROM_EMAIL

    Does NOT hardcode credentials. Fails gracefully if env vars are missing.
    """

    def __init__(self):
        self.host = os.getenv("SMTP_HOST") or os.getenv("GMAIL_SMTP_HOST", "smtp.gmail.com")
        port_val = os.getenv("SMTP_PORT") or os.getenv("GMAIL_SMTP_PORT", "587")
        try:
            self.port = int(port_val)
        except (ValueError, TypeError):
            self.port = 587
        self.username = os.getenv("SMTP_USERNAME") or os.getenv("GMAIL_USER") or os.getenv("GMAIL_EMAIL", "")
        self.password = os.getenv("SMTP_PASSWORD") or os.getenv("GMAIL_APP_PASSWORD", "")
        self.from_email = os.getenv("SMTP_FROM_EMAIL") or os.getenv("GMAIL_FROM_EMAIL") or self.username
        self.display_name = os.getenv("SENDER_DISPLAY_NAME", "Lead Magnet")

    def send_email(self, recipient, subject, body, metadata=None, html_body=None, unsubscribe_url=None):
        """Send an email via Gmail SMTP.

        Args:
            recipient: Destination email address.
            subject: Email subject line.
            body: Plain-text body.
            metadata: Optional dict of tracking metadata (not included in message).
            unsubscribe_url: Optional real List-Unsubscribe URL for marketing emails.
                             If None, no List-Unsubscribe header is added.
                             Do NOT pass a fake URL.

        Note:
            'success=True' confirms that the message was accepted for relay by the SMTP server
            (e.g., Gmail MTA). Final inbox placement (Inbox vs. Spam vs. Promotions) is determined
            asynchronously by the recipient provider and cannot be determined or guaranteed via SMTP.
        """
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
            # Build RFC 2822-compliant multipart/alternative message.
            msg = MIMEMultipart("alternative")
            from_addr = _format_from_address(self.display_name, self.from_email)
            msg["From"] = from_addr
            msg["To"] = recipient
            msg["Subject"] = subject
            msg["Date"] = email.utils.formatdate(localtime=False)
            message_id = email.utils.make_msgid(domain=self.from_email.split("@")[-1])
            msg["Message-ID"] = message_id

            # List-Unsubscribe: only added when a real URL is supplied.
            # Never add a fake or placeholder URL.
            if unsubscribe_url and unsubscribe_url.startswith("http"):
                msg["List-Unsubscribe"] = f"<{unsubscribe_url}>"
                msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"

            # Plain-text part (first, so it is the fallback)
            msg.attach(MIMEText(body, "plain", "utf-8"))

            # HTML part — use supplied html_body or generate from plain text (with optional product image)
            img_url = None
            if isinstance(metadata, dict):
                img_url = metadata.get("primary_image") or metadata.get("image_url") or metadata.get("product_image")
            rendered_html = html_body if html_body else _build_html_body(body, image_url=img_url)
            msg.attach(MIMEText(rendered_html, "html", "utf-8"))

            with smtplib.SMTP(self.host, self.port, timeout=30) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(self.username, self.password)
                # sendmail() returns {} on full success,
                # or {addr: (code, msg)} for any per-recipient failures.
                refused = server.sendmail(self.from_email, recipient, msg.as_string())

            if refused:
                code, err_msg = list(refused.values())[0]
                sanitized_err = str(err_msg)
                if self.password and self.password in sanitized_err:
                    sanitized_err = sanitized_err.replace(self.password, "[REDACTED]")
                return {
                    "success": False,
                    "provider": "gmail_smtp",
                    "provider_message_id": None,
                    "error": f"SMTP recipient refused ({code}): {sanitized_err}",
                    "channel": "email",
                }

            # provider_message_id is the RFC 2822 Message-ID we assigned
            return {
                "success": True,
                "provider": "gmail_smtp",
                "provider_message_id": message_id,
                "channel": "email",
                "recipient": recipient,
                "dispatched_at": datetime.now(timezone.utc).isoformat(),
            }

        except smtplib.SMTPAuthenticationError:
            return {
                "success": False,
                "provider": "gmail_smtp",
                "provider_message_id": None,
                "error": "SMTP authentication failed: Invalid username or App Password",
                "channel": "email",
            }
        except Exception as e:
            # Sanitize error to avoid leaking any credentials in tracebacks
            sanitized_err = str(e)
            if self.password and self.password in sanitized_err:
                sanitized_err = sanitized_err.replace(self.password, "[REDACTED]")
            return {
                "success": False,
                "provider": "gmail_smtp",
                "provider_message_id": None,
                "error": f"Email delivery failed: {sanitized_err}",
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
    """Production WhatsApp Business API provider via Meta Cloud API.

    Credentials MUST come from environment variables:
        WHATSAPP_API_TOKEN, WHATSAPP_PHONE_NUMBER_ID, and optional WHATSAPP_API_URL or WHATSAPP_GRAPH_VERSION

    API Endpoint:
        POST https://graph.facebook.com/<graph_version>/<phone_number_id>/messages

    Meta WhatsApp Cloud API Rules:
        - Outbound business-initiated communications outside the 24-hour customer service window
          strictly require approved WhatsApp Message Templates.
        - Text messages are permitted within active 24-hour customer service windows.
        - Recipients must be in E.164 international format without leading '+' or formatting characters.
    """

    def __init__(self):
        graph_version = os.getenv("WHATSAPP_GRAPH_VERSION") or os.getenv("GRAPH_API_VERSION", "v18.0")
        default_url = f"https://graph.facebook.com/{graph_version}"
        self.api_url = os.getenv("WHATSAPP_API_URL") or os.getenv("WHATSAPP_BASE_URL", default_url)
        self.api_token = os.getenv("WHATSAPP_API_TOKEN") or os.getenv("META_WHATSAPP_TOKEN", "")
        self.phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID") or os.getenv("META_PHONE_NUMBER_ID", "")
        self.template_lang = os.getenv("WHATSAPP_TEMPLATE_LANGUAGE", "en_US")

    def send_email(self, recipient, subject, body, metadata=None):
        return {
            "success": False,
            "provider": "whatsapp_business",
            "provider_message_id": None,
            "error": "Email not supported by WhatsApp Business provider",
            "channel": "email",
        }

    def send_whatsapp(self, recipient, body, metadata=None):
        """Send a WhatsApp message via Meta Cloud API.

        Args:
            recipient (str): Customer phone number (international format with country code).
            body (str): Clean customer-facing text message.
            metadata (dict, optional): Contextual metadata including campaign_type,
                                       template_name, template_components, template_language.
        """
        if not self.api_token or not self.phone_number_id:
            return {
                "success": False,
                "provider": "whatsapp_business",
                "provider_message_id": None,
                "error": "WhatsApp Business credentials not configured (WHATSAPP_API_TOKEN, WHATSAPP_PHONE_NUMBER_ID required)",
                "channel": "whatsapp",
            }

        norm_phone, norm_err = normalize_whatsapp_phone(recipient)
        if norm_err:
            return {
                "success": False,
                "provider": "whatsapp_business",
                "provider_message_id": None,
                "error": f"Invalid recipient phone: {norm_err}",
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

        meta_dict = metadata or {}
        campaign_type = meta_dict.get("campaign_type")

        # Check if an approved template is configured for this campaign or passed in metadata
        template_name = meta_dict.get("template_name")
        if not template_name and campaign_type:
            env_key = f"WHATSAPP_TEMPLATE_{campaign_type.upper()}"
            template_name = os.getenv(env_key)

        template_lang = meta_dict.get("template_language") or self.template_lang
        template_components = meta_dict.get("template_components")

        url = f"{self.api_url.rstrip('/')}/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

        # Build payload: template if configured, otherwise clean text
        if template_name:
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": norm_phone,
                "type": "template",
                "template": {
                    "name": template_name,
                    "language": {"code": template_lang},
                }
            }
            if template_components:
                payload["template"]["components"] = template_components
        else:
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": norm_phone,
                "type": "text",
                "text": {"preview_url": False, "body": body},
            }

        try:
            response = _requests_lib.post(url, json=payload, headers=headers, timeout=30)
            resp_data = response.json() if response.content else {}

            if response.status_code in (200, 201):
                messages = resp_data.get("messages", [])
                msg_id = messages[0].get("id") if (messages and isinstance(messages, list) and messages[0].get("id")) else None

                if not msg_id:
                    return {
                        "success": False,
                        "provider": "whatsapp_business",
                        "provider_message_id": None,
                        "error": "Meta API accepted request (200 OK) but provided no message ID in messages array",
                        "channel": "whatsapp",
                    }

                return {
                    "success": True,
                    "provider": "whatsapp_business",
                    "provider_message_id": msg_id,
                    "channel": "whatsapp",
                    "recipient": recipient,
                    "dispatched_at": datetime.now(timezone.utc).isoformat(),
                }
            else:
                error_obj = resp_data.get("error", {})
                err_code = error_obj.get("code")
                err_subcode = error_obj.get("error_subcode")
                err_msg = error_obj.get("message") or f"HTTP {response.status_code}"

                if err_code == 131047:
                    error_detail = (
                        "Meta API error 131047: Customer service window (24h) closed. "
                        "Business-initiated outbound messages require an approved WhatsApp Message Template."
                    )
                else:
                    detail_parts = [f"code {err_code}"] if err_code else []
                    if err_subcode:
                        detail_parts.append(f"subcode {err_subcode}")
                    code_prefix = f" ({', '.join(detail_parts)})" if detail_parts else ""
                    error_detail = f"Meta API error{code_prefix}: {err_msg}"

                # Never log or leak access tokens
                if self.api_token and self.api_token in error_detail:
                    error_detail = error_detail.replace(self.api_token, "[REDACTED]")

                return {
                    "success": False,
                    "provider": "whatsapp_business",
                    "provider_message_id": None,
                    "error": error_detail,
                    "channel": "whatsapp",
                }

        except Exception as e:
            sanitized_err = str(e)
            if self.api_token and self.api_token in sanitized_err:
                sanitized_err = sanitized_err.replace(self.api_token, "[REDACTED]")
            return {
                "success": False,
                "provider": "whatsapp_business",
                "provider_message_id": None,
                "error": f"WhatsApp delivery network failure: {sanitized_err}",
                "channel": "whatsapp",
            }


class MultiChannelProvider(CommunicationProvider):
    """Production provider that delegates email to GmailSMTPProvider and WhatsApp to WhatsAppBusinessProvider."""

    def __init__(self, email_provider=None, whatsapp_provider=None):
        self.email_provider = email_provider or GmailSMTPProvider()
        self.whatsapp_provider = whatsapp_provider or WhatsAppBusinessProvider()

    def send_email(self, recipient, subject, body, metadata=None):
        return self.email_provider.send_email(recipient, subject, body, metadata=metadata)

    def send_whatsapp(self, recipient, body, metadata=None):
        return self.whatsapp_provider.send_whatsapp(recipient, body, metadata=metadata)


def get_communication_provider(provider_name=None):
    """Factory function returning configured communication provider instance.

    Args:
        provider_name (str, optional): Provider name. Auto-detected from env if None.

    Returns:
        CommunicationProvider: Configured provider instance.
    """
    if provider_name is None:
        provider_name = os.getenv("COMMUNICATION_PROVIDER")
        if not provider_name:
            has_smtp = bool(os.getenv("SMTP_USERNAME") or os.getenv("GMAIL_USER")) and bool(os.getenv("SMTP_PASSWORD") or os.getenv("GMAIL_APP_PASSWORD"))
            has_wa = bool(os.getenv("WHATSAPP_API_TOKEN") or os.getenv("META_WHATSAPP_TOKEN")) and bool(os.getenv("WHATSAPP_PHONE_NUMBER_ID") or os.getenv("META_PHONE_NUMBER_ID"))
            if has_smtp or has_wa:
                provider_name = "multi_channel"
            else:
                provider_name = "dry_run"

    if provider_name == "dry_run":
        return DryRunCommunicationProvider()
    elif provider_name == "failing_mock":
        return FailingCommunicationProvider()
    elif provider_name == "gmail_smtp":
        return GmailSMTPProvider()
    elif provider_name == "whatsapp_business":
        return WhatsAppBusinessProvider()
    elif provider_name in ("multi_channel", "production"):
        return MultiChannelProvider()
    else:
        # Default fallback to dry-run for safety
        return DryRunCommunicationProvider()
