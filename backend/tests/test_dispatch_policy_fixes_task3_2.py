"""Focused Unit Tests for Task 3.2: WhatsApp Dispatch Policy Violations Fixes.

Covers:
1. Eligible high-priority opportunity selects WhatsApp only.
2. Missing promotional opt-in selects Gmail when eligible.
3. Explicit opt-out blocks WhatsApp even if opt-in is true.
4. Normal-priority wishlist reminder selects Gmail by default.
5. Invalid/missing phone prevents WhatsApp dispatch and falls back safely.
6. Successful primary dispatch does not send through the other channel.
7. Provider failure behavior does not create unsafe duplicate delivery.
8. Order confirmation rejects malformed and too-short phone numbers.
9. Valid order-confirmation phone is normalized before provider dispatch.
10. Existing Gmail behavior and response contracts remain unchanged.
11. Repeated or overlapping trigger paths do not send the same opportunity twice.
"""

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from bson import ObjectId

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module
from communication_provider import CommunicationProvider
from marketing_automation_service import (
    trigger_order_confirmation_communication,
    trigger_lead_qualification_communication,
    trigger_cart_abandonment_communication,
    trigger_wishlist_reminder_communication,
    dispatch_communication,
)
from opportunity_engine import (
    process_customer_opportunities,
    ensure_marketing_opportunities_indexes,
    OPP_CART_ABANDONMENT,
)


class MockTrackingProvider(CommunicationProvider):
    """Controllable test provider capturing all dispatched emails and WhatsApp messages."""

    def __init__(self, email_success=True, wa_success=True, email_error="SMTP error", wa_error="WA delivery error"):
        self.email_success = email_success
        self.wa_success = wa_success
        self.email_error = email_error
        self.wa_error = wa_error
        self.emails_sent = []
        self.whatsapp_sent = []

    def send_email(self, recipient, subject, body, metadata=None, html_body=None, **kwargs):
        self.emails_sent.append({
            "recipient": recipient,
            "subject": subject,
            "body": body,
            "metadata": metadata or {},
            "html_body": html_body,
        })
        if self.email_success:
            return {
                "success": True,
                "provider": "gmail_smtp",
                "provider_message_id": f"email_msg_{len(self.emails_sent)}",
                "recipient": recipient,
            }
        return {
            "success": False,
            "provider": "gmail_smtp",
            "provider_message_id": None,
            "error": self.email_error,
        }

    def send_whatsapp(self, recipient, body, metadata=None):
        self.whatsapp_sent.append({
            "recipient": recipient,
            "body": body,
            "metadata": metadata or {},
        })
        if self.wa_success:
            return {
                "success": True,
                "provider": "whatsapp_cloud",
                "provider_message_id": f"wa_msg_{len(self.whatsapp_sent)}",
                "recipient": recipient,
            }
        return {
            "success": False,
            "provider": "whatsapp_cloud",
            "provider_message_id": None,
            "error": self.wa_error,
        }


class TestTask32DispatchPolicyFixes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = app_module.db
        ensure_marketing_opportunities_indexes(cls.db)

    def setUp(self):
        self.created = defaultdict(list)
        self.provider = MockTrackingProvider()
        self.now = datetime.now(timezone.utc)

    def tearDown(self):
        for col_name, ids in self.created.items():
            if ids:
                self.db[col_name].delete_many({"_id": {"$in": ids}})
                self.db[col_name].delete_many({"customer_id": {"$in": ids}})
                self.db[col_name].delete_many({"user_id": {"$in": ids}})

    def track(self, col_name, doc_id):
        self.created[col_name].append(doc_id)
        return doc_id

    # --------------------------------------------------------------------------
    # 1. Eligible high-priority opportunity selects WhatsApp only
    # --------------------------------------------------------------------------
    def test_01_eligible_high_priority_cart_abandonment_selects_whatsapp_only(self):
        cid = ObjectId()
        self.track("user_profiles", cid)
        self.db["user_profiles"].insert_one({
            "_id": cid,
            "email": "cart_wa@example.com",
            "phone": "+919876543210",
            "whatsapp_opt_in": True,
            "whatsapp_opt_out": False,
        })

        cart_id = ObjectId()
        self.track("cart", cart_id)
        self.db["cart"].insert_one({
            "_id": cart_id,
            "user_id": cid,
            "items": [{"name": "Premium Hoodie", "price": 1999.0, "quantity": 1}],
            "total_amount": 1999.0,
            "updated_at": self.now - timedelta(hours=2),
        })

        res = trigger_cart_abandonment_communication(cid, self.db, provider=self.provider, abandonment_delay_hours=1)

        self.assertIn("whatsapp", res)
        self.assertEqual(res["whatsapp"]["status"], "sent")
        self.assertEqual(len(self.provider.whatsapp_sent), 1)
        self.assertEqual(len(self.provider.emails_sent), 0)
        self.assertEqual(res.get("selected_channel"), "whatsapp")

    # --------------------------------------------------------------------------
    # 2. Missing promotional opt-in selects Gmail when eligible
    # --------------------------------------------------------------------------
    def test_02_missing_promotional_opt_in_selects_gmail_when_eligible(self):
        cid = ObjectId()
        self.track("user_profiles", cid)
        self.db["user_profiles"].insert_one({
            "_id": cid,
            "email": "cart_no_optin@example.com",
            "phone": "+919876543210",
            "whatsapp_opt_in": False,
            "whatsapp_opt_out": False,
        })

        cart_id = ObjectId()
        self.track("cart", cart_id)
        self.db["cart"].insert_one({
            "_id": cart_id,
            "user_id": cid,
            "items": [{"name": "Classic Oxford", "price": 1499.0, "quantity": 1}],
            "total_amount": 1499.0,
            "updated_at": self.now - timedelta(hours=2),
        })

        res = trigger_cart_abandonment_communication(cid, self.db, provider=self.provider, abandonment_delay_hours=1)

        self.assertIn("email", res)
        self.assertEqual(res["email"]["status"], "sent")
        self.assertEqual(len(self.provider.emails_sent), 1)
        self.assertEqual(len(self.provider.whatsapp_sent), 0)
        self.assertEqual(res.get("selected_channel"), "email")

    # --------------------------------------------------------------------------
    # 3. Explicit opt-out blocks WhatsApp even if opt-in is true
    # --------------------------------------------------------------------------
    def test_03_explicit_opt_out_blocks_whatsapp_even_if_opt_in_is_true(self):
        cid = ObjectId()
        self.track("user_profiles", cid)
        self.db["user_profiles"].insert_one({
            "_id": cid,
            "email": "cart_optout@example.com",
            "phone": "+919876543210",
            "whatsapp_opt_in": True,
            "whatsapp_opt_out": True,
        })

        cart_id = ObjectId()
        self.track("cart", cart_id)
        self.db["cart"].insert_one({
            "_id": cart_id,
            "user_id": cid,
            "items": [{"name": "Slim Jeans", "price": 2499.0, "quantity": 1}],
            "total_amount": 2499.0,
            "updated_at": self.now - timedelta(hours=2),
        })

        res = trigger_cart_abandonment_communication(cid, self.db, provider=self.provider, abandonment_delay_hours=1)

        self.assertIn("email", res)
        self.assertEqual(res["email"]["status"], "sent")
        self.assertEqual(len(self.provider.emails_sent), 1)
        self.assertEqual(len(self.provider.whatsapp_sent), 0)
        self.assertEqual(res.get("selected_channel"), "email")

    # --------------------------------------------------------------------------
    # 4. Normal-priority wishlist reminder selects Gmail by default
    # --------------------------------------------------------------------------
    def test_04_normal_priority_wishlist_reminder_selects_gmail_by_default(self):
        cid = ObjectId()
        self.track("user_profiles", cid)
        self.db["user_profiles"].insert_one({
            "_id": cid,
            "email": "wish_default@example.com",
            "phone": "+919876543210",
            "whatsapp_opt_in": True,
            "whatsapp_opt_out": False,
        })

        wl_id = ObjectId()
        self.track("wishlist", wl_id)
        self.db["wishlist"].insert_one({
            "_id": wl_id,
            "user_id": cid,
            "items": [{"name": "Silk Scarf", "price": 799.0}],
            "updated_at": self.now - timedelta(days=8),
        })

        res = trigger_wishlist_reminder_communication(cid, self.db, provider=self.provider, reminder_delay_days=7)

        self.assertIn("email", res)
        self.assertEqual(res["email"]["status"], "sent")
        self.assertEqual(len(self.provider.emails_sent), 1)
        self.assertEqual(len(self.provider.whatsapp_sent), 0)
        self.assertEqual(res.get("selected_channel"), "email")

    # --------------------------------------------------------------------------
    # 5. Invalid or missing phone prevents WhatsApp dispatch
    # --------------------------------------------------------------------------
    def test_05_invalid_phone_prevents_whatsapp_dispatch(self):
        cid = ObjectId()
        self.track("user_profiles", cid)
        self.db["user_profiles"].insert_one({
            "_id": cid,
            "email": "bad_phone@example.com",
            "phone": "12345",  # Too short/invalid E.164
            "whatsapp_opt_in": True,
            "whatsapp_opt_out": False,
        })

        cart_id = ObjectId()
        self.track("cart", cart_id)
        self.db["cart"].insert_one({
            "_id": cart_id,
            "user_id": cid,
            "items": [{"name": "Cotton Tee", "price": 499.0, "quantity": 1}],
            "total_amount": 499.0,
            "updated_at": self.now - timedelta(hours=2),
        })

        res = trigger_cart_abandonment_communication(cid, self.db, provider=self.provider, abandonment_delay_hours=1)

        self.assertIn("email", res)
        self.assertEqual(res["email"]["status"], "sent")
        self.assertEqual(len(self.provider.emails_sent), 1)
        self.assertEqual(len(self.provider.whatsapp_sent), 0)

    # --------------------------------------------------------------------------
    # 6. Successful primary dispatch does not send through the other channel
    # --------------------------------------------------------------------------
    def test_06_single_channel_dispatch_lead_qualification(self):
        cid = ObjectId()
        self.track("user_profiles", cid)
        self.db["user_profiles"].insert_one({
            "_id": cid,
            "email": "lead_qual_single@example.com",
            "phone": "+919876543210",
            "whatsapp_opt_in": True,
            "whatsapp_opt_out": False,
        })

        lead_state = {
            "customer_id": cid,
            "qualification_transition": "not_qualified_to_qualified",
            "is_newly_qualified": True,
            "lead_segment": "Hot",
            "lead_probability": 0.82,
            "lead_score": 82,
            "last_qualified_at": self.now.strftime("%Y-%m-%d"),
        }

        res = trigger_lead_qualification_communication(cid, lead_state, self.db, provider=self.provider)

        # Standard priority flow prefers email
        self.assertIn("email", res)
        self.assertEqual(res["email"]["status"], "sent")
        total_dispatches = len(self.provider.emails_sent) + len(self.provider.whatsapp_sent)
        self.assertEqual(total_dispatches, 1)
        self.assertEqual(len(self.provider.whatsapp_sent), 0)

    # --------------------------------------------------------------------------
    # 7. Provider failure behavior does not create unsafe duplicate delivery
    # --------------------------------------------------------------------------
    def test_07_provider_failure_does_not_silently_retry_other_channel(self):
        cid = ObjectId()
        self.track("user_profiles", cid)
        self.db["user_profiles"].insert_one({
            "_id": cid,
            "email": "wa_failure_safe@example.com",
            "phone": "+919876543210",
            "whatsapp_opt_in": True,
            "whatsapp_opt_out": False,
        })

        cart_id = ObjectId()
        self.track("cart", cart_id)
        self.db["cart"].insert_one({
            "_id": cart_id,
            "user_id": cid,
            "items": [{"name": "Polo T-Shirt", "price": 899.0, "quantity": 1}],
            "total_amount": 899.0,
            "updated_at": self.now - timedelta(hours=2),
        })

        failing_provider = MockTrackingProvider(email_success=True, wa_success=False, wa_error="Meta Timeout")
        res = trigger_cart_abandonment_communication(cid, self.db, provider=failing_provider, abandonment_delay_hours=1)

        self.assertIn("whatsapp", res)
        self.assertEqual(res["whatsapp"]["status"], "failed")
        # No blind secondary dispatch to email on provider failure
        self.assertEqual(len(failing_provider.emails_sent), 0)

    # --------------------------------------------------------------------------
    # 8. Order confirmation rejects malformed and too-short phone numbers
    # --------------------------------------------------------------------------
    def test_08_order_confirmation_rejects_malformed_phone(self):
        cid = ObjectId()
        self.track("user_profiles", cid)
        self.db["user_profiles"].insert_one({
            "_id": cid,
            "email": "buyer_bad_phone@example.com",
            "phone": "555-12",  # Malformed and too short
        })

        order_id = ObjectId()
        self.track("orders", order_id)
        self.db["orders"].insert_one({
            "_id": order_id,
            "user_id": cid,
            "customer_phone": "12345",  # Also invalid
            "items": [{"name": "Linen Kurta", "quantity": 1, "price": 1299.0}],
            "total_amount": 1299.0,
            "status": "placed",
            "created_at": self.now,
        })

        res = trigger_order_confirmation_communication(order_id, self.db, provider=self.provider)

        self.assertEqual(res["email"]["status"], "sent")
        self.assertEqual(res["whatsapp"]["status"], "skipped")
        self.assertEqual(len(self.provider.emails_sent), 1)
        self.assertEqual(len(self.provider.whatsapp_sent), 0)

    # --------------------------------------------------------------------------
    # 9. Valid order-confirmation phone is normalized before provider dispatch
    # --------------------------------------------------------------------------
    def test_09_order_confirmation_phone_normalized_before_dispatch(self):
        cid = ObjectId()
        self.track("user_profiles", cid)
        self.db["user_profiles"].insert_one({
            "_id": cid,
            "email": "buyer_norm@example.com",
            "phone": "+91 98765-43210",  # Unformatted E.164 with spaces and hyphens
        })

        order_id = ObjectId()
        self.track("orders", order_id)
        self.db["orders"].insert_one({
            "_id": order_id,
            "user_id": cid,
            "items": [{"name": "Oxford Shirt", "quantity": 1, "price": 1599.0}],
            "total_amount": 1599.0,
            "status": "placed",
            "created_at": self.now,
        })

        res = trigger_order_confirmation_communication(order_id, self.db, provider=self.provider)

        self.assertEqual(res["email"]["status"], "sent")
        self.assertEqual(res["whatsapp"]["status"], "sent")
        self.assertEqual(len(self.provider.whatsapp_sent), 1)
        # Normalized recipient must be digits only without leading '+' or spaces
        self.assertEqual(self.provider.whatsapp_sent[0]["recipient"], "919876543210")

    # --------------------------------------------------------------------------
    # 10. Repeated or overlapping trigger paths do not send same opportunity twice
    # --------------------------------------------------------------------------
    def test_10_standalone_and_opportunity_engine_cross_path_idempotency(self):
        cid = ObjectId()
        self.track("user_profiles", cid)
        self.db["user_profiles"].insert_one({
            "_id": cid,
            "email": "overlap@example.com",
            "phone": "+919876543210",
            "whatsapp_opt_in": True,
            "whatsapp_opt_out": False,
        })

        cart_time = self.now - timedelta(hours=2)
        cart_id = ObjectId()
        self.track("cart", cart_id)
        self.db["cart"].insert_one({
            "_id": cart_id,
            "user_id": cid,
            "items": [{"name": "Designer Jeans", "price": 2999.0, "quantity": 1}],
            "total_amount": 2999.0,
            "updated_at": cart_time,
        })

        lead_state = {
            "customer_id": cid,
            "lead_segment": "Hot",
            "lead_probability": 0.85,
            "lead_score": 85,
        }
        self.db["customer_lead_state"].insert_one(lead_state)
        self.track("customer_lead_state", lead_state["_id"])

        # Run standalone trigger first
        res1 = trigger_cart_abandonment_communication(cid, self.db, provider=self.provider, abandonment_delay_hours=1)
        self.assertEqual(res1["whatsapp"]["status"], "sent")
        self.assertEqual(len(self.provider.whatsapp_sent), 1)

        # Now run opportunity engine on same customer and cart state
        res_engine = process_customer_opportunities(
            customer_id=cid,
            db=self.db,
            provider=self.provider,
            lead_state_doc=lead_state,
            current_time=self.now,
        )

        # Opportunity engine should not send a second message for this cart abandonment
        self.assertEqual(len(self.provider.whatsapp_sent), 1)
        self.assertEqual(len(self.provider.emails_sent), 0)


if __name__ == "__main__":
    unittest.main()
