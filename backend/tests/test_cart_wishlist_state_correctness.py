"""Focused regression tests for Phase 1: Current Cart & Wishlist State Correctness.

Tests:
1. Complete 12-step scenario separating current state from historical activity:
   - Customer adds 5 products to wishlist (wishlist = 5)
   - Moves 3 products from wishlist to cart (wishlist = 2, cart = 3)
   - Places order for 2 of the 3 cart products (wishlist = 2, cart = 1, orders = 1)
   - Purchased products removed from cart; unpurchased item remains
   - Historical events preserved in event log
   - Historical events do NOT alter current state
   - Admin Customer 360 reads current state accurately
   - Customer isolation / no IDOR between customers
2. Removing an item from cart
3. Removing an item from wishlist
4. Empty cart & empty wishlist state
5. Duplicate wishlist addition (idempotent)
6. Duplicate cart addition (quantity increment, distinct count preserved)
"""

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from bson import ObjectId
import jwt

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module
from app import (
    app,
    db,
    cart_collection,
    wishlist_collection,
    orders_collection,
    products_collection,
    profiles_collection,
    events_collection,
    JWT_SECRET,
)
from admin_intelligence_service import (
    get_customer_intelligence_detail,
    _resolve_cart,
    _resolve_wishlist,
    _compute_behavior_summary,
)


class TestCartWishlistStateCorrectness(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.jwt_secret = JWT_SECRET

        # Insert 6 sample products for testing
        self.products = []
        for i in range(1, 7):
            p_id = ObjectId()
            prod_doc = {
                "_id": p_id,
                "name": f"Test Garment {i}",
                "brand": "LeadBrand",
                "category": "Apparel",
                "gender": "Unisex",
                "price": 100.0 * i,
                "image": f"https://example.com/item{i}.jpg",
            }
            products_collection.insert_one(prod_doc)
            self.products.append(prod_doc)

    def _make_token(self, user_id, role="user"):
        exp_time = datetime.now(timezone.utc) + timedelta(hours=1)
        return jwt.encode(
            {"sub": str(user_id), "role": role, "exp": exp_time},
            self.jwt_secret,
            algorithm="HS256",
        )

    def _create_customer(self, email="customer1@example.com"):
        user_id = ObjectId()
        profiles_collection.insert_one({
            "_id": user_id,
            "email": email,
            "full_name": "Test Customer",
            "username": email.split("@")[0],
            "role": "user",
            "created_at": datetime.now(timezone.utc),
        })
        token = self._make_token(user_id, role="user")
        return user_id, token

    def test_full_twelve_step_state_correctness_scenario(self):
        """Execute the exact 12-step scenario verifying current state vs. historical activity."""

        # Step 1: Create one customer
        cust1_id, cust1_token = self._create_customer("twelve_steps@example.com")
        headers = {"Authorization": f"Bearer {cust1_token}"}

        # Step 2: Add 5 distinct products to wishlist
        p1, p2, p3, p4, p5 = self.products[:5]
        for p in [p1, p2, p3, p4, p5]:
            res = self.client.post(
                "/api/wishlist",
                json={"product_id": str(p["_id"])},
                headers=headers,
            )
            self.assertEqual(res.status_code, 200, res.get_json())

        # Step 3: Verify current wishlist = 5
        res = self.client.get("/api/wishlist", headers=headers)
        self.assertEqual(res.status_code, 200)
        wishlist_data = res.get_json()["data"]
        self.assertEqual(len(wishlist_data), 5)
        self.assertEqual(wishlist_collection.count_documents({"user_id": cust1_id}), 5)

        # Step 4: Move/remove 3 products (p1, p2, p3) from wishlist and add them to cart
        for p in [p1, p2, p3]:
            # Add to cart
            res_cart = self.client.post(
                "/api/cart",
                json={"product_id": str(p["_id"]), "quantity": 1},
                headers=headers,
            )
            self.assertEqual(res_cart.status_code, 200)
            # Remove from wishlist
            res_wl = self.client.delete(f"/api/wishlist/{str(p['_id'])}", headers=headers)
            self.assertEqual(res_wl.status_code, 200)

        # Step 5: Verify current wishlist = 2, current cart = 3
        res_wl = self.client.get("/api/wishlist", headers=headers)
        self.assertEqual(len(res_wl.get_json()["data"]), 2)
        self.assertEqual(wishlist_collection.count_documents({"user_id": cust1_id}), 2)

        res_cart = self.client.get("/api/cart", headers=headers)
        cart_items = res_cart.get_json()["data"]
        self.assertEqual(len(cart_items), 3)
        self.assertEqual(cart_collection.count_documents({"user_id": cust1_id}), 3)

        # Step 6: Place an order containing 2 of the cart products (p1, p2)
        res_order = self.client.post(
            "/api/orders",
            json={
                "customer_id": str(cust1_id),
                "items": [str(p1["_id"]), str(p2["_id"])],
                "payment_method": "Credit Card",
            },
            headers=headers,
        )
        self.assertIn(res_order.status_code, [200, 201], res_order.get_json())
        order_id = res_order.get_json()["data"]["order_id"]

        # Step 7: Verify current wishlist = 2, current cart = 1, orders = 1
        res_wl = self.client.get("/api/wishlist", headers=headers)
        self.assertEqual(len(res_wl.get_json()["data"]), 2)

        res_cart = self.client.get("/api/cart", headers=headers)
        remaining_cart = res_cart.get_json()["data"]
        self.assertEqual(len(remaining_cart), 1)
        self.assertEqual(orders_collection.count_documents({"user_id": cust1_id}), 1)

        # Step 8: Verify the purchased products do NOT remain in current cart
        remaining_product_ids = [item["product_id"] for item in remaining_cart]
        self.assertNotIn(str(p1["_id"]), remaining_product_ids)
        self.assertNotIn(str(p2["_id"]), remaining_product_ids)
        self.assertIn(str(p3["_id"]), remaining_product_ids)

        # Step 9: Verify historical events still contain the relevant actions
        # Insert or verify commerce events
        events_collection.insert_many([
            {
                "user_id": cust1_id,
                "event_type": "wishlist_add",
                "timestamp": datetime.now(timezone.utc),
                "entity": {"type": "product", "id": str(p1["_id"])},
            },
            {
                "user_id": cust1_id,
                "event_type": "add_to_cart",
                "timestamp": datetime.now(timezone.utc),
                "entity": {"type": "product", "id": str(p1["_id"])},
            },
        ])
        order_events = list(events_collection.find({"user_id": cust1_id, "event_type": "order_placed"}))
        self.assertGreaterEqual(len(order_events), 1)

        # Step 10: Verify historical events do NOT affect current cart/wishlist counts
        # Inject additional historical add_to_cart and wishlist_add events
        events_collection.insert_many([
            {
                "user_id": cust1_id,
                "event_type": "add_to_cart",
                "timestamp": datetime.now(timezone.utc),
                "entity": {"type": "product", "id": str(self.products[5]["_id"])},
                "metadata": {"quantity": 10},
            },
            {
                "user_id": cust1_id,
                "event_type": "wishlist_add",
                "timestamp": datetime.now(timezone.utc),
                "entity": {"type": "product", "id": str(self.products[5]["_id"])},
            },
        ])
        # Current cart and wishlist MUST remain 1 and 2 respectively
        res_cart = self.client.get("/api/cart", headers=headers)
        self.assertEqual(len(res_cart.get_json()["data"]), 1)
        res_wl = self.client.get("/api/wishlist", headers=headers)
        self.assertEqual(len(res_wl.get_json()["data"]), 2)

        # Step 11: Verify admin Customer 360 returns the same current state
        admin_id = ObjectId()
        admin_token = self._make_token(admin_id, role="admin")
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        admin_res = self.client.get(
            f"/api/admin/intelligence/customers/{str(cust1_id)}",
            headers=admin_headers,
        )
        self.assertEqual(admin_res.status_code, 200)
        detail = admin_res.get_json()["data"]

        # Current cart in Customer 360 has only 1 item (p3)
        self.assertEqual(len(detail["cart"]), 1)
        self.assertEqual(detail["cart"][0]["product_id"], str(p3["_id"]))
        self.assertEqual(detail["cart"][0]["quantity"], 1)
        self.assertEqual(detail["cart"][0]["price"], p3["price"])
        self.assertEqual(detail["cart"][0]["subtotal"], p3["price"])

        # Current wishlist in Customer 360 has only 2 items (p4, p5)
        self.assertEqual(len(detail["wishlist"]), 2)
        wishlist_pids = [item["product_id"] for item in detail["wishlist"]]
        self.assertIn(str(p4["_id"]), wishlist_pids)
        self.assertIn(str(p5["_id"]), wishlist_pids)
        self.assertNotIn(str(p1["_id"]), wishlist_pids)
        self.assertNotIn(str(p2["_id"]), wishlist_pids)
        self.assertNotIn(str(p3["_id"]), wishlist_pids)

        # Orders in Customer 360 has 1 placed order
        self.assertEqual(len(detail["orders"]), 1)

        # Behavior summary reflects canonical counts
        bs = detail["behavior_summary"]
        self.assertEqual(bs["cart_current_count"], 1)
        self.assertEqual(bs["wishlist_current_count"], 2)
        self.assertEqual(bs["orders_count"], 1)

        # Step 12: Verify another customer cannot access this customer's cart/wishlist
        cust2_id, cust2_token = self._create_customer("intruder@example.com")
        cust2_headers = {"Authorization": f"Bearer {cust2_token}"}

        res2_cart = self.client.get("/api/cart", headers=cust2_headers)
        self.assertEqual(len(res2_cart.get_json()["data"]), 0)

        res2_wl = self.client.get("/api/wishlist", headers=cust2_headers)
        self.assertEqual(len(res2_wl.get_json()["data"]), 0)

        # Intruder cannot query admin intelligence
        unauth_admin = self.client.get(
            f"/api/admin/intelligence/customers/{str(cust1_id)}",
            headers=cust2_headers,
        )
        self.assertIn(unauth_admin.status_code, [401, 403])

    def test_cart_item_removal(self):
        """Test removing an item from the cart decreases count and deletes document."""
        cust_id, token = self._create_customer("cart_remove@example.com")
        headers = {"Authorization": f"Bearer {token}"}
        p = self.products[0]

        # Add to cart
        self.client.post("/api/cart", json={"product_id": str(p["_id"]), "quantity": 1}, headers=headers)
        self.assertEqual(cart_collection.count_documents({"user_id": cust_id}), 1)

        # Remove from cart
        res = self.client.delete(f"/api/cart/{str(p['_id'])}", headers=headers)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.get_json()["data"]), 0)
        self.assertEqual(cart_collection.count_documents({"user_id": cust_id}), 0)

    def test_wishlist_item_removal(self):
        """Test removing an item from wishlist deletes document."""
        cust_id, token = self._create_customer("wl_remove@example.com")
        headers = {"Authorization": f"Bearer {token}"}
        p = self.products[0]

        # Add to wishlist
        self.client.post("/api/wishlist", json={"product_id": str(p["_id"])}, headers=headers)
        self.assertEqual(wishlist_collection.count_documents({"user_id": cust_id}), 1)

        # Remove from wishlist
        res = self.client.delete(f"/api/wishlist/{str(p['_id'])}", headers=headers)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.get_json()["data"]), 0)
        self.assertEqual(wishlist_collection.count_documents({"user_id": cust_id}), 0)

    def test_empty_cart_and_empty_wishlist_admin_resolution(self):
        """Verify empty cart and wishlist resolve to [] without historical reanimation."""
        cust_id, _ = self._create_customer("empty_state@example.com")

        # Inject historical events that would previously trick Strategy 2
        events_collection.insert_many([
            {
                "user_id": cust_id,
                "event_type": "add_to_cart",
                "timestamp": datetime.now(timezone.utc),
                "entity": {"type": "product", "id": str(self.products[0]["_id"])},
                "metadata": {"quantity": 3},
            },
            {
                "user_id": cust_id,
                "event_type": "wishlist_add",
                "timestamp": datetime.now(timezone.utc),
                "entity": {"type": "product", "id": str(self.products[1]["_id"])},
            },
        ])

        # State is actually empty
        cart_resolved = _resolve_cart(cust_id, db)
        wishlist_resolved = _resolve_wishlist(cust_id, db)
        self.assertEqual(cart_resolved, [])
        self.assertEqual(wishlist_resolved, [])

        bs = _compute_behavior_summary(cust_id, db)["behavior_summary"]
        self.assertEqual(bs["cart_current_count"], 0)
        self.assertEqual(bs["wishlist_current_count"], 0)
        # But historical adds count reflects events
        self.assertEqual(bs["cart_adds_count"], 1)
        self.assertEqual(bs["wishlist_adds_count"], 1)

    def test_duplicate_wishlist_addition(self):
        """Adding the same product to wishlist twice must be idempotent."""
        cust_id, token = self._create_customer("dup_wishlist@example.com")
        headers = {"Authorization": f"Bearer {token}"}
        p = self.products[0]

        res1 = self.client.post("/api/wishlist", json={"product_id": str(p["_id"])}, headers=headers)
        self.assertEqual(res1.status_code, 200)
        self.assertEqual(len(res1.get_json()["data"]), 1)

        res2 = self.client.post("/api/wishlist", json={"product_id": str(p["_id"])}, headers=headers)
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(len(res2.get_json()["data"]), 1)
        self.assertEqual(wishlist_collection.count_documents({"user_id": cust_id}), 1)

    def test_duplicate_cart_addition(self):
        """Adding the same product to cart increments quantity while keeping distinct item count = 1."""
        cust_id, token = self._create_customer("dup_cart@example.com")
        headers = {"Authorization": f"Bearer {token}"}
        p = self.products[0]

        res1 = self.client.post("/api/cart", json={"product_id": str(p["_id"]), "quantity": 2}, headers=headers)
        self.assertEqual(res1.status_code, 200)
        self.assertEqual(res1.get_json()["data"][0]["quantity"], 2)

        res2 = self.client.post("/api/cart", json={"product_id": str(p["_id"]), "quantity": 3}, headers=headers)
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(res2.get_json()["data"][0]["quantity"], 5)

        # Distinct cart document count is still 1
        self.assertEqual(cart_collection.count_documents({"user_id": cust_id}), 1)

        # Behavior summary distinguishes distinct count vs total quantity
        bs = _compute_behavior_summary(cust_id, db)["behavior_summary"]
        self.assertEqual(bs["cart_current_count"], 1)
        self.assertEqual(bs["cart_total_quantity"], 5)


if __name__ == "__main__":
    unittest.main()
