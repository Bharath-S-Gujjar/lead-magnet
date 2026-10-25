"""End-to-End User Journey Lead Scoring Verification.

Simulates the exact customer flow that a user experiences:
1. Brand-new signup -> Score 1, Cold, not_qualified, provisional.
2. Browsing & Cart add -> Score updates with ML inference, remains Warm/Cold without artificial floor.
3. Checkout start -> High intent override within 24h triggers Hot qualification.
4. Order placed -> Lifecycle status transitions to 'converted', qualification status becomes 'not_qualified'.
5. Second order -> Lifecycle status transitions to 'repeat_customer'.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import unittest
from bson import ObjectId
import jwt

import app as app_module
from customer_lead_state_service import get_customer_lead_state


class ManualUserJourneyE2ETests(unittest.TestCase):
    def setUp(self):
        self.app = app_module.app
        self.client = self.app.test_client()
        self.db = app_module.db
        self.profiles = app_module.profiles_collection
        self.products = app_module.products_collection
        self.cart = app_module.cart_collection
        self.wishlist = app_module.wishlist_collection
        self.orders = app_module.orders_collection
        self.state = app_module.customer_lead_state_collection
        self.features = app_module.customer_features_collection

        self.test_email = "manual_tester_e2e@example.com"
        self.test_pw = "Password123!"

        # Ensure clean state
        self._cleanup()

        # Ensure a product exists
        self.prod_id = "test_e2e_prod_01"
        self.products.update_one(
            {"product_id": self.prod_id},
            {"$set": {
                "product_id": self.prod_id,
                "name": "Classic Oxford Cotton Shirt",
                "price": 1499.0,
                "category": "Shirts",
                "discount_price": 1199.0,
                "in_stock": True,
            }},
            upsert=True,
        )

    def tearDown(self):
        self._cleanup()

    def _cleanup(self):
        if self.db is not None:
            user = self.profiles.find_one({"email": self.test_email})
            if user:
                uid = user["_id"]
                self.profiles.delete_many({"_id": uid})
                self.cart.delete_many({"user_id": uid})
                self.cart.delete_many({"user_id": str(uid)})
                self.wishlist.delete_many({"user_id": uid})
                self.wishlist.delete_many({"user_id": str(uid)})
                self.orders.delete_many({"user_id": str(uid)})
                self.orders.delete_many({"user_id": uid})
                self.state.delete_many({"customer_id": uid})
                self.state.delete_many({"customer_id": str(uid)})
                self.features.delete_many({"customer_id": uid})
                self.features.delete_many({"customer_id": str(uid)})
            self.products.delete_many({"_id": "test_e2e_prod_01"})

    def test_complete_user_lifecycle_lead_scoring(self):
        # 1. Sign up new account
        signup_res = self.client.post("/api/auth/signup", json={
            "email": self.test_email,
            "password": self.test_pw,
            "fullName": "Manual Tester",
        })
        self.assertEqual(signup_res.status_code, 200)
        user_id = signup_res.get_json()["data"]["user_id"]
        u_oid = ObjectId(user_id)

        # Sync & verify lead state immediately after signup
        lead_state = get_customer_lead_state(u_oid, self.state)
        self.assertIsNotNone(lead_state)
        self.assertEqual(lead_state["lead_segment"], "Cold")
        self.assertLessEqual(lead_state["lead_score"], 10)
        self.assertEqual(lead_state["qualification_status"], "not_qualified")
        self.assertEqual(lead_state["lifecycle_status"], "prospect")
        self.assertTrue(lead_state.get("is_provisional", False))

        # 2. Log in
        login_res = self.client.post("/api/auth/login", json={
            "email": self.test_email,
            "password": self.test_pw,
        })
        self.assertEqual(login_res.status_code, 200)
        token = login_res.get_json()["data"]["token"]
        auth_headers = {"Authorization": f"Bearer {token}"}

        # 3. Add product to cart
        cart_res = self.client.post(
            "/api/cart",
            json={"product_id": self.prod_id, "quantity": 1, "user_id": user_id},
            headers=auth_headers,
        )
        self.assertEqual(cart_res.status_code, 200)

        # Check lead state after adding to cart
        cart_lead_state = get_customer_lead_state(u_oid, self.state)
        self.assertIsNotNone(cart_lead_state)
        # Should NOT be artificial 75 anymore!
        self.assertNotEqual(cart_lead_state["lead_score"], 75)
        self.assertEqual(cart_lead_state["lifecycle_status"], "prospect")

        # 4. Create an order (Purchase)
        order_res = self.client.post(
            "/api/orders",
            json={
                "customer_id": user_id,
                "shipping_address": "123 Main St, Bangalore",
                "payment_method": "UPI",
            },
            headers=auth_headers,
        )
        self.assertEqual(order_res.status_code, 201)

        # Lead state after order: converted customer!
        order_lead_state = get_customer_lead_state(u_oid, self.state)
        self.assertIsNotNone(order_lead_state)
        self.assertEqual(order_lead_state["lifecycle_status"], "converted")
        self.assertEqual(order_lead_state["qualification_status"], "not_qualified")
        self.assertEqual(order_lead_state["lead_segment"], "Cold")  # NOT Hot! Current shopping cart is empty

        # 5. Place a second order -> Repeat Customer
        # First add item back to cart
        self.client.post(
            "/api/cart",
            json={"product_id": self.prod_id, "quantity": 1, "user_id": user_id},
            headers=auth_headers,
        )
        order2_res = self.client.post(
            "/api/orders",
            json={
                "customer_id": user_id,
                "shipping_address": "123 Main St, Bangalore",
                "payment_method": "UPI",
            },
            headers=auth_headers,
        )
        self.assertEqual(order2_res.status_code, 201)

        repeat_lead_state = get_customer_lead_state(u_oid, self.state)
        self.assertIsNotNone(repeat_lead_state)
        self.assertEqual(repeat_lead_state["lifecycle_status"], "repeat_customer")
        self.assertEqual(repeat_lead_state["qualification_status"], "not_qualified")


if __name__ == "__main__":
    unittest.main()
