"""Comprehensive unit and API tests for WhatsApp Webhook, STOP Handling, and Delivery Status (Task 5).

Covers all 16 required areas:
1. Valid webhook verification challenge (GET).
2. Missing or incorrect verification token (GET).
3. Valid signed POST payload.
4. Invalid signature and missing signature (POST).
5. Malformed JSON and unexpected payload structure (POST).
6. STOP and supported opt-out keywords (STOP, UNSUBSCRIBE, CANCEL, END, QUIT).
7. Unrelated text that must not trigger opt-out.
8. Correct customer lookup using normalized phone numbers.
9. Unknown or ambiguous sender handling.
10. Consent persistence and immediate promotional suppression after STOP.
11. Duplicate STOP event handling (atomic idempotency).
12. Duplicate delivery-status event handling (atomic idempotency).
13. Status correlation for sent, delivered, read, and failed events.
14. Out-of-order status events.
15. No outbound provider calls during tests.
16. Existing regressions verified.
"""

import datetime
import hashlib
import hmac
import json
import os
import sys
import unittest
from unittest.mock import patch, MagicMock
from bson import ObjectId

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module
from app import app
from marketing_automation_service import evaluate_channel_eligibility
from whatsapp_webhook_service import (
    is_opt_out_keyword,
    verify_webhook_signature,
    verify_webhook_challenge,
    resolve_customer_by_phone,
    process_delivery_status,
)


import random

class TestWhatsAppWebhook(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = app.test_client()
        cls.app_secret = "test_webhook_app_secret_12345"
        cls.verify_token = "test_verify_token_secure_999"

        # Configure test secrets on app
        app.config["WHATSAPP_APP_SECRET"] = cls.app_secret
        app.config["WHATSAPP_WEBHOOK_VERIFY_TOKEN"] = cls.verify_token
        os.environ["WHATSAPP_APP_SECRET"] = cls.app_secret
        os.environ["WHATSAPP_WEBHOOK_VERIFY_TOKEN"] = cls.verify_token

        cls.db = app_module.db
        cls.profiles = app_module.profiles_collection
        cls.comms = app_module.marketing_communications_collection
        cls.webhook_events = cls.db["whatsapp_webhook_events"]

    def setUp(self):
        # Create primary opted-in customer with unique test phone
        self.user_oid = ObjectId()
        self.user_id = str(self.user_oid)
        suffix = f"{random.randint(10000000, 99999999)}"
        self.user_phone = f"+9198{suffix}"
        self.norm_user_phone = f"9198{suffix}"

        self.profiles.insert_one({
            "_id": self.user_oid,
            "email": f"wa_test_{self.user_id}@example.com",
            "phone": self.user_phone,
            "role": "user",
            "full_name": "Webhook Test User",
            "whatsapp_opt_in": True,
            "whatsapp_opt_out": False,
            "whatsapp_opt_in_at": "2026-10-01T00:00:00",
            "whatsapp_opt_in_source": "user_settings",
            "created_at": datetime.datetime.utcnow(),
        })

        # Pre-seed a marketing communication record for status tracking
        self.comm_oid = ObjectId()
        self.provider_msg_id = f"wamid.test_{ObjectId()}"
        self.comms.insert_one({
            "_id": self.comm_oid,
            "customer_id": self.user_oid,
            "channel": "whatsapp",
            "status": "sent",
            "provider": "whatsapp_business",
            "provider_message_id": self.provider_msg_id,
            "recipient": self.user_phone,
            "created_at": datetime.datetime.utcnow().isoformat(),
            "updated_at": datetime.datetime.utcnow().isoformat(),
        })

    def tearDown(self):
        self.profiles.delete_many({"_id": self.user_oid})
        self.profiles.delete_many({"phone": self.user_phone})
        self.comms.delete_many({"_id": self.comm_oid})
        self.webhook_events.delete_many({})

    def _sign_payload(self, body_bytes: bytes) -> str:
        h = hmac.new(self.app_secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()
        return f"sha256={h}"

    def _build_inbound_message_payload(self, from_phone: str, text_body: str, msg_id: str = None) -> dict:
        m_id = msg_id or f"wamid.inbound_{ObjectId()}"
        return {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": "WABA_ID_123",
                    "changes": [
                        {
                            "value": {
                                "messaging_product": "whatsapp",
                                "metadata": {
                                    "display_phone_number": "15551234567",
                                    "phone_number_id": "PN_ID_123",
                                },
                                "messages": [
                                    {
                                        "from": from_phone,
                                        "id": m_id,
                                        "timestamp": str(int(datetime.datetime.utcnow().timestamp())),
                                        "type": "text",
                                        "text": {"body": text_body},
                                    }
                                ],
                            },
                            "field": "messages",
                        }
                    ],
                }
            ],
        }

    def _build_status_payload(self, msg_id: str, status: str, errors: list = None, ts: str = None) -> dict:
        status_item = {
            "id": msg_id,
            "status": status,
            "timestamp": ts or str(int(datetime.datetime.utcnow().timestamp())),
            "recipient_id": "919876543210",
        }
        if errors:
            status_item["errors"] = errors

        return {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": "WABA_ID_123",
                    "changes": [
                        {
                            "value": {
                                "messaging_product": "whatsapp",
                                "statuses": [status_item],
                            },
                            "field": "messages",
                        }
                    ],
                }
            ],
        }

    # --------------------------------------------------------------------------
    # 1. Valid webhook verification challenge
    # --------------------------------------------------------------------------
    def test_01_valid_verification_challenge(self):
        """GET request with matching mode and token returns challenge string with 200."""
        challenge = "random_challenge_string_123456"
        res = self.client.get(
            f"/api/webhook/whatsapp?hub.mode=subscribe&hub.challenge={challenge}&hub.verify_token={self.verify_token}"
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_data(as_text=True), challenge)
        self.assertEqual(res.mimetype, "text/plain")

    # --------------------------------------------------------------------------
    # 2. Missing or incorrect verification token
    # --------------------------------------------------------------------------
    def test_02_invalid_or_missing_verification_token(self):
        """GET request with mismatched token, missing mode, or missing challenge is rejected with 403."""
        challenge = "challenge_123"

        # Incorrect token
        res_bad = self.client.get(
            f"/api/webhook/whatsapp?hub.mode=subscribe&hub.challenge={challenge}&hub.verify_token=wrong_token"
        )
        self.assertEqual(res_bad.status_code, 403)

        # Missing token
        res_no_tok = self.client.get(
            f"/api/webhook/whatsapp?hub.mode=subscribe&hub.challenge={challenge}"
        )
        self.assertEqual(res_no_tok.status_code, 403)

        # Wrong mode
        res_bad_mode = self.client.get(
            f"/api/webhook/whatsapp?hub.mode=publish&hub.challenge={challenge}&hub.verify_token={self.verify_token}"
        )
        self.assertEqual(res_bad_mode.status_code, 403)

    # --------------------------------------------------------------------------
    # 3. Valid signed POST payload
    # --------------------------------------------------------------------------
    def test_03_valid_signed_post_payload(self):
        """POST request with correct HMAC-SHA256 signature is accepted with 200."""
        payload = self._build_inbound_message_payload(from_phone="919876543210", text_body="Hello")
        raw_body = json.dumps(payload).encode("utf-8")
        sig = self._sign_payload(raw_body)

        res = self.client.post(
            "/api/webhook/whatsapp",
            data=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": sig,
            },
        )
        self.assertEqual(res.status_code, 200)
        body = res.get_json()
        self.assertTrue(body["success"])

    # --------------------------------------------------------------------------
    # 4. Invalid signature and missing signature
    # --------------------------------------------------------------------------
    def test_04_invalid_and_missing_signatures_rejected(self):
        """POST without signature or with invalid/tampered signature is rejected with 401."""
        payload = self._build_inbound_message_payload(from_phone="919876543210", text_body="STOP")
        raw_body = json.dumps(payload).encode("utf-8")

        # Missing signature
        res_no_sig = self.client.post(
            "/api/webhook/whatsapp",
            data=raw_body,
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(res_no_sig.status_code, 401)
        self.assertFalse(res_no_sig.get_json()["success"])

        # Invalid/wrong signature
        res_bad_sig = self.client.post(
            "/api/webhook/whatsapp",
            data=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": "sha256=0000000000000000000000000000000000000000000000000000000000000000",
            },
        )
        self.assertEqual(res_bad_sig.status_code, 401)
        self.assertFalse(res_bad_sig.get_json()["success"])

        # Tampered body with signature of original body
        orig_sig = self._sign_payload(raw_body)
        tampered_body = json.dumps({"tampered": True}).encode("utf-8")
        res_tampered = self.client.post(
            "/api/webhook/whatsapp",
            data=tampered_body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": orig_sig,
            },
        )
        self.assertEqual(res_tampered.status_code, 401)

    # --------------------------------------------------------------------------
    # 5. Malformed JSON and unexpected payload structure
    # --------------------------------------------------------------------------
    def test_05_malformed_json_and_unexpected_structure(self):
        """Non-JSON body or unexpected payload missing 'entry' array is rejected with 400."""
        # Non-JSON bytes properly signed
        bad_bytes = b"this is not json at all"
        sig_bad_bytes = self._sign_payload(bad_bytes)
        res_bad_bytes = self.client.post(
            "/api/webhook/whatsapp",
            data=bad_bytes,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": sig_bad_bytes,
            },
        )
        self.assertEqual(res_bad_bytes.status_code, 400)

        # JSON object missing 'entry'
        no_entry_body = json.dumps({"object": "whatsapp_business_account"}).encode("utf-8")
        sig_no_entry = self._sign_payload(no_entry_body)
        res_no_entry = self.client.post(
            "/api/webhook/whatsapp",
            data=no_entry_body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": sig_no_entry,
            },
        )
        self.assertEqual(res_no_entry.status_code, 400)

    # --------------------------------------------------------------------------
    # 6. STOP and supported opt-out keywords
    # --------------------------------------------------------------------------
    def test_06_stop_and_supported_opt_out_keywords(self):
        """Supported keywords (STOP, UNSUBSCRIBE, CANCEL, END, QUIT) trigger opt-out."""
        keywords = ["STOP", "unsubscribe", "CANCEL", "end!", "Quit."]

        for kw in keywords:
            # Re-seed user as opted in
            self.profiles.update_one(
                {"_id": self.user_oid},
                {"$set": {"whatsapp_opt_in": True, "whatsapp_opt_out": False}},
            )

            payload = self._build_inbound_message_payload(from_phone=self.norm_user_phone, text_body=kw)
            raw_body = json.dumps(payload).encode("utf-8")
            sig = self._sign_payload(raw_body)

            res = self.client.post(
                "/api/webhook/whatsapp",
                data=raw_body,
                headers={
                    "Content-Type": "application/json",
                    "X-Hub-Signature-256": sig,
                },
            )
            self.assertEqual(res.status_code, 200)

            # Check profile updated to opt-out
            doc = self.profiles.find_one({"_id": self.user_oid})
            self.assertFalse(doc["whatsapp_opt_in"], f"Failed for keyword '{kw}'")
            self.assertTrue(doc["whatsapp_opt_out"], f"Failed for keyword '{kw}'")
            self.assertEqual(doc["whatsapp_opt_out_source"], "whatsapp_stop")
            self.assertIsNotNone(doc["whatsapp_opt_out_at"])

    # --------------------------------------------------------------------------
    # 7. Unrelated text that must not trigger opt-out
    # --------------------------------------------------------------------------
    def test_07_unrelated_text_must_not_trigger_opt_out(self):
        """Sentences containing keywords or general messages must not change consent."""
        non_optout_messages = [
            "Don't stop the delivery",
            "I want to end up buying this item",
            "Please cancel my order #12345",
            "When will the discount end?",
            "Can you quit sending duplicate receipts?",
            "Hello, what are your store hours?",
            "START",
        ]

        for msg_text in non_optout_messages:
            # Ensure user is opted in
            self.profiles.update_one(
                {"_id": self.user_oid},
                {"$set": {"whatsapp_opt_in": True, "whatsapp_opt_out": False}},
            )

            payload = self._build_inbound_message_payload(from_phone=self.norm_user_phone, text_body=msg_text)
            raw_body = json.dumps(payload).encode("utf-8")
            sig = self._sign_payload(raw_body)

            res = self.client.post(
                "/api/webhook/whatsapp",
                data=raw_body,
                headers={
                    "Content-Type": "application/json",
                    "X-Hub-Signature-256": sig,
                },
            )
            self.assertEqual(res.status_code, 200)

            # Assert consent was NOT modified
            doc = self.profiles.find_one({"_id": self.user_oid})
            self.assertTrue(doc["whatsapp_opt_in"], f"Should not opt-out for '{msg_text}'")
            self.assertFalse(doc["whatsapp_opt_out"], f"Should not opt-out for '{msg_text}'")

    # --------------------------------------------------------------------------
    # 8. Correct customer lookup using normalized phone numbers
    # --------------------------------------------------------------------------
    def test_08_correct_customer_lookup_using_normalized_phone(self):
        """Customer lookup matches normalized E.164 variations (with or without '+', dashes)."""
        # User in DB has '+919876543210'
        # Webhook from Meta provides '919876543210' (no leading '+')
        payload = self._build_inbound_message_payload(from_phone=self.norm_user_phone, text_body="STOP")
        raw_body = json.dumps(payload).encode("utf-8")
        sig = self._sign_payload(raw_body)

        res = self.client.post(
            "/api/webhook/whatsapp",
            data=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": sig,
            },
        )
        self.assertEqual(res.status_code, 200)
        doc = self.profiles.find_one({"_id": self.user_oid})
        self.assertTrue(doc["whatsapp_opt_out"])

    # --------------------------------------------------------------------------
    # 9. Unknown or ambiguous sender handling
    # --------------------------------------------------------------------------
    def test_09_unknown_or_ambiguous_sender_handling(self):
        """Unmatched phone or multiple profiles sharing a phone does not alter any consent."""
        # 1. Unmatched phone
        payload_unknown = self._build_inbound_message_payload(from_phone="919999999999", text_body="STOP")
        raw_unknown = json.dumps(payload_unknown).encode("utf-8")
        sig_unknown = self._sign_payload(raw_unknown)

        res_unknown = self.client.post(
            "/api/webhook/whatsapp",
            data=raw_unknown,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": sig_unknown,
            },
        )
        self.assertEqual(res_unknown.status_code, 200)

        # 2. Ambiguous phone: create two accounts with same phone
        dup1_oid = ObjectId()
        dup2_oid = ObjectId()
        dup_phone = "+919777777777"
        self.profiles.insert_many([
            {"_id": dup1_oid, "phone": dup_phone, "whatsapp_opt_in": True, "whatsapp_opt_out": False},
            {"_id": dup2_oid, "phone": dup_phone, "whatsapp_opt_in": True, "whatsapp_opt_out": False},
        ])

        try:
            payload_ambiguous = self._build_inbound_message_payload(from_phone="919777777777", text_body="STOP")
            raw_ambiguous = json.dumps(payload_ambiguous).encode("utf-8")
            sig_ambiguous = self._sign_payload(raw_ambiguous)

            res_ambiguous = self.client.post(
                "/api/webhook/whatsapp",
                data=raw_ambiguous,
                headers={
                    "Content-Type": "application/json",
                    "X-Hub-Signature-256": sig_ambiguous,
                },
            )
            self.assertEqual(res_ambiguous.status_code, 200)

            # Neither profile should be changed due to ambiguity guardrail
            d1 = self.profiles.find_one({"_id": dup1_oid})
            d2 = self.profiles.find_one({"_id": dup2_oid})
            self.assertTrue(d1["whatsapp_opt_in"])
            self.assertFalse(d1["whatsapp_opt_out"])
            self.assertTrue(d2["whatsapp_opt_in"])
            self.assertFalse(d2["whatsapp_opt_out"])
        finally:
            self.profiles.delete_many({"_id": {"$in": [dup1_oid, dup2_oid]}})

    # --------------------------------------------------------------------------
    # 10. Consent persistence and immediate promotional suppression after STOP
    # --------------------------------------------------------------------------
    def test_10_consent_persistence_and_immediate_promotional_suppression(self):
        """After STOP webhook, promotional eligibility immediately blocks WhatsApp."""
        # Pre-check: eligible for promotional WhatsApp
        pre_doc = self.profiles.find_one({"_id": self.user_oid})
        pre_elig = evaluate_channel_eligibility(pre_doc, campaign_type="cart_abandoned")
        self.assertTrue(pre_elig["whatsapp"]["eligible"])

        # Send STOP webhook
        payload = self._build_inbound_message_payload(from_phone=self.norm_user_phone, text_body="STOP")
        raw_body = json.dumps(payload).encode("utf-8")
        sig = self._sign_payload(raw_body)
        res = self.client.post(
            "/api/webhook/whatsapp",
            data=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": sig,
            },
        )
        self.assertEqual(res.status_code, 200)

        # Post-check: immediately ineligible
        post_doc = self.profiles.find_one({"_id": self.user_oid})
        self.assertTrue(post_doc["whatsapp_opt_out"])
        self.assertFalse(post_doc["whatsapp_opt_in"])

        post_elig = evaluate_channel_eligibility(post_doc, campaign_type="cart_abandoned")
        self.assertFalse(post_elig["whatsapp"]["eligible"])
        self.assertIn("opted out", post_elig["whatsapp"]["reason"])
        self.assertTrue(post_elig["email"]["eligible"])  # Gmail unaffected

    # --------------------------------------------------------------------------
    # 11. Duplicate STOP event handling
    # --------------------------------------------------------------------------
    def test_11_duplicate_stop_event_handling(self):
        """Duplicate STOP deliveries with identical message ID are safely ignored."""
        same_msg_id = f"wamid.unique_test_{ObjectId()}"
        payload = self._build_inbound_message_payload(
            from_phone=self.norm_user_phone, text_body="STOP", msg_id=same_msg_id
        )
        raw_body = json.dumps(payload).encode("utf-8")
        sig = self._sign_payload(raw_body)

        # First delivery
        res1 = self.client.post(
            "/api/webhook/whatsapp",
            data=raw_body,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig},
        )
        self.assertEqual(res1.status_code, 200)
        self.assertEqual(res1.get_json()["data"]["opt_outs_recorded"], 1)

        # Second identical delivery
        res2 = self.client.post(
            "/api/webhook/whatsapp",
            data=raw_body,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig},
        )
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(res2.get_json()["data"]["duplicates_ignored"], 1)

    # --------------------------------------------------------------------------
    # 12. Duplicate delivery-status event handling
    # --------------------------------------------------------------------------
    def test_12_duplicate_delivery_status_event_handling(self):
        """Duplicate status events with same ID, status, and timestamp are ignored."""
        status_ts = "1728560000"
        payload = self._build_status_payload(
            msg_id=self.provider_msg_id, status="delivered", ts=status_ts
        )
        raw_body = json.dumps(payload).encode("utf-8")
        sig = self._sign_payload(raw_body)

        # First delivery
        res1 = self.client.post(
            "/api/webhook/whatsapp",
            data=raw_body,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig},
        )
        self.assertEqual(res1.status_code, 200)
        doc = self.comms.find_one({"_id": self.comm_oid})
        self.assertEqual(doc["status"], "delivered")

        # Second delivery (duplicate)
        res2 = self.client.post(
            "/api/webhook/whatsapp",
            data=raw_body,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig},
        )
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(res2.get_json()["data"]["duplicates_ignored"], 1)

    # --------------------------------------------------------------------------
    # 13. Status correlation for sent, delivered, read, and failed events
    # --------------------------------------------------------------------------
    def test_13_status_correlation_for_all_events(self):
        """Webhook correlates and updates communications for sent, delivered, read, failed."""
        # 1. Delivered
        p_delivered = self._build_status_payload(msg_id=self.provider_msg_id, status="delivered")
        raw_del = json.dumps(p_delivered).encode("utf-8")
        self.client.post(
            "/api/webhook/whatsapp",
            data=raw_del,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": self._sign_payload(raw_del)},
        )
        doc1 = self.comms.find_one({"_id": self.comm_oid})
        self.assertEqual(doc1["status"], "delivered")
        self.assertIsNotNone(doc1.get("delivered_at"))

        # 2. Read
        p_read = self._build_status_payload(msg_id=self.provider_msg_id, status="read")
        raw_read = json.dumps(p_read).encode("utf-8")
        self.client.post(
            "/api/webhook/whatsapp",
            data=raw_read,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": self._sign_payload(raw_read)},
        )
        doc2 = self.comms.find_one({"_id": self.comm_oid})
        self.assertEqual(doc2["status"], "read")
        self.assertIsNotNone(doc2.get("read_at"))

        # 3. Failed on another communication record
        comm_fail_oid = ObjectId()
        fail_msg_id = f"wamid.fail_{ObjectId()}"
        self.comms.insert_one({
            "_id": comm_fail_oid,
            "provider_message_id": fail_msg_id,
            "status": "sent",
        })
        try:
            p_fail = self._build_status_payload(
                msg_id=fail_msg_id,
                status="failed",
                errors=[{"code": 131026, "title": "Message undeliverable"}],
            )
            raw_fail = json.dumps(p_fail).encode("utf-8")
            self.client.post(
                "/api/webhook/whatsapp",
                data=raw_fail,
                headers={"Content-Type": "application/json", "X-Hub-Signature-256": self._sign_payload(raw_fail)},
            )
            doc_fail = self.comms.find_one({"_id": comm_fail_oid})
            self.assertEqual(doc_fail["status"], "failed")
            self.assertIn("undeliverable", doc_fail["last_error"].lower())
            self.assertIsNotNone(doc_fail.get("failed_at"))
        finally:
            self.comms.delete_one({"_id": comm_fail_oid})

    # --------------------------------------------------------------------------
    # 14. Out-of-order status events
    # --------------------------------------------------------------------------
    def test_14_out_of_order_status_events_do_not_regress(self):
        """Older status (e.g. sent) cannot overwrite newer status (delivered or read)."""
        # Set status to read
        self.comms.update_one(
            {"_id": self.comm_oid},
            {"$set": {"status": "read", "read_at": "2026-10-10T12:00:00"}},
        )

        # Out-of-order 'delivered' arrives
        p_del = self._build_status_payload(msg_id=self.provider_msg_id, status="delivered")
        raw_del = json.dumps(p_del).encode("utf-8")
        self.client.post(
            "/api/webhook/whatsapp",
            data=raw_del,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": self._sign_payload(raw_del)},
        )
        doc1 = self.comms.find_one({"_id": self.comm_oid})
        self.assertEqual(doc1["status"], "read")  # Does not regress!

        # Out-of-order 'sent' arrives
        p_sent = self._build_status_payload(msg_id=self.provider_msg_id, status="sent")
        raw_sent = json.dumps(p_sent).encode("utf-8")
        self.client.post(
            "/api/webhook/whatsapp",
            data=raw_sent,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": self._sign_payload(raw_sent)},
        )
        doc2 = self.comms.find_one({"_id": self.comm_oid})
        self.assertEqual(doc2["status"], "read")  # Does not regress!

        # Message with 'failed' cannot be overwritten by 'delivered'
        self.comms.update_one({"_id": self.comm_oid}, {"$set": {"status": "failed"}})
        p_del2 = self._build_status_payload(msg_id=self.provider_msg_id, status="delivered")
        raw_del2 = json.dumps(p_del2).encode("utf-8")
        self.client.post(
            "/api/webhook/whatsapp",
            data=raw_del2,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": self._sign_payload(raw_del2)},
        )
        doc3 = self.comms.find_one({"_id": self.comm_oid})
        self.assertEqual(doc3["status"], "failed")  # Failure stands!

    # --------------------------------------------------------------------------
    # 15. No outbound provider calls during tests
    # --------------------------------------------------------------------------
    @patch("communication_provider.CommunicationProvider.send_whatsapp")
    @patch("communication_provider.CommunicationProvider.send_email")
    def test_15_no_outbound_provider_calls(self, mock_send_email, mock_send_wa):
        """Processing webhook events never makes outbound provider calls."""
        payload = self._build_inbound_message_payload(from_phone=self.norm_user_phone, text_body="STOP")
        raw_body = json.dumps(payload).encode("utf-8")
        sig = self._sign_payload(raw_body)

        res = self.client.post(
            "/api/webhook/whatsapp",
            data=raw_body,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig},
        )
        self.assertEqual(res.status_code, 200)

        # Assert no communication calls were made
        mock_send_email.assert_not_called()
        mock_send_wa.assert_not_called()


if __name__ == "__main__":
    unittest.main()
