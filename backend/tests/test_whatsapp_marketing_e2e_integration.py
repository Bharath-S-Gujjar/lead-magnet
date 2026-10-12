"""Task 16: End-to-End WhatsApp Marketing Integration Verification (Dry-Run Only).

Covers complete marketing journey across Scenarios A through F:
- Scenario A: Eligible WhatsApp customer (consent + valid E.164 + high-priority opportunity -> WhatsApp selected & logged, admin activity visible)
- Scenario B: Customer without consent (promotional WhatsApp blocked, fallback to email preserved, zero WhatsApp calls)
- Scenario C: Customer opted out (whatsapp_opt_out=True overrides all flags, zero WhatsApp calls)
- Scenario D: Invalid phone (unnormalized or non-E.164 phone rejected without provider call, falls back to email)
- Scenario E: Idempotency and cooldown (dedup on repeated dispatch, 24h opportunity cooldown enforced)
- Scenario F: Scheduler behavior (dry-run opportunity pipeline, lease locking, duplicate prevention)

Database isolation: Strictly confined to local test database (leadmagnet_test). Zero Atlas calls.
Dry-Run only: All providers mocked or dry-run. Zero real external communications.
"""

import os
import sys
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
from bson import ObjectId

# Ensure backend root is on sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

import app as app_module
from app import (
    app,
    db,
    profiles_collection,
    cart_collection,
    wishlist_collection,
    events_collection,
    JWT_SECRET,
    ADMIN_USERNAME,
    ADMIN_PASSWORD,
)
from opportunity_engine import (
    process_customer_opportunities,
    OPP_CART_ITEM_DISCOUNT,
    OPP_CART_ABANDONMENT,
    OPP_PRODUCT_PRICE_DROP,
)
from channel_selector_service import (
    select_communication_channel,
    POLICY_WHATSAPP_FIRST,
    POLICY_EMAIL_FIRST,
)
from marketing_automation_service import dispatch_communication
from communication_provider import (
    DryRunCommunicationProvider,
    normalize_whatsapp_phone,
)
from scheduler_service import (
    acquire_job_lease,
    renew_job_lease,
    is_job_lease_valid,
    release_job_lease,
    ensure_scheduler_indexes,
    run_opportunity_pipeline_job,
)
from admin_intelligence_service import get_marketing_activity


class TestWhatsAppMarketingE2EIntegration(unittest.TestCase):
    """End-to-end integration test suite for Task 16 WhatsApp marketing journeys."""

    @classmethod
    def setUpClass(cls):
        cls.db = getattr(app_module, "db", None)
        if cls.db is not None:
            ensure_scheduler_indexes(cls.db)

    def setUp(self):
        self.client = app.test_client()
        self.created_customer_ids = []
        self.created_opportunity_keys = []
        self.created_comm_ids = []
        self.created_product_ids = []

        # Collections
        self.opp_col = self.db["marketing_opportunities"]
        self.comm_col = self.db["marketing_communications"]
        self.profiles_col = self.db["user_profiles"]
        self.locks_col = self.db["scheduler_locks"]

        # Ensure scheduler locks collection is clean
        self.locks_col.delete_many({})

    def tearDown(self):
        # Clean up test records created during each test
        if self.created_customer_ids:
            self.profiles_col.delete_many({"_id": {"$in": self.created_customer_ids}})
            self.comm_col.delete_many({"customer_id": {"$in": self.created_customer_ids}})
            self.opp_col.delete_many({"customer_id": {"$in": self.created_customer_ids}})
            self.db["customer_lead_state"].delete_many({"customer_id": {"$in": self.created_customer_ids}})
            cust_str_ids = [str(c) for c in self.created_customer_ids]
            self.db["cart"].delete_many({"$or": [{"user_id": {"$in": cust_str_ids}}, {"user_id": {"$in": self.created_customer_ids}}]})
            self.db["wishlist"].delete_many({"$or": [{"user_id": {"$in": cust_str_ids}}, {"user_id": {"$in": self.created_customer_ids}}]})

        if self.created_product_ids:
            self.db["products"].delete_many({"_id": {"$in": self.created_product_ids}})

        if self.created_opportunity_keys:
            self.opp_col.delete_many({"opportunity_key": {"$in": self.created_opportunity_keys}})
            self.comm_col.delete_many({"metadata.opportunity_key": {"$in": self.created_opportunity_keys}})

        self.locks_col.delete_many({})

    def _get_admin_headers(self):
        """Helper to login as admin and obtain auth header."""
        res = self.client.post("/api/auth/admin/login", json={
            "username": os.environ.get("ADMIN_USERNAME", "test_admin"),
            "password": os.environ.get("ADMIN_PASSWORD", "test_admin_password"),
        })
        self.assertEqual(res.status_code, 200, res.get_json())
        token = res.get_json()["data"]["token"]
        return {"Authorization": f"Bearer {token}"}

    def _create_test_customer(
        self,
        email_prefix="test_wa",
        phone="+919999988888",
        opt_in=True,
        opt_out=False,
        promotional_consent=True,
    ):
        """Create an isolated test fixture customer in user_profiles."""
        cust_id = ObjectId()
        now_iso = datetime.now(timezone.utc).isoformat()
        profile_doc = {
            "_id": cust_id,
            "user_id": str(cust_id),
            "email": f"{email_prefix}_{cust_id}@example.com",
            "full_name": f"Test Customer {cust_id}",
            "phone": phone,
            "whatsapp_opt_in": opt_in,
            "whatsapp_promotional_consent": promotional_consent,
            "whatsapp_opt_out": opt_out,
            "preferred_channel": "whatsapp" if opt_in else "email",
            "created_at": now_iso,
            "updated_at": now_iso,
        }
        self.profiles_col.insert_one(profile_doc)
        self.created_customer_ids.append(cust_id)
        return cust_id, profile_doc

    # =========================================================================
    # Scenario A: Eligible WhatsApp Customer
    # =========================================================================

    def test_scenario_a_eligible_whatsapp_customer_end_to_end(self):
        """Scenario A: Customer with promotional consent and valid E.164 phone receives WhatsApp and appears in admin feed."""
        cust_id, profile = self._create_test_customer(
            email_prefix="scenario_a",
            phone="+919999988888",
            opt_in=True,
            promotional_consent=True,
            opt_out=False,
        )

        # 1. Seed a high-priority marketing opportunity
        product_id = ObjectId()
        opp_key = f"cart_discount:{cust_id}:{product_id}"
        self.created_opportunity_keys.append(opp_key)
        now_iso = datetime.now(timezone.utc).isoformat()

        opp_doc = {
            "opportunity_key": opp_key,
            "customer_id": cust_id,
            "opportunity_type": OPP_CART_ITEM_DISCOUNT,
            "opportunity_state": "detected",
            "product_id": product_id,
            "detected_at": now_iso,
            "metadata": {
                "product_name": "Premium Linen Casual Shirt",
                "primary_image": "https://assets.myntassets.com/test_shirt.jpg",
                "product_url": f"http://localhost:3001/product/{product_id}",
                "old_price": 1999.0,
                "new_price": 1399.0,
                "discount_percent": 30,
            },
        }
        self.opp_col.insert_one(opp_doc)

        # 2. Communication provider: use real DryRunCommunicationProvider wrapped in a spy
        real_dry_run_provider = DryRunCommunicationProvider()
        spy_send_whatsapp = MagicMock(wraps=real_dry_run_provider.send_whatsapp)
        spy_send_email = MagicMock(wraps=real_dry_run_provider.send_email)
        real_dry_run_provider.send_whatsapp = spy_send_whatsapp
        real_dry_run_provider.send_email = spy_send_email

        # 3. Process opportunities for customer
        result = process_customer_opportunities(
            customer_id=cust_id,
            db=self.db,
            provider=real_dry_run_provider,
        )

        # 4. Verify opportunity communication
        self.assertEqual(result["detected_count"], 1)
        self.assertEqual(len(result["communicated"]), 1)
        self.assertEqual(len(result["skipped"]), 0)

        comm_opp = result["communicated"][0]
        self.assertEqual(comm_opp["opportunity_key"], opp_key)
        self.assertEqual(comm_opp["channel"], "whatsapp")
        self.assertEqual(comm_opp["opportunity_state"], "communicated")

        # Verify WhatsApp provider was called with the normalized phone
        spy_send_whatsapp.assert_called_once()
        call_recipient = spy_send_whatsapp.call_args[0][0]
        self.assertEqual(call_recipient, "+919999988888")
        spy_send_email.assert_not_called()

        # 5. Verify communication record in MongoDB
        comm_record = self.comm_col.find_one({"customer_id": cust_id})
        self.assertIsNotNone(comm_record)
        self.assertEqual(comm_record["channel"], "whatsapp")
        self.assertEqual(comm_record["campaign_type"], "opportunity_cart_item_discount")
        self.assertEqual(comm_record["status"], "sent")
        self.assertEqual(comm_record["recipient"], "+919999988888")
        self.assertEqual(comm_record["provider"], "dry_run")
        self.assertTrue(comm_record["provider_message_id"].startswith("dry-run-whatsapp-"))
        self.assertIsNone(comm_record.get("last_error"))

        # 6. Verify Admin Marketing Activity Feed exposes the WhatsApp event
        admin_headers = self._get_admin_headers()
        api_res = self.client.get("/api/admin/intelligence/marketing-activity", headers=admin_headers)
        self.assertEqual(api_res.status_code, 200, api_res.get_json())
        activity_data = api_res.get_json()["data"]
        items = activity_data.get("items", [])

        # Locate our customer's communication
        target_item = next((item for item in items if str(item.get("customer_id")) == str(cust_id)), None)
        self.assertIsNotNone(target_item, "Dispatched WhatsApp communication must be visible in admin marketing activity feed")
        self.assertEqual(target_item["channel"], "whatsapp")
        self.assertEqual(target_item["campaign_type"], "opportunity_cart_item_discount")
        self.assertEqual(target_item["status"], "sent")
        self.assertEqual(target_item["recipient"], "+919999988888")
        self.assertEqual(target_item["provider"], "dry_run")

        # 7. Step 8: Verify repeat attempt does not create duplicate communication
        # 7a. Direct dispatch with same idempotency key returns existing communication
        repeat_comm = dispatch_communication(
            self.db,
            cust_id,
            campaign_type="opportunity_cart_item_discount",
            channel="whatsapp",
            recipient="+919999988888",
            body="Test repeat message",
            idempotency_key=f"{opp_key}:whatsapp",
            provider=real_dry_run_provider,
        )
        self.assertEqual(repeat_comm["status"], "sent")
        self.assertEqual(repeat_comm["_id"], comm_record["_id"], "Repeat dispatch must return existing record")
        self.assertEqual(spy_send_whatsapp.call_count, 1, "Repeat dispatch must not call provider again")

        # 7b. Opportunity engine evaluation confirms 0 new communications
        repeat_result = process_customer_opportunities(
            customer_id=cust_id,
            db=self.db,
            provider=real_dry_run_provider,
        )
        self.assertEqual(len(repeat_result["communicated"]), 0)
        self.assertEqual(spy_send_whatsapp.call_count, 1, "Repeat attempt must not dispatch duplicate WhatsApp message")

        # Confirm exactly one communication record exists in MongoDB
        all_cust_comms = list(self.comm_col.find({"customer_id": cust_id}))
        self.assertEqual(len(all_cust_comms), 1, "Exactly one communication record must exist for this customer fixture")

    # =========================================================================
    # Scenario B: Customer Without Consent
    # =========================================================================

    def test_scenario_b_customer_without_consent_blocks_whatsapp_falls_back_to_email(self):
        """Scenario B: Customer without promotional WhatsApp consent falls back to Gmail; zero WhatsApp calls."""
        cust_id, profile = self._create_test_customer(
            email_prefix="scenario_b",
            phone="+919999988888",
            opt_in=False,
            promotional_consent=False,
            opt_out=False,
        )

        product_id = ObjectId()
        opp_key = f"cart_abandon:{cust_id}:{product_id}"
        self.created_opportunity_keys.append(opp_key)
        now_iso = datetime.now(timezone.utc).isoformat()

        self.opp_col.insert_one({
            "opportunity_key": opp_key,
            "customer_id": cust_id,
            "opportunity_type": OPP_CART_ABANDONMENT,
            "opportunity_state": "detected",
            "product_id": product_id,
            "detected_at": now_iso,
            "metadata": {"old_price": 2499.0, "new_price": 1999.0},
        })

        mock_provider = MagicMock(spec=DryRunCommunicationProvider)
        mock_provider.send_email.return_value = {
            "success": True,
            "provider": "dry_run",
            "provider_message_id": f"dry-run-email-{ObjectId()}",
            "channel": "email",
            "recipient": profile["email"],
            "dispatched_at": now_iso,
        }

        result = process_customer_opportunities(
            customer_id=cust_id,
            db=self.db,
            provider=mock_provider,
        )

        # Communication succeeded via fallback channel (email)
        self.assertEqual(len(result["communicated"]), 1)
        comm_opp = result["communicated"][0]
        self.assertEqual(comm_opp["channel"], "email")

        # Zero WhatsApp provider calls occurred
        mock_provider.send_whatsapp.assert_not_called()
        mock_provider.send_email.assert_called_once()

        # Database record confirms email dispatch
        comm_doc = self.comm_col.find_one({"customer_id": cust_id})
        self.assertEqual(comm_doc["channel"], "email")
        self.assertEqual(comm_doc["status"], "sent")

    # =========================================================================
    # Scenario C: Customer Opted Out
    # =========================================================================

    def test_scenario_c_opt_out_overrides_consent_completely(self):
        """Scenario C: whatsapp_opt_out=True overrides promotional consent even if flags are contradictory."""
        cust_id, profile = self._create_test_customer(
            email_prefix="scenario_c",
            phone="+919999988888",
            opt_in=True,               # Contradictory flag
            promotional_consent=True,  # Contradictory flag
            opt_out=True,              # Explicit opt-out MUST dominate
        )

        product_id = ObjectId()
        opp_key = f"price_drop:{cust_id}:{product_id}"
        self.created_opportunity_keys.append(opp_key)
        now_iso = datetime.now(timezone.utc).isoformat()

        self.opp_col.insert_one({
            "opportunity_key": opp_key,
            "customer_id": cust_id,
            "opportunity_type": OPP_PRODUCT_PRICE_DROP,
            "opportunity_state": "detected",
            "product_id": product_id,
            "detected_at": now_iso,
            "metadata": {"old_price": 2999.0, "new_price": 2199.0},
        })

        mock_provider = MagicMock(spec=DryRunCommunicationProvider)
        mock_provider.send_email.return_value = {
            "success": True,
            "provider": "dry_run",
            "provider_message_id": f"dry-run-email-{ObjectId()}",
            "channel": "email",
            "recipient": profile["email"],
            "dispatched_at": now_iso,
        }

        result = process_customer_opportunities(
            customer_id=cust_id,
            db=self.db,
            provider=mock_provider,
        )

        self.assertEqual(len(result["communicated"]), 1)
        self.assertEqual(result["communicated"][0]["channel"], "email")

        # Strictly zero WhatsApp provider calls
        mock_provider.send_whatsapp.assert_not_called()
        mock_provider.send_email.assert_called_once()

    # =========================================================================
    # Scenario D: Invalid Phone Number
    # =========================================================================

    def test_scenario_d_invalid_phone_rejected_without_whatsapp_provider_call(self):
        """Scenario D: National 10-digit phone lacking country code rejects WhatsApp without attempting provider call."""
        cust_id, profile = self._create_test_customer(
            email_prefix="scenario_d",
            phone="9999988888",  # 10 digits without country code prefix
            opt_in=True,
            promotional_consent=True,
            opt_out=False,
        )

        product_id = ObjectId()
        opp_key = f"cart_discount_badphone:{cust_id}:{product_id}"
        self.created_opportunity_keys.append(opp_key)
        now_iso = datetime.now(timezone.utc).isoformat()

        self.opp_col.insert_one({
            "opportunity_key": opp_key,
            "customer_id": cust_id,
            "opportunity_type": OPP_CART_ITEM_DISCOUNT,
            "opportunity_state": "detected",
            "product_id": product_id,
            "detected_at": now_iso,
            "metadata": {"old_price": 1500.0, "new_price": 1000.0},
        })

        mock_provider = MagicMock(spec=DryRunCommunicationProvider)
        mock_provider.send_email.return_value = {
            "success": True,
            "provider": "dry_run",
            "provider_message_id": f"dry-run-email-{ObjectId()}",
            "channel": "email",
            "recipient": profile["email"],
            "dispatched_at": now_iso,
        }

        result = process_customer_opportunities(
            customer_id=cust_id,
            db=self.db,
            provider=mock_provider,
        )

        self.assertEqual(len(result["communicated"]), 1)
        self.assertEqual(result["communicated"][0]["channel"], "email")

        # WhatsApp provider was never invoked with the unnormalized phone
        mock_provider.send_whatsapp.assert_not_called()
        mock_provider.send_email.assert_called_once()

    # =========================================================================
    # Scenario E: Idempotency and Cooldown
    # =========================================================================

    def test_scenario_e_idempotency_and_cooldown_enforcement(self):
        """Scenario E: Repeated dispatch does not duplicate sends; 24h cooldown blocks subsequent opportunities."""
        cust_id, profile = self._create_test_customer(
            email_prefix="scenario_e",
            phone="+919999988888",
            opt_in=True,
            promotional_consent=True,
            opt_out=False,
        )

        # Establish customer Hot lead state so opportunity engine detects product actions
        self.db["customer_lead_state"].insert_one({
            "customer_id": cust_id,
            "lead_score": 85,
            "lead_probability": 0.85,
            "lead_segment": "Hot",
        })

        product_1 = ObjectId()
        product_2 = ObjectId()
        self.created_product_ids.extend([product_1, product_2])

        self.db["products"].insert_one({
            "_id": product_1,
            "name": "Nike Running Shoes",
            "price": 2000.0,
            "discount": 25,
            "brand": "Nike",
            "category": "Shoes",
        })
        self.db["cart"].insert_one({
            "user_id": str(cust_id),
            "product_id": product_1,
        })

        now_dt = datetime.now(timezone.utc)
        now_iso = now_dt.isoformat()

        mock_provider = MagicMock(spec=DryRunCommunicationProvider)
        mock_provider.send_whatsapp.return_value = {
            "success": True,
            "provider": "dry_run",
            "provider_message_id": f"dry-run-wa-{ObjectId()}",
            "channel": "whatsapp",
            "recipient": "+919999988888",
            "dispatched_at": now_iso,
        }

        # First run: detects cart discount and successfully communicates opp_1 via WhatsApp
        res1 = process_customer_opportunities(
            customer_id=cust_id,
            db=self.db,
            provider=mock_provider,
            current_time=now_dt,
        )
        self.assertEqual(len(res1["communicated"]), 1)
        self.assertEqual(res1["communicated"][0]["channel"], "whatsapp")
        self.assertEqual(mock_provider.send_whatsapp.call_count, 1)

        # 1. Repeat exact same opportunity run -> Idempotency skips it, zero WhatsApp provider calls
        res_repeat = process_customer_opportunities(
            customer_id=cust_id,
            db=self.db,
            provider=mock_provider,
            current_time=now_dt,
            opportunity_cooldown_hours=0,  # even with cooldown 0, opportunity idempotency blocks duplicate!
        )
        self.assertEqual(len(res_repeat["communicated"]), 0)
        self.assertGreaterEqual(len(res_repeat["skipped"]), 1)
        self.assertIn("already communicated", res_repeat["skipped"][0]["reason"].lower())
        self.assertEqual(mock_provider.send_whatsapp.call_count, 1, "Call count must remain 1 (no duplicate send)")

        # 2. Add second product in wishlist for same customer -> Customer cooldown (24h) skips within 6h window
        self.db["products"].insert_one({
            "_id": product_2,
            "name": "Adidas Track Jacket",
            "price": 3000.0,
            "discount": 20,
            "brand": "Adidas",
            "category": "Jackets",
        })
        self.db["wishlist"].insert_one({
            "user_id": str(cust_id),
            "product_id": product_2,
        })

        within_window_dt = now_dt + timedelta(hours=6)
        res_cooldown = process_customer_opportunities(
            customer_id=cust_id,
            db=self.db,
            provider=mock_provider,
            current_time=within_window_dt,
            opportunity_cooldown_hours=24,
        )
        self.assertEqual(len(res_cooldown["communicated"]), 0)
        self.assertGreaterEqual(len(res_cooldown["skipped"]), 1)
        cooldown_skip = next((s for s in res_cooldown["skipped"] if "cooldown" in s["reason"].lower()), None)
        self.assertIsNotNone(cooldown_skip, f"Expected cooldown skip, got: {res_cooldown['skipped']}")
        self.assertEqual(mock_provider.send_whatsapp.call_count, 1, "Call count must remain 1 across cooldown window")

        # 3. After 25 hours (24h cooldown expired) -> Second opportunity communicates cleanly via WhatsApp
        after_cooldown_dt = now_dt + timedelta(hours=25)
        res_after = process_customer_opportunities(
            customer_id=cust_id,
            db=self.db,
            provider=mock_provider,
            current_time=after_cooldown_dt,
            opportunity_cooldown_hours=24,
        )
        self.assertEqual(len(res_after["communicated"]), 1)
        self.assertEqual(res_after["communicated"][0]["channel"], "whatsapp")
        self.assertEqual(mock_provider.send_whatsapp.call_count, 2, "Call count should increment to 2 after cooldown expires")

    # =========================================================================
    # Scenario F: Scheduler Behavior and Lease Safety
    # =========================================================================

    def test_scenario_f_scheduler_lease_fencing_prevents_duplicate_processing(self):
        """Scenario F: Scheduler lease locking enforces owner exclusivity and aborts when lease is lost."""
        cust_id, profile = self._create_test_customer(
            email_prefix="scenario_f",
            phone="+919999988888",
            opt_in=True,
            promotional_consent=True,
            opt_out=False,
        )

        job_id = "test_e2e_opp_pipeline"
        worker_1 = "worker_alpha"
        worker_2 = "worker_beta"

        # 1. Worker 1 acquires lease
        acquired_1 = acquire_job_lease(self.db, job_id, worker_1, lease_seconds=60)
        self.assertTrue(acquired_1)

        # 2. Worker 2 attempts to acquire same active lease -> Fails
        acquired_2 = acquire_job_lease(self.db, job_id, worker_2, lease_seconds=60)
        self.assertFalse(acquired_2)

        # 3. Verify lease checker lambda prevents dispatch when lease ownership is lost
        product_id = ObjectId()
        opp_key = f"lease_test:{cust_id}:{product_id}"
        self.created_opportunity_keys.append(opp_key)
        now_iso = datetime.now(timezone.utc).isoformat()

        self.opp_col.insert_one({
            "opportunity_key": opp_key,
            "customer_id": cust_id,
            "opportunity_type": OPP_CART_ITEM_DISCOUNT,
            "opportunity_state": "detected",
            "product_id": product_id,
            "detected_at": now_iso,
            "metadata": {"old_price": 1000.0, "new_price": 700.0},
        })

        mock_provider = MagicMock(spec=DryRunCommunicationProvider)

        # Simulate Worker 2 attempting to run with an invalid lease checker
        stale_lease_checker = lambda: is_job_lease_valid(self.db, job_id, worker_2)
        res_stale = process_customer_opportunities(
            customer_id=cust_id,
            db=self.db,
            provider=mock_provider,
            lease_checker=stale_lease_checker,
        )

        # Stale worker was safely blocked by lease checker
        self.assertEqual(len(res_stale["communicated"]), 0)
        self.assertEqual(len(res_stale["skipped"]), 1)
        self.assertIn("lease", res_stale["skipped"][0]["reason"].lower())
        mock_provider.send_whatsapp.assert_not_called()

        # 4. Legitimate worker (Worker 1) runs with valid lease checker -> Dispatches cleanly
        valid_lease_checker = lambda: is_job_lease_valid(self.db, job_id, worker_1)
        mock_provider.send_whatsapp.return_value = {
            "success": True,
            "provider": "dry_run",
            "provider_message_id": f"dry-run-wa-{ObjectId()}",
            "channel": "whatsapp",
            "recipient": "+919999988888",
            "dispatched_at": now_iso,
        }

        res_valid = process_customer_opportunities(
            customer_id=cust_id,
            db=self.db,
            provider=mock_provider,
            lease_checker=valid_lease_checker,
        )
        self.assertEqual(len(res_valid["communicated"]), 1)
        mock_provider.send_whatsapp.assert_called_once()

        # 5. Clean release of lease
        released = release_job_lease(self.db, job_id, worker_1)
        self.assertTrue(released)
        self.assertFalse(is_job_lease_valid(self.db, job_id, worker_1))


if __name__ == "__main__":
    unittest.main()
