import datetime
import os
import sys
import unittest

import bcrypt
import jwt
from bson import ObjectId

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import (
    JWT_SECRET,
    app,
    cart_collection,
    events_collection,
    profiles_collection,
    products_collection,
    sessions_collection,
    wishlist_collection,
)


class AuthenticationIdentityFoundationTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.product_id = ObjectId()
        products_collection.insert_one({
            "_id": self.product_id,
            "name": "Identity Test Product",
            "price": 1200,
            "category": "shirts",
            "brand": "IdentityBrand",
        })

    def _signup(self, email="identity@example.com", password="SecurePassword123", **extra):
        payload = {"email": email, "password": password}
        payload.update(extra)
        response = self.client.post("/api/auth/signup", json=payload)
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()["data"]["user_id"]

    def _login(self, email="identity@example.com", password="SecurePassword123", **extra):
        payload = {"email": email, "password": password}
        payload.update(extra)
        response = self.client.post("/api/auth/login", json=payload)
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()["data"]

    def test_anonymous_identity_session_event_and_signup_ownership_transfer(self):
        first = self.client.post("/api/session/start", json={}).get_json()["data"]
        second = self.client.post("/api/session/start", json={}).get_json()["data"]
        self.assertNotEqual(first["anonymous_id"], second["anonymous_id"])

        repeated = self.client.post(
            "/api/session/start", json={"anonymous_id": first["anonymous_id"]}
        ).get_json()["data"]
        self.assertEqual(repeated["anonymous_id"], first["anonymous_id"])

        event_response = self.client.post("/api/session/event", json={
            "session_id": first["session_id"],
            "event_type": "page_view",
            "page": "/identity-test",
        })
        self.assertEqual(event_response.status_code, 200)
        second_event_response = self.client.post("/api/session/event", json={
            "session_id": repeated["session_id"],
            "event_type": "click",
            "page": "/identity-test",
        })
        self.assertEqual(second_event_response.status_code, 200)

        user_id = self._signup(anonymous_id=first["anonymous_id"])
        user_object_id = ObjectId(user_id)
        owned_sessions = list(sessions_collection.find({"user_id": user_object_id}))
        owned_events = list(events_collection.find({"user_id": user_object_id}))
        self.assertEqual(len(owned_sessions), 2)
        self.assertEqual(len(owned_events), 2)
        self.assertTrue(all(item["identity_status"] == "authenticated" for item in owned_sessions))

    def test_signup_merges_cart_and_wishlist_and_keeps_password_private(self):
        anonymous_id = "anon_merge_foundation"
        cart_response = self.client.post("/api/cart", json={
            "product_id": str(self.product_id),
            "quantity": 2,
            "anonymous_id": anonymous_id,
        })
        wishlist_response = self.client.post("/api/wishlist", json={
            "product_id": str(self.product_id),
            "anonymous_id": anonymous_id,
        })
        self.assertEqual(cart_response.status_code, 200)
        self.assertEqual(wishlist_response.status_code, 200)

        signup = self.client.post("/api/auth/signup", json={
            "email": "merge@example.com",
            "password": "SecurePassword123",
            "anonymous_id": anonymous_id,
        })
        self.assertEqual(signup.status_code, 200)
        signup_data = signup.get_json()
        user_id = ObjectId(signup_data["data"]["user_id"])
        self.assertNotIn("password", signup_data["data"])
        self.assertEqual(signup_data["data"]["identity_resolution"]["cart_merged"], 1)
        self.assertEqual(signup_data["data"]["identity_resolution"]["wishlist_merged"], 1)

        profile = profiles_collection.find_one({"_id": user_id})
        self.assertIsInstance(profile["password"], bytes)
        self.assertNotEqual(profile["password"], b"SecurePassword123")
        self.assertEqual(cart_collection.count_documents({"user_id": user_id}), 1)
        self.assertEqual(wishlist_collection.count_documents({"user_id": user_id}), 1)
        self.assertEqual(cart_collection.count_documents({"anonymous_id": anonymous_id}), 0)
        self.assertEqual(wishlist_collection.count_documents({"anonymous_id": anonymous_id}), 0)

    def test_login_duplicate_merge_is_idempotent_and_sums_cart_quantity(self):
        user_id = ObjectId(self._signup(email="login-merge@example.com"))
        anonymous_id = "anon_login_merge_foundation"
        cart_collection.insert_one({"user_id": user_id, "product_id": self.product_id, "quantity": 3})
        cart_collection.insert_one({"anonymous_id": anonymous_id, "product_id": self.product_id, "quantity": 2})
        wishlist_collection.insert_one({"user_id": user_id, "product_id": self.product_id})
        wishlist_collection.insert_one({"anonymous_id": anonymous_id, "product_id": self.product_id})

        first_login = self._login(email="login-merge@example.com", anonymous_id=anonymous_id)
        self.assertEqual(first_login["identity_resolution"]["cart_merged"], 1)
        self.assertEqual(first_login["identity_resolution"]["wishlist_merged"], 1)
        self.assertEqual(cart_collection.find_one({"user_id": user_id})["quantity"], 5)
        self.assertEqual(wishlist_collection.count_documents({"user_id": user_id}), 1)

        second_login = self._login(email="login-merge@example.com", anonymous_id=anonymous_id)
        self.assertEqual(second_login["identity_resolution"]["cart_merged"], 0)
        self.assertEqual(second_login["identity_resolution"]["wishlist_merged"], 0)
        self.assertEqual(cart_collection.count_documents({"user_id": user_id}), 1)
        self.assertEqual(wishlist_collection.count_documents({"user_id": user_id}), 1)

    def test_auth_validation_duplicate_registration_and_password_comparison(self):
        self.assertEqual(self.client.post("/api/auth/signup", json={}).status_code, 400)
        self.assertEqual(self.client.post("/api/auth/signup", data="not-json", content_type="text/plain").status_code, 400)
        self._signup(email="duplicate@example.com", username="duplicate-user")
        duplicate_email = self.client.post("/api/auth/signup", json={
            "email": "duplicate@example.com", "password": "SecurePassword123"
        })
        duplicate_username = self.client.post("/api/auth/signup", json={
            "email": "another@example.com", "password": "SecurePassword123", "username": "duplicate-user"
        })
        self.assertEqual(duplicate_email.status_code, 400)
        self.assertEqual(duplicate_username.status_code, 400)
        self.assertEqual(self.client.post("/api/auth/login", json={}).status_code, 400)
        self.assertEqual(self.client.post("/api/auth/login", json={
            "email": "duplicate@example.com", "password": "wrong"
        }).status_code, 401)
        self.assertEqual(self.client.post("/api/auth/login", json={
            "email": "duplicate@example.com", "password": 123
        }).status_code, 400)
        self.assertEqual(self.client.post("/api/auth/signup", json={
            "email": "bad-anon@example.com", "password": "SecurePassword123", "anonymous_id": {}
        }).status_code, 400)

    def test_token_validation_and_admin_authorization(self):
        user_id = self._signup(email="token-user@example.com")
        user_token = self._login(email="token-user@example.com")["token"]
        admin_token = self.client.post("/api/auth/admin/login", json={
            "username": "admin", "password": "admin12345"
        }).get_json()["data"]["token"]

        self.assertEqual(self.client.get("/api/admin/dashboard").status_code, 401)
        self.assertEqual(self.client.get("/api/admin/dashboard", headers={
            "Authorization": "Bearer malformed"
        }).status_code, 401)
        self.assertEqual(self.client.get("/api/admin/dashboard", headers={
            "Authorization": f"Bearer {user_token}"
        }).status_code, 403)
        self.assertEqual(self.client.get("/api/admin/dashboard", headers={
            "Authorization": f"Bearer {admin_token}"
        }).status_code, 200)

        expired = jwt.encode({
            "sub": user_id,
            "role": "user",
            "exp": datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=1),
        }, JWT_SECRET, algorithm="HS256")
        self.assertEqual(self.client.get("/api/admin/dashboard", headers={
            "Authorization": f"Bearer {expired}"
        }).status_code, 401)
        self.assertEqual(self.client.post("/api/auth/admin/login", json={}).status_code, 400)

    def test_malformed_session_identity_is_controlled(self):
        response = self.client.post("/api/session/start", json={"anonymous_id": {}})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.get_json()["success"])
        self.assertEqual(self.client.post("/api/session/event", json={}).status_code, 400)


if __name__ == "__main__":
    unittest.main()
