import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import jwt

import app as app_module


class AdminAuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.leads_collection = Mock()
        self.collection_patch = patch.object(app_module, "leads_collection", self.leads_collection)
        self.collection_patch.start()
        self.client = app_module.app.test_client()
        self.secret = app_module.JWT_SECRET

    def tearDown(self):
        self.collection_patch.stop()

    def make_token(self, role, expires_at):
        return jwt.encode({"role": role, "exp": expires_at}, self.secret, algorithm="HS256")

    def test_valid_admin_token_allows_admin_route(self):
        self.leads_collection.aggregate.return_value = []
        token = self.make_token("admin", datetime.now(timezone.utc) + timedelta(minutes=5))

        response = self.client.get(
            "/api/admin/dashboard", headers={"Authorization": f"Bearer {token}"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["success"])

    def test_expired_token_is_unauthorized(self):
        token = self.make_token("admin", datetime.now(timezone.utc) - timedelta(minutes=1))

        response = self.client.get(
            "/api/admin/dashboard", headers={"Authorization": f"Bearer {token}"}
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json()["message"], "Token has expired")

    def test_invalid_token_is_unauthorized(self):
        response = self.client.get(
            "/api/admin/dashboard", headers={"Authorization": "Bearer not-a-jwt"}
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json()["message"], "Invalid token")

    def test_normal_user_token_is_forbidden_from_all_admin_routes(self):
        token = self.make_token("user", datetime.now(timezone.utc) + timedelta(minutes=5))
        headers = {"Authorization": f"Bearer {token}"}
        lead_id = "507f1f77bcf86cd799439011"

        requests = [
            ("GET", "/api/admin/leads"),
            ("GET", f"/api/admin/leads/{lead_id}"),
            ("PUT", f"/api/admin/leads/{lead_id}/status"),
            ("GET", "/api/admin/dashboard"),
        ]
        for method, path in requests:
            response = self.client.open(path, method=method, headers=headers, json={"status": "New"})
            self.assertEqual(response.status_code, 403, path)

    def test_missing_authorization_header_is_unauthorized_for_all_admin_routes(self):
        lead_id = "507f1f77bcf86cd799439011"
        requests = [
            ("GET", "/api/admin/leads"),
            ("GET", f"/api/admin/leads/{lead_id}"),
            ("PUT", f"/api/admin/leads/{lead_id}/status"),
            ("GET", "/api/admin/dashboard"),
        ]
        for method, path in requests:
            response = self.client.open(path, method=method, json={"status": "New"})
            self.assertEqual(response.status_code, 401, path)


if __name__ == "__main__":
    unittest.main()
