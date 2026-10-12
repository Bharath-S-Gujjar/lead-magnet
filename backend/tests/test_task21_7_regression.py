"""Regression tests for Task 21.7: Close Runtime Isolation Bypass Gaps.

Proves:
1. Finding 1: verify_database_connection validates explicit uri and db_name arguments
   before constructing MongoClient (MongoClient is never instantiated for unsafe args).
2. Finding 1: Unsafe database names and real dispatch / scheduler flags reject before connection.
3. Finding 2: Importing verify_real_delivery creates ZERO MongoDB clients and contacts ZERO remote hosts.
4. Finding 2: run_application_whatsapp_journey without isolated test database fails closed immediately.
5. Finding 2: Direct CLI execution of --send-workflow-whatsapp fails closed under unsafe ambient environment.
6. Finding 2: Safe local test launcher remains fully functional.
"""

import os
import subprocess
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
    run_local_test_journey,
    LOCAL_MONGO_URI,
    LOCAL_DATABASE_NAME,
)
from verify_real_delivery import (
    run_application_whatsapp_journey,
    check_configuration,
    validate_phone_utility,
)


class TestTask21_7Regression(unittest.TestCase):
    """Test suite proving fixes for Task 21.6 audit findings."""

    def setUp(self):
        self.orig_env = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.orig_env)

    # -------------------------------------------------------------------------
    # Finding 1 Tests: Explicit Connection Argument Validation
    # -------------------------------------------------------------------------

    def test_f1_01_explicit_atlas_uri_rejected_before_client_construction(self):
        """verify_database_connection rejects an explicit Atlas URI before MongoClient is created, even if env is safe."""
        configure_local_test_environment()
        self.assertEqual(os.environ.get("MONGO_URI"), LOCAL_MONGO_URI)

        with patch("pymongo.MongoClient") as mock_client_cls:
            with self.assertRaises(RuntimeError) as ctx:
                verify_database_connection(
                    uri="mongodb+srv://admin:pass@leadmagnetcluster.mongodb.net/test",
                    db_name=LOCAL_DATABASE_NAME,
                )
            self.assertIn("remote/atlas pattern", str(ctx.exception).lower())
            mock_client_cls.assert_not_called()

    def test_f1_02_explicit_production_dbname_rejected_before_client_construction(self):
        """verify_database_connection rejects explicit production db_name before MongoClient is created."""
        configure_local_test_environment()

        with patch("pymongo.MongoClient") as mock_client_cls:
            for forbidden_db in ("leadmagnet", "production", "lead_magnet", "leadmagnetdb"):
                with self.assertRaises(RuntimeError) as ctx:
                    verify_database_connection(
                        uri=LOCAL_MONGO_URI,
                        db_name=forbidden_db,
                    )
                self.assertIn("forbidden production", str(ctx.exception).lower())
                mock_client_cls.assert_not_called()

    def test_f1_03_explicit_dbname_without_test_rejected_before_client_construction(self):
        """verify_database_connection rejects explicit db_name without 'test' before MongoClient is created."""
        configure_local_test_environment()

        with patch("pymongo.MongoClient") as mock_client_cls:
            with self.assertRaises(RuntimeError) as ctx:
                verify_database_connection(
                    uri=LOCAL_MONGO_URI,
                    db_name="customer_orders_data",
                )
            self.assertIn("does not contain 'test'", str(ctx.exception).lower())
            mock_client_cls.assert_not_called()

    def test_f1_04_explicit_non_loopback_uri_rejected_before_client_construction(self):
        """verify_database_connection rejects non-loopback IP/host before MongoClient is created."""
        configure_local_test_environment()

        with patch("pymongo.MongoClient") as mock_client_cls:
            with self.assertRaises(RuntimeError) as ctx:
                verify_database_connection(
                    uri="mongodb://192.168.1.50:27017",
                    db_name=LOCAL_DATABASE_NAME,
                )
            self.assertIn("does not target a loopback host", str(ctx.exception).lower())
            mock_client_cls.assert_not_called()

    def test_f1_05_unsafe_runtime_switches_rejected_in_verify_database_connection(self):
        """verify_database_connection fails closed if ALLOW_REAL_DISPATCH or ENABLE_SCHEDULER is enabled."""
        configure_local_test_environment()
        os.environ["ALLOW_REAL_DISPATCH"] = "true"

        with patch("pymongo.MongoClient") as mock_client_cls:
            with self.assertRaises(RuntimeError) as ctx:
                verify_database_connection()
            self.assertIn("allow_real_dispatch cannot be 'true'", str(ctx.exception).lower())
            mock_client_cls.assert_not_called()

    # -------------------------------------------------------------------------
    # Finding 2 Tests: Legacy CLI Entry Point Hardening
    # -------------------------------------------------------------------------

    def test_f2_01_verify_real_delivery_import_creates_zero_mongo_clients(self):
        """Importing verify_real_delivery never initializes a MongoClient at module scope."""
        # Clean import test
        if "verify_real_delivery" in sys.modules:
            del sys.modules["verify_real_delivery"]

        with patch("pymongo.MongoClient") as mock_client_cls:
            import verify_real_delivery
            mock_client_cls.assert_not_called()

    def test_f2_02_direct_journey_without_isolated_db_fails_closed(self):
        """run_application_whatsapp_journey fails closed immediately when db=None and TESTING!=1."""
        os.environ["TESTING"] = "0"
        os.environ["MONGO_URI"] = "mongodb+srv://admin:pass@cluster.mongodb.net/prod"

        success, res = run_application_whatsapp_journey(
            "test_user@example.com",
            confirm_real=True,
            db=None,
        )
        self.assertFalse(success)
        self.assertIn("direct execution requires isolated test database", res["error"].lower())

    def test_f2_03_direct_cli_workflow_dispatch_fails_closed_under_unsafe_env(self):
        """Direct execution of verify_real_delivery.py --send-workflow-whatsapp fails closed with code 1."""
        env = dict(os.environ)
        env["TESTING"] = "0"
        env["MONGO_URI"] = "mongodb+srv://admin:pass@leadmagnetcluster.mongodb.net/leadmagnet"

        cmd = [
            sys.executable,
            os.path.join(backend_dir, "verify_real_delivery.py"),
            "--send-workflow-whatsapp",
            "test_user@example.com",
            "--confirm-real-dispatch",
        ]
        proc = subprocess.run(cmd, env=env, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("SAFEGUARD BLOCKED", proc.stdout)
        self.assertIn("local test launcher", proc.stdout.lower())

    def test_f2_04_direct_cli_validate_phone_runs_cleanly_without_mongo(self):
        """Direct execution of verify_real_delivery.py --validate-phone does not require or touch MongoDB."""
        env = dict(os.environ)
        cmd = [
            sys.executable,
            os.path.join(backend_dir, "verify_real_delivery.py"),
            "--validate-phone",
            "+919876543210",
        ]
        proc = subprocess.run(cmd, env=env, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("Status:             VALID", proc.stdout)
        self.assertIn("E.164", proc.stdout)

    def test_f2_05_direct_cli_check_config_runs_cleanly_without_mongo(self):
        """Direct execution of verify_real_delivery.py --check-config runs safely without touching MongoDB."""
        env = dict(os.environ)
        cmd = [
            sys.executable,
            os.path.join(backend_dir, "verify_real_delivery.py"),
            "--check-config",
        ]
        proc = subprocess.run(cmd, env=env, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("REAL COMMUNICATION & WHATSAPP READINESS AUDIT", proc.stdout)

    def test_f2_06_safe_local_test_launcher_remains_fully_functional(self):
        """local_test_launcher.py --check-isolation completes successfully with verified loopback."""
        env = dict(os.environ)
        cmd = [
            sys.executable,
            os.path.join(backend_dir, "local_test_launcher.py"),
            "--check-isolation",
        ]
        proc = subprocess.run(cmd, env=env, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("LOCAL TEST ENVIRONMENT FULLY ISOLATED & SAFE", proc.stdout)


if __name__ == "__main__":
    unittest.main()
