"""Task 21.3: Isolated WhatsApp Test Fixture Verification.

Verifies:
1. Explicit connection check proving database is strictly localhost:27017 and leadmagnet_test.
2. Synthetic customer fixture with test phone +919999988888 and synthetic promotional consent.
3. Synthetic high-priority opportunity in marketing_opportunities.
4. Dry-run opportunity processing selecting exactly one WhatsApp communication.
5. Idempotency blocking repeated dispatch.
6. Admin intelligence marketing activity visibility.
7. Reliable teardown with verification of zero residual fixture records.

Strict Safety Rules:
- No connection to Atlas or production database.
- No real external messages sent (DryRun provider only).
- Communication provider defaults to dry_run.
"""

import os
import sys
import unittest
from datetime import datetime, timezone
from bson import ObjectId

# Ensure backend root is in sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

import app as app_module
from app import app, db
from communication_provider import DryRunCommunicationProvider
from verify_real_delivery import run_application_whatsapp_journey
from admin_intelligence_service import get_marketing_activity
from opportunity_engine import OPP_CART_ITEM_DISCOUNT


class TestWhatsAppIsolatedFixtureVerification(unittest.TestCase):
    """Isolated test suite for Task 21.3 verifying synthetic WhatsApp workflow."""

    @classmethod
    def setUpClass(cls):
        # 1. Establish strict connection isolation check
        cls.db = getattr(app_module, "db", None)
        if cls.db is None:
            raise RuntimeError("[ISOLATION FAILURE] Database connection is None.")

        # Check DB name
        if cls.db.name != "leadmagnet_test":
            raise RuntimeError(
                f"[ISOLATION FAILURE] Expected database 'leadmagnet_test', got: '{cls.db.name}'"
            )

        # Check MongoDB host and port
        client = cls.db.client
        address = getattr(client, "address", None)
        nodes = getattr(client, "nodes", set())

        # Verify host is localhost / 127.0.0.1
        hosts = [address[0]] if address else [n[0] for n in nodes]
        ports = [address[1]] if address else [n[1] for n in nodes]

        for h in hosts:
            if h not in ("127.0.0.1", "localhost", "::1"):
                raise RuntimeError(
                    f"[ISOLATION FAILURE] Database host '{h}' is not localhost/127.0.0.1. "
                    "Aborting to prevent non-local operations."
                )
        for p in ports:
            if p != 27017:
                raise RuntimeError(
                    f"[ISOLATION FAILURE] Database port '{p}' is not 27017."
                )

        # Confirm environment flags
        if os.environ.get("TESTING") != "1":
            raise RuntimeError("[ISOLATION FAILURE] TESTING environment variable is not '1'.")
        if "mongodb.net" in os.environ.get("MONGO_URI", "").lower():
            raise RuntimeError("[ISOLATION FAILURE] MONGO_URI contains remote Atlas domain.")

    def setUp(self):
        self.client = app.test_client()
        self.created_cust_ids = []
        self.created_opp_keys = []
        self.created_comm_ids = []

        # Collections
        self.profiles_col = self.db["user_profiles"]
        self.opp_col = self.db["marketing_opportunities"]
        self.comm_col = self.db["marketing_communications"]
        self.lead_state_col = self.db["customer_lead_state"]
        self.cart_col = self.db["cart"]

    def tearDown(self):
        residual_errors = []
        # Reliable cleanup
        if self.created_cust_ids:
            res_p = self.profiles_col.delete_many({"_id": {"$in": self.created_cust_ids}})
            res_c = self.comm_col.delete_many({"customer_id": {"$in": self.created_cust_ids}})
            res_o = self.opp_col.delete_many({"customer_id": {"$in": self.created_cust_ids}})
            res_l = self.lead_state_col.delete_many({"customer_id": {"$in": self.created_cust_ids}})
            cust_str_ids = [str(cid) for cid in self.created_cust_ids]
            self.cart_col.delete_many({"$or": [{"user_id": {"$in": cust_str_ids}}, {"user_id": {"$in": self.created_cust_ids}}]})

            # Check residual records
            rem_p = self.profiles_col.count_documents({"_id": {"$in": self.created_cust_ids}})
            if rem_p > 0:
                residual_errors.append(f"Residual user_profiles: {rem_p}")
            rem_o = self.opp_col.count_documents({"customer_id": {"$in": self.created_cust_ids}})
            if rem_o > 0:
                residual_errors.append(f"Residual marketing_opportunities: {rem_o}")

        if residual_errors:
            raise AssertionError(f"Cleanup failed with residual records: {residual_errors}")

    def _get_admin_token(self):
        """Obtain admin authentication token for intelligence feed access."""
        res = self.client.post("/api/auth/admin/login", json={
            "username": os.environ.get("ADMIN_USERNAME", "test_admin"),
            "password": os.environ.get("ADMIN_PASSWORD", "test_admin_password"),
        })
        self.assertEqual(res.status_code, 200, res.get_json())
        return res.get_json()["data"]["token"]

    def test_01_database_connection_isolation_verified(self):
        """Verify that connection is strictly localhost:27017 on leadmagnet_test."""
        self.assertEqual(self.db.name, "leadmagnet_test")
        self.assertIn(self.db.client.address[0], ("127.0.0.1", "localhost"))
        self.assertEqual(self.db.client.address[1], 27017)
        self.assertNotIn("mongodb.net", str(self.db.client.nodes))

    def test_02_synthetic_fixture_lifecycle_dry_run_dispatch_and_idempotency(self):
        """Create synthetic fixture, execute dry-run journey, verify admin feed, and test idempotency."""
        # 1. Create synthetic customer fixture
        cust_id = ObjectId()
        self.created_cust_ids.append(cust_id)
        now_iso = datetime.now(timezone.utc).isoformat()

        synthetic_profile = {
            "_id": cust_id,
            "user_id": str(cust_id),
            "email": f"synthetic_test_{cust_id}@leadmagnet.internal",
            "full_name": "Synthetic Test Recipient",
            "phone": "+919999988888",
            "whatsapp_opt_in": True,
            "whatsapp_promotional_consent": True,
            "whatsapp_opt_out": False,
            "is_synthetic_test_fixture": True,
            "notes": "Dedicated synthetic fixture for Task 21.3 testing. Not real customer consent.",
            "created_at": now_iso,
        }
        self.profiles_col.insert_one(synthetic_profile)

        # 2. Create customer lead state (Hot customer, probability 0.85)
        lead_state_doc = {
            "customer_id": cust_id,
            "lead_score": 85,
            "lead_probability": 0.85,
            "lead_segment": "Hot",
            "updated_at": now_iso,
        }
        self.lead_state_col.insert_one(lead_state_doc)

        # 3. Create synthetic high-priority opportunity in marketing_opportunities
        opp_key = f"opp:{str(cust_id)}:cart_discount:synth_prod_101:25"
        self.created_opp_keys.append(opp_key)

        opp_doc = {
            "customer_id": cust_id,
            "opportunity_type": OPP_CART_ITEM_DISCOUNT,
            "opportunity_key": opp_key,
            "opportunity_state": "detected",
            "product_name": "Synthetic Linen Summer Shirt",
            "metadata": {
                "product_name": "Synthetic Linen Summer Shirt",
                "discount_percent": 25,
                "current_price": 1499.0,
                "original_price": 1999.0,
                "primary_image": "http://localhost:3001/images/shirt.jpg",
            },
            "detected_at": now_iso,
            "communicated_at": None,
        }
        self.opp_col.insert_one(opp_doc)

        # 4. Verify exactly one eligible opportunity exists before dispatch
        pending = list(self.opp_col.find({"customer_id": cust_id, "opportunity_state": "detected"}))
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["opportunity_key"], opp_key)

        # 5. Execute dry-run marketing journey through run_application_whatsapp_journey
        dry_run_provider = DryRunCommunicationProvider()
        success, res = run_application_whatsapp_journey(
            customer_identifier=str(cust_id),
            opportunity_identifier=opp_key,
            confirm_real=True,
            provider=dry_run_provider,
            db=self.db,
        )

        self.assertTrue(success, f"Workflow dispatch failed: {res}")
        self.assertTrue(res["api_accepted"])
        self.assertFalse(res["delivery_confirmed"])
        self.assertIn("API Acceptance", res["delivery_status_note"])

        # Check opportunity updated in marketing_opportunities
        updated_opp = self.opp_col.find_one({"opportunity_key": opp_key})
        self.assertEqual(updated_opp["opportunity_state"], "communicated")
        self.assertEqual(updated_opp["channel"], "whatsapp")

        # Check recorded in marketing_communications
        comm_records = list(self.comm_col.find({"customer_id": cust_id}))
        self.assertEqual(len(comm_records), 1)
        comm = comm_records[0]
        self.assertEqual(comm["status"], "sent")
        self.assertEqual(comm["channel"], "whatsapp")
        self.assertIn(comm["recipient"], ("+919999988888", "919999988888"))
        self.assertEqual(comm["provider"], "dry_run")
        self.assertIn("Linen Summer Shirt", comm["body"])

        # 6. Idempotency test: Repeat dispatch for the exact same customer & opportunity
        repeat_success, repeat_res = run_application_whatsapp_journey(
            customer_identifier=str(cust_id),
            opportunity_identifier=opp_key,
            confirm_real=True,
            provider=dry_run_provider,
            db=self.db,
        )

        # Must be blocked by idempotency (opportunity is already communicated)
        self.assertFalse(repeat_success)
        self.assertIn("not eligible", repeat_res["error"])

        # Verify no duplicate communication record was added
        comm_records_after = list(self.comm_col.find({"customer_id": cust_id}))
        self.assertEqual(len(comm_records_after), 1)

        # 7. Admin Intelligence Visibility: Query admin activity endpoint
        admin_token = self._get_admin_token()
        feed_res = self.client.get(
            "/api/admin/intelligence/marketing-activity?limit=25",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        self.assertEqual(feed_res.status_code, 200)
        feed_data = feed_res.get_json()["data"]
        activities = feed_data.get("items") or feed_data.get("activities", [])

        # Find the activity for our synthetic customer
        matching = [
            a for a in activities
            if a.get("customer_id") == str(cust_id) or a.get("recipient") in ("919999988888", "+919999988888")
        ]
        self.assertGreaterEqual(len(matching), 1, "Dry-run dispatch not found in admin marketing activity feed")
        activity_item = matching[0]
        self.assertEqual(activity_item["channel"], "whatsapp")
        self.assertEqual(activity_item["status"], "sent")
        self.assertEqual(activity_item["provider"], "dry_run")


if __name__ == "__main__":
    unittest.main()
