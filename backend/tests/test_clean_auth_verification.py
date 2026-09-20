import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import unittest
from app import app, profiles_collection, sessions_collection, events_collection


class CleanStateAuthVerificationTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.test_email = "clean_verify_user@example.com"
        self.test_password = "SecurePassword123"

    def tearDown(self):
        # Cleanup test user profile, session, and events created during authentication test
        profiles_collection.delete_many({"email": self.test_email})
        sessions_collection.delete_many({"visitor_id": "clean_anon_123"})
        events_collection.delete_many({"visitor_id": "clean_anon_123"})

    def test_clean_auth_lifecycle(self):
        # 1. Anonymous visitor session start
        anon_res = self.client.post("/api/session/start", json={"visitor_id": "clean_anon_123"})
        self.assertEqual(anon_res.status_code, 200)
        anon_data = anon_res.get_json()["data"]
        session_id = anon_data["session_id"]
        self.assertTrue(session_id)

        # 2. Track event for anonymous visitor
        event_res = self.client.post("/api/session/event", json={
            "session_id": session_id,
            "event_type": "page_view",
            "page": "/products"
        })
        self.assertEqual(event_res.status_code, 200)

        # 3. Fresh signup with anonymous identity resolution
        signup_res = self.client.post("/api/auth/signup", json={
            "email": self.test_email,
            "password": self.test_password,
            "anonymous_id": "clean_anon_123"
        })
        self.assertEqual(signup_res.status_code, 200)
        signup_data = signup_res.get_json()
        self.assertTrue(signup_data["success"])
        self.assertIn("identity_resolution", signup_data["data"])
        user_id = signup_data["data"]["user_id"]

        # 4. Login using the new account
        login_res = self.client.post("/api/auth/login", json={
            "email": self.test_email,
            "password": self.test_password,
            "anonymous_id": "clean_anon_123"
        })
        self.assertEqual(login_res.status_code, 200)
        login_data = login_res.get_json()["data"]
        token = login_data["token"]
        self.assertTrue(token)

        # 5. Invalid login test
        bad_login_res = self.client.post("/api/auth/login", json={
            "email": self.test_email,
            "password": "WrongPassword!"
        })
        self.assertEqual(bad_login_res.status_code, 401)

        # 6. Authenticated admin request test
        admin_login = self.client.post("/api/auth/admin/login", json={
            "username": "admin",
            "password": "admin12345"
        })
        self.assertEqual(admin_login.status_code, 200)
        admin_token = admin_login.get_json()["data"]["token"]

        protected_res = self.client.get("/api/admin/dashboard", headers={
            "Authorization": f"Bearer {admin_token}"
        })
        self.assertEqual(protected_res.status_code, 200)

        # 7. End browsing session
        end_res = self.client.post("/api/session/end", json={"session_id": session_id})
        self.assertEqual(end_res.status_code, 200)


if __name__ == "__main__":
    unittest.main()
