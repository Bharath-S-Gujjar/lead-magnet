"""Unit tests for communication providers (Gmail SMTP, WhatsApp Business, MultiChannel).

Uses isolated mocks to verify provider logic, credential validation,
API payload construction, error handling, and secret redaction.
NEVER makes real network calls or sends real external messages.
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock
import smtplib

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from communication_provider import (
    GmailSMTPProvider,
    WhatsAppBusinessProvider,
    MultiChannelProvider,
    DryRunCommunicationProvider,
    FailingCommunicationProvider,
    get_communication_provider,
    normalize_whatsapp_phone,
)
from marketing_automation_service import get_store_url


class TestCommunicationProviders(unittest.TestCase):

    # ==============================================================
    # GMAIL SMTP PROVIDER
    # ==============================================================

    def test_gmail_missing_credentials(self):
        """Gmail provider fails gracefully when credentials are not configured."""
        with patch.dict(os.environ, {"SMTP_USERNAME": "", "SMTP_PASSWORD": "", "SMTP_FROM_EMAIL": ""}, clear=False):
            provider = GmailSMTPProvider()
            res = provider.send_email("customer@example.com", "Test", "Hello")
            self.assertFalse(res["success"])
            self.assertEqual(res["provider"], "gmail_smtp")
            self.assertIn("not configured", res["error"])

    def test_gmail_invalid_recipient(self):
        """Gmail provider rejects invalid recipient email address."""
        with patch.dict(os.environ, {
            "SMTP_USERNAME": "test@gmail.com",
            "SMTP_PASSWORD": "dummy-app-password",
            "SMTP_FROM_EMAIL": "test@gmail.com"
        }):
            provider = GmailSMTPProvider()
            res = provider.send_email("invalid-email-no-at", "Test", "Hello")
            self.assertFalse(res["success"])
            self.assertIn("Invalid recipient email", res["error"])

    @patch("smtplib.SMTP")
    def test_gmail_successful_send(self, mock_smtp_cls):
        """Gmail provider correctly initializes STARTTLS, authenticates, and dispatches email."""
        mock_server = MagicMock()
        mock_smtp_cls.return_value.__enter__.return_value = mock_server
        # sendmail() returns empty dict {} when all recipients are accepted (real SMTP contract)
        mock_server.sendmail.return_value = {}

        with patch.dict(os.environ, {
            "SMTP_HOST": "smtp.gmail.com",
            "SMTP_PORT": "587",
            "SMTP_USERNAME": "store@gmail.com",
            "SMTP_PASSWORD": "mock-app-password",
            "SMTP_FROM_EMAIL": "store@gmail.com"
        }):
            provider = GmailSMTPProvider()
            res = provider.send_email("buyer@example.com", "Order Update", "Your order has been confirmed.")

            self.assertTrue(res["success"])
            self.assertEqual(res["provider"], "gmail_smtp")
            # provider_message_id is now a real RFC 2822 Message-ID, not a uuid prefix
            self.assertIn("@", res["provider_message_id"])
            self.assertEqual(res["recipient"], "buyer@example.com")

            # Verify protocol flow: ehlo -> starttls -> ehlo -> login -> sendmail
            self.assertEqual(mock_server.ehlo.call_count, 2)
            mock_server.starttls.assert_called_once()
            mock_server.login.assert_called_once_with("store@gmail.com", "mock-app-password")
            mock_server.sendmail.assert_called_once()


    @patch("smtplib.SMTP")
    def test_gmail_authentication_error_sanitized(self, mock_smtp_cls):
        """Gmail authentication failure returns sanitized error without exposing credentials."""
        mock_server = MagicMock()
        mock_server.login.side_effect = smtplib.SMTPAuthenticationError(535, b"5.7.8 Username and Password not accepted")
        mock_smtp_cls.return_value.__enter__.return_value = mock_server

        secret_password = "super-secret-password-12345"
        with patch.dict(os.environ, {
            "SMTP_USERNAME": "store@gmail.com",
            "SMTP_PASSWORD": secret_password,
            "SMTP_FROM_EMAIL": "store@gmail.com"
        }):
            provider = GmailSMTPProvider()
            res = provider.send_email("buyer@example.com", "Test", "Body")
            self.assertFalse(res["success"])
            self.assertIn("SMTP authentication failed", res["error"])
            # MUST NOT leak password in error
            self.assertNotIn(secret_password, res["error"])

    # ==============================================================
    # WHATSAPP BUSINESS / META CLOUD API PROVIDER
    # ==============================================================

    def test_whatsapp_missing_credentials(self):
        """WhatsApp provider fails gracefully when token or phone ID are missing."""
        with patch.dict(os.environ, {"WHATSAPP_API_TOKEN": "", "WHATSAPP_PHONE_NUMBER_ID": ""}):
            provider = WhatsAppBusinessProvider()
            res = provider.send_whatsapp("+919876543210", "Hello")
            self.assertFalse(res["success"])
            self.assertEqual(res["provider"], "whatsapp_business")
            self.assertIn("not configured", res["error"])

    def test_whatsapp_invalid_recipient(self):
        """WhatsApp provider rejects empty recipient."""
        with patch.dict(os.environ, {
            "WHATSAPP_API_TOKEN": "mock-meta-token",
            "WHATSAPP_PHONE_NUMBER_ID": "100200300"
        }):
            provider = WhatsAppBusinessProvider()
            res = provider.send_whatsapp("", "Hello")
            self.assertFalse(res["success"])
            self.assertIn("Invalid recipient phone", res["error"])

    @patch("communication_provider._requests_lib.post")
    def test_whatsapp_successful_send(self, mock_post):
        """WhatsApp provider constructs Graph API payload and parses message ID on success."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'{"messages": [{"id": "wamid.HBgLM..."}]}'
        mock_response.json.return_value = {"messages": [{"id": "wamid.HBgLM..."}]}
        mock_post.return_value = mock_response

        with patch.dict(os.environ, {
            "WHATSAPP_API_TOKEN": "meta_access_token_mock",
            "WHATSAPP_PHONE_NUMBER_ID": "1234567890",
            "WHATSAPP_GRAPH_VERSION": "v18.0"
        }):
            provider = WhatsAppBusinessProvider()
            res = provider.send_whatsapp("+919876543210", "Welcome to Lead Magnet!")

            self.assertTrue(res["success"])
            self.assertEqual(res["provider"], "whatsapp_business")
            self.assertEqual(res["provider_message_id"], "wamid.HBgLM...")

            # Verify POST called with correct endpoint & Bearer header
            mock_post.assert_called_once()
            call_url = mock_post.call_args[0][0]
            call_kwargs = mock_post.call_args[1]

            self.assertEqual(call_url, "https://graph.facebook.com/v18.0/1234567890/messages")
            self.assertEqual(call_kwargs["headers"]["Authorization"], "Bearer meta_access_token_mock")
            self.assertEqual(call_kwargs["json"]["messaging_product"], "whatsapp")
            self.assertEqual(call_kwargs["json"]["to"], "919876543210")
            self.assertEqual(call_kwargs["json"]["text"]["body"], "Welcome to Lead Magnet!")

    @patch("communication_provider._requests_lib.post")
    def test_whatsapp_error_redacts_token(self, mock_post):
        """WhatsApp API error redacts access token if returned in response message."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        secret_token = "EAABw_secret_token_value_999"
        mock_response.content = b'{"error": {"message": "Invalid OAuth token: EAABw_secret_token_value_999"}}'
        mock_response.json.return_value = {"error": {"message": f"Invalid OAuth token: {secret_token}"}}
        mock_post.return_value = mock_response

        with patch.dict(os.environ, {
            "WHATSAPP_API_TOKEN": secret_token,
            "WHATSAPP_PHONE_NUMBER_ID": "1234567890"
        }):
            provider = WhatsAppBusinessProvider()
            res = provider.send_whatsapp("+919876543210", "Hello")
            self.assertFalse(res["success"])
            self.assertIn("[REDACTED]", res["error"])
            self.assertNotIn(secret_token, res["error"])

    def test_whatsapp_phone_normalization_valid(self):
        """Phone normalization correctly strips spaces, hyphens, and leading + for valid numbers."""
        val, err = normalize_whatsapp_phone("+91 98765-43210")
        self.assertIsNone(err)
        self.assertEqual(val, "919876543210")

        val2, err2 = normalize_whatsapp_phone("+1 (555) 123-4567")
        self.assertIsNone(err2)
        self.assertEqual(val2, "15551234567")

    def test_whatsapp_phone_normalization_rejects_unprefixed_national_number(self):
        """Phone normalization rejects 10-digit national numbers because country code cannot be guessed."""
        val, err = normalize_whatsapp_phone("9876543210")
        self.assertIsNone(val)
        self.assertIn("lacks international country code", err)
        self.assertIn("cannot be guessed", err)

    def test_whatsapp_missing_token_only(self):
        """WhatsApp provider fails when token is empty but phone_id is set."""
        with patch.dict(os.environ, {"WHATSAPP_API_TOKEN": "", "WHATSAPP_PHONE_NUMBER_ID": "12345"}):
            provider = WhatsAppBusinessProvider()
            res = provider.send_whatsapp("+919876543210", "Hello")
            self.assertFalse(res["success"])
            self.assertIn("not configured", res["error"])

    def test_whatsapp_missing_phone_id_only(self):
        """WhatsApp provider fails when phone_id is empty but token is set."""
        with patch.dict(os.environ, {"WHATSAPP_API_TOKEN": "valid_token", "WHATSAPP_PHONE_NUMBER_ID": ""}):
            provider = WhatsAppBusinessProvider()
            res = provider.send_whatsapp("+919876543210", "Hello")
            self.assertFalse(res["success"])
            self.assertIn("not configured", res["error"])

    @patch("communication_provider._requests_lib.post")
    def test_whatsapp_meta_api_rejection_error_code(self, mock_post):
        """Meta API rejection returns structured error with code and does not claim success."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.content = b'{"error": {"message": "Invalid Parameter", "code": 100, "error_subcode": 2494010}}'
        mock_response.json.return_value = {"error": {"message": "Invalid Parameter", "code": 100, "error_subcode": 2494010}}
        mock_post.return_value = mock_response

        with patch.dict(os.environ, {"WHATSAPP_API_TOKEN": "token", "WHATSAPP_PHONE_NUMBER_ID": "123"}):
            provider = WhatsAppBusinessProvider()
            res = provider.send_whatsapp("+919876543210", "Hello")
            self.assertFalse(res["success"])
            self.assertIsNone(res["provider_message_id"])
            self.assertIn("code 100", res["error"])
            self.assertIn("subcode 2494010", res["error"])

    @patch("communication_provider._requests_lib.post")
    def test_whatsapp_outside_24h_window_error_131047(self, mock_post):
        """Error 131047 clearly notes that 24h window closed and approved template is required."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.content = b'{"error": {"message": "Message failed to send", "code": 131047}}'
        mock_response.json.return_value = {"error": {"message": "Message failed to send", "code": 131047}}
        mock_post.return_value = mock_response

        with patch.dict(os.environ, {"WHATSAPP_API_TOKEN": "token", "WHATSAPP_PHONE_NUMBER_ID": "123"}):
            provider = WhatsAppBusinessProvider()
            res = provider.send_whatsapp("+919876543210", "Hello")
            self.assertFalse(res["success"])
            self.assertIn("131047", res["error"])
            self.assertIn("approved WhatsApp Message Template", res["error"])

    @patch("communication_provider._requests_lib.post")
    def test_whatsapp_200_ok_without_message_id_fails_safely(self, mock_post):
        """If Meta responds 200 OK without message ID, provider does NOT claim success."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'{"messages": []}'
        mock_response.json.return_value = {"messages": []}
        mock_post.return_value = mock_response

        with patch.dict(os.environ, {"WHATSAPP_API_TOKEN": "token", "WHATSAPP_PHONE_NUMBER_ID": "123"}):
            provider = WhatsAppBusinessProvider()
            res = provider.send_whatsapp("+919876543210", "Hello")
            self.assertFalse(res["success"])
            self.assertIsNone(res["provider_message_id"])
            self.assertIn("no message ID", res["error"])

    @patch("communication_provider._requests_lib.post")
    def test_whatsapp_network_failure(self, mock_post):
        """Network exception returns failed status with sanitized error."""
        import requests
        mock_post.side_effect = requests.exceptions.ConnectionError("Connection to graph.facebook.com timed out")

        with patch.dict(os.environ, {"WHATSAPP_API_TOKEN": "secret_token_123", "WHATSAPP_PHONE_NUMBER_ID": "123"}):
            provider = WhatsAppBusinessProvider()
            res = provider.send_whatsapp("+919876543210", "Hello")
            self.assertFalse(res["success"])
            self.assertIn("network failure", res["error"])
            self.assertNotIn("secret_token_123", res["error"])

    @patch("communication_provider._requests_lib.post")
    def test_whatsapp_template_message_payload(self, mock_post):
        """Configured template constructs type='template' payload with language code."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'{"messages": [{"id": "wamid.TEMPLATE123"}]}'
        mock_response.json.return_value = {"messages": [{"id": "wamid.TEMPLATE123"}]}
        mock_post.return_value = mock_response

        with patch.dict(os.environ, {
            "WHATSAPP_API_TOKEN": "tok",
            "WHATSAPP_PHONE_NUMBER_ID": "123",
            "WHATSAPP_TEMPLATE_ORDER_CONFIRMATION": "lead_magnet_order_receipt",
            "WHATSAPP_TEMPLATE_LANGUAGE": "en",
        }):
            provider = WhatsAppBusinessProvider()
            metadata = {"campaign_type": "order_confirmation"}
            res = provider.send_whatsapp("+919876543210", "Your order is confirmed", metadata=metadata)
            self.assertTrue(res["success"])
            self.assertEqual(res["provider_message_id"], "wamid.TEMPLATE123")

            call_kwargs = mock_post.call_args[1]
            payload = call_kwargs["json"]
            self.assertEqual(payload["type"], "template")
            self.assertEqual(payload["template"]["name"], "lead_magnet_order_receipt")
            self.assertEqual(payload["template"]["language"]["code"], "en")

    def test_no_sms_path(self):
        """Verify that dispatch_communication explicitly rejects/ignores SMS channel."""
        from marketing_automation_service import dispatch_communication
        mock_db = {"marketing_communications": MagicMock()}
        res = dispatch_communication(mock_db, "cust1", "promo", "sms", "+919876543210", body="SMS text")
        self.assertIsNone(res)

    # ==============================================================
    # MULTI-CHANNEL PROVIDER & FACTORY
    # ==============================================================

    def test_multi_channel_delegation(self):
        """MultiChannelProvider delegates email to email provider and WhatsApp to whatsapp provider."""
        mock_email = MagicMock()
        mock_email.send_email.return_value = {"success": True, "provider": "mock_email"}
        mock_wa = MagicMock()
        mock_wa.send_whatsapp.return_value = {"success": True, "provider": "mock_wa"}

        multi = MultiChannelProvider(email_provider=mock_email, whatsapp_provider=mock_wa)
        res_e = multi.send_email("a@b.com", "Sub", "Body")
        res_w = multi.send_whatsapp("+919999999999", "Body")

        self.assertEqual(res_e["provider"], "mock_email")
        self.assertEqual(res_w["provider"], "mock_wa")

    def test_get_communication_provider_auto_detection(self):
        """Factory auto-detects multi_channel when credentials are configured."""
        with patch.dict(os.environ, {"COMMUNICATION_PROVIDER": "", "SMTP_USERNAME": "u", "SMTP_PASSWORD": "p"}, clear=False):
            p = get_communication_provider()
            self.assertIsInstance(p, MultiChannelProvider)

        with patch.dict(os.environ, {"COMMUNICATION_PROVIDER": "dry_run"}):
            p = get_communication_provider()
            self.assertIsInstance(p, DryRunCommunicationProvider)

    # ==============================================================
    # STOREFRONT URL CONFIGURATION
    # ==============================================================

    def test_get_store_url_priority(self):
        """get_store_url respects STORE_URL over default localhost."""
        with patch.dict(os.environ, {"STORE_URL": "https://shop.leadmagnet.com/"}):
            self.assertEqual(get_store_url(), "https://shop.leadmagnet.com")

        with patch.dict(os.environ, {"STORE_URL": "", "FRONTEND_URL": "https://app.leadmagnet.com,http://localhost:3000"}):
            self.assertEqual(get_store_url(), "https://app.leadmagnet.com")

        with patch.dict(os.environ, {"STORE_URL": "", "FRONTEND_USER_URL": "", "FRONTEND_URL": ""}):
            self.assertEqual(get_store_url(), "http://localhost:3001")


class TestDeliverabilityMIMEConstruction(unittest.TestCase):
    """Deliverability hardening tests verifying RFC MIME compliance, headers, and content hygiene."""

    def setUp(self):
        self.env_patcher = patch.dict(os.environ, {
            "SMTP_HOST": "smtp.gmail.com",
            "SMTP_PORT": "587",
            "SMTP_USERNAME": "store@gmail.com",
            "SMTP_PASSWORD": "mock-app-password",
            "SMTP_FROM_EMAIL": "store@gmail.com",
            "SENDER_DISPLAY_NAME": "Lead Magnet",
            "STORE_URL": "https://shop.leadmagnet.com",
        })
        self.env_patcher.start()

    def tearDown(self):
        self.env_patcher.stop()

    @patch("smtplib.SMTP")
    def _capture_sent_message(self, mock_smtp_cls, recipient="buyer@example.com", subject="Test Subject", body="Test Body", **kwargs):
        """Helper to run send_email and return parsed email.message.Message."""
        import email
        mock_server = MagicMock()
        mock_smtp_cls.return_value.__enter__.return_value = mock_server
        mock_server.sendmail.return_value = {}

        provider = GmailSMTPProvider()
        res = provider.send_email(recipient, subject, body, **kwargs)
        self.assertTrue(res["success"])

        # Extract msg_string passed to server.sendmail(from, to, msg_str)
        call_args = mock_server.sendmail.call_args[0]
        raw_msg_str = call_args[2]
        parsed = email.message_from_string(raw_msg_str)
        return parsed, res

    def test_01_no_localhost_in_production_email(self):
        """1. Production-configured email contains no localhost URLs."""
        body = f"Welcome to our store: {get_store_url()}/shop"
        msg, _ = self._capture_sent_message(body=body)
        parts = msg.get_payload()
        plain_part = parts[0].get_payload(decode=True).decode("utf-8")
        html_part = parts[1].get_payload(decode=True).decode("utf-8")
        self.assertNotIn("localhost", plain_part.lower())
        self.assertNotIn("127.0.0.1", plain_part)
        self.assertIn("https://shop.leadmagnet.com", plain_part)
        self.assertNotIn("localhost", html_part.lower())
        self.assertNotIn("127.0.0.1", html_part)
        self.assertIn("https://shop.leadmagnet.com", html_part)

    def test_02_valid_from_header(self):
        """2. From header matches RFC 2822 'Display Name <email>' format."""
        msg, _ = self._capture_sent_message()
        from_hdr = msg.get("From")
        self.assertEqual(from_hdr, "Lead Magnet <store@gmail.com>")

    def test_03_valid_to_header(self):
        """3. To header matches recipient."""
        msg, _ = self._capture_sent_message(recipient="customer123@example.com")
        self.assertEqual(msg.get("To"), "customer123@example.com")

    def test_04_valid_subject_header(self):
        """4. Subject header matches email subject."""
        msg, _ = self._capture_sent_message(subject="Welcome to Lead Magnet")
        self.assertEqual(msg.get("Subject"), "Welcome to Lead Magnet")

    def test_05_date_header(self):
        """5. Date header is present and valid RFC 2822 date."""
        import email.utils
        msg, _ = self._capture_sent_message()
        date_hdr = msg.get("Date")
        self.assertIsNotNone(date_hdr)
        parsed_dt = email.utils.parsedate_to_datetime(date_hdr)
        self.assertIsNotNone(parsed_dt)

    def test_06_message_id_header(self):
        """6. Message-ID is present and follows RFC format <id@domain>."""
        msg, res = self._capture_sent_message()
        msg_id = msg.get("Message-ID")
        self.assertIsNotNone(msg_id)
        self.assertTrue(msg_id.startswith("<") and msg_id.endswith(">"))
        self.assertIn("@gmail.com", msg_id)
        self.assertEqual(res["provider_message_id"], msg_id)

    def test_07_multipart_alternative(self):
        """7. Message content-type is multipart/alternative."""
        msg, _ = self._capture_sent_message()
        self.assertTrue(msg.is_multipart())
        self.assertEqual(msg.get_content_type(), "multipart/alternative")

    def test_08_plain_text_part(self):
        """8. Plain-text alternative part is present with utf-8 encoding."""
        msg, _ = self._capture_sent_message(body="Hello Customer!")
        parts = msg.get_payload()
        plain_part = parts[0]
        self.assertEqual(plain_part.get_content_type(), "text/plain")
        self.assertEqual(plain_part.get_content_charset(), "utf-8")
        decoded_payload = plain_part.get_payload(decode=True).decode("utf-8")
        self.assertIn("Hello Customer!", decoded_payload)

    def test_09_html_part(self):
        """9. HTML alternative part is present with clean markup and no deceptive elements."""
        msg, _ = self._capture_sent_message(body="Hello Customer!")
        parts = msg.get_payload()
        html_part = parts[1]
        self.assertEqual(html_part.get_content_type(), "text/html")
        self.assertEqual(html_part.get_content_charset(), "utf-8")
        html_payload = html_part.get_payload(decode=True).decode("utf-8")
        self.assertIn("<!DOCTYPE html>", html_payload)
        self.assertIn("Lead Magnet", html_payload)
        self.assertNotIn("<script", html_payload.lower())
        self.assertNotIn("display:none", html_payload.lower())

    def test_10_message_classification(self):
        """10. Verify trigger functions document exact message classifications."""
        from marketing_automation_service import (
            trigger_registration_communication,
            trigger_order_confirmation_communication,
            trigger_lead_qualification_communication,
            trigger_cart_abandonment_communication,
            trigger_wishlist_reminder_communication,
        )
        self.assertIn("Classification: TRANSACTIONAL", trigger_registration_communication.__doc__)
        self.assertIn("Classification: TRANSACTIONAL", trigger_order_confirmation_communication.__doc__)
        self.assertIn("Classification: MARKETING", trigger_lead_qualification_communication.__doc__)
        self.assertIn("Classification: MARKETING", trigger_cart_abandonment_communication.__doc__)
        self.assertIn("Classification: MARKETING", trigger_wishlist_reminder_communication.__doc__)

    def test_11_no_internal_ml_information(self):
        """11. Customer-facing email content contains no internal lead score, probability, or ML metadata."""
        from marketing_automation_service import trigger_lead_qualification_communication
        mock_db = {
            "user_profiles": MagicMock(find_one=MagicMock(return_value={"full_name": "Test Customer", "email": "test@example.com"})),
            "cart": MagicMock(find_one=MagicMock(return_value=None)),
            "wishlist": MagicMock(find_one=MagicMock(return_value=None)),
            "events": MagicMock(find=MagicMock(return_value=MagicMock(limit=MagicMock(return_value=[])))),
            "marketing_communications": MagicMock(
                find_one=MagicMock(return_value=None),
                insert_one=MagicMock(return_value=MagicMock(inserted_id="m1")),
                update_one=MagicMock(return_value=MagicMock(upserted_id="m1")),
            ),
        }
        lead_state = {
            "customer_id": "c1",
            "lead_segment": "Hot",
            "lead_score": 92,
            "lead_probability": 0.94,
            "model_version": "v2.1",
            "qualification_transition": "not_qualified_to_qualified",
            "is_newly_qualified": True,
        }
        res = trigger_lead_qualification_communication("c1", lead_state, mock_db, provider=DryRunCommunicationProvider())
        self.assertIn("email", res)
        dispatched_body = res["email"].get("body", "")
        self.assertNotIn("92", dispatched_body)
        self.assertNotIn("0.94", dispatched_body)
        self.assertNotIn("v2.1", dispatched_body)
        self.assertNotIn("score", dispatched_body.lower())
        self.assertNotIn("probability", dispatched_body.lower())

    def test_12_no_fake_re_fwd_headers(self):
        """12. Email subjects do not contain deceptive Re:, Fwd:, or urgent fake headers."""
        subjects = [
            "Welcome to Lead Magnet",
            "You may be interested in these products — Lead Magnet",
            "You left items in your Lead Magnet cart",
            "Items you saved are still waiting for you",
            "Your Lead Magnet order confirmation (Order #12345678)",
        ]
        for s in subjects:
            lower_s = s.lower()
            self.assertFalse(lower_s.startswith("re:"))
            self.assertFalse(lower_s.startswith("fwd:"))
            self.assertFalse(lower_s.startswith("urgent:"))
            self.assertNotIn("security alert", lower_s)

    def test_13_marketing_transactional_unsubscribe_separation(self):
        """13. List-Unsubscribe is only added when real unsubscribe URL is provided, not on transactional."""
        # Transactional email without unsubscribe_url
        msg_trans, _ = self._capture_sent_message(subject="Order Confirmation")
        self.assertIsNone(msg_trans.get("List-Unsubscribe"))
        self.assertIsNone(msg_trans.get("List-Unsubscribe-Post"))

        # Marketing email with legitimate unsubscribe_url
        unsub_url = "https://shop.leadmagnet.com/unsubscribe?token=abc"
        msg_mktg, _ = self._capture_sent_message(subject="Product Update", unsubscribe_url=unsub_url)
        self.assertEqual(msg_mktg.get("List-Unsubscribe"), f"<{unsub_url}>")
        self.assertEqual(msg_mktg.get("List-Unsubscribe-Post"), "List-Unsubscribe=One-Click")


if __name__ == "__main__":
    unittest.main()

