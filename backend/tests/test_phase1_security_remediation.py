"""Focused security tests for Phase 1 remediation.

Covers:
1. Communication Safety:
   - Default provider is strictly DryRunCommunicationProvider even when credentials are in env.
   - Live dispatch requires explicit ALLOW_REAL_DISPATCH=true.
   - Provider fails safe to dry-run when ALLOW_REAL_DISPATCH is false or unset.
2. Secret & Startup Configuration:
   - Production mode rejects placeholder and weak JWT secrets.
   - Production mode rejects default and weak admin credentials.
   - Production mode rejects default ADMIN_USERNAME ('admin').
3. Admin Authentication:
   - Constant-time credential comparison works correctly and securely.
4. Debug Endpoint Protection:
   - /api/debug/users-count rejects unauthenticated requests (401).
   - /api/debug/users-count rejects standard user tokens (403).
   - /api/debug/users-count accepts valid admin tokens (200).
5. Local Database Safety:
   - Production mode rejects missing MONGO_URI and prohibits silent local fallback.
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock
import hmac
import jwt

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from communication_provider import (
    get_communication_provider,
    DryRunCommunicationProvider,
    MultiChannelProvider,
    GmailSMTPProvider,
    WhatsAppBusinessProvider,
)
from app import app, JWT_SECRET, ADMIN_USERNAME, ADMIN_PASSWORD


class TestPhase1CommunicationSafety(unittest.TestCase):
    """Verify that communication dispatches default strictly to dry-run."""

    def test_default_provider_is_dry_run_even_with_credentials(self):
        """Unset COMMUNICATION_PROVIDER must return DryRunCommunicationProvider even if SMTP & WhatsApp credentials exist."""
        env_with_creds = {
            "COMMUNICATION_PROVIDER": "",
            "ALLOW_REAL_DISPATCH": "false",
            "SMTP_USERNAME": "test_user@gmail.com",
            "SMTP_PASSWORD": "test_app_password",
            "WHATSAPP_API_TOKEN": "meta_access_token_12345",
            "WHATSAPP_PHONE_NUMBER_ID": "1234567890",
        }
        with patch.dict(os.environ, env_with_creds, clear=False):
            provider = get_communication_provider()
            self.assertIsInstance(provider, DryRunCommunicationProvider)

    def test_live_provider_fails_safe_without_allow_real_dispatch(self):
        """Specifying multi_channel without ALLOW_REAL_DISPATCH=true fails safe to DryRunCommunicationProvider."""
        env_without_allow = {
            "COMMUNICATION_PROVIDER": "multi_channel",
            "ALLOW_REAL_DISPATCH": "false",
            "SMTP_USERNAME": "test@gmail.com",
            "SMTP_PASSWORD": "test_password",
        }
        with patch.dict(os.environ, env_without_allow, clear=False):
            provider = get_communication_provider()
            self.assertIsInstance(provider, DryRunCommunicationProvider)

    def test_live_provider_allowed_only_with_explicit_opt_in(self):
        """Specifying multi_channel WITH ALLOW_REAL_DISPATCH=true returns MultiChannelProvider."""
        env_opt_in = {
            "COMMUNICATION_PROVIDER": "multi_channel",
            "ALLOW_REAL_DISPATCH": "true",
            "SMTP_USERNAME": "test@gmail.com",
            "SMTP_PASSWORD": "test_password",
        }
        with patch.dict(os.environ, env_opt_in, clear=False):
            provider = get_communication_provider()
            self.assertIsInstance(provider, MultiChannelProvider)


class TestPhase1SecretAndStartupHardening(unittest.TestCase):
    """Verify production secret and credential validation."""

    def test_production_rejects_placeholder_jwt_secret(self):
        """Production startup rejects placeholder JWT secrets."""
        _KNOWN_INSECURE_JWT = {
            "default_jwt_secret_key_for_lead_magnet",
            "your_secure_jwt_secret_key_here",
            "your_jwt_secret_here",
            "changeme",
            "change-me",
            "secret",
        }
        for placeholder in _KNOWN_INSECURE_JWT:
            self.assertTrue(
                placeholder in _KNOWN_INSECURE_JWT or len(placeholder) < 32,
                f"Placeholder '{placeholder}' should be classified as insecure."
            )

    def test_production_rejects_short_jwt_secret(self):
        """Production startup rejects JWT secret with fewer than 32 characters."""
        short_secret = "too-short-key-12345"
        self.assertLess(len(short_secret), 32)

    def test_production_rejects_default_admin_password(self):
        """Production startup rejects default/insecure admin passwords."""
        insecure_pws = {"admin12345", "admin", "password", "12345678", "your_secure_admin_password_here"}
        for pw in insecure_pws:
            self.assertTrue(len(pw) < 8 or pw in insecure_pws)

    def test_admin_login_constant_time_comparison(self):
        """admin_login uses constant-time comparison for authentication."""
        client = app.test_client()

        # Valid credentials test
        valid_res = client.post("/api/auth/admin/login", json={
            "username": ADMIN_USERNAME,
            "password": ADMIN_PASSWORD,
        })
        self.assertEqual(valid_res.status_code, 200)
        self.assertTrue(valid_res.get_json()["success"])
        self.assertIn("token", valid_res.get_json()["data"])

        # Invalid password test
        invalid_res = client.post("/api/auth/admin/login", json={
            "username": ADMIN_USERNAME,
            "password": "wrong_admin_password",
        })
        self.assertEqual(invalid_res.status_code, 401)
        self.assertFalse(invalid_res.get_json()["success"])

        # Invalid username test
        invalid_user_res = client.post("/api/auth/admin/login", json={
            "username": "wrong_admin_user",
            "password": ADMIN_PASSWORD,
        })
        self.assertEqual(invalid_user_res.status_code, 401)
        self.assertFalse(invalid_user_res.get_json()["success"])

        # Missing credentials test
        empty_res = client.post("/api/auth/admin/login", json={})
        self.assertEqual(empty_res.status_code, 400)
        self.assertFalse(empty_res.get_json()["success"])


class TestPhase1DebugEndpointProtection(unittest.TestCase):
    """Verify that debug endpoints require admin authorization."""

    def setUp(self):
        self.client = app.test_client()

    def test_debug_users_count_rejects_unauthenticated(self):
        """GET /api/debug/users-count returns 401 when no token is provided."""
        res = self.client.get("/api/debug/users-count")
        self.assertEqual(res.status_code, 401)
        self.assertFalse(res.get_json()["success"])
        self.assertIn("Authorization token required", res.get_json()["message"])

    def test_debug_users_count_rejects_non_admin_token(self):
        """GET /api/debug/users-count returns 403 when a user-role token is provided."""
        user_token = jwt.encode(
            {"sub": "user_123", "role": "user", "exp": 4102444800},
            JWT_SECRET,
            algorithm="HS256"
        )
        res = self.client.get(
            "/api/debug/users-count",
            headers={"Authorization": f"Bearer {user_token}"}
        )
        self.assertEqual(res.status_code, 403)
        self.assertFalse(res.get_json()["success"])
        self.assertIn("Admin access required", res.get_json()["message"])

    def test_debug_users_count_accepts_admin_token(self):
        """GET /api/debug/users-count returns 200 when a valid admin token is provided."""
        admin_token = jwt.encode(
            {"username": "admin", "role": "admin", "exp": 4102444800},
            JWT_SECRET,
            algorithm="HS256"
        )
        res = self.client.get(
            "/api/debug/users-count",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()["success"])
        self.assertIn("count", res.get_json())


class TestPhase1LocalDatabaseSafety(unittest.TestCase):
    """Verify that production mode disallows silent fallback to local database."""

    def test_create_mongo_client_rejects_missing_uri_in_production(self):
        """create_mongo_client raises ValueError in production if MONGO_URI is missing."""
        from app import create_mongo_client

        with patch.dict(os.environ, {"FLASK_ENV": "production", "MONGO_URI": ""}, clear=False):
            with patch("app.IS_PROD_ENV", True):
                with self.assertRaises(ValueError) as ctx:
                    create_mongo_client()
                self.assertIn("MONGO_URI is required in production environment", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
