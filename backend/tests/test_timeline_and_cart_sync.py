"""Comprehensive Regression Test Suite for Timeline & Cart Synchronization.
=============================================================================

Validates the 14 required regression scenarios:
1.  Add items to cart -> current cart reflects items and subtotal.
2.  Remove an item from cart -> current cart updates.
3.  Remove all items from cart / clear cart -> current cart shows 0 items and 0 value.
4.  Historical cart addition count remains accurate after items are removed.
5.  Wishlist addition -> wishlist persists and reflects in customer and admin views.
6.  Wishlist removal -> wishlist updates in customer and admin views.
7.  Product view events recorded and appear in admin timeline with product name.
8.  Search events recorded with query terms and appear in timeline.
9.  Cart addition and removal events appear in admin timeline with details.
10. Checkout initiation and purchase appear with order details and status updates.
11. Registration and login events appear in timeline.
12. Anonymous session events are merged into customer timeline upon login/signup.
13. Admin Customer Intelligence Dashboard reflects updated state dynamically.
14. Lead scoring updates appropriately based on current state and behavioral history.
"""

import os
import sys
import json
import jwt
import unittest
from datetime import datetime, timezone, timedelta
from bson import ObjectId

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module
from admin_intelligence_service import (
    get_customer_intelligence_detail,
    _build_journey_timeline,
    _resolve_cart,
    _resolve_wishlist,
    _compute_behavior_summary,
    get_qualified_leads_list,
)
from customer_lead_state_service import (
    sync_customer_lead_state,
    get_customer_lead_state,
    ensure_customer_lead_state_indexes,
)
from customer_feature_service import (
    aggregate_customer_features,
    upsert_customer_features,
    ensure_customer_features_indexes,
)
from identity_service import resolve_anonymous_identity
from behavior_event_service import log_behavior_event
from behavioral_scoring_service import compute_behavioral_score


class TimelineAndCartSyncTests(unittest.TestCase):
    def setUp(self):
        self.client = app_module.app.test_client()
        self.db = app_module.db
        self.jwt_secret = app_module.JWT_SECRET
        self.profiles = app_module.profiles_collection
        self.features = app_module.customer_features_collection
        self.lead_state = app_module.customer_lead_state_collection
        self.sessions = app_module.sessions_collection
        self.events = app_module.events_collection
        self.orders = app_module.orders_collection
        self.cart = app_module.cart_collection
        self.wishlist = app_module.wishlist_collection
        self.products = app_module.products_collection

        ensure_customer_features_indexes(self.features)
        ensure_customer_lead_state_indexes(self.lead_state)

    def _make_token(self, user_id, role="user"):
        exp_time = datetime.now(timezone.utc) + timedelta(hours=2)
        return jwt.encode(
            {"sub": str(user_id), "role": role, "exp": exp_time},
            self.jwt_secret,
            algorithm="HS256",
        )

    def _create_customer(self, email="testuser@example.com", username="testuser"):
        user_id = ObjectId()
        self.profiles.insert_one({
            "_id": user_id,
            "email": email,
            "username": username,
            "role": "user",
            "created_at": datetime.now(timezone.utc),
        })
        token = self._make_token(user_id)
        headers = {"Authorization": f"Bearer {token}"}
        return user_id, token, headers

    # -------------------------------------------------------------------------
    # Scenario 1: Add items to cart -> current cart reflects items and subtotal
    # -------------------------------------------------------------------------
    def test_01_add_items_to_cart_reflects_items_and_subtotal(self):
        user_id, token, headers = self._create_customer("cart1@test.com", "cart1")
        prod_id = ObjectId()

        self.products.insert_one({
            "_id": prod_id,
            "name": "Classic Oxford Shirt",
            "title": "Classic Oxford Shirt",
            "price": 1299.0,
            "price_inr": 1299.0,
            "category": "Shirts",
        })

        # Add item via route: POST /api/cart with Auth
        res = self.client.post("/api/cart", json={
            "user_id": str(user_id),
            "product_id": str(prod_id),
            "quantity": 2,
        }, headers=headers)
        self.assertEqual(res.status_code, 200)

        # Verify customer cart: GET /api/cart?user_id=...
        cart_res = self.client.get(f"/api/cart?user_id={user_id}", headers=headers)
        self.assertEqual(cart_res.status_code, 200)
        cart_data = json.loads(cart_res.data)["data"]
        self.assertEqual(len(cart_data), 1)
        self.assertEqual(cart_data[0]["title"], "Classic Oxford Shirt")
        self.assertEqual(cart_data[0]["quantity"], 2)
        total_subtotal = sum(float(item["price"]) * int(item["quantity"]) for item in cart_data)
        self.assertEqual(total_subtotal, 2598.0)

        # Verify admin _resolve_cart
        admin_cart = _resolve_cart(user_id, self.db)
        self.assertEqual(len(admin_cart), 1)
        self.assertEqual(admin_cart[0]["quantity"], 2)
        self.assertEqual(admin_cart[0]["subtotal"], 2598.0)

    # -------------------------------------------------------------------------
    # Scenario 2: Remove an item from cart -> current cart updates
    # -------------------------------------------------------------------------
    def test_02_remove_item_from_cart_updates_current_cart(self):
        user_id, token, headers = self._create_customer("cart2@test.com", "cart2")
        p1 = ObjectId()
        p2 = ObjectId()

        self.products.insert_one({"_id": p1, "name": "Item 1", "price": 500.0})
        self.products.insert_one({"_id": p2, "name": "Item 2", "price": 800.0})

        self.client.post("/api/cart", json={"user_id": str(user_id), "product_id": str(p1), "quantity": 1}, headers=headers)
        self.client.post("/api/cart", json={"user_id": str(user_id), "product_id": str(p2), "quantity": 1}, headers=headers)

        # Remove p1: DELETE /api/cart/<product_id>?user_id=...
        rem_res = self.client.delete(f"/api/cart/{p1}?user_id={user_id}", headers=headers)
        self.assertEqual(rem_res.status_code, 200)

        # Cart should only contain p2
        cart_res = self.client.get(f"/api/cart?user_id={user_id}", headers=headers)
        cart_data = json.loads(cart_res.data)["data"]
        self.assertEqual(len(cart_data), 1)
        self.assertEqual(cart_data[0]["product_id"], str(p2))
        self.assertEqual(cart_data[0]["quantity"], 1)

    # -------------------------------------------------------------------------
    # Scenario 3: Remove all items / clear cart -> shows 0 items and 0 value
    # -------------------------------------------------------------------------
    def test_03_clear_cart_shows_zero_items_and_zero_value(self):
        user_id, token, headers = self._create_customer("clear@test.com", "clear_user")
        p1 = ObjectId()

        self.products.insert_one({"_id": p1, "name": "Clear Item", "price": 999.0})

        self.client.post("/api/cart", json={"user_id": str(user_id), "product_id": str(p1), "quantity": 3}, headers=headers)

        # Clear cart: DELETE /api/cart?user_id=...
        clear_res = self.client.delete(f"/api/cart?user_id={user_id}", headers=headers)
        self.assertEqual(clear_res.status_code, 200)

        # Customer view
        cart_res = self.client.get(f"/api/cart?user_id={user_id}", headers=headers)
        cart_data = json.loads(cart_res.data)["data"]
        self.assertEqual(len(cart_data), 0)

        # Admin intelligence view
        admin_detail = get_customer_intelligence_detail(self.db, user_id)
        self.assertEqual(len(admin_detail["cart"]), 0)
        self.assertEqual(admin_detail["behavior_summary"]["cart_total_quantity"], 0)
        self.assertEqual(admin_detail["behavior_summary"]["cart_current_count"], 0)

    # -------------------------------------------------------------------------
    # Scenario 4: Historical cart addition count remains accurate after clearing
    # -------------------------------------------------------------------------
    def test_04_historical_cart_adds_count_preserved_after_clear(self):
        user_id, token, headers = self._create_customer("history@test.com", "history")
        sess_id = ObjectId()
        p1 = ObjectId()
        p2 = ObjectId()
        now = datetime.now(timezone.utc)

        self.sessions.insert_one({"_id": sess_id, "user_id": user_id, "started_at": now})
        self.products.insert_one({"_id": p1, "name": "Item A", "price": 400.0})
        self.products.insert_one({"_id": p2, "name": "Item B", "price": 600.0})

        self.client.post("/api/cart", json={"user_id": str(user_id), "product_id": str(p1), "quantity": 1, "session_id": str(sess_id)}, headers=headers)
        self.client.post("/api/cart", json={"user_id": str(user_id), "product_id": str(p2), "quantity": 1, "session_id": str(sess_id)}, headers=headers)

        # Clear cart
        self.client.delete(f"/api/cart?user_id={user_id}&session_id={sess_id}", headers=headers)

        # Features aggregation
        feat = aggregate_customer_features(user_id, self.db)
        # Current cart quantity is 0
        self.assertEqual(feat["cart_item_count"], 0)
        self.assertEqual(feat["cart_value"], 0.0)

        # Lifetime cart additions still reflect 2 in behavior summary
        bs_data = _compute_behavior_summary(user_id, self.db)
        self.assertEqual(bs_data["behavior_summary"]["cart_adds_count"], 2)

    # -------------------------------------------------------------------------
    # Scenario 5: Wishlist addition persists and reflects in customer and admin
    # -------------------------------------------------------------------------
    def test_05_wishlist_addition_reflects_in_customer_and_admin(self):
        user_id, token, headers = self._create_customer("wish1@test.com", "wish1")
        prod_id = ObjectId()

        self.products.insert_one({"_id": prod_id, "name": "Leather Jacket", "title": "Leather Jacket", "price": 4999.0})

        res = self.client.post("/api/wishlist", json={
            "user_id": str(user_id),
            "product_id": str(prod_id),
        }, headers=headers)
        self.assertEqual(res.status_code, 200)

        # Customer view
        wish_res = self.client.get(f"/api/wishlist?user_id={user_id}", headers=headers)
        self.assertEqual(wish_res.status_code, 200)
        wish_data = json.loads(wish_res.data)["data"]
        self.assertEqual(len(wish_data), 1)
        self.assertEqual(wish_data[0]["title"], "Leather Jacket")

        # Admin view
        admin_detail = get_customer_intelligence_detail(self.db, user_id)
        self.assertEqual(admin_detail["behavior_summary"]["wishlist_current_count"], 1)
        self.assertEqual(len(admin_detail["wishlist"]), 1)
        self.assertEqual(admin_detail["wishlist"][0]["name"], "Leather Jacket")

    # -------------------------------------------------------------------------
    # Scenario 6: Wishlist removal updates customer and admin views
    # -------------------------------------------------------------------------
    def test_06_wishlist_removal_updates_customer_and_admin(self):
        user_id, token, headers = self._create_customer("wish2@test.com", "wish2")
        sess_id = ObjectId()
        prod_id = ObjectId()
        now = datetime.now(timezone.utc)

        self.sessions.insert_one({"_id": sess_id, "user_id": user_id, "started_at": now})
        self.products.insert_one({"_id": prod_id, "name": "Running Shoes", "price": 2499.0})

        self.client.post("/api/wishlist", json={"user_id": str(user_id), "product_id": str(prod_id), "session_id": str(sess_id)}, headers=headers)

        # Remove from wishlist: DELETE /api/wishlist/<product_id>?user_id=...
        rem_res = self.client.delete(f"/api/wishlist/{prod_id}?user_id={user_id}&session_id={sess_id}", headers=headers)
        self.assertEqual(rem_res.status_code, 200)

        # Customer view
        wish_res = self.client.get(f"/api/wishlist?user_id={user_id}", headers=headers)
        wish_data = json.loads(wish_res.data)["data"]
        self.assertEqual(len(wish_data), 0)

        # Admin view
        admin_detail = get_customer_intelligence_detail(self.db, user_id)
        self.assertEqual(admin_detail["behavior_summary"]["wishlist_current_count"], 0)
        self.assertEqual(len(admin_detail["wishlist"]), 0)

        # Lifetime wishlist addition count preserved
        bs_data = _compute_behavior_summary(user_id, self.db)
        self.assertEqual(bs_data["behavior_summary"]["wishlist_adds_count"], 1)

    # -------------------------------------------------------------------------
    # Scenario 7: Product view events appear in admin timeline with product name
    # -------------------------------------------------------------------------
    def test_07_product_view_event_appears_with_product_name(self):
        user_id, token, headers = self._create_customer("pv@test.com", "pv")
        prod_id = ObjectId()
        now = datetime.now(timezone.utc)

        self.products.insert_one({
            "_id": prod_id,
            "name": "Wireless Noise-Cancelling Headphones",
            "price": 7999.0,
        })

        # Insert product_view event without embedded title to test server-side enrichment
        self.events.insert_one({
            "user_id": user_id,
            "event_type": "product_view",
            "entity": {"type": "product", "id": str(prod_id)},
            "metadata": {"price": 7999.0},
            "timestamp": now,
        })

        timeline = _build_journey_timeline(user_id, self.db)
        pv_entries = [e for e in timeline if e.get("event_type") == "product_view"]
        self.assertEqual(len(pv_entries), 1)
        self.assertEqual(pv_entries[0]["product_name"], "Wireless Noise-Cancelling Headphones")
        self.assertEqual(pv_entries[0]["entity"]["name"], "Wireless Noise-Cancelling Headphones")

    # -------------------------------------------------------------------------
    # Scenario 8: Search events recorded with query terms and appear in timeline
    # -------------------------------------------------------------------------
    def test_08_search_events_appear_with_query_terms(self):
        user_id, token, headers = self._create_customer("searcher@test.com", "searcher")
        now = datetime.now(timezone.utc)

        self.events.insert_one({
            "user_id": user_id,
            "event_type": "search",
            "entity": {"type": "search", "query": "summer linen shirt"},
            "metadata": {"query": "summer linen shirt", "results_count": 14},
            "timestamp": now,
        })

        timeline = _build_journey_timeline(user_id, self.db)
        search_entries = [e for e in timeline if e.get("event_type") == "search"]
        self.assertEqual(len(search_entries), 1)
        self.assertEqual(search_entries[0]["entity"]["query"], "summer linen shirt")
        self.assertEqual(search_entries[0]["metadata"]["results_count"], 14)

    # -------------------------------------------------------------------------
    # Scenario 9: Cart addition and removal events appear in admin timeline
    # -------------------------------------------------------------------------
    def test_09_cart_addition_and_removal_events_in_timeline(self):
        user_id, token, headers = self._create_customer("cart_events@test.com", "cart_events")
        sess_id = ObjectId()
        prod_id = ObjectId()
        now = datetime.now(timezone.utc)

        self.sessions.insert_one({"_id": sess_id, "user_id": user_id, "started_at": now})
        self.products.insert_one({"_id": prod_id, "name": "Formal Blazer", "price": 3499.0})

        # Cart add
        self.client.post("/api/cart", json={
            "user_id": str(user_id),
            "product_id": str(prod_id),
            "quantity": 1,
            "session_id": str(sess_id),
        }, headers=headers)

        # Cart remove
        self.client.delete(f"/api/cart/{prod_id}?user_id={user_id}&session_id={sess_id}", headers=headers)

        timeline = _build_journey_timeline(user_id, self.db)
        cart_adds = [e for e in timeline if e.get("event_type") in ("cart_add", "add_to_cart")]
        cart_removes = [e for e in timeline if e.get("event_type") in ("cart_remove", "remove_from_cart")]

        self.assertEqual(len(cart_adds), 1)
        self.assertEqual(cart_adds[0]["product_name"], "Formal Blazer")
        self.assertEqual(len(cart_removes), 1)
        self.assertEqual(cart_removes[0]["product_name"], "Formal Blazer")

    # -------------------------------------------------------------------------
    # Scenario 10: Checkout initiation and purchase appear with order details
    # -------------------------------------------------------------------------
    def test_10_checkout_and_purchase_with_details_and_status_update(self):
        user_id, token, headers = self._create_customer("checkout@test.com", "checkout")
        order_id = ObjectId()
        now = datetime.now(timezone.utc)

        # Checkout start event
        self.events.insert_one({
            "user_id": user_id,
            "event_type": "checkout_start",
            "entity": {"type": "checkout"},
            "metadata": {"cart_items": 2, "cart_value": 2999.0},
            "timestamp": now - timedelta(minutes=5),
        })

        # Order document
        self.orders.insert_one({
            "_id": order_id,
            "user_id": user_id,
            "total_amount": 2999.0,
            "status": "processing",
            "items": [{"product_id": "p1", "name": "Blue Suit", "quantity": 1, "price": 2999.0}],
            "created_at": now - timedelta(minutes=2),
        })

        # Order status update route: PATCH /api/orders/<order_id>/status
        patch_res = self.client.patch(f"/api/orders/{order_id}/status", json={"status": "delivered"})
        self.assertEqual(patch_res.status_code, 200)

        timeline = _build_journey_timeline(user_id, self.db)
        checkout_starts = [e for e in timeline if e.get("event_type") == "checkout_start"]
        order_entries = [e for e in timeline if e.get("type") == "order"]
        status_updates = [e for e in timeline if e.get("event_type") == "order_status_update"]

        self.assertEqual(len(checkout_starts), 1)
        self.assertEqual(len(order_entries), 1)
        self.assertEqual(order_entries[0]["order_id"], str(order_id))
        self.assertEqual(order_entries[0]["status"], "delivered")
        self.assertEqual(len(status_updates), 1)
        self.assertEqual(status_updates[0]["metadata"]["status"], "delivered")

    # -------------------------------------------------------------------------
    # Scenario 11: Registration and login events appear in timeline
    # -------------------------------------------------------------------------
    def test_11_registration_and_login_events_appear_in_timeline(self):
        user_id, token, headers = self._create_customer("auth_flow@test.com", "auth_flow")
        now = datetime.now(timezone.utc)

        self.events.insert_one({
            "user_id": user_id,
            "event_type": "registration",
            "entity": {"type": "auth"},
            "metadata": {"email": "auth_flow@test.com"},
            "timestamp": now - timedelta(hours=1),
        })

        self.events.insert_one({
            "user_id": user_id,
            "event_type": "login",
            "entity": {"type": "auth"},
            "metadata": {"email": "auth_flow@test.com"},
            "timestamp": now - timedelta(minutes=30),
        })

        timeline = _build_journey_timeline(user_id, self.db)
        regs = [e for e in timeline if e.get("event_type") == "registration"]
        logins = [e for e in timeline if e.get("event_type") == "login"]

        self.assertEqual(len(regs), 1)
        self.assertEqual(len(logins), 1)

    # -------------------------------------------------------------------------
    # Scenario 12: Anonymous session events merged into customer timeline
    # -------------------------------------------------------------------------
    def test_12_anonymous_session_events_merged_into_customer_timeline(self):
        user_id = ObjectId()
        anon_id = "guest_anon_7788"
        vis_id = "guest_vis_7788"
        sess_id = ObjectId()
        now = datetime.now(timezone.utc)

        # 1. Anonymous guest activity before signup
        self.sessions.insert_one({
            "_id": sess_id,
            "session_id": "sess_guest_99",
            "anonymous_id": anon_id,
            "visitor_id": vis_id,
            "user_id": None,
            "started_at": now - timedelta(hours=2),
            "last_active_at": now - timedelta(hours=2),
        })

        self.events.insert_one({
            "user_id": None,
            "anonymous_id": anon_id,
            "visitor_id": vis_id,
            "session_id": "sess_guest_99",
            "event_type": "search",
            "metadata": {"query": "designer sunglasses"},
            "timestamp": now - timedelta(hours=2),
        })

        # 2. User registers and logs in
        self.profiles.insert_one({
            "_id": user_id,
            "email": "converted_guest@test.com",
            "anonymous_id": anon_id,
            "visitor_id": vis_id,
        })

        # Resolve anonymous identity with collections
        resolve_anonymous_identity(
            anon_id,
            user_id,
            self.profiles,
            self.sessions,
            self.events,
            self.lead_state,
            self.cart,
            self.wishlist,
            self.features,
            self.db,
        )

        # Post-login event
        self.events.insert_one({
            "user_id": user_id,
            "event_type": "login",
            "metadata": {"email": "converted_guest@test.com"},
            "timestamp": now - timedelta(hours=1),
        })

        timeline = _build_journey_timeline(user_id, self.db)
        search_entries = [e for e in timeline if e.get("event_type") == "search"]
        login_entries = [e for e in timeline if e.get("event_type") == "login"]

        self.assertEqual(len(search_entries), 1)
        self.assertEqual(search_entries[0]["metadata"]["query"], "designer sunglasses")
        self.assertEqual(len(login_entries), 1)

    # -------------------------------------------------------------------------
    # Scenario 13: Admin Customer Intelligence Dashboard reflects updated state dynamically
    # -------------------------------------------------------------------------
    def test_13_admin_customer_intelligence_dashboard_reflects_updates_dynamically(self):
        user_id, token, headers = self._create_customer("dynamic@test.com", "dynamic_user")
        p1 = ObjectId()
        now = datetime.now(timezone.utc)

        self.products.insert_one({"_id": p1, "name": "Smart Watch", "price": 4999.0})

        # 1. Initially empty
        detail1 = get_customer_intelligence_detail(self.db, user_id)
        self.assertEqual(len(detail1["cart"]), 0)
        self.assertEqual(detail1["behavior_summary"]["orders_count"], 0)

        # 2. Add to cart
        self.client.post("/api/cart", json={"user_id": str(user_id), "product_id": str(p1), "quantity": 1}, headers=headers)
        detail2 = get_customer_intelligence_detail(self.db, user_id)
        self.assertEqual(len(detail2["cart"]), 1)
        self.assertEqual(detail2["cart"][0]["quantity"], 1)
        self.assertEqual(detail2["behavior_summary"]["cart_total_quantity"], 1)

        # 3. Clear cart
        self.client.delete(f"/api/cart?user_id={user_id}", headers=headers)
        detail3 = get_customer_intelligence_detail(self.db, user_id)
        self.assertEqual(len(detail3["cart"]), 0)
        self.assertEqual(detail3["behavior_summary"]["cart_total_quantity"], 0)

        # 4. Place order
        self.orders.insert_one({
            "_id": ObjectId(),
            "user_id": user_id,
            "total_amount": 4999.0,
            "status": "completed",
            "created_at": now,
        })
        detail4 = get_customer_intelligence_detail(self.db, user_id)
        self.assertEqual(detail4["behavior_summary"]["orders_count"], 1)

    # -------------------------------------------------------------------------
    # Scenario 14: Lead scoring updates appropriately based on current state & history
    # -------------------------------------------------------------------------
    def test_14_lead_scoring_updates_appropriately_on_state_changes(self):
        user_id, token, headers = self._create_customer("scoring_flow@test.com", "scoring_flow")
        prod_id = ObjectId()
        sess_id = ObjectId()
        now = datetime.now(timezone.utc)

        self.products.insert_one({"_id": prod_id, "name": "Premium Wool Coat", "price": 6999.0})

        self.sessions.insert_one({
            "_id": sess_id,
            "user_id": user_id,
            "started_at": now,
            "last_active_at": now,
            "total_time_seconds": 600,
            "page_views": 8,
        })

        for i in range(4):
            self.events.insert_one({
                "session_id": sess_id,
                "user_id": user_id,
                "event_type": "product_view",
                "entity": {"id": f"item_{i}"},
                "timestamp": now,
            })
        for i in range(2):
            self.events.insert_one({
                "session_id": sess_id,
                "user_id": user_id,
                "event_type": "search",
                "timestamp": now,
            })

        self.wishlist.insert_one({
            "user_id": user_id,
            "product_id": str(prod_id),
            "created_at": now,
        })

        # Customer adds to cart
        self.client.post("/api/cart", json={"user_id": str(user_id), "product_id": str(prod_id), "quantity": 1}, headers=headers)
        upsert_customer_features(user_id, self.db)
        state_cart = sync_customer_lead_state(user_id, self.db)

        # Active cart user is warm or hot, not cold
        self.assertIn(state_cart["lead_segment"], ("Warm", "Hot"))

        # Customer clears cart
        self.client.delete(f"/api/cart?user_id={user_id}", headers=headers)
        upsert_customer_features(user_id, self.db)
        state_cleared = sync_customer_lead_state(user_id, self.db)

        # Score after clearing cart decreases since active cart points are removed
        self.assertLess(state_cleared["lead_score"], state_cart["lead_score"])

        # Customer completes purchase
        self.orders.insert_one({
            "_id": ObjectId(),
            "user_id": user_id,
            "total_amount": 6999.0,
            "status": "completed",
            "created_at": now,
        })
        upsert_customer_features(user_id, self.db)
        state_ordered = sync_customer_lead_state(user_id, self.db)

        # Buyer is converted, not cold, and properly acknowledged
        self.assertTrue(state_ordered["is_converted"])
        self.assertEqual(state_ordered["lifecycle_status"], "converted")
        self.assertNotEqual(state_ordered["lead_segment"], "Cold")


if __name__ == "__main__":
    unittest.main()
