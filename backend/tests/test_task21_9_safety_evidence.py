"""Task 21.9: Focused Runtime Safety Evidence Audit Tests.

Covers the three audit areas:
1. Test Process Isolation: Proves each test process enforces loopback leadmagnet_test before app import.
2. Dry-Run Provider Enforcement: Traces dispatch paths, asserting zero live provider invocations.
3. Persisted Idempotency Verification: Verifies persisted records, single dispatch, duplicate suppression,
   and cooldown against leadmagnet_test, with complete teardown.
"""

import os
import subprocess
import sys
import unittest
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from bson import ObjectId

# Ensure backend root is on sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from local_test_launcher import (
    configure_local_test_environment,
    assert_local_only_safety,
    verify_database_connection,
    LOCAL_MONGO_URI,
    LOCAL_DATABASE_NAME,
)
from communication_provider import (
    get_communication_provider,
    DryRunCommunicationProvider,
    WhatsAppBusinessProvider,
    GmailSMTPProvider,
)
from verify_real_delivery import run_application_whatsapp_journey
from opportunity_engine import (
    process_customer_opportunities,
    OPP_CART_ITEM_DISCOUNT,
    OPPORTUNITY_COOLDOWN_HOURS,
)


class TestTask21_9SafetyEvidence(unittest.TestCase):
    """Rigorous audit suite providing empirical evidence for the three Task 21.9 audit areas."""

    def setUp(self):
        self.orig_env = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.orig_env)

    # -------------------------------------------------------------------------
    # Area 1: Test Process Isolation
    # -------------------------------------------------------------------------

    def test_01_subprocess_proves_isolation_configured_before_app_import(self):
        """A clean Python subprocess confirms tests._isolation runs before app import and enforces loopback."""
        code = (
            "import os, sys\n"
            "sys.path.insert(0, r'" + backend_dir + "')\n"
            "import tests._isolation\n"
            "tests._isolation.publish_test_environment()\n"
            "assert os.environ.get('TESTING') == '1'\n"
            "assert os.environ.get('LOCAL_ONLY_TESTING') == '1'\n"
            "assert '127.0.0.1' in os.environ.get('MONGO_URI')\n"
            "assert os.environ.get('MONGO_DB_NAME') == 'leadmagnet_test'\n"
            "import app as app_module\n"
            "client = getattr(app_module, 'mongo_client', None)\n"
            "assert client is not None\n"
            "addr = client.address\n"
            "assert addr[0] in ('127.0.0.1', 'localhost')\n"
            "assert addr[1] == 27017\n"
            "print('SUBPROCESS_ISOLATION_OK')\n"
        )
        proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, f"Subprocess stderr: {proc.stderr}")
        self.assertIn("SUBPROCESS_ISOLATION_OK", proc.stdout)

    def test_02_subprocess_proves_remote_uri_fails_closed_before_app_import(self):
        """Subprocess with remote Atlas URI in TEST_MONGO_URI fails closed with RuntimeError before app import."""
        code = (
            "import os, sys\n"
            "sys.path.insert(0, r'" + backend_dir + "')\n"
            "os.environ['TEST_MONGO_URI'] = 'mongodb+srv://admin:pass@cluster.mongodb.net/prod'\n"
            "import tests._isolation\n"
            "tests._isolation.publish_test_environment()\n"
        )
        proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("Refusing to use URI that looks like a remote/Atlas", proc.stderr)

    def test_03_connected_topology_is_strictly_loopback(self):
        """Active test database client connects strictly to loopback 127.0.0.1:27017 with zero remote nodes."""
        configure_local_test_environment()
        client, db = verify_database_connection()

        self.assertEqual(db.name, "leadmagnet_test")
        self.assertIn(client.address[0], ("127.0.0.1", "localhost"))
        self.assertEqual(client.address[1], 27017)

        nodes = getattr(client, "nodes", set())
        for node in nodes:
            self.assertIn(node[0], ("127.0.0.1", "localhost"))
            self.assertEqual(node[1], 27017)
            self.assertNotIn("mongodb.net", node[0].lower())
            self.assertNotIn("atlas", node[0].lower())

    # -------------------------------------------------------------------------
    # Area 2: Dry-Run Provider Enforcement Across Dispatch Paths
    # -------------------------------------------------------------------------

    def test_04_get_communication_provider_enforces_dry_run_during_isolated_testing(self):
        """get_communication_provider returns DryRunCommunicationProvider when isolated testing is active."""
        configure_local_test_environment()
        p = get_communication_provider()
        self.assertIsInstance(p, DryRunCommunicationProvider)
        self.assertEqual(p.send_whatsapp("+919876543210", "test")["provider"], "dry_run")

    def test_05_live_dispatch_safeguards_prevent_unconfirmed_live_sends(self):
        """run_application_whatsapp_journey rejects live dispatch when confirm_real is False."""
        mock_provider = MagicMock()
        success, res = run_application_whatsapp_journey(
            "test_user@example.com",
            confirm_real=False,
            provider=mock_provider,
        )
        self.assertFalse(success)
        self.assertIn("confirmation required", res["error"].lower())
        mock_provider.send_whatsapp.assert_not_called()
        mock_provider.send_email.assert_not_called()

    @patch("communication_provider._requests_lib.post")
    @patch("smtplib.SMTP")
    def test_06_opportunity_engine_in_dry_run_makes_zero_network_calls(self, mock_smtp, mock_post):
        """Executing process_customer_opportunities with dry-run provider makes ZERO SMTP and ZERO HTTP calls."""
        mock_db = MagicMock()
        mock_db["marketing_communications"].find_one.return_value = None
        mock_db["marketing_communications"].insert_one.return_value = MagicMock(inserted_id="comm_1")
        mock_db["marketing_opportunities"].find_one.return_value = None
        mock_db["marketing_opportunities"].update_one.return_value = MagicMock(modified_count=1)

        dry_run = DryRunCommunicationProvider()
        with patch("opportunity_engine.detect_opportunities_for_customer") as mock_detect, \
             patch("opportunity_engine.evaluate_channel_eligibility") as mock_elig, \
             patch("opportunity_engine.select_communication_channel") as mock_chan, \
             patch("opportunity_engine._is_within_opportunity_cooldown", return_value=False):

            mock_detect.return_value = [{
                "_id": "opp_1",
                "opportunity_key": "cart_drop_001",
                "opportunity_type": "cart_item_discount",
                "priority": "high",
                "target_product": {"title": "Test Product", "price": 499},
            }]
            mock_elig.return_value = {"whatsapp": {"eligible": True}}
            mock_chan.return_value = {
                "eligible": True,
                "channel": "whatsapp",
                "recipient": "+919876543210",
                "reason": "WhatsApp Preferred",
            }

            res = process_customer_opportunities(
                customer_id="cust_1",
                db=mock_db,
                provider=dry_run,
            )

        self.assertEqual(len(res["communicated"]), 1)
        # Assert that real network providers were NEVER invoked
        mock_post.assert_not_called()
        mock_smtp.assert_not_called()

    # -------------------------------------------------------------------------
    # Area 3: Persisted Idempotency and Cooldown Lifecycle on leadmagnet_test
    # -------------------------------------------------------------------------

    def test_07_persisted_idempotency_and_cooldown_lifecycle_on_leadmagnet_test(self):
        """Persisted end-to-end lifecycle verification on leadmagnet_test:
        1. Create synthetic customer with promotional consent and valid synthetic phone.
        2. Create 1 high-priority detected opportunity.
        3. Execute dry-run journey -> verifies communication recorded and opportunity communicated.
        4. Re-execute -> verifies second attempt is blocked and communication count remains 1.
        5. Verify customer cooldown against persisted timestamps.
        6. Clean up synthetic records in a finally block.
        """
        configure_local_test_environment()
        client, test_db = verify_database_connection()

        # Unique synthetic identifiers
        unique_suffix = uuid.uuid4().hex[:8]
        synthetic_cust_id = ObjectId()
        synthetic_user_id = f"synthetic_audit_{unique_suffix}"
        synthetic_email = f"audit_{unique_suffix}@synthetic-leadmagnet-test.com"
        synthetic_phone = "+919999988888"  # Reserved synthetic test number
        opp_key = f"opp_cart_drop_{unique_suffix}"

        profiles_col = test_db["user_profiles"]
        opp_col = test_db["marketing_opportunities"]
        comm_col = test_db["marketing_communications"]

        try:
            # 1. Insert synthetic customer profile
            now_iso = datetime.now(timezone.utc).isoformat()
            profiles_col.insert_one({
                "_id": synthetic_cust_id,
                "user_id": synthetic_user_id,
                "email": synthetic_email,
                "phone": synthetic_phone,
                "full_name": f"Synthetic Audit User {unique_suffix}",
                "whatsapp_opt_in": True,
                "whatsapp_promotional_consent": True,
                "whatsapp_opt_out": False,
                "created_at": now_iso,
                "updated_at": now_iso,
            })

            # 2. Insert synthetic opportunity in 'detected' state
            opp_col.insert_one({
                "customer_id": synthetic_cust_id,
                "opportunity_key": opp_key,
                "opportunity_type": OPP_CART_ITEM_DISCOUNT,
                "priority": "high",
                "opportunity_state": "detected",
                "detected_at": now_iso,
                "target_product": {
                    "product_id": f"prod_{unique_suffix}",
                    "title": "Synthetic Wireless Earbuds",
                    "price": 1299,
                    "discount_percent": 20,
                },
            })

            # 3. First execution via dry-run provider
            provider = DryRunCommunicationProvider()
            success_1, res_1 = run_application_whatsapp_journey(
                customer_identifier=str(synthetic_cust_id),
                opportunity_identifier=opp_key,
                confirm_real=True,
                provider=provider,
                db=test_db,
            )

            self.assertTrue(success_1, f"First journey failed: {res_1}")

            # 4. Verify communication is persisted and opportunity state updated
            persisted_comms = list(comm_col.find({
                "customer_id": {"$in": [synthetic_cust_id, str(synthetic_cust_id)]},
                "metadata.opportunity_key": opp_key,
            }))
            self.assertEqual(len(persisted_comms), 1, "Expected exactly 1 persisted communication record.")
            first_comm = persisted_comms[0]
            self.assertEqual(first_comm.get("status"), "sent")
            self.assertEqual(first_comm.get("provider"), "dry_run")
            self.assertEqual(first_comm.get("channel"), "whatsapp")

            updated_opp = opp_col.find_one({"opportunity_key": opp_key})
            self.assertIsNotNone(updated_opp)
            self.assertEqual(updated_opp.get("opportunity_state"), "communicated")
            self.assertIsNotNone(updated_opp.get("communicated_at"))

            # 5. Second execution of the exact same opportunity -> MUST BE BLOCKED
            success_2, res_2 = run_application_whatsapp_journey(
                customer_identifier=str(synthetic_cust_id),
                opportunity_identifier=opp_key,
                confirm_real=True,
                provider=provider,
                db=test_db,
            )

            self.assertFalse(success_2, "Second dispatch of same opportunity must be blocked by idempotency!")
            self.assertIn("not found or not eligible", res_2.get("error", "").lower())

            # 6. Verify communication record count is STILL exactly 1
            persisted_comms_after = list(comm_col.find({
                "customer_id": {"$in": [synthetic_cust_id, str(synthetic_cust_id)]},
                "metadata.opportunity_key": opp_key,
            }))
            self.assertEqual(
                len(persisted_comms_after),
                1,
                "Idempotency violation: duplicate communication record was persisted!"
            )

            # 7. Verify Cooldown enforcement on a newly detected opportunity for the same customer
            opp_key_2 = f"opp_cart_drop_second_{unique_suffix}"
            opp_col.insert_one({
                "customer_id": synthetic_cust_id,
                "opportunity_key": opp_key_2,
                "opportunity_type": OPP_CART_ITEM_DISCOUNT,
                "priority": "high",
                "opportunity_state": "detected",
                "detected_at": datetime.now(timezone.utc).isoformat(),
                "target_product": {
                    "product_id": f"prod_2_{unique_suffix}",
                    "title": "Synthetic Smart Watch",
                    "price": 2499,
                },
            })

            # Attempt dispatch of second opportunity immediately:
            res_pipeline = process_customer_opportunities(
                customer_id=synthetic_cust_id,
                db=test_db,
                provider=provider,
                target_opportunity_key=opp_key_2,
            )

            # Must be skipped due to cooldown
            self.assertEqual(len(res_pipeline.get("communicated", [])), 0)
            skipped_reasons = [s.get("reason", "").lower() for s in res_pipeline.get("skipped", [])]
            self.assertTrue(
                any("cooldown" in r for r in skipped_reasons),
                f"Expected cooldown skip reason, got: {skipped_reasons}"
            )

        finally:
            # 8. Clean up ONLY the synthetic records created in this test
            del_p = profiles_col.delete_many({"_id": synthetic_cust_id})
            del_o = opp_col.delete_many({"customer_id": {"$in": [synthetic_cust_id, str(synthetic_cust_id)]}})
            del_c = comm_col.delete_many({"customer_id": {"$in": [synthetic_cust_id, str(synthetic_cust_id)]}})

            # Verify complete teardown
            rem_p = profiles_col.count_documents({"_id": synthetic_cust_id})
            rem_o = opp_col.count_documents({"customer_id": {"$in": [synthetic_cust_id, str(synthetic_cust_id)]}})
            rem_c = comm_col.count_documents({"customer_id": {"$in": [synthetic_cust_id, str(synthetic_cust_id)]}})

            self.assertEqual(rem_p, 0, "Residual synthetic user_profiles remained after teardown!")
            self.assertEqual(rem_o, 0, "Residual synthetic marketing_opportunities remained after teardown!")
            self.assertEqual(rem_c, 0, "Residual synthetic marketing_communications remained after teardown!")


if __name__ == "__main__":
    unittest.main()
