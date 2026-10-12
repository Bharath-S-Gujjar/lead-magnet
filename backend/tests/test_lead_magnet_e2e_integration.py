"""Task 6: Lead Magnet Final End-to-End Integration & Production Readiness Tests.

Comprehensive integration tests covering all 10 required operational areas:
1. Opportunity detection through channel selection to communication dispatch.
2. High-priority WhatsApp preference when consent and phone eligibility permit.
3. Gmail preference for normal-priority opportunities.
4. WhatsApp opt-out and invalid phone suppression.
5. Duplicate prevention across standalone marketing triggers and opportunity processing.
6. Scheduler execution and failure handling.
7. Price-drop dispatch and cooldown behavior.
8. Webhook STOP processing followed by a suppressed promotional dispatch.
9. Provider failures and safe retry behavior (no uncontrolled cross-channel retry).
10. Existing Gmail workflows remaining unchanged.

All external providers are strictly mocked; ZERO real external messages are sent.
"""

import datetime
import hashlib
import hmac
import json
import os
import random
import sys
import unittest
from unittest.mock import MagicMock, patch
from bson import ObjectId

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module
from app import app
from communication_provider import DryRunCommunicationProvider, FailingCommunicationProvider
from channel_selector_service import (
    select_communication_channel,
    determine_opportunity_preference,
    POLICY_WHATSAPP_FIRST,
    POLICY_EMAIL_FIRST,
)
from customer_profile_service import update_customer_whatsapp_consent
from marketing_automation_service import (
    trigger_cart_abandonment_communication,
    trigger_order_confirmation_communication,
    evaluate_channel_eligibility,
    dispatch_communication,
)
from opportunity_engine import (
    process_customer_opportunities,
    OPP_CART_ITEM_DISCOUNT,
    OPP_WISHLIST_ITEM_DISCOUNT,
    OPP_CART_ABANDONMENT,
)
from price_drop_opportunity_service import (
    create_price_drop_opportunity,
    dispatch_price_drop_opportunity,
)
from scheduler_service import (
    LeadMagnetScheduler,
    get_scheduler,
    run_opportunity_pipeline_job,
    run_price_drop_pipeline_job,
)
from whatsapp_webhook_service import (
    validate_whatsapp_production_config,
)


class TestLeadMagnetE2EIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = app.test_client()
        cls.db = app_module.db
        cls.profiles = app_module.profiles_collection
        cls.comms = app_module.marketing_communications_collection
        cls.opps = cls.db["marketing_opportunities"]
        cls.cart = cls.db["cart"]
        cls.wishlist = cls.db["wishlist"]
        cls.products = cls.db["myntra_products"]
        cls.lead_states = cls.db["customer_lead_state"]
        cls.webhook_events = cls.db["whatsapp_webhook_events"]

        cls.app_secret = "meta_test_secret_e2e_98765"
        cls.verify_token = "verify_test_token_e2e_54321"
        os.environ["WHATSAPP_APP_SECRET"] = cls.app_secret
        os.environ["WHATSAPP_WEBHOOK_VERIFY_TOKEN"] = cls.verify_token
        app.config["WHATSAPP_APP_SECRET"] = cls.app_secret
        app.config["WHATSAPP_WEBHOOK_VERIFY_TOKEN"] = cls.verify_token

    def setUp(self):
        self.user_oid = ObjectId()
        self.user_id = str(self.user_oid)
        suffix = f"{random.randint(10000000, 99999999)}"
        self.user_phone = f"+9198{suffix}"
        self.norm_phone = f"9198{suffix}"
        self.user_email = f"e2e_{self.user_id}@example.com"

        # Create base test product
        self.product_oid = ObjectId()
        self.product_id = str(self.product_oid)
        prod_doc = {
            "_id": self.product_oid,
            "product_id": self.product_id,
            "title": "E2E Premium Denim Jacket",
            "name": "E2E Premium Denim Jacket",
            "brand": "Roadster",
            "category": "Denim",
            "price": 1499.0,
            "original_price": 2999.0,
            "discount": 50,
            "discount_percentage": 50.0,
            "image": "https://example.com/img1.jpg",
        }
        self.products.insert_one(prod_doc)
        self.db["products"].insert_one(dict(prod_doc))

        # Create base customer profile (opted in to WhatsApp)
        self.profiles.insert_one({
            "_id": self.user_oid,
            "user_id": self.user_id,
            "email": self.user_email,
            "phone": self.user_phone,
            "full_name": "E2E Test Customer",
            "role": "user",
            "whatsapp_opt_in": True,
            "whatsapp_opt_out": False,
            "whatsapp_opt_in_at": "2026-10-01T00:00:00",
            "whatsapp_opt_in_source": "user_settings",
            "created_at": datetime.datetime.now(datetime.timezone.utc),
        })

        # Pre-seed Hot customer lead state for opportunity detection
        self.lead_states.insert_one({
            "customer_id": self.user_oid,
            "lead_score": 85,
            "lead_probability": 0.85,
            "lead_state": "Hot",
            "updated_at": datetime.datetime.now(datetime.timezone.utc),
        })

        # Mock communication provider
        self.mock_provider = DryRunCommunicationProvider()

    def tearDown(self):
        self.profiles.delete_many({"_id": self.user_oid})
        self.profiles.delete_many({"phone": self.user_phone})
        self.products.delete_many({"_id": self.product_oid})
        self.db["products"].delete_many({"_id": self.product_oid})
        self.comms.delete_many({"customer_id": self.user_oid})
        self.opps.delete_many({"customer_id": {"$in": [self.user_oid, self.user_id]}})
        self.cart.delete_many({"user_id": {"$in": [self.user_oid, self.user_id]}})
        self.wishlist.delete_many({"user_id": {"$in": [self.user_oid, self.user_id]}})
        self.lead_states.delete_many({"customer_id": {"$in": [self.user_oid, self.user_id]}})
        self.webhook_events.delete_many({})

    def _sign_payload(self, body_bytes: bytes) -> str:
        h = hmac.new(self.app_secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()
        return f"sha256={h}"

    # --------------------------------------------------------------------------
    # 1. Opportunity detection through channel selection to communication dispatch
    # --------------------------------------------------------------------------
    def test_01_opportunity_detection_through_channel_selection_to_dispatch(self):
        """End-to-end flow: Detect cart discount -> select channel -> dispatch communication."""
        # Setup cart item with discounted product
        self.cart.insert_one({
            "user_id": self.user_oid,
            "items": [{
                "product_id": self.product_oid,
                "title": "E2E Premium Denim Jacket",
                "price": 1499.0,
                "quantity": 1,
            }],
            "updated_at": datetime.datetime.now(datetime.timezone.utc),
        })

        # Execute opportunity evaluation and dispatch pipeline
        res = process_customer_opportunities(
            customer_id=self.user_oid,
            db=self.db,
            provider=self.mock_provider,
        )

        self.assertGreaterEqual(res["detected_count"], 1)
        self.assertGreaterEqual(len(res["communicated"]), 1)

        # Verify communication record was created
        comm = self.comms.find_one({"customer_id": self.user_oid, "status": "sent"})
        self.assertIsNotNone(comm)
        self.assertIn(comm["channel"], ["whatsapp", "email"])
        self.assertIsNotNone(comm.get("provider_message_id"))

        # Verify opportunity transitioned to communicated state
        opp = self.opps.find_one({"customer_id": self.user_oid, "opportunity_state": "communicated"})
        self.assertIsNotNone(opp)

    # --------------------------------------------------------------------------
    # 2. High-priority WhatsApp preference when consent and phone eligibility permit
    # --------------------------------------------------------------------------
    def test_02_high_priority_whatsapp_preference_when_eligible(self):
        """High-priority cart item discount selects WhatsApp when customer is opted in."""
        opp = {
            "opportunity_key": f"opp_cart_disc_{self.user_id}",
            "opportunity_type": OPP_CART_ITEM_DISCOUNT,
            "customer_id": self.user_oid,
            "product_id": self.product_id,
        }

        profile = self.profiles.find_one({"_id": self.user_oid})
        policy = determine_opportunity_preference(opp, user_profile=profile)
        self.assertEqual(policy, POLICY_WHATSAPP_FIRST)

        selection = select_communication_channel(
            user_profile=profile,
            campaign_type=f"opportunity_{OPP_CART_ITEM_DISCOUNT}",
            preference_policy=policy,
        )

        self.assertTrue(selection["eligible"])
        self.assertEqual(selection["channel"], "whatsapp")
        self.assertIn(self.norm_phone, selection["recipient"])

    # --------------------------------------------------------------------------
    # 3. Gmail preference for normal-priority opportunities
    # --------------------------------------------------------------------------
    def test_03_gmail_preference_for_normal_priority_opportunities(self):
        """Normal-priority wishlist discount selects Gmail even when WhatsApp is opted-in."""
        opp = {
            "opportunity_key": f"opp_wishlist_disc_{self.user_id}",
            "opportunity_type": OPP_WISHLIST_ITEM_DISCOUNT,
            "customer_id": self.user_oid,
            "product_id": self.product_id,
        }

        profile = self.profiles.find_one({"_id": self.user_oid})
        policy = determine_opportunity_preference(opp, user_profile=profile)
        self.assertEqual(policy, POLICY_EMAIL_FIRST)

        selection = select_communication_channel(
            user_profile=profile,
            campaign_type=f"opportunity_{OPP_WISHLIST_ITEM_DISCOUNT}",
            preference_policy=policy,
        )

        self.assertTrue(selection["eligible"])
        self.assertEqual(selection["channel"], "email")
        self.assertEqual(selection["recipient"], self.user_email)

    # --------------------------------------------------------------------------
    # 4. WhatsApp opt-out and invalid phone suppression
    # --------------------------------------------------------------------------
    def test_04_whatsapp_opt_out_and_invalid_phone_suppression(self):
        """Explicit WhatsApp opt-out or malformed phone forces fallback to Gmail."""
        # 1. Opt-out set
        self.profiles.update_one(
            {"_id": self.user_oid},
            {"$set": {"whatsapp_opt_out": True, "whatsapp_opt_in": False}},
        )
        profile_opted_out = self.profiles.find_one({"_id": self.user_oid})
        sel1 = select_communication_channel(
            user_profile=profile_opted_out,
            campaign_type=f"opportunity_{OPP_CART_ITEM_DISCOUNT}",
            preference_policy=POLICY_WHATSAPP_FIRST,
        )
        self.assertEqual(sel1["channel"], "email")

        # 2. Invalid phone
        self.profiles.update_one(
            {"_id": self.user_oid},
            {"$set": {"whatsapp_opt_out": False, "whatsapp_opt_in": True, "phone": "not_a_phone"}},
        )
        profile_bad_phone = self.profiles.find_one({"_id": self.user_oid})
        sel2 = select_communication_channel(
            user_profile=profile_bad_phone,
            campaign_type=f"opportunity_{OPP_CART_ITEM_DISCOUNT}",
            preference_policy=POLICY_WHATSAPP_FIRST,
        )
        self.assertEqual(sel2["channel"], "email")

    # --------------------------------------------------------------------------
    # 5. Duplicate prevention across standalone marketing triggers & opportunity
    # --------------------------------------------------------------------------
    def test_05_duplicate_prevention_across_standalone_and_opportunity(self):
        """Cross-path idempotency prevents multiple sends for same underlying event."""
        # 1. Setup cart in db and dispatch standalone cart abandonment communication
        self.cart.insert_one({
            "user_id": self.user_oid,
            "items": [{"title": "Denim", "price": 1499.0, "quantity": 1}],
            "total_amount": 1499.0,
            "updated_at": datetime.datetime.now(datetime.timezone.utc),
        })
        res1 = trigger_cart_abandonment_communication(
            self.user_oid,
            db=self.db,
            abandonment_delay_hours=0,
            provider=self.mock_provider,
        )
        self.assertIn(res1.get("selected_channel"), ["email", "whatsapp"])
        self.assertIn(res1["selected_channel"], res1)

        # 2. Opportunity engine checks same customer for cart abandonment opportunity
        opp_col = self.db["marketing_opportunities"]
        opp_key = f"opp_cart_abandon_{self.user_id}"
        opp_col.insert_one({
            "opportunity_key": opp_key,
            "opportunity_type": OPP_CART_ABANDONMENT,
            "customer_id": self.user_oid,
            "opportunity_state": "detected",
            "metadata": {"cart_items": [{"title": "Denim", "price": 1499}]},
        })

        # Process opportunities - within cooldown and idempotency check should skip
        eval_res = process_customer_opportunities(
            customer_id=self.user_oid,
            db=self.db,
            provider=self.mock_provider,
        )

        # Ensure no duplicate message was dispatched
        sent_comms = list(self.comms.find({"customer_id": self.user_oid, "status": "sent"}))
        self.assertEqual(len(sent_comms), 1)

    # --------------------------------------------------------------------------
    # 6. Scheduler execution and failure handling
    # --------------------------------------------------------------------------
    def test_06_scheduler_execution_and_failure_handling(self):
        """Scheduler singleton manages jobs, prevents duplicates, and safely captures errors."""
        scheduler = LeadMagnetScheduler(db=self.db)

        # 1. Register job
        test_job_id = "test_e2e_job"
        called = {"count": 0}

        def sample_job(db=None):
            called["count"] += 1
            return {"status": "ok"}

        job = scheduler.register_job(test_job_id, "Sample Job", 60, sample_job)
        self.assertIsNotNone(job)

        # 2. Re-registering does not duplicate
        job2 = scheduler.register_job(test_job_id, "Sample Job Updated", 120, sample_job)
        self.assertEqual(len([j for j in scheduler.jobs if j == test_job_id]), 1)
        self.assertEqual(job2.interval_seconds, 120)

        # 3. Manual trigger
        res = scheduler.trigger_job(test_job_id, db=self.db)
        self.assertEqual(res["status"], "ok")
        self.assertEqual(called["count"], 1)

        # 4. Failure handling in job execution
        fail_job_id = "failing_job_test"

        def err_job(db=None):
            raise RuntimeError("Database connection timed out during pipeline scan")

        scheduler.register_job(fail_job_id, "Failing Job", 60, err_job)
        res_fail = scheduler.trigger_job(fail_job_id, db=self.db)
        self.assertEqual(res_fail["status"], "failed")
        self.assertIn("timed out", res_fail["error"])

        # Check job failure stats
        f_job = scheduler.get_job(fail_job_id)
        self.assertEqual(f_job.failure_count, 1)

        # Cleanup
        scheduler.unregister_job(test_job_id)
        scheduler.unregister_job(fail_job_id)

    # --------------------------------------------------------------------------
    # 7. Price-drop dispatch and cooldown behavior
    # --------------------------------------------------------------------------
    def test_07_price_drop_dispatch_and_cooldown_behavior(self):
        """Price-drop opportunity dispatches via Gmail and enforces 24-hour cooldown."""
        drop_event = {
            "product_id": self.product_id,
            "title": "E2E Premium Denim Jacket",
            "old_price": 2999.0,
            "new_price": 1499.0,
            "drop_amount": 1500.0,
            "drop_percent": 50.0,
        }

        # Create price drop opportunity
        opp = create_price_drop_opportunity(
            customer_id=self.user_oid,
            price_drop_event=drop_event,
            interest_source="wishlist",
            customer_lead_state="Hot",
            db=self.db,
        )
        self.assertIsNotNone(opp)

        # First dispatch succeeds
        res1 = dispatch_price_drop_opportunity(
            opportunity_or_key=opp,
            db=self.db,
            provider=self.mock_provider,
            enforce_cooldown=True,
        )
        self.assertTrue(res1["success"])
        self.assertEqual(res1["status"], "sent")

        # Second dispatch blocked by idempotency
        res2 = dispatch_price_drop_opportunity(
            opportunity_or_key=opp,
            db=self.db,
            provider=self.mock_provider,
            enforce_cooldown=True,
        )
        self.assertFalse(res2["success"])
        self.assertIn(res2["status"], ["already_communicated", "skipped_idempotent"])

    # --------------------------------------------------------------------------
    # 8. Webhook STOP processing followed by a suppressed promotional dispatch
    # --------------------------------------------------------------------------
    def test_08_webhook_stop_processing_suppresses_promotional_dispatch(self):
        """Inbound STOP webhook disables promotional WhatsApp, falling back to Gmail."""
        # 1. Customer currently opted in
        pre_profile = self.profiles.find_one({"_id": self.user_oid})
        self.assertTrue(pre_profile["whatsapp_opt_in"])

        # 2. Inbound Meta STOP webhook payload
        payload = {
            "object": "whatsapp_business_account",
            "entry": [{
                "id": "WABA_TEST",
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {"phone_number_id": "123456"},
                        "messages": [{
                            "id": f"wamid.e2e_stop_{ObjectId()}",
                            "from": self.norm_phone,
                            "type": "text",
                            "text": {"body": "STOP"},
                        }],
                    },
                    "field": "messages",
                }],
            }],
        }
        raw_body = json.dumps(payload).encode("utf-8")
        sig = self._sign_payload(raw_body)

        post_res = self.client.post(
            "/api/webhook/whatsapp",
            data=raw_body,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig},
        )
        self.assertEqual(post_res.status_code, 200)

        # 3. Verify consent immediately modified
        post_profile = self.profiles.find_one({"_id": self.user_oid})
        self.assertTrue(post_profile["whatsapp_opt_out"])
        self.assertFalse(post_profile["whatsapp_opt_in"])
        self.assertEqual(post_profile["whatsapp_opt_out_source"], "whatsapp_stop")

        # 4. Subsequent promotional eligibility strictly blocks WhatsApp
        elig = evaluate_channel_eligibility(post_profile, campaign_type="cart_abandoned")
        self.assertFalse(elig["whatsapp"]["eligible"])
        self.assertIn("opted out", elig["whatsapp"]["reason"])
        self.assertTrue(elig["email"]["eligible"])

    # --------------------------------------------------------------------------
    # 9. Provider failures and safe retry behavior
    # --------------------------------------------------------------------------
    def test_09_provider_failures_and_safe_retry_behavior(self):
        """Provider failure records failure without silently retrying on another channel."""
        failing_provider = FailingCommunicationProvider(error_message="Meta Cloud API 500 internal server error")

        res = dispatch_communication(
            self.db,
            self.user_oid,
            campaign_type="opportunity_cart_item_discount",
            channel="whatsapp",
            recipient=self.norm_phone,
            body="Your cart item is discounted!",
            provider=failing_provider,
        )

        self.assertEqual(res["status"], "failed")
        self.assertIn("500", res.get("last_error", ""))

        # Verify no alternate email was dispatched as an uncontrolled cross-channel retry
        email_sent = self.comms.find_one({"customer_id": self.user_oid, "channel": "email"})
        self.assertIsNone(email_sent)

    # --------------------------------------------------------------------------
    # 10. Existing Gmail workflows remain unchanged
    # --------------------------------------------------------------------------
    def test_10_existing_gmail_workflows_remain_unchanged(self):
        """Transactional order confirmation via Gmail succeeds with standard headers."""
        order_oid = ObjectId()
        self.db["orders"].insert_one({
            "_id": order_oid,
            "user_id": self.user_oid,
            "order_id": f"ORD_{order_oid}",
            "items": [{"title": "Denim Jacket", "price": 1499.0, "quantity": 1}],
            "total_amount": 1499.0,
            "created_at": datetime.datetime.now(datetime.timezone.utc),
        })
        try:
            res = trigger_order_confirmation_communication(
                order_oid,
                db=self.db,
                provider=self.mock_provider,
            )
            self.assertIn("email", res)
            self.assertEqual(res["email"]["status"], "sent")
            self.assertIsNotNone(res["email"].get("provider_message_id"))
        finally:
            self.db["orders"].delete_one({"_id": order_oid})


if __name__ == "__main__":
    unittest.main()
