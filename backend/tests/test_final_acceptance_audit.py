import os
import sys
import unittest
from bson import ObjectId

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import (
    app,
    cart_collection,
    events_collection,
    orders_collection,
    products_collection,
    profiles_collection,
    sessions_collection,
    wishlist_collection,
)

class FinalAcceptanceAuditTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.admin_user = os.environ.get("ADMIN_USERNAME", "test_admin")
        self.admin_pass = os.environ.get("ADMIN_PASSWORD", "test_admin_password")

        # Create 2 test products in products_collection
        self.prod1_id = ObjectId()
        self.prod2_id = ObjectId()
        products_collection.insert_many([
            {
                "_id": self.prod1_id,
                "product_id": f"myntra_{self.prod1_id}",
                "name": "Organic Summer Linen Shirt",
                "title": "Organic Summer Linen Shirt",
                "price": 1299.0,
                "current_price": 1299.0,
                "mrp": 2199.0,
                "discount_percent": 40,
                "category": "Shirts",
                "brand": "Zara",
                "gender": "Men",
                "rating": 4.5,
                "reviews_count": 88,
                "in_stock": True,
                "image": "https://images.unsplash.com/photo-1596755094514-f87e34085b2c",
                "images": ["https://images.unsplash.com/photo-1596755094514-f87e34085b2c"],
                "sizes": ["S", "M", "L", "XL"],
                "colors": ["White", "Beige"]
            },
            {
                "_id": self.prod2_id,
                "product_id": f"myntra_{self.prod2_id}",
                "name": "Heavyweight French Terry Hoodie",
                "title": "Heavyweight French Terry Hoodie",
                "price": 2499.0,
                "current_price": 2499.0,
                "mrp": 3499.0,
                "discount_percent": 28,
                "category": "Hoodies",
                "brand": "H&M",
                "gender": "Men",
                "rating": 4.8,
                "reviews_count": 140,
                "in_stock": True,
                "image": "https://images.unsplash.com/photo-1556905055-8f358a7a47b2",
                "images": ["https://images.unsplash.com/photo-1556905055-8f358a7a47b2"],
                "sizes": ["M", "L"],
                "colors": ["Black", "Heather Grey"]
            }
        ])

    def _get_admin_token(self):
        res = self.client.post("/api/auth/admin/login", json={
            "username": self.admin_user,
            "password": self.admin_pass
        })
        self.assertEqual(res.status_code, 200, res.get_json())
        data = res.get_json()["data"]
        return data["token"]

    def _create_customer(self, email="test_customer@example.com"):
        signup_res = self.client.post("/api/auth/signup", json={
            "email": email,
            "password": "Password123!",
            "full_name": "Test Shopper",
            "phone": "+919876543210"
        })
        self.assertEqual(signup_res.status_code, 200, signup_res.get_json())
        user_id = signup_res.get_json()["data"]["user_id"]

        login_res = self.client.post("/api/auth/login", json={
            "email": email,
            "password": "Password123!"
        })
        self.assertEqual(login_res.status_code, 200, login_res.get_json())
        token = login_res.get_json()["data"]["token"]
        return user_id, token, email

    # -------------------------------------------------------------
    # 1. Product Catalog Endpoints
    # -------------------------------------------------------------
    def test_01_product_catalog_endpoints(self):
        # GET /api/products
        res = self.client.get("/api/products?page=1&limit=10")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("success", False))
        self.assertIsInstance(data.get("data"), list)
        self.assertGreaterEqual(len(data["data"]), 2)

        # GET /api/products/<id>
        res = self.client.get(f"/api/products/{self.prod1_id}")
        self.assertEqual(res.status_code, 200)
        p_data = res.get_json()["data"]
        self.assertEqual(p_data["brand"], "Zara")
        self.assertEqual(p_data["category"], "Shirts")

        # GET /api/products/meta
        res = self.client.get("/api/products/meta")
        self.assertEqual(res.status_code, 200)
        meta = res.get_json()
        self.assertTrue(meta.get("success", False))

    # -------------------------------------------------------------
    # 2. Authentication & Authorization Guards
    # -------------------------------------------------------------
    def test_02_auth_and_role_guards(self):
        user_id, user_token, email = self._create_customer("auth_test@example.com")
        admin_token = self._get_admin_token()

        # Login endpoint validation
        login_res = self.client.post("/api/auth/login", json={
            "email": email,
            "password": "Password123!"
        })
        self.assertEqual(login_res.status_code, 200)
        self.assertIn("token", login_res.get_json()["data"])

        # Invalid login
        bad_login = self.client.post("/api/auth/login", json={
            "email": email,
            "password": "WrongPassword!"
        })
        self.assertIn(bad_login.status_code, [400, 401])

        # Admin route without auth -> 401
        res = self.client.get("/api/admin/intelligence/overview")
        self.assertEqual(res.status_code, 401)

        # Admin route with normal customer token -> 403
        res = self.client.get(
            "/api/admin/intelligence/overview",
            headers={"Authorization": f"Bearer {user_token}"}
        )
        self.assertEqual(res.status_code, 403)

        # Admin route with valid admin token -> 200
        res = self.client.get(
            "/api/admin/intelligence/overview",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        self.assertEqual(res.status_code, 200)

    # -------------------------------------------------------------
    # 3. Session & Behavioral Tracking
    # -------------------------------------------------------------
    def test_03_session_and_event_tracking(self):
        # Start customer session
        start_res = self.client.post("/api/session/start", json={
            "visitor_id": "session_test@example.com",
            "anonymous_id": "anon_session_123"
        })
        self.assertEqual(start_res.status_code, 200)
        session_id = start_res.get_json()["data"]["session_id"]
        self.assertTrue(session_id)

        # Track session event
        event_res = self.client.post("/api/session/event", json={
            "session_id": session_id,
            "event_type": "product_view",
            "page": "/product/1",
            "entity": {"type": "product", "id": str(self.prod1_id)},
            "metadata": {"brand": "Zara"}
        })
        self.assertEqual(event_res.status_code, 200)

        # End session
        end_res = self.client.post("/api/session/end", json={
            "session_id": session_id
        })
        self.assertEqual(end_res.status_code, 200)

    # -------------------------------------------------------------
    # 4. Cart, Wishlist, and Selective Checkout Lifecycle
    # -------------------------------------------------------------
    def test_04_cart_wishlist_selective_checkout(self):
        user_id, token, email = self._create_customer("checkout_test@example.com")
        headers = {"Authorization": f"Bearer {token}"}

        # 4a. Add Item 1 and Item 2 to cart
        add1 = self.client.post("/api/cart", json={
            "user_id": user_id,
            "product_id": str(self.prod1_id),
            "quantity": 2
        }, headers=headers)
        self.assertEqual(add1.status_code, 200)

        add2 = self.client.post("/api/cart", json={
            "user_id": user_id,
            "product_id": str(self.prod2_id),
            "quantity": 1
        }, headers=headers)
        self.assertEqual(add2.status_code, 200)

        # Verify cart has both items
        cart_res = self.client.get(f"/api/cart?user_id={user_id}", headers=headers)
        self.assertEqual(cart_res.status_code, 200)
        cart_items = cart_res.get_json()["data"]
        self.assertEqual(len(cart_items), 2)

        # 4b. Perform selective checkout of ONLY Item 1
        checkout_res = self.client.post("/api/orders", json={
            "user_id": user_id,
            "items": [{"product_id": str(self.prod1_id), "quantity": 2}],
            "shipping_address": {"city": "Bengaluru", "zip": "560001"}
        }, headers=headers)
        self.assertIn(checkout_res.status_code, [200, 201], checkout_res.get_json())
        order_res_data = checkout_res.get_json()["data"]
        order_id = order_res_data["order_id"]
        self.assertEqual(order_res_data["status"], "placed")

        # Verify order in database
        order_doc = orders_collection.find_one({"_id": ObjectId(order_id)})
        self.assertIsNotNone(order_doc)
        self.assertEqual(len(order_doc["items"]), 1)
        self.assertEqual(order_doc["items"][0]["product_id"], f"myntra_{self.prod1_id}")
        self.assertEqual(order_doc["total_amount"], 1299.0 * 2)

        # 4c. Verify that unselected Item 2 is PRESERVED in cart
        cart_after = self.client.get(f"/api/cart?user_id={user_id}", headers=headers)
        self.assertEqual(cart_after.status_code, 200)
        remaining = cart_after.get_json()["data"]
        self.assertEqual(len(remaining), 1, "Unselected item must remain in cart!")
        self.assertEqual(remaining[0]["product_id"], f"myntra_{self.prod2_id}")

        # 4d. Verify customer order history & ownership
        orders_res = self.client.get(f"/api/orders?user_id={user_id}", headers=headers)
        self.assertEqual(orders_res.status_code, 200)
        orders_list = orders_res.get_json()["data"]
        self.assertEqual(len(orders_list), 1)
        self.assertEqual(str(orders_list[0]["_id"]), str(order_id))

        # 4e. Cross-customer ownership check: Customer 2 cannot see Customer 1's orders
        user2_id, token2, _ = self._create_customer("other_customer@example.com")
        orders2_res = self.client.get(f"/api/orders?user_id={user2_id}", headers={"Authorization": f"Bearer {token2}"})
        self.assertEqual(orders2_res.status_code, 200)
        self.assertEqual(len(orders2_res.get_json()["data"]), 0)

        # 4f. Wishlist add, fetch, remove
        w_add = self.client.post("/api/wishlist", json={
            "user_id": user_id,
            "product_id": str(self.prod1_id)
        }, headers=headers)
        self.assertEqual(w_add.status_code, 200)

        w_get = self.client.get(f"/api/wishlist?user_id={user_id}", headers=headers)
        self.assertEqual(w_get.status_code, 200)
        self.assertEqual(len(w_get.get_json()["data"]), 1)

        w_del = self.client.delete(f"/api/wishlist/{self.prod1_id}?user_id={user_id}", headers=headers)
        self.assertEqual(w_del.status_code, 200)

    # -------------------------------------------------------------
    # 5. Admin Intelligence Endpoints Suite
    # -------------------------------------------------------------
    def test_05_admin_intelligence_endpoints(self):
        admin_token = self._get_admin_token()
        headers = {"Authorization": f"Bearer {admin_token}"}

        # 5a. Overview
        res = self.client.get("/api/admin/intelligence/overview", headers=headers)
        self.assertEqual(res.status_code, 200)

        # 5b. Leads directory
        res = self.client.get("/api/admin/intelligence/leads?page=1&limit=10", headers=headers)
        self.assertEqual(res.status_code, 200)

        # 5c. Lead distribution
        res = self.client.get("/api/admin/intelligence/lead-distribution", headers=headers)
        self.assertEqual(res.status_code, 200)

        # 5d. Recent leads
        res = self.client.get("/api/admin/intelligence/recent-leads?page=1&limit=5", headers=headers)
        self.assertEqual(res.status_code, 200)

        # 5e. Marketing activity
        res = self.client.get("/api/admin/intelligence/marketing-activity?page=1&limit=5", headers=headers)
        self.assertEqual(res.status_code, 200)

        # 5f. Notifications
        res = self.client.get("/api/admin/intelligence/notifications", headers=headers)
        self.assertEqual(res.status_code, 200)

        # 5g. Mark all read
        res = self.client.post("/api/admin/intelligence/notifications/mark-all-read", headers=headers)
        self.assertEqual(res.status_code, 200)

        # 5h. Funnel
        res = self.client.get("/api/admin/intelligence/funnel", headers=headers)
        self.assertEqual(res.status_code, 200)

        # 5i. RFM
        res = self.client.get("/api/admin/intelligence/rfm", headers=headers)
        self.assertEqual(res.status_code, 200)

        # 5j. Retention
        res = self.client.get("/api/admin/intelligence/retention", headers=headers)
        self.assertEqual(res.status_code, 200)

        # 5k. Revenue attribution
        res = self.client.get("/api/admin/intelligence/revenue-attribution", headers=headers)
        self.assertEqual(res.status_code, 200)

        # 5l. Recent activity
        res = self.client.get("/api/admin/intelligence/recent-activity?limit=10", headers=headers)
        self.assertEqual(res.status_code, 200)

        # 5m. Simulation
        res = self.client.post("/api/admin/intelligence/simulate", json={
            "feature_overrides": {"cart_add_count": 5, "total_spend": 5000}
        }, headers=headers)
        self.assertEqual(res.status_code, 200)

    # -------------------------------------------------------------
    # 6. Failed Checkout Preserves Cart State & Validation
    # -------------------------------------------------------------
    def test_06_failed_checkout_preserves_cart_and_edge_cases(self):
        # 6a. Empty cart checkout rejection
        empty_user_id, empty_token, _ = self._create_customer("empty_cart@example.com")
        fail_empty = self.client.post("/api/orders", json={
            "user_id": empty_user_id,
        }, headers={"Authorization": f"Bearer {empty_token}"})
        self.assertIn(fail_empty.status_code, [400, 422, 500])

        # 6b. User with valid item has a failed checkout (e.g. unavailable product)
        user_id, token, _ = self._create_customer("failed_checkout@example.com")
        headers = {"Authorization": f"Bearer {token}"}

        # Put item in cart
        add = self.client.post("/api/cart", json={
            "user_id": user_id,
            "product_id": str(self.prod1_id),
            "quantity": 1
        }, headers=headers)
        self.assertEqual(add.status_code, 200)

        # Temporarily make product price None to trigger validation error during checkout
        products_collection.update_one({"_id": self.prod1_id}, {"$set": {"price": None, "current_price": None}})
        try:
            fail_res = self.client.post("/api/orders", json={
                "user_id": user_id,
            }, headers=headers)
            self.assertIn(fail_res.status_code, [400, 500])

            # Verify that the cart still retains the existing product
            cart_after = self.client.get(f"/api/cart?user_id={user_id}", headers=headers)
            self.assertEqual(cart_after.status_code, 200)
            cart_items = cart_after.get_json()["data"]
            self.assertEqual(len(cart_items), 1, "Failed checkout must never delete existing cart contents!")
        finally:
            products_collection.update_one({"_id": self.prod1_id}, {"$set": {"price": 1299.0, "current_price": 1299.0}})

    # -------------------------------------------------------------
    # 7. Recommendations & Embedded Analytics Endpoints
    # -------------------------------------------------------------
    def test_07_recommendations_and_embedded_analytics(self):
        user_id, token, _ = self._create_customer("rec_analytics@example.com")
        admin_token = self._get_admin_token()
        headers = {"Authorization": f"Bearer {token}"}
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        # Recommendations endpoint
        rec_res = self.client.get(f"/api/recommendations?user_id={user_id}&limit=4")
        self.assertEqual(rec_res.status_code, 200)

        # Embedded admin / legacy endpoints with admin token
        res_overview = self.client.get("/api/analytics/overview", headers=admin_headers)
        self.assertEqual(res_overview.status_code, 200)

        res_events = self.client.get("/api/analytics/events", headers=admin_headers)
        self.assertEqual(res_events.status_code, 200)

        res_leads = self.client.get("/api/leads", headers=admin_headers)
        self.assertEqual(res_leads.status_code, 200)

        res_sessions = self.client.get("/api/sessions", headers=admin_headers)
        self.assertEqual(res_sessions.status_code, 200)

        res_profiles = self.client.get("/api/profiles", headers=admin_headers)
        self.assertEqual(res_profiles.status_code, 200)

if __name__ == "__main__":
    unittest.main()
