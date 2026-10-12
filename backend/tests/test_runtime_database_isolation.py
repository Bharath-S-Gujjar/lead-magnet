"""Offline tests for Task 21.5 Runtime Database Isolation and Staging Readiness.

Proves:
1. Local test launcher enforces loopback MongoDB and database leadmagnet_test.
2. Remote MongoDB URIs (Atlas, mongodb+srv, non-loopback) are rejected before any connection.
3. Production database names and database names without 'test' are rejected.
4. Live communication providers are rejected in local test launcher.
5. Real dispatch and scheduler startup remain disabled and fail closed if enabled.
6. Local test guard requirement prevents loading production configuration.
7. run_application_whatsapp_journey fails closed if target_db points to a remote/Atlas host.
8. The regular backend/.env file on disk is never altered.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock

# Ensure backend root is on sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from local_test_launcher import (
    configure_local_test_environment,
    assert_local_only_safety,
    LOCAL_MONGO_URI,
    LOCAL_DATABASE_NAME,
)
from verify_real_delivery import run_application_whatsapp_journey


class TestRuntimeDatabaseIsolation(unittest.TestCase):
    """Test suite verifying fail-closed runtime database isolation."""

    def setUp(self):
        self.orig_env = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.orig_env)

    def test_01_local_launch_configures_and_uses_local_test_database(self):
        """configure_local_test_environment establishes verified local settings."""
        env_map = configure_local_test_environment()
        self.assertEqual(os.environ.get("TESTING"), "1")
        self.assertEqual(os.environ.get("LOCAL_ONLY_TESTING"), "1")
        self.assertEqual(os.environ.get("MONGO_URI"), LOCAL_MONGO_URI)
        self.assertEqual(os.environ.get("MONGO_DB_NAME"), LOCAL_DATABASE_NAME)
        self.assertEqual(os.environ.get("COMMUNICATION_PROVIDER"), "dry_run")
        self.assertEqual(os.environ.get("ALLOW_REAL_DISPATCH"), "false")
        self.assertEqual(os.environ.get("ENABLE_SCHEDULER"), "false")
        self.assertIn("127.0.0.1", os.environ.get("MONGO_URI"))

    def test_02_remote_atlas_uri_rejected_before_connection(self):
        """assert_local_only_safety immediately rejects mongodb+srv Atlas URIs."""
        unsafe_env = {
            "TESTING": "1",
            "MONGO_URI": "mongodb+srv://admin:pass@leadmagnetcluster.mongodb.net/leadmagnet",
            "MONGO_DB_NAME": "leadmagnet_test",
            "COMMUNICATION_PROVIDER": "dry_run",
            "ALLOW_REAL_DISPATCH": "false",
            "ENABLE_SCHEDULER": "false",
        }
        with self.assertRaises(RuntimeError) as ctx:
            assert_local_only_safety(unsafe_env)
        self.assertIn("remote/atlas pattern", str(ctx.exception).lower())

    def test_03_atlas_subdomain_rejected_before_connection(self):
        """assert_local_only_safety immediately rejects standard URIs with .mongodb.net domain."""
        unsafe_env = {
            "TESTING": "1",
            "MONGO_URI": "mongodb://cluster-shard-00-00.mongodb.net:27017",
            "MONGO_DB_NAME": "leadmagnet_test",
            "COMMUNICATION_PROVIDER": "dry_run",
            "ALLOW_REAL_DISPATCH": "false",
            "ENABLE_SCHEDULER": "false",
        }
        with self.assertRaises(RuntimeError) as ctx:
            assert_local_only_safety(unsafe_env)
        self.assertIn("remote/atlas pattern", str(ctx.exception).lower())

    def test_04_non_loopback_ip_rejected(self):
        """assert_local_only_safety rejects private LAN or public non-loopback IP addresses."""
        unsafe_env = {
            "TESTING": "1",
            "MONGO_URI": "mongodb://192.168.1.150:27017",
            "MONGO_DB_NAME": "leadmagnet_test",
            "COMMUNICATION_PROVIDER": "dry_run",
            "ALLOW_REAL_DISPATCH": "false",
            "ENABLE_SCHEDULER": "false",
        }
        with self.assertRaises(RuntimeError) as ctx:
            assert_local_only_safety(unsafe_env)
        self.assertIn("does not target a loopback host", str(ctx.exception).lower())

    def test_05_production_database_names_rejected(self):
        """assert_local_only_safety rejects production database names."""
        for forbidden in ("leadmagnet", "production", "lead_magnet", "leadmagnetdb"):
            unsafe_env = {
                "TESTING": "1",
                "MONGO_URI": "mongodb://127.0.0.1:27017",
                "MONGO_DB_NAME": forbidden,
                "COMMUNICATION_PROVIDER": "dry_run",
                "ALLOW_REAL_DISPATCH": "false",
                "ENABLE_SCHEDULER": "false",
            }
            with self.assertRaises(RuntimeError) as ctx:
                assert_local_only_safety(unsafe_env)
            self.assertIn("forbidden production", str(ctx.exception).lower())

    def test_06_database_name_without_test_rejected(self):
        """assert_local_only_safety rejects database names that do not contain 'test'."""
        unsafe_env = {
            "TESTING": "1",
            "MONGO_URI": "mongodb://127.0.0.1:27017",
            "MONGO_DB_NAME": "custom_analytics_data",
            "COMMUNICATION_PROVIDER": "dry_run",
            "ALLOW_REAL_DISPATCH": "false",
            "ENABLE_SCHEDULER": "false",
        }
        with self.assertRaises(RuntimeError) as ctx:
            assert_local_only_safety(unsafe_env)
        self.assertIn("does not contain 'test'", str(ctx.exception).lower())

    def test_07_live_provider_rejected_in_local_launcher(self):
        """assert_local_only_safety rejects live providers in local launcher mode."""
        for live_prov in ("whatsapp_business", "gmail_smtp", "multi_channel", "production"):
            unsafe_env = {
                "TESTING": "1",
                "MONGO_URI": "mongodb://127.0.0.1:27017",
                "MONGO_DB_NAME": "leadmagnet_test",
                "COMMUNICATION_PROVIDER": live_prov,
                "ALLOW_REAL_DISPATCH": "false",
                "ENABLE_SCHEDULER": "false",
            }
            with self.assertRaises(RuntimeError) as ctx:
                assert_local_only_safety(unsafe_env)
            self.assertIn("must be 'dry_run'", str(ctx.exception).lower())

    def test_08_real_dispatch_switch_rejected(self):
        """assert_local_only_safety rejects ALLOW_REAL_DISPATCH=true."""
        unsafe_env = {
            "TESTING": "1",
            "MONGO_URI": "mongodb://127.0.0.1:27017",
            "MONGO_DB_NAME": "leadmagnet_test",
            "COMMUNICATION_PROVIDER": "dry_run",
            "ALLOW_REAL_DISPATCH": "true",
            "ENABLE_SCHEDULER": "false",
        }
        with self.assertRaises(RuntimeError) as ctx:
            assert_local_only_safety(unsafe_env)
        self.assertIn("allow_real_dispatch cannot be 'true'", str(ctx.exception).lower())

    def test_09_scheduler_enable_rejected(self):
        """assert_local_only_safety rejects ENABLE_SCHEDULER=true."""
        unsafe_env = {
            "TESTING": "1",
            "MONGO_URI": "mongodb://127.0.0.1:27017",
            "MONGO_DB_NAME": "leadmagnet_test",
            "COMMUNICATION_PROVIDER": "dry_run",
            "ALLOW_REAL_DISPATCH": "false",
            "ENABLE_SCHEDULER": "true",
        }
        with self.assertRaises(RuntimeError) as ctx:
            assert_local_only_safety(unsafe_env)
        self.assertIn("enable_scheduler cannot be 'true'", str(ctx.exception).lower())

    def test_10_missing_testing_guard_rejected(self):
        """assert_local_only_safety rejects execution when neither TESTING nor LOCAL_ONLY_TESTING is set."""
        unsafe_env = {
            "TESTING": "",
            "LOCAL_ONLY_TESTING": "",
            "MONGO_URI": "mongodb://127.0.0.1:27017",
            "MONGO_DB_NAME": "leadmagnet_test",
            "COMMUNICATION_PROVIDER": "dry_run",
            "ALLOW_REAL_DISPATCH": "false",
            "ENABLE_SCHEDULER": "false",
        }
        with self.assertRaises(RuntimeError) as ctx:
            assert_local_only_safety(unsafe_env)
        self.assertIn("testing guard is missing", str(ctx.exception).lower())

    def test_11_verify_real_delivery_fails_closed_against_atlas(self):
        """run_application_whatsapp_journey immediately halts if target_db points to remote Atlas."""
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

    def test_12_regular_application_configuration_file_unchanged(self):
        """configure_local_test_environment does NOT modify backend/.env on disk."""
        env_path = os.path.join(backend_dir, ".env")
        mtime_before = os.path.getmtime(env_path) if os.path.exists(env_path) else None

        # Execute launcher configuration
        configure_local_test_environment()

        mtime_after = os.path.getmtime(env_path) if os.path.exists(env_path) else None
        self.assertEqual(mtime_before, mtime_after, ".env file modification time changed!")


if __name__ == "__main__":
    unittest.main()
