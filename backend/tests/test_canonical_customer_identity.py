import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from bson import ObjectId

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module
from lead_processing_service import process_session


class CanonicalCustomerIdentityTests(unittest.TestCase):
    def setUp(self):
        self.client = app_module.app.test_client()
        self.product_id = ObjectId()
        app_module.products_collection.insert_one({
            "_id": self.product_id,
            "name": "Identity Test Product",
            "price": 25,
            "category": "Test",
        })

    def _signup_and_login(self, email, anonymous_id=None):
        signup_payload = {"email": email, "password": "SecurePassword123"}
        if anonymous_id:
            signup_payload["anonymous_id"] = anonymous_id
        signup = self.client.post("/api/auth/signup", json=signup_payload)
        self.assertEqual(signup.status_code, 200, signup.get_json())
        user_id = signup.get_json()["data"]["user_id"]

        login_payload = {"email": email, "password": "SecurePassword123"}
        if anonymous_id:
            login_payload["anonymous_id"] = anonymous_id
        login = self.client.post("/api/auth/login", json=login_payload)
        self.assertEqual(login.status_code, 200, login.get_json())
        return user_id, login.get_json()["data"]["token"]

    def _start_session(self, anonymous_id, token=None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        response = self.client.post(
            "/api/session/start",
            json={"anonymous_id": anonymous_id},
            headers=headers,
        )
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()["data"]["session_id"]

    def _log_event(self, session_id, event_type="product_view"):
        response = self.client.post("/api/session/event", json={
            "session_id": session_id,
            "event_type": event_type,
            "page": "/products",
            "entity": {"type": "product", "id": str(self.product_id)},
        })
        self.assertEqual(response.status_code, 200, response.get_json())

    def test_anonymous_sessions_and_events_resolve_to_one_customer(self):
        anonymous_id = "anon_identity_foundation"
        session_one = self._start_session(anonymous_id)
        session_two = self._start_session(anonymous_id)
        self._log_event(session_one)
        self._log_event(session_two, "add_to_cart")

        user_id, token = self._signup_and_login(
            "canonical@example.com",
            anonymous_id,
        )

        canonical_id = ObjectId(user_id)
        sessions = list(app_module.sessions_collection.find({"user_id": canonical_id}))
        events = list(app_module.events_collection.find({"user_id": canonical_id}))
        profile = app_module.profiles_collection.find_one({"_id": canonical_id})

        self.assertEqual(len(sessions), 2)
        self.assertEqual(len(events), 2)
        self.assertEqual(profile["user_id"], canonical_id)
        self.assertEqual(profile["anonymous_ids"], [anonymous_id])

        authenticated_session = self._start_session(anonymous_id, token)
        authenticated_session_doc = app_module.sessions_collection.find_one({
            "_id": ObjectId(authenticated_session)
        })
        self.assertEqual(authenticated_session_doc["user_id"], canonical_id)
        self.assertEqual(authenticated_session_doc["identity_status"], "authenticated")

        self.client.post(
            "/api/auth/login",
            json={
                "email": "canonical@example.com",
                "password": "SecurePassword123",
                "anonymous_id": anonymous_id,
            },
        )
        self.assertEqual(
            app_module.profiles_collection.count_documents({"email": "canonical@example.com"}),
            1,
        )
        self.assertEqual(
            app_module.sessions_collection.count_documents({"user_id": canonical_id}),
            3,
        )

    def test_cart_wishlist_and_orders_share_the_canonical_customer_id(self):
        anonymous_id = "anon_purchase_identity"
        user_id, token = self._signup_and_login("purchase@example.com", anonymous_id)
        canonical_id = ObjectId(user_id)
        auth_headers = {"Authorization": f"Bearer {token}"}

        cart = self.client.post("/api/cart", json={
            "user_id": user_id,
            "anonymous_id": anonymous_id,
            "product_id": str(self.product_id),
            "quantity": 2,
        }, headers=auth_headers)
        self.assertEqual(cart.status_code, 200, cart.get_json())
        wishlist = self.client.post("/api/wishlist", json={
            "user_id": user_id,
            "anonymous_id": anonymous_id,
            "product_id": str(self.product_id),
        }, headers=auth_headers)
        self.assertEqual(wishlist.status_code, 200, wishlist.get_json())

        order = self.client.post(
            "/api/orders",
            json={"customer_id": user_id},
            headers=auth_headers,
        )
        self.assertEqual(order.status_code, 201, order.get_json())
        order_id = ObjectId(order.get_json()["data"]["order_id"])

        self.assertEqual(
            app_module.cart_collection.count_documents({"user_id": canonical_id}),
            0,
        )
        self.assertEqual(
            app_module.wishlist_collection.count_documents({"user_id": canonical_id}),
            1,
        )
        self.assertEqual(
            app_module.orders_collection.count_documents({"user_id": canonical_id}),
            1,
        )
        self.assertEqual(
            app_module.orders_collection.find_one({"_id": order_id})["user_id"],
            canonical_id,
        )

    def test_multiple_leads_retain_one_customer_identity(self):
        user_id = ObjectId()
        session_id = ObjectId()
        session = {
            "_id": session_id,
            "visitor_id": "legacy-email@example.com",
            "anonymous_id": "anon_lead_identity",
            "user_id": user_id,
        }
        sessions = app_module.sessions_collection
        events = app_module.events_collection
        leads = app_module.leads_collection
        sessions.insert_one(session)

        prediction = {
            "score": 0.8,
            "segment": "Hot",
            "next_action": "Follow up",
            "prediction_time": "2026-09-19T00:00:00+00:00",
            "model_version": "test",
        }
        with patch("lead_processing_service.predict_session", return_value=prediction), \
             patch("lead_processing_service.adapt_behavioral_features", return_value={}), \
             patch("lead_processing_service.aggregate_session_features", return_value={
                 "landing_source": "test",
                 "landing_page": "/",
                 "event_count": 0,
                 "page_views": 0,
                 "high_intent_page_visits": 0,
                 "form_submit_count": 0,
             }):
            first = process_session(session_id, sessions, events, leads)
            second_session_id = sessions.insert_one({
                **session,
                "_id": ObjectId(),
            }).inserted_id
            second = process_session(second_session_id, sessions, events, leads)

        self.assertEqual(leads.count_documents({"user_id": user_id}), 2)
        self.assertEqual(first["user_id"], user_id)
        self.assertEqual(second["user_id"], user_id)
        self.assertEqual(leads.count_documents({"visitor_id": session["visitor_id"]}), 2)


if __name__ == "__main__":
    unittest.main()
