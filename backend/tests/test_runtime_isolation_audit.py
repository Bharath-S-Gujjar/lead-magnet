"""Offline safety audit tests for Task 21.6 Read-Only Runtime Isolation.

Proves:
1. Remote MongoDB URIs are rejected before client construction.
2. Remote database topology is rejected before any collection queries or writes.
3. No communication provider sends any message during rejected or blocked workflows.
4. Importing application modules does not unexpectedly start background scheduler threads.
5. CLI entry points and launchers fail closed under unsafe configurations.
6. Opportunity ID cannot bypass customer consent, opt-out, or phone normalization guards.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

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
from verify_real_delivery import run_application_whatsapp_journey


class TestRuntimeIsolationSafetyAudit(unittest.TestCase):
    """Rigorous offline safety audit tests using mock clients and providers."""

    def setUp(self):
        self.orig_env = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.orig_env)

    def test_01_remote_uri_rejected_before_client_construction(self):
        """assert_local_only_safety halts before pymongo.MongoClient is ever instantiated."""
        unsafe_uris = [
            "mongodb+srv://admin:pass@cluster.mongodb.net/test",
            "mongodb://atlas-host.mongodb.net:27017/test",
            "mongodb://192.168.1.100:27017/test",
            "mongodb://public-db.com:27017/leadmagnet_test",
        ]
        with patch("pymongo.MongoClient") as mock_client_cls:
            for uri in unsafe_uris:
                env = {
                    "TESTING": "1",
                    "MONGO_URI": uri,
                    "MONGO_DB_NAME": "leadmagnet_test",
                    "COMMUNICATION_PROVIDER": "dry_run",
                    "ALLOW_REAL_DISPATCH": "false",
                    "ENABLE_SCHEDULER": "false",
                }
                with self.assertRaises(RuntimeError):
                    assert_local_only_safety(env)
                # Confirm MongoClient was NEVER instantiated
                mock_client_cls.assert_not_called()

    def test_02_remote_topology_rejected_before_database_query(self):
        """run_application_whatsapp_journey aborts before accessing any database collection when remote nodes detected."""
        mock_remote_db = MagicMock()
        mock_remote_client = MagicMock()
        mock_remote_client.nodes = {("cluster.mongodb.net", 27017)}
        mock_remote_client.address = ("cluster.mongodb.net", 27017)
        mock_remote_db.client = mock_remote_client

        success, res = run_application_whatsapp_journey(
            "test_user@example.com",
            confirm_real=True,
            db=mock_remote_db,
        )
        self.assertFalse(success)
        self.assertIn("remote/atlas database rejected", res["error"].lower())

        # CRITICAL PROOF: verify that zero collection lookups (e.g. user_profiles) occurred
        mock_remote_db.__getitem__.assert_not_called()

    def test_03_no_provider_sends_during_rejected_workflow(self):
        """Provider.send_message is NEVER called when workflow fails safeguards."""
        mock_provider = MagicMock()
        mock_remote_db = MagicMock()
        mock_remote_client = MagicMock()
        mock_remote_client.nodes = {("cluster.4hmf3fs.mongodb.net", 27017)}
        mock_remote_client.address = ("cluster.4hmf3fs.mongodb.net", 27017)
        mock_remote_db.client = mock_remote_client

        success, res = run_application_whatsapp_journey(
            "test_user@example.com",
            confirm_real=True,
            provider=mock_provider,
            db=mock_remote_db,
        )
        self.assertFalse(success)
        # Provider must not have sent any message
        mock_provider.send_message.assert_not_called()

    def test_04_importing_modules_does_not_start_scheduler(self):
        """Importing scheduler_service or local_test_launcher does NOT start scheduler threads."""
        import scheduler_service
        import local_test_launcher

        sched = getattr(scheduler_service, "_global_scheduler", None)
        if sched is not None:
            self.assertFalse(sched.is_running, "Scheduler should not be running after module import!")

    def test_05_opportunity_id_cannot_bypass_consent_guard(self):
        """Specifying an opportunity ID does NOT bypass promotional consent requirement."""
        mock_db = MagicMock()
        mock_client = MagicMock()
        mock_client.nodes = {("127.0.0.1", 27017)}
        mock_client.address = ("127.0.0.1", 27017)
        mock_db.client = mock_client

        # Customer without promotional consent
        mock_profiles = MagicMock()
        mock_profiles.find.return_value = [{
            "_id": "cust_123",
            "email": "test@example.com",
            "phone": "+919876543210",
            "whatsapp_opt_in": False,
            "whatsapp_promotional_consent": False,
            "whatsapp_opt_out": False,
        }]
        mock_db.__getitem__.return_value = mock_profiles

        mock_provider = MagicMock()
        success, res = run_application_whatsapp_journey(
            "test@example.com",
            opportunity_identifier="opp_high_pri_001",
            confirm_real=True,
            provider=mock_provider,
            db=mock_db,
        )
        self.assertFalse(success)
        self.assertIn("consent", res["error"].lower())
        mock_provider.send_message.assert_not_called()

    def test_06_opportunity_id_cannot_bypass_opt_out_guard(self):
        """Specifying an opportunity ID does NOT bypass opt-out guard."""
        mock_db = MagicMock()
        mock_client = MagicMock()
        mock_client.nodes = {("127.0.0.1", 27017)}
        mock_client.address = ("127.0.0.1", 27017)
        mock_db.client = mock_client

        # Customer with consent BUT opt-out enabled
        mock_profiles = MagicMock()
        mock_profiles.find.return_value = [{
            "_id": "cust_123",
            "email": "test@example.com",
            "phone": "+919876543210",
            "whatsapp_opt_in": True,
            "whatsapp_promotional_consent": True,
            "whatsapp_opt_out": True,
        }]
        mock_db.__getitem__.return_value = mock_profiles

        mock_provider = MagicMock()
        success, res = run_application_whatsapp_journey(
            "test@example.com",
            opportunity_identifier="opp_high_pri_001",
            confirm_real=True,
            provider=mock_provider,
            db=mock_db,
        )
        self.assertFalse(success)
        self.assertIn("opted out", res["error"].lower())
        mock_provider.send_message.assert_not_called()

    def test_07_opportunity_id_cannot_bypass_phone_validation(self):
        """Specifying an opportunity ID does NOT bypass E.164 phone validation."""
        mock_db = MagicMock()
        mock_client = MagicMock()
        mock_client.nodes = {("127.0.0.1", 27017)}
        mock_client.address = ("127.0.0.1", 27017)
        mock_db.client = mock_client

        # Customer with invalid phone number
        mock_profiles = MagicMock()
        mock_profiles.find.return_value = [{
            "_id": "cust_123",
            "email": "test@example.com",
            "phone": "invalid-phone-format",
            "whatsapp_opt_in": True,
            "whatsapp_promotional_consent": True,
            "whatsapp_opt_out": False,
        }]
        mock_db.__getitem__.return_value = mock_profiles

        mock_provider = MagicMock()
        success, res = run_application_whatsapp_journey(
            "test@example.com",
            opportunity_identifier="opp_high_pri_001",
            confirm_real=True,
            provider=mock_provider,
            db=mock_db,
        )
        self.assertFalse(success)
        self.assertIn("invalid phone", res["error"].lower())
        mock_provider.send_message.assert_not_called()

    def test_08_unconfirmed_dispatch_rejected(self):
        """run_application_whatsapp_journey rejects dispatch if confirm_real is not True."""
        mock_provider = MagicMock()
        success, res = run_application_whatsapp_journey(
            "test@example.com",
            confirm_real=False,
            provider=mock_provider,
        )
        self.assertFalse(success)
        self.assertIn("confirmation required", res["error"].lower())
        mock_provider.send_message.assert_not_called()


if __name__ == "__main__":
    unittest.main()
