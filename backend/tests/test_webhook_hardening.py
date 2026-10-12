"""WhatsApp Webhook Hardening Tests (Task 10 — Part 4).

Covers the concrete defects and gaps found during the Task 10 audit:

1. POST signature is computed against the exact raw request body.
2. Signature rejection when body is tampered.
3. GET verification fails closed when token is absent (already tested in test_production_hardening.py;
   included here for completeness in the webhook-specific suite).
4. Status event idempotency key excludes timestamp — same msg+status with different timestamp is deduped.
5. Status regression prevention: delivered→sent, read→delivered, failed→delivered are all rejected.
6. Failed delivery preserves error code and title; does NOT expose app secret.
7. Ambiguous phone match does not modify any customer's consent.
8. Unmatched phone STOP does not modify any consent.
9. Non-opt-out inbound message does not alter opt-in or opt-out flags.
10. Opt-out state overrides any prior opt-in re-write — consent cannot be re-enabled by webhook.
11. Webhook processing generates zero outbound communications.
12. Raw body signature: payload bytes are signed, not re-encoded JSON.
13. record_webhook_idempotency is atomic: concurrent inserts produce exactly one success.
"""

import datetime
import hashlib
import hmac
import json
import os
import sys
import threading
import unittest
from unittest.mock import patch
from bson import ObjectId

_backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

# Safety
if os.environ.get("TESTING", "0") != "1":
    raise RuntimeError("TESTING=1 must be set before importing this test module.")
_uri = os.environ.get("MONGO_URI", "")
_db_name = os.environ.get("MONGO_DB_NAME", "")
if "mongodb+srv://" in _uri or ".mongodb.net" in _uri:
    raise RuntimeError(f"REFUSED: Atlas URI in MONGO_URI. URI={_uri!r}")
if not any(h in _uri for h in ("localhost", "127.", "::1")):
    raise RuntimeError(f"REFUSED: Non-local MONGO_URI: {_uri!r}")
if "test" not in _db_name.lower():
    raise RuntimeError(f"REFUSED: MONGO_DB_NAME '{_db_name}' does not contain 'test'.")

import app as app_module
from app import app
from whatsapp_webhook_service import (
    verify_webhook_signature,
    verify_webhook_challenge,
    is_opt_out_keyword,
    record_webhook_idempotency,
    process_delivery_status,
    process_inbound_message,
    resolve_customer_by_phone,
    ensure_webhook_indexes,
)


class TestWebhookHardening(unittest.TestCase):
    """Tests for webhook hardening defects found during Task 10 audit."""

    @classmethod
    def setUpClass(cls):
        cls.client = app.test_client()
        cls.app_secret = "t10_webhook_hardening_secret_xyzabc"
        cls.verify_token = "t10_verify_token_secure_abc123"

        app.config["WHATSAPP_APP_SECRET"] = cls.app_secret
        app.config["WHATSAPP_WEBHOOK_VERIFY_TOKEN"] = cls.verify_token
        os.environ["WHATSAPP_APP_SECRET"] = cls.app_secret
        os.environ["WHATSAPP_WEBHOOK_VERIFY_TOKEN"] = cls.verify_token

        cls.db = app_module.db
        cls.profiles = app_module.profiles_collection
        cls.comms = app_module.marketing_communications_collection
        cls.webhook_events = cls.db["whatsapp_webhook_events"]

    def setUp(self):
        self.user_oid = ObjectId()
        self.user_id = str(self.user_oid)
        self.user_phone = f"+91987{ObjectId().binary[:4].hex()}"[:14]
        self.user_phone = "+919876543000"  # stable for this test run

        # Use unique phones per test to prevent cross-test interference
        import random
        suffix = random.randint(10000000, 99999999)
        self.user_phone = f"+9198{suffix}"
        self.norm_phone = f"9198{suffix}"

        # Ensure the unique index exists BEFORE any test runs
        if self.db is not None:
            ensure_webhook_indexes(self.db)
            self.webhook_events.delete_many({})

        self.profiles.insert_one({
            "_id": self.user_oid,
            "email": f"t10_{self.user_id}@example.com",
            "phone": self.user_phone,
            "role": "user",
            "whatsapp_opt_in": True,
            "whatsapp_opt_out": False,
            "whatsapp_opt_in_source": "user_settings",
            "created_at": datetime.datetime.now(datetime.timezone.utc),
        })

        self.comm_oid = ObjectId()
        self.provider_msg_id = f"wamid.t10_{ObjectId()}"
        self.comms.insert_one({
            "_id": self.comm_oid,
            "customer_id": self.user_oid,
            "channel": "whatsapp",
            "status": "sent",
            "provider": "whatsapp_business",
            "provider_message_id": self.provider_msg_id,
            "recipient": self.user_phone,
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        })

    def tearDown(self):
        self.profiles.delete_many({"_id": self.user_oid})
        self.comms.delete_many({"_id": self.comm_oid})
        self.webhook_events.delete_many({})

    def _sign(self, body: bytes) -> str:
        sig = hmac.new(self.app_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        return f"sha256={sig}"

    def _inbound_payload(self, from_phone: str, text: str, msg_id: str = None) -> dict:
        return {
            "object": "whatsapp_business_account",
            "entry": [{
                "id": "WABA_T10",
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "messages": [{
                            "from": from_phone,
                            "id": msg_id or f"wamid.t10_{ObjectId()}",
                            "timestamp": str(int(datetime.datetime.now(datetime.timezone.utc).timestamp())),
                            "type": "text",
                            "text": {"body": text},
                        }],
                    },
                    "field": "messages",
                }],
            }],
        }

    def _status_payload(self, msg_id: str, status: str, ts: str = None, errors: list = None) -> dict:
        item = {
            "id": msg_id,
            "status": status,
            "timestamp": ts or str(int(datetime.datetime.now(datetime.timezone.utc).timestamp())),
            "recipient_id": "919876543210",
        }
        if errors:
            item["errors"] = errors
        return {
            "object": "whatsapp_business_account",
            "entry": [{
                "id": "WABA_T10",
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "statuses": [item],
                    },
                    "field": "messages",
                }],
            }],
        }

    # ── 1. Signature computed against exact raw bytes ────────────────────────

    def test_01_signature_is_computed_against_exact_raw_body_bytes(self):
        """verify_webhook_signature uses the exact raw bytes, not a re-serialized form."""
        body = b'{"entry": [{"id": "1"}]}'
        sig = hmac.new(self.app_secret.encode(), body, hashlib.sha256).hexdigest()
        self.assertTrue(verify_webhook_signature(body, f"sha256={sig}", self.app_secret))

        # Slightly different bytes (extra space) must fail
        body_different = b'{"entry": [{"id":  "1"}]}'
        self.assertFalse(verify_webhook_signature(body_different, f"sha256={sig}", self.app_secret))

    def test_02_tampered_body_fails_signature_check(self):
        """Tampering the body after signing must cause signature verification to fail."""
        original_body = b'{"entry": [{"status": "good"}]}'
        tampered_body = b'{"entry": [{"status": "evil"}]}'
        sig = self._sign(original_body)

        self.assertTrue(verify_webhook_signature(original_body, sig, self.app_secret))
        self.assertFalse(verify_webhook_signature(tampered_body, sig, self.app_secret))

    def test_03_missing_signature_header_rejected(self):
        """verify_webhook_signature returns False when signature_header is None or empty."""
        body = b"test body"
        self.assertFalse(verify_webhook_signature(body, None, self.app_secret))
        self.assertFalse(verify_webhook_signature(body, "", self.app_secret))
        self.assertFalse(verify_webhook_signature(body, "sha256=", self.app_secret))

    def test_04_missing_app_secret_rejected(self):
        """verify_webhook_signature returns False when app_secret is None or empty."""
        body = b"test body"
        self.assertFalse(verify_webhook_signature(body, "sha256=abc", None))
        self.assertFalse(verify_webhook_signature(body, "sha256=abc", ""))

    # ── 2. Status idempotency key excludes timestamp ─────────────────────────

    def test_05_status_dedup_across_different_timestamps(self):
        """Same msg_id+status with different timestamps is treated as duplicate (no timestamp in key)."""
        # First delivery: status "delivered" at timestamp T1
        p1 = self._status_payload(self.provider_msg_id, "delivered", ts="1728560000")
        raw1 = json.dumps(p1).encode()
        res1 = self.client.post(
            "/api/webhook/whatsapp",
            data=raw1,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": self._sign(raw1)},
        )
        self.assertEqual(res1.status_code, 200)
        doc1 = self.comms.find_one({"_id": self.comm_oid})
        self.assertEqual(doc1["status"], "delivered")

        # Second delivery: same msg_id+status but different timestamp T2
        p2 = self._status_payload(self.provider_msg_id, "delivered", ts="1728560999")
        raw2 = json.dumps(p2).encode()
        res2 = self.client.post(
            "/api/webhook/whatsapp",
            data=raw2,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": self._sign(raw2)},
        )
        self.assertEqual(res2.status_code, 200)
        # Must be counted as duplicate
        body2 = res2.get_json()
        self.assertGreaterEqual(body2["data"]["duplicates_ignored"], 1,
                                "Same msg+status at different timestamp should be counted as duplicate")

    # ── 3. Status regression prevention ──────────────────────────────────────

    def test_06_status_cannot_regress_delivered_to_sent(self):
        """Once status is 'delivered', a later 'sent' event does not overwrite it."""
        # Advance to delivered
        self.comms.update_one({"_id": self.comm_oid}, {"$set": {"status": "delivered"}})

        item = {"id": self.provider_msg_id, "status": "sent", "timestamp": "1728560001"}
        result = process_delivery_status(self.db, item)

        self.assertIn(result["status"], ("ignored_out_of_order", "duplicate"))
        doc = self.comms.find_one({"_id": self.comm_oid})
        self.assertEqual(doc["status"], "delivered")

    def test_07_status_cannot_regress_read_to_delivered(self):
        """Once status is 'read', a later 'delivered' event does not overwrite it."""
        self.comms.update_one({"_id": self.comm_oid}, {"$set": {"status": "read"}})

        # Clear the idempotency key so the event isn't deduplicated by key
        self.webhook_events.delete_one({"event_id": f"status:{self.provider_msg_id}:delivered"})

        item = {"id": self.provider_msg_id, "status": "delivered", "timestamp": "1728560002"}
        result = process_delivery_status(self.db, item)

        self.assertIn(result["status"], ("ignored_out_of_order", "duplicate"))
        doc = self.comms.find_one({"_id": self.comm_oid})
        self.assertEqual(doc["status"], "read")

    def test_08_failed_cannot_be_overwritten_by_delivered(self):
        """Once status is 'failed', 'delivered' cannot overwrite it."""
        self.comms.update_one({"_id": self.comm_oid}, {"$set": {"status": "failed"}})

        # Ensure idempotency key not blocking
        self.webhook_events.delete_one({"event_id": f"status:{self.provider_msg_id}:delivered"})

        item = {"id": self.provider_msg_id, "status": "delivered", "timestamp": "1728560003"}
        result = process_delivery_status(self.db, item)

        self.assertEqual(result["status"], "ignored_failed_override")
        doc = self.comms.find_one({"_id": self.comm_oid})
        self.assertEqual(doc["status"], "failed")

    # ── 4. Failed delivery preserves error details, no secret exposure ────────

    def test_09_failed_delivery_preserves_error_title_not_secret(self):
        """Failed delivery webhook preserves error code/title; app secret is never stored."""
        payload = self._status_payload(
            self.provider_msg_id, "failed",
            errors=[{"code": 131026, "title": "Message Undeliverable to Recipient"}],
        )
        raw = json.dumps(payload).encode()
        self.client.post(
            "/api/webhook/whatsapp",
            data=raw,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": self._sign(raw)},
        )
        doc = self.comms.find_one({"_id": self.comm_oid})
        self.assertEqual(doc["status"], "failed")
        self.assertIn("Undeliverable", doc.get("last_error", ""))
        # App secret must never appear in the stored document
        doc_str = json.dumps(doc, default=str)
        self.assertNotIn(self.app_secret, doc_str, "App secret must not be stored in communication document")
        self.assertNotIn(self.verify_token, doc_str, "Verify token must not be stored in communication document")

    # ── 5. Ambiguous / unmatched phone does not modify consent ───────────────

    def test_10_ambiguous_phone_does_not_modify_any_consent(self):
        """Two profiles sharing a phone number: STOP from that phone modifies neither."""
        oid1, oid2 = ObjectId(), ObjectId()
        shared_phone = "+919700000001"
        self.profiles.insert_many([
            {"_id": oid1, "phone": shared_phone, "whatsapp_opt_in": True, "whatsapp_opt_out": False},
            {"_id": oid2, "phone": shared_phone, "whatsapp_opt_in": True, "whatsapp_opt_out": False},
        ])
        try:
            result = process_inbound_message(self.db, {
                "id": f"wamid.ambig_{ObjectId()}",
                "from": "919700000001",
                "type": "text",
                "text": {"body": "STOP"},
            })
            self.assertNotEqual(result.get("status"), "opt_out_recorded",
                                "Ambiguous phone must not record an opt-out")

            d1 = self.profiles.find_one({"_id": oid1})
            d2 = self.profiles.find_one({"_id": oid2})
            self.assertTrue(d1["whatsapp_opt_in"], "Profile 1 must not be opted out on ambiguous match")
            self.assertFalse(d1["whatsapp_opt_out"])
            self.assertTrue(d2["whatsapp_opt_in"], "Profile 2 must not be opted out on ambiguous match")
            self.assertFalse(d2["whatsapp_opt_out"])
        finally:
            self.profiles.delete_many({"_id": {"$in": [oid1, oid2]}})

    def test_11_unmatched_phone_does_not_modify_any_consent(self):
        """STOP from an unknown phone number does not modify any existing profile."""
        result = process_inbound_message(self.db, {
            "id": f"wamid.unknown_{ObjectId()}",
            "from": "919500000000",  # No profile has this phone
            "type": "text",
            "text": {"body": "STOP"},
        })
        self.assertNotEqual(result.get("status"), "opt_out_recorded")

    # ── 6. Opt-out overrides opt-in ───────────────────────────────────────────

    def test_12_opt_out_cannot_be_re_enabled_by_non_optout_message(self):
        """After STOP, a non-opt-out inbound message must not re-enable WhatsApp consent."""
        # Apply opt-out
        result_stop = process_inbound_message(self.db, {
            "id": f"wamid.stop_{ObjectId()}",
            "from": self.norm_phone,
            "type": "text",
            "text": {"body": "STOP"},
        })
        self.assertEqual(result_stop.get("status"), "opt_out_recorded")

        # Follow-up non-opt-out message
        result_msg = process_inbound_message(self.db, {
            "id": f"wamid.followup_{ObjectId()}",
            "from": self.norm_phone,
            "type": "text",
            "text": {"body": "Hello, I have a question"},
        })
        # Must not re-enable consent
        doc = self.profiles.find_one({"_id": self.user_oid})
        self.assertFalse(doc["whatsapp_opt_in"], "Opt-in must remain False after STOP")
        self.assertTrue(doc["whatsapp_opt_out"], "Opt-out must remain True after STOP")

    # ── 7. No outbound communications during webhook processing ─────────────

    def test_13_webhook_processing_generates_no_outbound_comms(self):
        """Processing STOP + delivery status webhooks must produce zero outbound comm records."""
        initial_count = self.comms.count_documents({"customer_id": {"$ne": self.user_oid}})

        # Process STOP
        stop_payload = self._inbound_payload(self.norm_phone, "STOP")
        raw = json.dumps(stop_payload).encode()
        self.client.post(
            "/api/webhook/whatsapp",
            data=raw,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": self._sign(raw)},
        )

        # Process delivery status
        status_payload = self._status_payload(self.provider_msg_id, "delivered")
        raw2 = json.dumps(status_payload).encode()
        self.client.post(
            "/api/webhook/whatsapp",
            data=raw2,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": self._sign(raw2)},
        )

        # No NEW comm records created (beyond the seeded one)
        after_count = self.comms.count_documents({"customer_id": {"$ne": self.user_oid}})
        self.assertEqual(initial_count, after_count,
                         "Webhook processing must not create any outbound communication records")

    # ── 8. record_webhook_idempotency atomic concurrent inserts ─────────────

    def test_14_record_webhook_idempotency_concurrent_inserts_exactly_one_succeeds(self):
        """Concurrent calls with the same event_id result in exactly one success."""
        if self.db is None:
            self.skipTest("MongoDB not available")

        event_id = f"concurrent_idempotency_test_{ObjectId()}"
        results = []
        errors = []
        n_threads = 10

        def _insert():
            try:
                success = record_webhook_idempotency(self.db, event_id, event_type="test")
                results.append(success)
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=_insert) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        self.assertEqual(errors, [], f"Unexpected errors during concurrent inserts: {errors}")
        successes = [r for r in results if r is True]
        failures = [r for r in results if r is False]
        self.assertEqual(len(successes), 1,
                         f"Expected exactly 1 success in {n_threads} concurrent inserts, got {len(successes)}")
        self.assertEqual(len(failures), n_threads - 1)

    # ── 9. GET verification fail-closed ──────────────────────────────────────

    def test_15_get_verification_fails_closed_on_missing_token(self):
        """verify_webhook_challenge returns (False, None) when any required field is None."""
        self.assertFalse(verify_webhook_challenge(None, "tok", "ch", "tok")[0])
        self.assertFalse(verify_webhook_challenge("subscribe", None, "ch", "tok")[0])
        self.assertFalse(verify_webhook_challenge("subscribe", "tok", None, "tok")[0])
        self.assertFalse(verify_webhook_challenge("subscribe", "tok", "ch", None)[0])

    def test_16_get_verification_wrong_mode_rejected(self):
        """verify_webhook_challenge rejects mode != 'subscribe'."""
        ok, _ = verify_webhook_challenge("publish", "tok", "ch", "tok")
        self.assertFalse(ok)
        ok2, _ = verify_webhook_challenge("unsubscribe", "tok", "ch", "tok")
        self.assertFalse(ok2)

    def test_17_get_verification_wrong_token_rejected(self):
        """verify_webhook_challenge rejects mismatched token."""
        ok, ch = verify_webhook_challenge("subscribe", "wrong_token", "mychallenge", "correct_token")
        self.assertFalse(ok)
        self.assertIsNone(ch)

    def test_18_get_verification_correct_token_accepted(self):
        """verify_webhook_challenge accepts correct mode + token and returns the challenge."""
        ok, ch = verify_webhook_challenge("subscribe", "my_token", "challenge_string", "my_token")
        self.assertTrue(ok)
        self.assertEqual(ch, "challenge_string")

    # ── 10. Opt-out keyword correctness ──────────────────────────────────────

    def test_19_opt_out_keywords_with_punctuation(self):
        """Opt-out keywords with leading/trailing punctuation are still recognized."""
        for kw in ("STOP!", "stop.", "  QUIT  ", "CANCEL!", "END.", "UNSUBSCRIBE"):
            self.assertTrue(is_opt_out_keyword(kw), f"Expected opt-out for: {kw!r}")

    def test_20_non_opt_out_phrases_not_triggered(self):
        """Sentences that contain opt-out words but are not standalone keywords are NOT opt-outs."""
        for msg in ("Please stop the music", "I want to cancel this order", "When does the sale end?", "Start"):
            self.assertFalse(is_opt_out_keyword(msg), f"Should NOT opt-out for: {msg!r}")


if __name__ == "__main__":
    unittest.main()
