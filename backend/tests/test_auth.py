import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import unittest
from app import app


class AuthEndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_auth_flow(self):
        # 1. Signup
        signup_res = self.client.post("/api/auth/signup", json={
            "email": "testuser_test@example.com",
            "password": "test1234"
        })
        self.assertIn(signup_res.status_code, (200, 400))

        # 2. Customer login
        login_res = self.client.post("/api/auth/login", json={
            "email": "testuser_test@example.com",
            "password": "test1234"
        })
        self.assertIn(login_res.status_code, (200, 401))

        # 3. Admin login
        admin_res = self.client.post("/api/auth/admin/login", json={
            "username": "admin",
            "password": "admin12345"
        })
        self.assertEqual(admin_res.status_code, 200)
        data = admin_res.get_json()
        self.assertTrue(data.get("success"))
        self.assertIn("token", data.get("data", {}))


if __name__ == "__main__":
    unittest.main()
