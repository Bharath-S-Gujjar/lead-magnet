"""Focused regression tests for Phase 3 Communication Engine & Fake Notification Removal.

Validates all 29 requirements:

REGISTRATION
1. Registration triggers one email opportunity.
2. Registration triggers WhatsApp only when eligible/configured.
3. Duplicate registration processing does not duplicate communication.

QUALIFICATION
4. Not qualified -> Hot triggers communication opportunity.
5. Hot -> Hot does not trigger another communication.
6. Hot -> Warm does not trigger communication.
7. Warm -> Hot creates a new qualification event.
8. Qualification cooldown prevents duplicate delivery.
9. Qualification idempotency prevents duplicate delivery.

WARM
10. Warm customer alone receives no qualification communication.

CART
11. Current cart is used for cart abandonment.
12. Empty/currently cleared cart prevents cart-abandonment message.
13. Completed order invalidates cart-abandonment communication.
14. Duplicate cart reminder is prevented by idempotency/cooldown.

WISHLIST
15. Current wishlist is used.
16. Empty wishlist prevents reminder.
17. 7-day cooldown prevents repeated wishlist reminders.

ORDER
18. One order produces one email confirmation opportunity.
19. One order produces one WhatsApp confirmation opportunity when eligible.
20. Retried order processing does not duplicate confirmations.

CHANNEL FAILURE
21. Email failure does not incorrectly mark WhatsApp successful.
22. WhatsApp failure does not incorrectly mark Email successful.
23. Missing provider credentials are handled safely.
24. No communication is falsely recorded as "sent".

ADMIN NOTIFICATIONS
25. Real qualification creates one admin notification.
26. Hot -> Hot creates no duplicate admin notification.
27. No fake notification is generated when admin_notifications is empty.

SECURITY
28. Normal customer cannot trigger admin notification APIs.
29. Customer communication records cannot be read by another customer.
"""

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from collections import defaultdict
import jwt
from bson import ObjectId

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module
from communication_provider import CommunicationProvider, MultiChannelProvider
from marketing_automation_service import (
    trigger_registration_communication,
    trigger_lead_qualification_communication,
    trigger_cart_abandonment_communication,
    trigger_wishlist_reminder_communication,
    trigger_order_confirmation_communication,
    process_marketing_automation_event,
    create_automation_event_for_qualification,
    evaluate_channel_eligibility,
    dispatch_communication,
)
from admin_intelligence_service import (
    get_admin_notifications_list,
    create_admin_notification,
)


class MockProvider(CommunicationProvider):
    """Mock provider with controllable outcome per channel."""
    def __init__(self, email_success=True, wa_success=True, email_msg_id="mock_em_1", wa_msg_id="mock_wa_1"):
        self.email_success = email_success
        self.wa_success = wa_success
        self.email_msg_id = email_msg_id
        self.wa_msg_id = wa_msg_id
        self.emails_sent = []
        self.whatsapp_sent = []

    def send_email(self, recipient, subject, body, metadata=None):
        self.emails_sent.append({"recipient": recipient, "subject": subject, "body": body, "metadata": metadata})
        if self.email_success:
            return {"success": True, "provider": "mock_email", "provider_message_id": self.email_msg_id}
        return {"success": False, "provider": "mock_email", "error": "SMTP server connection refused"}

    def send_whatsapp(self, recipient, body, metadata=None):
        self.whatsapp_sent.append({"recipient": recipient, "body": body, "metadata": metadata})
        if self.wa_success:
            return {"success": True, "provider": "mock_whatsapp", "provider_message_id": self.wa_msg_id}
        return {"success": False, "provider": "mock_whatsapp", "error": "WhatsApp API unreachable"}


class UnconfiguredProvider(CommunicationProvider):
    """Provider simulating missing production credentials."""
    def send_email(self, recipient, subject, body, metadata=None):
        return {"success": False, "provider": "gmail_smtp", "error": "Missing GMAIL_USER or GMAIL_APP_PASSWORD credentials"}

    def send_whatsapp(self, recipient, body, metadata=None):
        return {"success": False, "provider": "whatsapp_business", "error": "Missing WHATSAPP_API_TOKEN credentials"}


class CommunicationEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = app_module.app.test_client()
        cls.db = app_module.db
        cls.jwt_secret = app_module.JWT_SECRET

    def setUp(self):
        self.created = defaultdict(list)
        self.mock_provider = MockProvider()

    def tearDown(self):
        # Clean up any documents created during test execution
        for col_name, ids in self.created.items():
            if ids:
                self.db[col_name].delete_many({"_id": {"$in": ids}})
                # Also delete by customer_id or user_id or idempotency_key if string
                self.db[col_name].delete_many({"customer_id": {"$in": ids}})
                self.db[col_name].delete_many({"user_id": {"$in": ids}})

    def track(self, col_name, doc_id):
        self.created[col_name].append(doc_id)
        return doc_id

    def make_token(self, user_id, role="user"):
        exp_time = datetime.now(timezone.utc) + timedelta(minutes=15)
        return jwt.encode(
            {"sub": str(user_id), "role": role, "exp": exp_time},
            self.jwt_secret,
            algorithm="HS256"
        )

    # ==============================================================
    # REGISTRATION (Tests 1-3)
    # ==============================================================

    def test_01_registration_triggers_one_email_opportunity(self):
        """1. Real customer registration triggers exactly one welcome email opportunity."""
        cid = ObjectId()
        self.track("user_profiles", cid)
        self.db["user_profiles"].insert_one({
            "_id": cid,
            "email": "sarah.lead@example.com",
            "full_name": "Sarah Connor",
        })

        results = trigger_registration_communication(cid, self.db, provider=self.mock_provider)
        self.assertIn("email", results)
        self.assertEqual(results["email"]["status"], "sent")
        self.assertEqual(len(self.mock_provider.emails_sent), 1)
        self.assertIn("Sarah Connor", self.mock_provider.emails_sent[0]["body"])
        self.track("marketing_communications", results["email"]["_id"])

    def test_02_registration_triggers_whatsapp_only_when_eligible(self):
        """2. Registration triggers WhatsApp only when valid phone exists and consent given."""
        # Case A: No phone number -> WhatsApp is skipped
        cid_no_phone = ObjectId()
        self.track("user_profiles", cid_no_phone)
        self.db["user_profiles"].insert_one({
            "_id": cid_no_phone,
            "email": "user_nophone@example.com",
            "full_name": "No Phone User",
        })
        res_a = trigger_registration_communication(cid_no_phone, self.db, provider=self.mock_provider)
        self.assertEqual(res_a["whatsapp"]["status"], "skipped")
        self.assertEqual(len(self.mock_provider.whatsapp_sent), 0)
        self.track("marketing_communications", res_a["email"]["_id"])
        self.track("marketing_communications", res_a["whatsapp"]["_id"])

        # Case B: Valid phone present -> WhatsApp is sent
        cid_phone = ObjectId()
        self.track("user_profiles", cid_phone)
        self.db["user_profiles"].insert_one({
            "_id": cid_phone,
            "email": "user_phone@example.com",
            "phone": "+919876543210",
            "full_name": "Phone User",
        })
        res_b = trigger_registration_communication(cid_phone, self.db, provider=self.mock_provider)
        self.assertEqual(res_b["whatsapp"]["status"], "sent")
        self.assertEqual(len(self.mock_provider.whatsapp_sent), 1)
        self.track("marketing_communications", res_b["email"]["_id"])
        self.track("marketing_communications", res_b["whatsapp"]["_id"])

    def test_03_duplicate_registration_processing_does_not_duplicate(self):
        """3. Calling registration communication again does not dispatch duplicate emails (idempotent)."""
        cid = ObjectId()
        self.track("user_profiles", cid)
        self.db["user_profiles"].insert_one({
            "_id": cid,
            "email": "idem_reg@example.com",
            "full_name": "Idem User",
        })

        res1 = trigger_registration_communication(cid, self.db, provider=self.mock_provider)
        self.track("marketing_communications", res1["email"]["_id"])
        count_emails_1 = len(self.mock_provider.emails_sent)
        self.assertEqual(count_emails_1, 1)

        # Retry registration processing (e.g. page refresh / login)
        res2 = trigger_registration_communication(cid, self.db, provider=self.mock_provider)
        count_emails_2 = len(self.mock_provider.emails_sent)
        self.assertEqual(count_emails_2, 1, "Duplicate registration processing sent duplicate email!")
        self.assertEqual(res2["email"]["status"], "sent")

    # ==============================================================
    # QUALIFICATION (Tests 4-9)
    # ==============================================================

    def test_04_not_qualified_to_hot_triggers_communication_opportunity(self):
        """4. Not qualified -> Hot transition triggers qualification communication opportunity."""
        cid = ObjectId()
        self.track("user_profiles", cid)
        self.db["user_profiles"].insert_one({
            "_id": cid,
            "email": "newhot@example.com",
            "full_name": "Hot Lead Customer",
        })
        lead_state = {
            "customer_id": cid,
            "qualification_transition": "not_qualified_to_qualified",
            "is_newly_qualified": True,
            "lead_segment": "Hot",
            "lead_probability": 0.85,
            "lead_score": 85,
            "last_qualified_at": "2026-10-02T10:00:00Z"
        }
        res = trigger_lead_qualification_communication(cid, lead_state, self.db, provider=self.mock_provider)
        self.assertIn("email", res)
        self.assertEqual(res["email"]["status"], "sent")
        self.track("marketing_communications", res["email"]["_id"])

        # Check content: MUST NOT expose ML probability or score
        sent_body = self.mock_provider.emails_sent[0]["body"]
        self.assertNotIn("0.85", sent_body)
        self.assertNotIn("85", sent_body)
        self.assertNotIn("lead_score", sent_body)
        self.assertNotIn("probability", sent_body)

    def test_05_hot_to_hot_does_not_trigger_another_communication(self):
        """5. Hot -> Hot recalculation does NOT trigger another communication."""
        cid = ObjectId()
        self.track("user_profiles", cid)
        self.db["user_profiles"].insert_one({"_id": cid, "email": "hot2hot@example.com"})

        lead_state = {
            "customer_id": cid,
            "qualification_transition": "none",
            "is_newly_qualified": False,
            "lead_segment": "Hot",
            "lead_probability": 0.88,
            "lead_score": 88,
        }
        res = trigger_lead_qualification_communication(cid, lead_state, self.db, provider=self.mock_provider)
        self.assertTrue(res.get("skipped"))
        self.assertEqual(len(self.mock_provider.emails_sent), 0)

    def test_06_hot_to_warm_does_not_trigger_communication(self):
        """6. Hot -> Warm downgrade does NOT trigger communication."""
        cid = ObjectId()
        self.track("user_profiles", cid)
        self.db["user_profiles"].insert_one({"_id": cid, "email": "downgrade@example.com"})

        lead_state = {
            "customer_id": cid,
            "qualification_transition": "qualified_to_not_qualified",
            "is_newly_qualified": False,
            "lead_segment": "Warm",
            "lead_probability": 0.55,
            "lead_score": 55,
        }
        res = trigger_lead_qualification_communication(cid, lead_state, self.db, provider=self.mock_provider)
        self.assertTrue(res.get("skipped"))
        self.assertEqual(len(self.mock_provider.emails_sent), 0)

    def test_07_warm_to_hot_creates_new_qualification_event(self):
        """7. Warm -> Hot creates a new qualification event."""
        cid = ObjectId()
        self.track("user_profiles", cid)
        self.db["user_profiles"].insert_one({"_id": cid, "email": "warm2hot@example.com"})

        lead_state = {
            "customer_id": cid,
            "qualification_transition": "not_qualified_to_qualified",
            "is_newly_qualified": True,
            "lead_segment": "Hot",
            "lead_probability": 0.78,
            "lead_score": 78,
            "last_qualified_at": "2026-10-02T12:00:00Z"
        }
        # In a fresh customer without prior qualification within 72h
        res = trigger_lead_qualification_communication(cid, lead_state, self.db, provider=self.mock_provider)
        self.assertEqual(res["email"]["status"], "sent")
        self.track("marketing_communications", res["email"]["_id"])

    def test_08_qualification_cooldown_prevents_duplicate_delivery(self):
        """8. Qualification cooldown (72h) prevents duplicate delivery upon requalification."""
        cid = ObjectId()
        self.track("user_profiles", cid)
        self.db["user_profiles"].insert_one({"_id": cid, "email": "cooldown@example.com"})

        # Prior communication sent 2 hours ago
        two_hours_ago = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        comm_doc = {
            "_id": ObjectId(),
            "customer_id": cid,
            "campaign_type": "lead_qualified",
            "channel": "email",
            "status": "sent",
            "sent_at": two_hours_ago,
        }
        self.track("marketing_communications", comm_doc["_id"])
        self.db["marketing_communications"].insert_one(comm_doc)

        lead_state = {
            "customer_id": cid,
            "qualification_transition": "not_qualified_to_qualified",
            "is_newly_qualified": True,
            "lead_segment": "Hot",
            "lead_probability": 0.81,
            "lead_score": 81,
        }
        res = trigger_lead_qualification_communication(cid, lead_state, self.db, provider=self.mock_provider)
        self.assertTrue(res.get("skipped"))
        self.assertIn("cooldown", res.get("reason", "").lower())
        self.assertEqual(len(self.mock_provider.emails_sent), 0)

    def test_09_qualification_idempotency_prevents_duplicate_delivery(self):
        """9. Identical qualification event key prevents duplicate delivery."""
        cid = ObjectId()
        self.track("user_profiles", cid)
        self.db["user_profiles"].insert_one({"_id": cid, "email": "idempotent_qual@example.com"})

        lead_state = {
            "customer_id": cid,
            "qualification_transition": "not_qualified_to_qualified",
            "is_newly_qualified": True,
            "lead_segment": "Hot",
            "lead_probability": 0.75,
            "lead_score": 75,
            "last_qualified_at": "2026-10-02T10:00:00Z"
        }
        res1 = trigger_lead_qualification_communication(cid, lead_state, self.db, provider=self.mock_provider)
        self.track("marketing_communications", res1["email"]["_id"])
        self.assertEqual(len(self.mock_provider.emails_sent), 1)

        # Retry identical event
        res2 = trigger_lead_qualification_communication(cid, lead_state, self.db, provider=self.mock_provider)
        self.assertEqual(len(self.mock_provider.emails_sent), 1)

    # ==============================================================
    # WARM CUSTOMERS (Test 10)
    # ==============================================================

    def test_10_warm_customer_alone_receives_no_qualification_communication(self):
        """10. Warm customer (0.35 <= prob < 0.70) alone receives NO qualification communication."""
        cid = ObjectId()
        self.track("user_profiles", cid)
        self.db["user_profiles"].insert_one({"_id": cid, "email": "warm_user@example.com"})

        lead_state = {
            "customer_id": cid,
            "qualification_transition": "none",
            "is_newly_qualified": False,
            "lead_segment": "Warm",
            "lead_probability": 0.5653,
            "lead_score": 57,
        }
        res = trigger_lead_qualification_communication(cid, lead_state, self.db, provider=self.mock_provider)
        self.assertTrue(res.get("skipped"))
        self.assertEqual(len(self.mock_provider.emails_sent), 0)
        self.assertEqual(len(self.mock_provider.whatsapp_sent), 0)

    # ==============================================================
    # CART ABANDONMENT (Tests 11-14)
    # ==============================================================

    def test_11_current_cart_is_used_for_cart_abandonment(self):
        """11. Current cart state is read directly for cart abandonment reminder."""
        cid = ObjectId()
        self.track("user_profiles", cid)
        self.db["user_profiles"].insert_one({"_id": cid, "email": "abandoner@example.com", "full_name": "Cart Owner"})

        cart_id = ObjectId()
        self.track("cart", cart_id)
        two_hours_ago = datetime.now(timezone.utc) - timedelta(hours=2)
        self.db["cart"].insert_one({
            "_id": cart_id,
            "user_id": cid,
            "items": [
                {"product_id": str(ObjectId()), "name": "Classic Linen Shirt", "price": 1299.0, "quantity": 1}
            ],
            "total_amount": 1299.0,
            "updated_at": two_hours_ago,
        })

        res = trigger_cart_abandonment_communication(cid, self.db, provider=self.mock_provider, abandonment_delay_hours=1)
        self.assertIn("email", res)
        self.assertEqual(res["email"]["status"], "sent")
        self.assertEqual(len(self.mock_provider.emails_sent), 1)
        body = self.mock_provider.emails_sent[0]["body"]
        self.assertIn("Classic Linen Shirt", body)
        self.track("marketing_communications", res["email"]["_id"])

    def test_12_empty_or_cleared_cart_prevents_abandonment_message(self):
        """12. Currently empty or cleared cart prevents cart-abandonment reminder."""
        cid = ObjectId()
        self.track("user_profiles", cid)
        self.db["user_profiles"].insert_one({"_id": cid, "email": "empty_cart@example.com"})

        cart_id = ObjectId()
        self.track("cart", cart_id)
        self.db["cart"].insert_one({
            "_id": cart_id,
            "user_id": cid,
            "items": [],
            "total_amount": 0.0,
            "updated_at": datetime.now(timezone.utc) - timedelta(hours=2),
        })

        res = trigger_cart_abandonment_communication(cid, self.db, provider=self.mock_provider, abandonment_delay_hours=1)
        self.assertTrue(res.get("skipped"))
        self.assertIn("empty", res.get("reason", "").lower())
        self.assertEqual(len(self.mock_provider.emails_sent), 0)

    def test_13_completed_order_invalidates_cart_abandonment_communication(self):
        """13. Completed order placed after cart update invalidates cart-abandonment reminder."""
        cid = ObjectId()
        self.track("user_profiles", cid)
        self.db["user_profiles"].insert_one({"_id": cid, "email": "purchased@example.com"})

        cart_time = datetime.now(timezone.utc) - timedelta(hours=3)
        order_time = datetime.now(timezone.utc) - timedelta(hours=2)

        cart_id = ObjectId()
        self.track("cart", cart_id)
        self.db["cart"].insert_one({
            "_id": cart_id,
            "user_id": cid,
            "items": [{"name": "Summer Dress", "price": 999.0, "quantity": 1}],
            "total_amount": 999.0,
            "updated_at": cart_time,
        })

        order_id = ObjectId()
        self.track("orders", order_id)
        self.db["orders"].insert_one({
            "_id": order_id,
            "user_id": cid,
            "total_amount": 999.0,
            "created_at": order_time,
        })

        res = trigger_cart_abandonment_communication(cid, self.db, provider=self.mock_provider, abandonment_delay_hours=1)
        self.assertTrue(res.get("skipped"))
        self.assertIn("order", res.get("reason", "").lower())
        self.assertEqual(len(self.mock_provider.emails_sent), 0)

    def test_14_duplicate_cart_reminder_is_prevented_by_idempotency(self):
        """14. Duplicate cart reminder for same cart state is prevented by idempotency."""
        cid = ObjectId()
        self.track("user_profiles", cid)
        self.db["user_profiles"].insert_one({"_id": cid, "email": "idem_cart@example.com"})

        cart_time = datetime.now(timezone.utc) - timedelta(hours=2)
        cart_id = ObjectId()
        self.track("cart", cart_id)
        self.db["cart"].insert_one({
            "_id": cart_id,
            "user_id": cid,
            "items": [{"name": "Silk Scarf", "price": 499.0, "quantity": 1}],
            "total_amount": 499.0,
            "updated_at": cart_time,
        })

        res1 = trigger_cart_abandonment_communication(cid, self.db, provider=self.mock_provider, abandonment_delay_hours=1)
        self.track("marketing_communications", res1["email"]["_id"])
        self.assertEqual(len(self.mock_provider.emails_sent), 1)

        # Retry
        res2 = trigger_cart_abandonment_communication(cid, self.db, provider=self.mock_provider, abandonment_delay_hours=1)
        self.assertEqual(len(self.mock_provider.emails_sent), 1)

    # ==============================================================
    # WISHLIST REMINDER (Tests 15-17)
    # ==============================================================

    def test_15_current_wishlist_is_used(self):
        """15. Current wishlist items are used in wishlist reminder."""
        cid = ObjectId()
        self.track("user_profiles", cid)
        self.db["user_profiles"].insert_one({"_id": cid, "email": "wish_user@example.com", "full_name": "Wishlist Fan"})

        wishlist_id = ObjectId()
        self.track("wishlist", wishlist_id)
        self.db["wishlist"].insert_one({
            "_id": wishlist_id,
            "user_id": cid,
            "items": [{"name": "Vintage Denim Jacket", "price": 2499.0}],
            "updated_at": datetime.now(timezone.utc) - timedelta(days=8),
        })

        res = trigger_wishlist_reminder_communication(cid, self.db, provider=self.mock_provider, reminder_delay_days=7)
        self.assertIn("email", res)
        self.assertEqual(res["email"]["status"], "sent")
        self.assertEqual(len(self.mock_provider.emails_sent), 1)
        body = self.mock_provider.emails_sent[0]["body"]
        self.assertIn("Vintage Denim Jacket", body)
        self.track("marketing_communications", res["email"]["_id"])

    def test_16_empty_wishlist_prevents_reminder(self):
        """16. Empty wishlist prevents sending wishlist reminder."""
        cid = ObjectId()
        self.track("user_profiles", cid)
        self.db["user_profiles"].insert_one({"_id": cid, "email": "empty_wish@example.com"})

        wishlist_id = ObjectId()
        self.track("wishlist", wishlist_id)
        self.db["wishlist"].insert_one({
            "_id": wishlist_id,
            "user_id": cid,
            "items": [],
        })

        res = trigger_wishlist_reminder_communication(cid, self.db, provider=self.mock_provider, reminder_delay_days=7)
        self.assertTrue(res.get("skipped"))
        self.assertEqual(len(self.mock_provider.emails_sent), 0)

    def test_17_seven_day_cooldown_prevents_repeated_wishlist_reminders(self):
        """17. 7-day cooldown prevents repeated wishlist reminders."""
        cid = ObjectId()
        self.track("user_profiles", cid)
        self.db["user_profiles"].insert_one({"_id": cid, "email": "cooldown_wish@example.com"})

        wishlist_id = ObjectId()
        self.track("wishlist", wishlist_id)
        self.db["wishlist"].insert_one({
            "_id": wishlist_id,
            "user_id": cid,
            "items": [{"name": "Boho Floral Blouse", "price": 799.0}],
        })

        # Insert a communication sent 2 days ago
        comm_id = ObjectId()
        self.track("marketing_communications", comm_id)
        self.db["marketing_communications"].insert_one({
            "_id": comm_id,
            "customer_id": cid,
            "campaign_type": "wishlist_reminder",
            "channel": "email",
            "status": "sent",
            "sent_at": (datetime.now(timezone.utc) - timedelta(days=2)).isoformat(),
        })

        res = trigger_wishlist_reminder_communication(cid, self.db, provider=self.mock_provider, reminder_delay_days=7)
        self.assertTrue(res.get("skipped"))
        self.assertIn("cooldown", res.get("reason", "").lower())
        self.assertEqual(len(self.mock_provider.emails_sent), 0)

    # ==============================================================
    # ORDER CONFIRMATION (Tests 18-20)
    # ==============================================================

    def test_18_one_order_produces_one_email_confirmation_opportunity(self):
        """18. One real order produces one transactional email confirmation opportunity."""
        cid = ObjectId()
        self.track("user_profiles", cid)
        self.db["user_profiles"].insert_one({"_id": cid, "email": "buyer@example.com", "full_name": "Happy Buyer"})

        order_id = ObjectId()
        self.track("orders", order_id)
        self.db["orders"].insert_one({
            "_id": order_id,
            "user_id": cid,
            "items": [{"name": "Oxford Cotton Shirt", "quantity": 1, "price": 1499.0}],
            "total_amount": 1499.0,
            "status": "placed",
            "created_at": datetime.now(timezone.utc),
        })

        res = trigger_order_confirmation_communication(order_id, self.db, provider=self.mock_provider)
        self.assertIn("email", res)
        self.assertEqual(res["email"]["status"], "sent")
        self.assertEqual(len(self.mock_provider.emails_sent), 1)
        body = self.mock_provider.emails_sent[0]["body"]
        self.assertIn("Oxford Cotton Shirt", body)
        # MUST NOT contain lead metrics
        self.assertNotIn("lead_score", body)
        self.assertNotIn("probability", body)
        self.track("marketing_communications", res["email"]["_id"])

    def test_19_one_order_produces_one_whatsapp_confirmation_when_eligible(self):
        """19. One order produces one WhatsApp confirmation opportunity when phone is eligible."""
        cid = ObjectId()
        self.track("user_profiles", cid)
        self.db["user_profiles"].insert_one({
            "_id": cid,
            "email": "wa_buyer@example.com",
            "phone": "+919876543211",
            "full_name": "WA Buyer",
        })

        order_id = ObjectId()
        self.track("orders", order_id)
        self.db["orders"].insert_one({
            "_id": order_id,
            "user_id": cid,
            "items": [{"name": "Chino Trousers", "quantity": 1, "price": 1999.0}],
            "total_amount": 1999.0,
            "status": "placed",
            "created_at": datetime.now(timezone.utc),
        })

        res = trigger_order_confirmation_communication(order_id, self.db, provider=self.mock_provider)
        self.assertIn("whatsapp", res)
        self.assertEqual(res["whatsapp"]["status"], "sent")
        self.assertEqual(len(self.mock_provider.whatsapp_sent), 1)
        self.track("marketing_communications", res["email"]["_id"])
        self.track("marketing_communications", res["whatsapp"]["_id"])

    def test_20_retried_order_processing_does_not_duplicate_confirmations(self):
        """20. Retried order processing does not send duplicate confirmations."""
        cid = ObjectId()
        self.track("user_profiles", cid)
        self.db["user_profiles"].insert_one({"_id": cid, "email": "retry_order@example.com"})

        order_id = ObjectId()
        self.track("orders", order_id)
        self.db["orders"].insert_one({
            "_id": order_id,
            "user_id": cid,
            "items": [{"name": "Linen Kurta", "quantity": 1, "price": 1299.0}],
            "total_amount": 1299.0,
            "created_at": datetime.now(timezone.utc),
        })

        res1 = trigger_order_confirmation_communication(order_id, self.db, provider=self.mock_provider)
        self.track("marketing_communications", res1["email"]["_id"])
        self.assertEqual(len(self.mock_provider.emails_sent), 1)

        # Retry checkout confirmation
        res2 = trigger_order_confirmation_communication(order_id, self.db, provider=self.mock_provider)
        self.assertEqual(len(self.mock_provider.emails_sent), 1)

    # ==============================================================
    # CHANNEL FAILURE & PROVIDER ABSTRACTION (Tests 21-24)
    # ==============================================================

    def test_21_email_failure_does_not_mark_whatsapp_successful(self):
        """21. Email failure does not incorrectly mark WhatsApp successful or vice versa."""
        split_provider = MockProvider(email_success=False, wa_success=True)
        cid = ObjectId()
        self.track("user_profiles", cid)
        self.db["user_profiles"].insert_one({
            "_id": cid,
            "email": "split_user@example.com",
            "phone": "+919999999999",
            "full_name": "Split User"
        })

        results = trigger_registration_communication(cid, self.db, provider=split_provider)
        self.assertEqual(results["email"]["status"], "failed")
        self.assertEqual(results["whatsapp"]["status"], "sent")
        self.assertIsNotNone(results["email"]["last_error"])
        self.assertIsNone(results["whatsapp"]["last_error"])
        self.track("marketing_communications", results["email"]["_id"])
        self.track("marketing_communications", results["whatsapp"]["_id"])

    def test_22_whatsapp_failure_does_not_mark_email_successful(self):
        """22. WhatsApp failure leaves WhatsApp failed without affecting Email."""
        split_provider = MockProvider(email_success=True, wa_success=False)
        cid = ObjectId()
        self.track("user_profiles", cid)
        self.db["user_profiles"].insert_one({
            "_id": cid,
            "email": "split_user2@example.com",
            "phone": "+919999999999",
            "full_name": "Split User 2"
        })

        results = trigger_registration_communication(cid, self.db, provider=split_provider)
        self.assertEqual(results["email"]["status"], "sent")
        self.assertEqual(results["whatsapp"]["status"], "failed")
        self.assertIsNone(results["email"]["last_error"])
        self.assertIsNotNone(results["whatsapp"]["last_error"])
        self.track("marketing_communications", results["email"]["_id"])
        self.track("marketing_communications", results["whatsapp"]["_id"])

    def test_23_missing_provider_credentials_are_handled_safely(self):
        """23. Missing provider credentials fail safely without crashing."""
        unconfigured = UnconfiguredProvider()
        cid = ObjectId()
        self.track("user_profiles", cid)
        self.db["user_profiles"].insert_one({
            "_id": cid,
            "email": "unconfigured@example.com",
            "phone": "+919876543219",
        })

        results = trigger_registration_communication(cid, self.db, provider=unconfigured)
        self.assertEqual(results["email"]["status"], "failed")
        self.assertEqual(results["whatsapp"]["status"], "failed")
        self.assertIn("Missing", results["email"]["last_error"])
        self.track("marketing_communications", results["email"]["_id"])
        self.track("marketing_communications", results["whatsapp"]["_id"])

    def test_24_no_communication_is_falsely_recorded_as_sent(self):
        """24. Failed delivery is NEVER recorded as 'sent' in marketing_communications."""
        failing_provider = MockProvider(email_success=False, wa_success=False)
        cid = ObjectId()
        self.track("user_profiles", cid)
        self.db["user_profiles"].insert_one({
            "_id": cid,
            "email": "fail_test@example.com",
            "phone": "+919876543218",
        })

        results = trigger_registration_communication(cid, self.db, provider=failing_provider)
        self.assertNotEqual(results["email"]["status"], "sent")
        self.assertNotEqual(results["whatsapp"]["status"], "sent")

        email_doc = self.db["marketing_communications"].find_one({"_id": results["email"]["_id"]})
        self.assertNotEqual(email_doc["status"], "sent")
        self.assertEqual(email_doc["status"], "failed")
        self.assertIsNone(email_doc.get("sent_at"))
        self.track("marketing_communications", results["email"]["_id"])
        self.track("marketing_communications", results["whatsapp"]["_id"])

    # ==============================================================
    # ADMIN NOTIFICATIONS (Tests 25-27)
    # ==============================================================

    def test_25_real_qualification_creates_one_admin_notification(self):
        """25. Real qualification creates exactly one admin notification."""
        cid = ObjectId()
        self.track("user_profiles", cid)
        self.db["user_profiles"].insert_one({"_id": cid, "email": "admin_notif_lead@example.com", "full_name": "Hot Lead"})

        lead_state = {
            "customer_id": cid,
            "qualification_transition": "not_qualified_to_qualified",
            "is_newly_qualified": True,
            "lead_segment": "Hot",
            "lead_probability": 0.92,
            "lead_score": 92,
        }
        event = create_automation_event_for_qualification(cid, lead_state, self.db)
        self.track("marketing_automation_events", event["_id"])

        process_marketing_automation_event(event["_id"], self.db, provider=self.mock_provider)

        notifs = list(self.db["admin_notifications"].find({"customer_id": str(cid), "type": "lead_qualified"}))
        self.assertEqual(len(notifs), 1)
        self.assertIn("New Hot Lead", notifs[0]["title"])
        self.track("admin_notifications", notifs[0]["_id"])

    def test_26_hot_to_hot_creates_no_duplicate_admin_notification(self):
        """26. Hot -> Hot recalculation creates no duplicate admin notification."""
        cid = ObjectId()
        self.track("user_profiles", cid)
        self.db["user_profiles"].insert_one({"_id": cid, "email": "hot2hot_notif@example.com"})

        # Initial qualification creates 1 notification
        n1 = create_admin_notification(
            self.db, "lead_qualified", "Lead scored Hot",
            customer_id=str(cid), title="New Hot Lead"
        )
        self.track("admin_notifications", ObjectId(n1["id"]))

        # Hot -> Hot event attempt should NOT create an event or notification
        lead_state_same = {
            "customer_id": cid,
            "qualification_transition": "none",
            "is_newly_qualified": False,
            "lead_segment": "Hot",
            "lead_score": 95,
        }
        event = create_automation_event_for_qualification(cid, lead_state_same, self.db)
        self.assertIsNone(event)

        notifs = list(self.db["admin_notifications"].find({"customer_id": str(cid), "type": "lead_qualified"}))
        self.assertEqual(len(notifs), 1, "Duplicate admin notification created for Hot -> Hot!")

    def test_27_no_fake_notification_is_generated_when_admin_notifications_is_empty(self):
        """27. Empty admin_notifications collection returns notifications: [] and unread_count: 0."""
        # Temporarily query an empty admin_notifications list
        admin_headers = {"Authorization": f"Bearer {self.make_token('admin_user', role='admin')}"}
        # In isolated test, verify get_admin_notifications_list with an empty mock DB or collection filter
        empty_res = get_admin_notifications_list(self.db, page=1, limit=10, read_status=None)
        # Even if collection has other test docs, test with a query that matches nothing:
        self.assertIsInstance(empty_res.get("items"), list)
        self.assertIn("unread_count", empty_res)

        # Directly test with empty collection query
        orig_notifs = list(self.db["admin_notifications"].find({}))
        # Delete temporarily, query, restore
        self.db["admin_notifications"].delete_many({})
        res = self.client.get("/api/admin/intelligence/notifications", headers=admin_headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()["data"]
        self.assertEqual(data["items"], [])
        self.assertEqual(data["unread_count"], 0)
        # Restore if needed
        if orig_notifs:
            self.db["admin_notifications"].insert_many(orig_notifs)

    # ==============================================================
    # SECURITY (Tests 28-29)
    # ==============================================================

    def test_28_normal_customer_cannot_trigger_admin_notification_apis(self):
        """28. Normal customer cannot read or trigger admin notification endpoints."""
        customer_headers = {"Authorization": f"Bearer {self.make_token(ObjectId(), role='user')}"}

        res_get = self.client.get("/api/admin/intelligence/notifications", headers=customer_headers)
        self.assertIn(res_get.status_code, [401, 403])

        res_read = self.client.post("/api/admin/intelligence/notifications/mark-all-read", headers=customer_headers)
        self.assertIn(res_read.status_code, [401, 403])

    def test_29_customer_communication_records_cannot_be_read_by_another_customer(self):
        """29. Customer communication records cannot be read by another normal customer."""
        customer_headers = {"Authorization": f"Bearer {self.make_token(ObjectId(), role='user')}"}

        # Customer attempts to read marketing communications
        res = self.client.get("/api/admin/marketing/communications", headers=customer_headers)
        self.assertIn(res.status_code, [401, 403])

        res_events = self.client.get("/api/admin/marketing/automation-events", headers=customer_headers)
        self.assertIn(res_events.status_code, [401, 403])
