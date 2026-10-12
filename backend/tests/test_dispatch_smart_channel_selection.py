"""Focused tests for Smart Channel Selection in Communication Dispatch Pipeline.

Validates all 12 Task 3 requirements:
1. High-priority promotional opportunity selects WhatsApp for an eligible, opted-in customer.
2. The same opportunity selects Gmail when WhatsApp consent is missing.
3. WhatsApp opt-out forces Gmail fallback when Gmail is eligible.
4. Invalid or missing WhatsApp phone number forces Gmail fallback.
5. Lower-priority promotional flows prefer Gmail when eligible.
6. Transactional flows follow existing transactional eligibility rules.
7. No eligible channel produces the correct existing no-channel outcome.
8. Only one channel is dispatched for one opportunity.
9. A provider failure does not automatically dispatch the same opportunity through another channel.
10. Idempotency prevents duplicate dispatch on repeated processing.
11. Existing Gmail-only behavior remains unchanged.
12. Existing cooldown, opportunity state, and communication persistence behavior remain correct.
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
    trigger_registration_communication,
    trigger_order_confirmation_communication,
    trigger_lead_qualification_communication,
    evaluate_channel_eligibility,
    dispatch_communication,
)
from opportunity_engine import (
    OPP_CART_ITEM_DISCOUNT,
    OPP_WISHLIST_ITEM_DISCOUNT,
    OPP_SIMILAR_PRODUCT_DISCOUNT,
    OPP_HOT_TO_WARM_REENGAGEMENT,
    OPP_CART_ABANDONMENT,
    OPP_WISHLIST_INACTIVITY,
    OPP_PRODUCT_PRICE_DROP,
    OPPORTUNITY_COOLDOWN_HOURS,
    ensure_marketing_opportunities_indexes,
    process_customer_opportunities,
    _is_within_opportunity_cooldown,
)
from price_drop_opportunity_service import (
    create_price_drop_opportunity,
    dispatch_price_drop_opportunity,
)
from channel_selector_service import (
    select_communication_channel,
    determine_opportunity_preference,
    is_high_priority_opportunity,
    HIGH_PRIORITY_PROMOTIONAL_TYPES,
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


class SmartChannelDispatchTests(unittest.TestCase):
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
    # 1. High-priority promotional selects WhatsApp for eligible, opted-in customer
    # --------------------------------------------------------------------------
    def test_01_high_priority_promotional_selects_whatsapp_when_opted_in(self):
        """1. High-priority promotional opportunities prefer WhatsApp when customer is opted in."""
        cid = ObjectId()
        self.track("user_profiles", cid)
        self.db["user_profiles"].insert_one({
            "_id": cid,
            "email": "opted_in@example.com",
            "phone": "+919876543210",
            "full_name": "Priya Sharma",
            "whatsapp_opt_in": True,
            "whatsapp_opt_out": False,
        })

        opp_key = f"opp:{str(cid)}:cart_disc:prod_1"
        opp_doc = {
            "customer_id": cid,
            "opportunity_type": OPP_CART_ITEM_DISCOUNT,
            "opportunity_key": opp_key,
            "product_id": "prod_1",
            "product_name": "Silk Saree",
            "opportunity_state": "detected",
            "metadata": {
                "product_name": "Silk Saree",
                "discount_percent": 25,
                "current_price": 2499.0,
            },
        }
        self.db["marketing_opportunities"].insert_one(opp_doc)
        self.track("marketing_opportunities", opp_doc["_id"])

        lead_state = {
            "customer_id": cid,
            "lead_segment": "Hot",
            "lead_probability": 0.85,
            "lead_score": 85,
        }
        self.db["customer_lead_state"].insert_one(lead_state)
        self.track("customer_lead_state", lead_state["_id"])

        res = process_customer_opportunities(
            customer_id=cid,
            db=self.db,
            provider=self.provider,
            lead_state_doc=lead_state,
            current_time=self.now,
        )

        self.assertEqual(len(res["communicated"]), 1)
        self.assertEqual(res["communicated"][0]["channel"], "whatsapp")
        self.assertEqual(len(self.provider.whatsapp_sent), 1)
        self.assertEqual(len(self.provider.emails_sent), 0)
        self.assertEqual(self.provider.whatsapp_sent[0]["recipient"], "+919876543210")
        self.assertIn("Silk Saree", self.provider.whatsapp_sent[0]["body"])

        # Check DB opportunity record
        saved_opp = self.db["marketing_opportunities"].find_one({"opportunity_key": opp_key})
        self.assertEqual(saved_opp["opportunity_state"], "communicated")
        self.assertEqual(saved_opp["channel"], "whatsapp")

    # --------------------------------------------------------------------------
    # 2. High-priority promotional falls back to Gmail when consent missing
    # --------------------------------------------------------------------------
    def test_02_high_priority_promotional_selects_gmail_when_consent_missing(self):
        """2. Same high-priority opportunity falls back to Gmail when WhatsApp consent is missing."""
        cid = ObjectId()
        self.track("user_profiles", cid)
        self.db["user_profiles"].insert_one({
            "_id": cid,
            "email": "no_consent@example.com",
            "phone": "+919876543210",
            "full_name": "Rohan Verma",
            "whatsapp_opt_in": False,  # Missing / default false consent
            "whatsapp_opt_out": False,
        })

        opp_key = f"opp:{str(cid)}:cart_disc:prod_2"
        opp_doc = {
            "customer_id": cid,
            "opportunity_type": OPP_CART_ITEM_DISCOUNT,
            "opportunity_key": opp_key,
            "product_id": "prod_2",
            "product_name": "Denim Jacket",
            "opportunity_state": "detected",
            "metadata": {
                "product_name": "Denim Jacket",
                "discount_percent": 15,
                "current_price": 1899.0,
            },
        }
        self.db["marketing_opportunities"].insert_one(opp_doc)
        self.track("marketing_opportunities", opp_doc["_id"])

        lead_state = {
            "customer_id": cid,
            "lead_segment": "Hot",
            "lead_probability": 0.82,
            "lead_score": 82,
        }
        self.db["customer_lead_state"].insert_one(lead_state)
        self.track("customer_lead_state", lead_state["_id"])

        res = process_customer_opportunities(
            customer_id=cid,
            db=self.db,
            provider=self.provider,
            lead_state_doc=lead_state,
            current_time=self.now,
        )

        self.assertEqual(len(res["communicated"]), 1)
        self.assertEqual(res["communicated"][0]["channel"], "email")
        self.assertEqual(len(self.provider.emails_sent), 1)
        self.assertEqual(len(self.provider.whatsapp_sent), 0)
        self.assertEqual(self.provider.emails_sent[0]["recipient"], "no_consent@example.com")
        self.assertIn("Denim Jacket", self.provider.emails_sent[0]["body"])

    # --------------------------------------------------------------------------
    # 3. WhatsApp opt-out forces Gmail fallback
    # --------------------------------------------------------------------------
    def test_03_whatsapp_opt_out_forces_gmail_fallback(self):
        """3. Explicit WhatsApp opt-out strictly overrides opt-in and falls back to Gmail."""
        cid = ObjectId()
        self.track("user_profiles", cid)
        self.db["user_profiles"].insert_one({
            "_id": cid,
            "email": "opted_out@example.com",
            "phone": "+919876543210",
            "full_name": "Aman Patel",
            "whatsapp_opt_in": True,
            "whatsapp_opt_out": True,  # Opted out overrides opt-in!
        })

        opp_key = f"opp:{str(cid)}:cart_abandon:cart_1"
        opp_doc = {
            "customer_id": cid,
            "opportunity_type": OPP_CART_ABANDONMENT,
            "opportunity_key": opp_key,
            "product_id": None,
            "opportunity_state": "detected",
            "metadata": {},
        }
        self.db["marketing_opportunities"].insert_one(opp_doc)
        self.track("marketing_opportunities", opp_doc["_id"])

        lead_state = {
            "customer_id": cid,
            "lead_segment": "Hot",
            "lead_probability": 0.77,
            "lead_score": 77,
        }
        self.db["customer_lead_state"].insert_one(lead_state)
        self.track("customer_lead_state", lead_state["_id"])

        res = process_customer_opportunities(
            customer_id=cid,
            db=self.db,
            provider=self.provider,
            lead_state_doc=lead_state,
            current_time=self.now,
        )

        self.assertEqual(len(res["communicated"]), 1)
        self.assertEqual(res["communicated"][0]["channel"], "email")
        self.assertEqual(len(self.provider.emails_sent), 1)
        self.assertEqual(len(self.provider.whatsapp_sent), 0)
        self.assertEqual(self.provider.emails_sent[0]["recipient"], "opted_out@example.com")

    # --------------------------------------------------------------------------
    # 4. Invalid or missing WhatsApp phone forces Gmail fallback
    # --------------------------------------------------------------------------
    def test_04_invalid_or_missing_phone_forces_gmail_fallback(self):
        """4. Invalid or missing phone number forces Gmail fallback for high-priority flow."""
        # Case A: Missing phone
        cid_a = ObjectId()
        self.track("user_profiles", cid_a)
        self.db["user_profiles"].insert_one({
            "_id": cid_a,
            "email": "no_phone@example.com",
            "phone": None,
            "whatsapp_opt_in": True,
        })
        pref_a = determine_opportunity_preference(OPP_CART_ITEM_DISCOUNT, user_profile={"email": "no_phone@example.com"})
        sel_a = select_communication_channel(
            user_profile={"email": "no_phone@example.com", "phone": None, "whatsapp_opt_in": True},
            campaign_type="opportunity_cart_item_discount",
            classification="promotional",
            preference_policy=pref_a,
        )
        self.assertTrue(sel_a["eligible"])
        self.assertEqual(sel_a["channel"], "email")
        self.assertEqual(sel_a["fallback_applied"], True)

        # Case B: Invalid phone number (<8 digits)
        cid_b = ObjectId()
        self.track("user_profiles", cid_b)
        self.db["user_profiles"].insert_one({
            "_id": cid_b,
            "email": "bad_phone@example.com",
            "phone": "+123",  # invalid
            "whatsapp_opt_in": True,
        })
        pref_b = determine_opportunity_preference(OPP_PRODUCT_PRICE_DROP, user_profile={"email": "bad_phone@example.com"})
        sel_b = select_communication_channel(
            user_profile={"email": "bad_phone@example.com", "phone": "+123", "whatsapp_opt_in": True},
            campaign_type="product_price_drop",
            classification="promotional",
            preference_policy=pref_b,
        )
        self.assertTrue(sel_b["eligible"])
        self.assertEqual(sel_b["channel"], "email")
        self.assertEqual(sel_b["fallback_applied"], True)

    # --------------------------------------------------------------------------
    # 5. Lower-priority promotional flows prefer Gmail when eligible
    # --------------------------------------------------------------------------
    def test_05_lower_priority_promotional_flows_prefer_gmail(self):
        """5. Lower-priority promotional flows (wishlist discount, similar product, etc.) prefer Gmail."""
        cid = ObjectId()
        self.track("user_profiles", cid)
        profile = {
            "_id": cid,
            "email": "fashion_lover@example.com",
            "phone": "+919876543210",
            "full_name": "Maya Singh",
            "whatsapp_opt_in": True,
            "whatsapp_opt_out": False,
        }
        self.db["user_profiles"].insert_one(profile)

        # Verify classifications in channel_selector_service
        self.assertFalse(is_high_priority_opportunity(OPP_WISHLIST_ITEM_DISCOUNT))
        self.assertFalse(is_high_priority_opportunity(OPP_SIMILAR_PRODUCT_DISCOUNT))
        self.assertFalse(is_high_priority_opportunity(OPP_HOT_TO_WARM_REENGAGEMENT))
        self.assertFalse(is_high_priority_opportunity(OPP_WISHLIST_INACTIVITY))

        # Test wishlist item discount opportunity
        opp_key = f"opp:{str(cid)}:wish_disc:prod_w1"
        opp_doc = {
            "customer_id": cid,
            "opportunity_type": OPP_WISHLIST_ITEM_DISCOUNT,
            "opportunity_key": opp_key,
            "product_id": "prod_w1",
            "product_name": "Summer Floral Dress",
            "opportunity_state": "detected",
            "metadata": {
                "product_name": "Summer Floral Dress",
                "discount_percent": 20,
                "current_price": 1599.0,
            },
        }
        self.db["marketing_opportunities"].insert_one(opp_doc)
        self.track("marketing_opportunities", opp_doc["_id"])

        lead_state = {
            "customer_id": cid,
            "lead_segment": "Hot",
            "lead_probability": 0.80,
            "lead_score": 80,
        }
        self.db["customer_lead_state"].insert_one(lead_state)
        self.track("customer_lead_state", lead_state["_id"])

        res = process_customer_opportunities(
            customer_id=cid,
            db=self.db,
            provider=self.provider,
            lead_state_doc=lead_state,
            current_time=self.now,
        )

        self.assertEqual(len(res["communicated"]), 1)
        self.assertEqual(res["communicated"][0]["channel"], "email")
        self.assertEqual(len(self.provider.emails_sent), 1)
        self.assertEqual(len(self.provider.whatsapp_sent), 0)
        self.assertEqual(self.provider.emails_sent[0]["recipient"], "fashion_lover@example.com")

    # --------------------------------------------------------------------------
    # 6. Transactional flows follow existing transactional eligibility rules
    # --------------------------------------------------------------------------
    def test_06_transactional_flows_follow_transactional_eligibility(self):
        """6. Transactional flows do not require promotional opt-in, but obey opt-out."""
        # Case A: User without promotional opt-in still receives transactional WhatsApp when phone is valid
        cid_tx = ObjectId()
        self.track("user_profiles", cid_tx)
        self.db["user_profiles"].insert_one({
            "_id": cid_tx,
            "email": "tx_buyer@example.com",
            "phone": "+919876543210",
            "whatsapp_opt_in": False,  # No promotional consent
            "whatsapp_opt_out": False,
        })

        order_id = ObjectId()
        self.track("orders", order_id)
        self.db["orders"].insert_one({
            "_id": order_id,
            "user_id": cid_tx,
            "items": [{"name": "Classic Oxford Shirt", "quantity": 1, "price": 1499.0}],
            "total_amount": 1499.0,
            "status": "placed",
            "created_at": datetime.now(timezone.utc),
        })

        res_order = trigger_order_confirmation_communication(order_id, self.db, provider=self.provider)
        self.assertEqual(res_order["email"]["status"], "sent")
        self.assertEqual(res_order["whatsapp"]["status"], "sent")

        # Case B: Opt-out blocks transactional WhatsApp
        cid_optout = ObjectId()
        self.track("user_profiles", cid_optout)
        self.db["user_profiles"].insert_one({
            "_id": cid_optout,
            "email": "tx_optout@example.com",
            "phone": "+919876543210",
            "whatsapp_opt_out": True,
        })
        order_id_2 = ObjectId()
        self.track("orders", order_id_2)
        self.db["orders"].insert_one({
            "_id": order_id_2,
            "user_id": cid_optout,
            "items": [{"name": "Slim Chinos", "quantity": 1, "price": 1999.0}],
            "total_amount": 1999.0,
            "status": "placed",
            "created_at": datetime.now(timezone.utc),
        })

        res_order_2 = trigger_order_confirmation_communication(order_id_2, self.db, provider=self.provider)
        self.assertEqual(res_order_2["email"]["status"], "sent")
        self.assertEqual(res_order_2["whatsapp"]["status"], "skipped")

    # --------------------------------------------------------------------------
    # 7. No eligible channel produces clear no-channel outcome
    # --------------------------------------------------------------------------
    def test_07_no_eligible_channel_produces_clear_no_channel_outcome(self):
        """7. When customer has neither valid email nor eligible phone, selection returns clear no-channel result."""
        cid = ObjectId()
        self.track("user_profiles", cid)
        profile = {
            "_id": cid,
            "email": None,
            "phone": None,
        }
        self.db["user_profiles"].insert_one(profile)

        sel = select_communication_channel(
            user_profile=profile,
            campaign_type="opportunity_cart_item_discount",
            classification="promotional",
        )
        self.assertFalse(sel["eligible"])
        self.assertIsNone(sel["channel"])
        self.assertIn("No eligible channel available", sel["reason"])

        # Also verify opportunity processing records skipped status
        opp_key = f"opp:{str(cid)}:no_chan:1"
        opp_doc = {
            "customer_id": cid,
            "opportunity_type": OPP_CART_ITEM_DISCOUNT,
            "opportunity_key": opp_key,
            "product_id": "prod_x",
            "opportunity_state": "detected",
            "metadata": {"discount_percent": 10, "current_price": 500},
        }
        self.db["marketing_opportunities"].insert_one(opp_doc)
        self.track("marketing_opportunities", opp_doc["_id"])

        lead_state = {
            "customer_id": cid,
            "lead_segment": "Hot",
            "lead_probability": 0.75,
            "lead_score": 75,
        }
        self.db["customer_lead_state"].insert_one(lead_state)
        self.track("customer_lead_state", lead_state["_id"])

        res = process_customer_opportunities(
            customer_id=cid,
            db=self.db,
            provider=self.provider,
            lead_state_doc=lead_state,
            current_time=self.now,
        )
        self.assertEqual(len(res["communicated"]), 0)
        self.assertEqual(len(res["skipped"]), 1)
        self.assertEqual(res["skipped"][0]["opportunity_key"], opp_key)
        self.assertEqual(len(self.provider.emails_sent), 0)
        self.assertEqual(len(self.provider.whatsapp_sent), 0)

    # --------------------------------------------------------------------------
    # 8. Only one channel is dispatched for one opportunity
    # --------------------------------------------------------------------------
    def test_08_only_one_channel_dispatched_per_opportunity(self):
        """8. Smart selection never blindly dispatches both channels for a single opportunity."""
        cid = ObjectId()
        self.track("user_profiles", cid)
        self.db["user_profiles"].insert_one({
            "_id": cid,
            "email": "both_eligible@example.com",
            "phone": "+919876543210",
            "whatsapp_opt_in": True,
            "whatsapp_opt_out": False,
        })

        opp_key = f"opp:{str(cid)}:single_channel:1"
        opp_doc = {
            "customer_id": cid,
            "opportunity_type": OPP_PRODUCT_PRICE_DROP,
            "opportunity_key": opp_key,
            "product_id": "prod_single",
            "product_name": "Linen Blazer",
            "opportunity_state": "detected",
            "metadata": {
                "product_title": "Linen Blazer",
                "old_price": 3999.0,
                "new_price": 2999.0,
                "discount_amount": 1000.0,
                "discount_percentage": 25,
            },
        }
        self.db["marketing_opportunities"].insert_one(opp_doc)
        self.track("marketing_opportunities", opp_doc["_id"])

        res = dispatch_price_drop_opportunity(
            opportunity_or_key=opp_doc,
            db=self.db,
            provider=self.provider,
            enforce_cooldown=False,
            current_time=self.now,
        )

        self.assertTrue(res["success"])
        self.assertEqual(res["channel"], "whatsapp")

        # Total dispatches across all channels for this opportunity must be exactly 1
        total_dispatches = len(self.provider.whatsapp_sent) + len(self.provider.emails_sent)
        self.assertEqual(total_dispatches, 1)

        # Database must have exactly 1 communication record for this opportunity
        comms = list(self.db["marketing_communications"].find({"metadata.opportunity_key": opp_key}))
        self.assertEqual(len(comms), 1)
        self.assertEqual(comms[0]["channel"], "whatsapp")

    # --------------------------------------------------------------------------
    # 9. Provider failure does not automatically dispatch through another channel
    # --------------------------------------------------------------------------
    def test_09_provider_failure_does_not_silently_retry_other_channel(self):
        """9. An ambiguous provider failure on WhatsApp does NOT trigger secondary Gmail dispatch."""
        cid = ObjectId()
        self.track("user_profiles", cid)
        self.db["user_profiles"].insert_one({
            "_id": cid,
            "email": "safe_failure@example.com",
            "phone": "+919876543210",
            "whatsapp_opt_in": True,
            "whatsapp_opt_out": False,
        })

        opp_key = f"opp:{str(cid)}:fail_safety:1"
        opp_doc = {
            "customer_id": cid,
            "opportunity_type": OPP_PRODUCT_PRICE_DROP,
            "opportunity_key": opp_key,
            "product_id": "prod_fail",
            "opportunity_state": "detected",
            "metadata": {
                "product_title": "Sneakers",
                "old_price": 2499.0,
                "new_price": 1999.0,
            },
        }
        self.db["marketing_opportunities"].insert_one(opp_doc)
        self.track("marketing_opportunities", opp_doc["_id"])

        # Configure provider with failing WhatsApp
        failing_provider = MockTrackingProvider(email_success=True, wa_success=False, wa_error="Meta Cloud API Timeout")

        res = dispatch_price_drop_opportunity(
            opportunity_or_key=opp_doc,
            db=self.db,
            provider=failing_provider,
            enforce_cooldown=False,
            current_time=self.now,
        )

        # Dispatch reported failure
        self.assertFalse(res["success"])
        self.assertEqual(res["status"], "failed")
        self.assertEqual(res["channel"], "whatsapp")

        # CRITICAL SAFETY: Email was NEVER dispatched as a fallback after WhatsApp failed!
        self.assertEqual(len(failing_provider.emails_sent), 0)
        self.assertEqual(len(failing_provider.whatsapp_sent), 1)

        # Opportunity state marked failed, not communicated
        saved_opp = self.db["marketing_opportunities"].find_one({"opportunity_key": opp_key})
        self.assertEqual(saved_opp["opportunity_state"], "failed")

    # --------------------------------------------------------------------------
    # 10. Idempotency prevents duplicate dispatch on repeated processing
    # --------------------------------------------------------------------------
    def test_10_idempotency_prevents_duplicate_dispatch(self):
        """10. Repeated execution for the same opportunity key does not duplicate communication."""
        cid = ObjectId()
        self.track("user_profiles", cid)
        self.db["user_profiles"].insert_one({
            "_id": cid,
            "email": "idem_test@example.com",
            "phone": "+919876543210",
            "whatsapp_opt_in": True,
            "whatsapp_opt_out": False,
        })

        opp_key = f"opp:{str(cid)}:idem:1"
        opp_doc = {
            "customer_id": cid,
            "opportunity_type": OPP_PRODUCT_PRICE_DROP,
            "opportunity_key": opp_key,
            "product_id": "prod_idem",
            "opportunity_state": "detected",
            "metadata": {
                "product_title": "Leather Belt",
                "old_price": 999.0,
                "new_price": 799.0,
            },
        }
        self.db["marketing_opportunities"].insert_one(opp_doc)
        self.track("marketing_opportunities", opp_doc["_id"])

        # First dispatch
        res1 = dispatch_price_drop_opportunity(
            opportunity_or_key=opp_doc,
            db=self.db,
            provider=self.provider,
            enforce_cooldown=False,
            current_time=self.now,
        )
        self.assertTrue(res1["success"])
        self.assertEqual(res1["status"], "sent")
        self.assertEqual(len(self.provider.whatsapp_sent), 1)

        # Second dispatch (immediate retry for same opportunity)
        res2 = dispatch_price_drop_opportunity(
            opportunity_or_key=opp_doc,
            db=self.db,
            provider=self.provider,
            enforce_cooldown=False,
            current_time=self.now,
        )
        self.assertFalse(res2["success"])
        self.assertIn(res2["status"], ["already_communicated", "already_sent"])
        self.assertIn("already", res2["reason"].lower())

        # Total dispatches remain exactly 1 across all channels
        self.assertEqual(len(self.provider.whatsapp_sent), 1)
        self.assertEqual(len(self.provider.emails_sent), 0)

    # --------------------------------------------------------------------------
    # 11. Existing Gmail-only behavior remains unchanged
    # --------------------------------------------------------------------------
    def test_11_existing_gmail_only_behavior_remains_unchanged(self):
        """11. Customers without WhatsApp consent continue to receive standard Gmail notifications."""
        cid = ObjectId()
        self.track("user_profiles", cid)
        self.db["user_profiles"].insert_one({
            "_id": cid,
            "email": "standard_gmail@example.com",
            "full_name": "Standard Customer",
        })

        opp_key = f"opp:{str(cid)}:gmail_standard:1"
        opp_doc = {
            "customer_id": cid,
            "opportunity_type": OPP_PRODUCT_PRICE_DROP,
            "opportunity_key": opp_key,
            "product_id": "prod_std",
            "product_name": "Casual Shoes",
            "opportunity_state": "detected",
            "metadata": {
                "product_title": "Casual Shoes",
                "old_price": 2999.0,
                "new_price": 2499.0,
                "discount_amount": 500.0,
                "discount_percentage": 17,
                "primary_image": "https://images.example.com/shoes.jpg",
            },
        }
        self.db["marketing_opportunities"].insert_one(opp_doc)
        self.track("marketing_opportunities", opp_doc["_id"])

        res = dispatch_price_drop_opportunity(
            opportunity_or_key=opp_doc,
            db=self.db,
            provider=self.provider,
            enforce_cooldown=False,
            current_time=self.now,
        )

        self.assertTrue(res["success"])
        self.assertEqual(res["channel"], "email")
        self.assertEqual(len(self.provider.emails_sent), 1)
        self.assertEqual(self.provider.emails_sent[0]["recipient"], "standard_gmail@example.com")
        self.assertIn("Casual Shoes", self.provider.emails_sent[0]["subject"])
        self.assertIn("Standard Customer", self.provider.emails_sent[0]["body"])

    # --------------------------------------------------------------------------
    # 12. Existing cooldown, opportunity state, and persistence behavior correct
    # --------------------------------------------------------------------------
    def test_12_cooldown_and_opportunity_state_persistence_behavior(self):
        """12. 24-hour opportunity cooldown suppresses subsequent communications across channels."""
        cid = ObjectId()
        self.track("user_profiles", cid)
        self.db["user_profiles"].insert_one({
            "_id": cid,
            "email": "cooldown_test@example.com",
            "phone": "+919876543210",
            "whatsapp_opt_in": True,
            "whatsapp_opt_out": False,
        })

        # Insert a communication record sent 2 hours ago via WhatsApp
        two_hours_ago = (self.now - timedelta(hours=2)).isoformat()
        comm_doc = {
            "customer_id": cid,
            "campaign_type": "opportunity_cart_item_discount",
            "channel": "whatsapp",
            "status": "sent",
            "sent_at": two_hours_ago,
        }
        self.db["marketing_communications"].insert_one(comm_doc)
        self.track("marketing_communications", comm_doc["_id"])

        # Customer is within 24h cooldown
        self.assertTrue(_is_within_opportunity_cooldown(cid, self.db, cooldown_hours=OPPORTUNITY_COOLDOWN_HOURS, current_time=self.now))

        opp_key = f"opp:{str(cid)}:pd_cooldown:1"
        opp_doc = {
            "customer_id": cid,
            "opportunity_type": OPP_PRODUCT_PRICE_DROP,
            "opportunity_key": opp_key,
            "product_id": "prod_cool",
            "opportunity_state": "detected",
            "metadata": {
                "product_title": "Hoodie",
                "old_price": 1999.0,
                "new_price": 1499.0,
            },
        }
        self.db["marketing_opportunities"].insert_one(opp_doc)
        self.track("marketing_opportunities", opp_doc["_id"])

        res = dispatch_price_drop_opportunity(
            opportunity_or_key=opp_doc,
            db=self.db,
            provider=self.provider,
            enforce_cooldown=True,
            current_time=self.now,
        )

        self.assertFalse(res["success"])
        self.assertEqual(res["status"], "cooldown_suppressed")
        self.assertIn("cooldown", res["reason"].lower())
        self.assertEqual(len(self.provider.whatsapp_sent), 0)
        self.assertEqual(len(self.provider.emails_sent), 0)

        # After 25 hours, cooldown is lifted and message can be dispatched
        future_time = self.now + timedelta(hours=25)
        self.assertFalse(_is_within_opportunity_cooldown(cid, self.db, cooldown_hours=OPPORTUNITY_COOLDOWN_HOURS, current_time=future_time))

        res_future = dispatch_price_drop_opportunity(
            opportunity_or_key=opp_doc,
            db=self.db,
            provider=self.provider,
            enforce_cooldown=True,
            current_time=future_time,
        )
        self.assertTrue(res_future["success"])
        self.assertEqual(res_future["status"], "sent")
        self.assertEqual(res_future["channel"], "whatsapp")
        self.assertEqual(len(self.provider.whatsapp_sent), 1)


if __name__ == "__main__":
    unittest.main()
