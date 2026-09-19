"""Security regression tests for Lead Magnet application (Task 15)."""

import datetime
import os
import time
import unittest
from bson import ObjectId

import jwt

import app as app_module
from app import app


class SecurityHardeningTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.jwt_secret = app_module.JWT_SECRET

        # Clear test collections
        app_module.profiles_collection.delete_many({})
        app_module.customer_features_collection.delete_many({})
        app_module.customer_lead_state_collection.delete_many({})
        app_module.sessions_collection.delete_many({})
        app_module.events_collection.delete_many({})
        app_module.leads_collection.delete_many({})

        # Clear rate limiter state for tests
        app_module.AUTH_RATE_LIMIT_ATTEMPTS.clear()

        # Seed test user profile
        self.user_id = str(ObjectId())
        self.user_email = "test_user_sec@example.com"
        app_module.profiles_collection.insert_one({
            "_id": ObjectId(self.user_id),
            "email": self.user_email,
            "password": b"$2b$12$somehashedpasswordstringfortesting",
            "password_hash": "hash_should_be_stripped",
            "role": "user",
            "full_name": "Test Security User",
            "created_at": datetime.datetime.utcnow(),
        })

        # Seed second victim profile
        self.victim_id = str(ObjectId())
        self.victim_email = "victim_sec@example.com"
        app_module.profiles_collection.insert_one({
            "_id": ObjectId(self.victim_id),
            "email": self.victim_email,
            "password": b"$2b$12$victimpasswordhash",
            "role": "user",
            "full_name": "Victim User",
            "created_at": datetime.datetime.utcnow(),
        })

    def _generate_token(self, role="user", user_id=None, exp_minutes=60, include_exp=True):
        payload = {
            "role": role,
            "sub": user_id or self.user_id,
            "email": self.user_email if role == "user" else "admin",
        }
        if include_exp:
            exp_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=exp_minutes)
            payload["exp"] = exp_time
        return jwt.encode(payload, self.jwt_secret, algorithm="HS256")

    # --- 1. AUTHENTICATION TESTS ---

    def test_expired_admin_token_rejected(self):
        """Expired admin tokens must be rejected with 401."""
        expired_token = self._generate_token(role="admin", exp_minutes=-10)
        res = self.client.get(
            "/api/admin/intelligence/overview",
            headers={"Authorization": f"Bearer {expired_token}"},
        )
        self.assertEqual(res.status_code, 401)
        data = res.get_json()
        self.assertFalse(data["success"])
        self.assertIn("expired", data["message"].lower())

    def test_invalid_tampered_admin_token_rejected(self):
        """Invalid or tampered tokens must be rejected with 401."""
        tampered_token = self._generate_token(role="admin") + "tampered"
        res = self.client.get(
            "/api/admin/intelligence/overview",
            headers={"Authorization": f"Bearer {tampered_token}"},
        )
        self.assertEqual(res.status_code, 401)
        data = res.get_json()
        self.assertFalse(data["success"])
        self.assertIn("invalid", data["message"].lower())

    def test_token_missing_exp_claim_rejected(self):
        """Tokens lacking explicit expiration claim must be rejected."""
        token_no_exp = self._generate_token(role="admin", include_exp=False)
        res = self.client.get(
            "/api/admin/intelligence/overview",
            headers={"Authorization": f"Bearer {token_no_exp}"},
        )
        self.assertEqual(res.status_code, 401)

    # --- 2. AUTHORIZATION TESTS ---

    def test_customer_cannot_access_admin_endpoint(self):
        """Non-admin user token must be forbidden (403) from admin endpoints."""
        customer_token = self._generate_token(role="user")
        res = self.client.get(
            "/api/admin/intelligence/overview",
            headers={"Authorization": f"Bearer {customer_token}"},
        )
        self.assertEqual(res.status_code, 403)
        data = res.get_json()
        self.assertFalse(data["success"])
        self.assertIn("admin", data["message"].lower())

    def test_customer_cannot_access_another_customer_profile(self):
        """Customer A cannot request Customer B's profile via user_id parameter."""
        user_a_token = self._generate_token(role="user", user_id=self.user_id)
        res = self.client.get(
            f"/api/profile?user_id={self.victim_id}",
            headers={"Authorization": f"Bearer {user_a_token}"},
        )
        self.assertEqual(res.status_code, 403)
        data = res.get_json()
        self.assertFalse(data["success"])

    def test_unauthenticated_request_to_protected_endpoint_rejected(self):
        """Missing Authorization token on protected route must return 401."""
        res = self.client.get("/api/customer/lead-score")
        self.assertEqual(res.status_code, 401)

    # --- 3. DATA EXPOSURE & SANITIZATION TESTS ---

    def test_sensitive_fields_stripped_from_profile_response(self):
        """Passwords and hashes must never be returned in profile API responses."""
        user_token = self._generate_token(role="user", user_id=self.user_id)
        res = self.client.get(
            f"/api/profile?user_id={self.user_id}",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()["data"]
        self.assertNotIn("password", data)
        self.assertNotIn("password_hash", data)

    # --- 4. INPUT VALIDATION & CONTROLLED ERROR TESTS ---

    def test_malformed_customer_id_returns_controlled_400(self):
        """Invalid customer_id format must produce controlled 400 response."""
        admin_token = self._generate_token(role="admin")
        res = self.client.get(
            "/api/admin/intelligence/customers/invalid-non-objectid-string",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertFalse(data["success"])

    def test_invalid_pagination_parameters_handled_safely(self):
        """Invalid page or limit values (e.g. non-int or negative) must not crash server."""
        admin_token = self._generate_token(role="admin")
        res = self.client.get(
            "/api/admin/intelligence/leads?page=invalid_string&limit=-5",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        self.assertEqual(res.status_code, 200)

    # --- 5. SECURITY HEADERS & CORS TESTS ---

    def test_security_headers_present_on_response(self):
        """Production security headers must be injected on all HTTP responses."""
        res = self.client.get("/api/health")
        self.assertEqual(res.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(res.headers.get("X-Frame-Options"), "SAMEORIGIN")
        self.assertEqual(res.headers.get("Referrer-Policy"), "strict-origin-when-cross-origin")
        self.assertEqual(res.headers.get("X-XSS-Protection"), "1; mode=block")

    # --- 6. RATE LIMITING TESTS ---

    def test_rate_limiting_on_auth_login_endpoint(self):
        """Exceeding max attempts on login endpoint must trigger 429 rate limit."""
        original_testing = app.testing
        original_config_testing = app.config.get("TESTING")
        try:
            app.testing = False
            app.config["TESTING"] = False
            ip = "192.168.1.100"
            for i in range(10):
                res = self.client.post(
                    "/api/auth/login",
                    json={"email": "attempt@example.com", "password": "wrong"},
                    environ_base={"REMOTE_ADDR": ip},
                )
                if i < 10:
                    self.assertIn(res.status_code, [400, 401])

            # 11th request should be rate limited
            res = self.client.post(
                "/api/auth/login",
                json={"email": "attempt@example.com", "password": "wrong"},
                environ_base={"REMOTE_ADDR": ip},
            )
            self.assertEqual(res.status_code, 429)
            data = res.get_json()
            self.assertIn("too many requests", data["message"].lower())
        finally:
            app.testing = original_testing
            app.config["TESTING"] = original_config_testing
            app_module.AUTH_RATE_LIMIT_ATTEMPTS.clear()

    def tearDown(self):
        app_module.AUTH_RATE_LIMIT_ATTEMPTS.clear()


if __name__ == "__main__":
    unittest.main()
