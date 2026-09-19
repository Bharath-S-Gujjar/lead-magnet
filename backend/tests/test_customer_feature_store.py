import os
import sys
import unittest
from datetime import datetime, timezone
from bson import ObjectId

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module
from customer_feature_service import (
    aggregate_customer_features,
    upsert_customer_features,
    get_customer_features,
    ensure_customer_features_indexes,
)
from identity_service import resolve_anonymous_identity
from lead_processing_service import process_session


class CustomerFeatureStoreTests(unittest.TestCase):
    def setUp(self):
        self.client = app_module.app.test_client()
        self.db = app_module.db
        self.profiles = app_module.profiles_collection
        self.sessions = app_module.sessions_collection
        self.events = app_module.events_collection
        self.cart = app_module.cart_collection
        self.wishlist = app_module.wishlist_collection
        self.orders = app_module.orders_collection
        self.products = app_module.products_collection
        self.leads = app_module.leads_collection
        self.features = app_module.customer_features_collection

        ensure_customer_features_indexes(self.features)

        self.product_1_id = ObjectId()
        self.product_2_id = ObjectId()
        self.products.insert_many([
            {
                "_id": self.product_1_id,
                "name": "Feature Test Shirt",
                "price": 100.0,
                "category": "Apparel",
                "brand": "TestBrand",
            },
            {
                "_id": self.product_2_id,
                "name": "Feature Test Pants",
                "price": 200.0,
                "category": "Apparel",
                "brand": "TestBrand",
            },
        ])

    # 1. One customer with one session.
    def test_one_customer_one_session(self):
        user_id = ObjectId()
        self.profiles.insert_one({"_id": user_id, "email": "session1@example.com"})
        session_id = ObjectId()
        self.sessions.insert_one({
            "_id": session_id,
            "user_id": user_id,
            "started_at": datetime.now(timezone.utc),
            "total_time_seconds": 120.0,
            "page_views": 3,
            "status": "ended",
        })

        features = upsert_customer_features(user_id, self.db)
        self.assertEqual(features["customer_id"], user_id)
        self.assertEqual(features["sessions_count"], 1)
        self.assertEqual(features["total_time_spent"], 120.0)
        self.assertEqual(features["average_session_duration"], 120.0)

    # 2. One customer with multiple sessions.
    def test_one_customer_multiple_sessions(self):
        user_id = ObjectId()
        self.profiles.insert_one({"_id": user_id, "email": "multi_session@example.com"})
        self.sessions.insert_many([
            {"_id": ObjectId(), "user_id": user_id, "started_at": datetime.now(timezone.utc), "total_time_seconds": 60.0},
            {"_id": ObjectId(), "user_id": user_id, "started_at": datetime.now(timezone.utc), "total_time_seconds": 180.0},
        ])

        features = upsert_customer_features(user_id, self.db)
        self.assertEqual(features["sessions_count"], 2)
        self.assertEqual(features["total_time_spent"], 240.0)
        self.assertEqual(features["average_session_duration"], 120.0)

    # 3. One customer with multiple events.
    def test_one_customer_multiple_events(self):
        user_id = ObjectId()
        session_id = ObjectId()
        self.profiles.insert_one({"_id": user_id, "email": "events@example.com"})
        self.sessions.insert_one({"_id": session_id, "user_id": user_id})
        self.events.insert_many([
            {"_id": ObjectId(), "session_id": session_id, "user_id": user_id, "event_type": "page_view", "page": "/home"},
            {"_id": ObjectId(), "session_id": session_id, "user_id": user_id, "event_type": "search", "page": "/search"},
            {"_id": ObjectId(), "session_id": session_id, "user_id": user_id, "event_type": "form_submit", "page": "/contact"},
        ])

        features = upsert_customer_features(user_id, self.db)
        self.assertEqual(features["total_events"], 3)
        self.assertEqual(features["search_count"], 1)
        self.assertEqual(features["form_submit_count"], 1)

    # 4. Product-view aggregation.
    def test_product_view_aggregation(self):
        user_id = ObjectId()
        session_id = ObjectId()
        self.profiles.insert_one({"_id": user_id, "email": "prod_view@example.com"})
        self.sessions.insert_one({"_id": session_id, "user_id": user_id})
        self.events.insert_many([
            {"_id": ObjectId(), "session_id": session_id, "user_id": user_id, "event_type": "product_view", "entity": {"id": str(self.product_1_id)}},
            {"_id": ObjectId(), "session_id": session_id, "user_id": user_id, "event_type": "product_view", "entity": {"id": str(self.product_1_id)}},
            {"_id": ObjectId(), "session_id": session_id, "user_id": user_id, "event_type": "product_view", "entity": {"id": str(self.product_2_id)}},
        ])

        features = upsert_customer_features(user_id, self.db)
        self.assertEqual(features["products_viewed"], 3)
        self.assertEqual(features["unique_products_viewed"], 2)

    # 5. Cart aggregation.
    def test_cart_aggregation(self):
        user_id = ObjectId()
        self.profiles.insert_one({"_id": user_id, "email": "cart@example.com"})
        self.cart.insert_many([
            {"_id": ObjectId(), "user_id": user_id, "product_id": self.product_1_id, "quantity": 2},
            {"_id": ObjectId(), "user_id": user_id, "product_id": self.product_2_id, "quantity": 1},
        ])

        features = upsert_customer_features(user_id, self.db)
        self.assertEqual(features["cart_item_count"], 3)
        self.assertEqual(features["cart_value"], 400.0)

    # 6. Wishlist aggregation.
    def test_wishlist_aggregation(self):
        user_id = ObjectId()
        self.profiles.insert_one({"_id": user_id, "email": "wishlist@example.com"})
        self.wishlist.insert_many([
            {"_id": ObjectId(), "user_id": user_id, "product_id": self.product_1_id},
            {"_id": ObjectId(), "user_id": user_id, "product_id": self.product_2_id},
        ])

        features = upsert_customer_features(user_id, self.db)
        self.assertEqual(features["wishlist_item_count"], 2)

    # 7. Order aggregation.
    def test_order_aggregation(self):
        user_id = ObjectId()
        self.profiles.insert_one({"_id": user_id, "email": "order1@example.com"})
        self.orders.insert_one({
            "_id": ObjectId(),
            "user_id": user_id,
            "total_amount": 250.0,
            "created_at": datetime.now(timezone.utc),
        })

        features = upsert_customer_features(user_id, self.db)
        self.assertEqual(features["orders_count"], 1)
        self.assertEqual(features["total_order_value"], 250.0)
        self.assertEqual(features["average_order_value"], 250.0)

    # 8. Multiple orders.
    def test_multiple_orders(self):
        user_id = ObjectId()
        self.profiles.insert_one({"_id": user_id, "email": "multi_order@example.com"})
        self.orders.insert_many([
            {"_id": ObjectId(), "user_id": user_id, "total_amount": 100.0, "created_at": datetime.now(timezone.utc)},
            {"_id": ObjectId(), "user_id": user_id, "total_amount": 300.0, "created_at": datetime.now(timezone.utc)},
        ])

        features = upsert_customer_features(user_id, self.db)
        self.assertEqual(features["orders_count"], 2)
        self.assertEqual(features["total_order_value"], 400.0)
        self.assertEqual(features["average_order_value"], 200.0)

    # 9. Empty cart/wishlist.
    def test_empty_cart_wishlist(self):
        user_id = ObjectId()
        self.profiles.insert_one({"_id": user_id, "email": "empty_cw@example.com"})
        features = upsert_customer_features(user_id, self.db)
        self.assertEqual(features["cart_item_count"], 0)
        self.assertEqual(features["cart_value"], 0.0)
        self.assertEqual(features["wishlist_item_count"], 0)

    # 10. Customer with no orders.
    def test_customer_no_orders(self):
        user_id = ObjectId()
        self.profiles.insert_one({"_id": user_id, "email": "no_orders@example.com"})
        features = upsert_customer_features(user_id, self.db)
        self.assertEqual(features["orders_count"], 0)
        self.assertEqual(features["total_order_value"], 0.0)
        self.assertEqual(features["average_order_value"], 0.0)
        self.assertIsNone(features["last_order_at"])

    # 11. Customer with no events.
    def test_customer_no_events(self):
        user_id = ObjectId()
        self.profiles.insert_one({"_id": user_id, "email": "no_events@example.com"})
        features = upsert_customer_features(user_id, self.db)
        self.assertEqual(features["total_events"], 0)
        self.assertEqual(features["products_viewed"], 0)
        self.assertEqual(features["unique_products_viewed"], 0)

    # 12. Anonymous behavior before registration.
    def test_anonymous_behavior_before_registration(self):
        anon_id = "anon_before_reg_123"
        session_id = ObjectId()
        self.sessions.insert_one({"_id": session_id, "anonymous_id": anon_id, "total_time_seconds": 90.0})
        self.events.insert_one({"_id": ObjectId(), "session_id": session_id, "anonymous_id": anon_id, "event_type": "page_view"})

        features = upsert_customer_features(anon_id, self.db)
        self.assertEqual(features["customer_id"], anon_id)
        self.assertEqual(features["identity_type"], "anonymous")
        self.assertEqual(features["sessions_count"], 1)
        self.assertEqual(features["total_events"], 1)

    # 13. Anonymous behavior after registration resolves to customer.
    def test_anonymous_behavior_after_registration_resolves(self):
        anon_id = "anon_resolution_456"
        session_id = ObjectId()
        self.sessions.insert_one({"_id": session_id, "anonymous_id": anon_id, "total_time_seconds": 150.0})
        self.events.insert_one({"_id": ObjectId(), "session_id": session_id, "anonymous_id": anon_id, "event_type": "product_view", "entity": {"id": str(self.product_1_id)}})
        self.cart.insert_one({"_id": ObjectId(), "anonymous_id": anon_id, "product_id": self.product_1_id, "quantity": 1})

        # Upsert anon features initially
        upsert_customer_features(anon_id, self.db)
        self.assertEqual(self.features.count_documents({"customer_id": anon_id}), 1)

        # Register user
        user_id = ObjectId()
        self.profiles.insert_one({"_id": user_id, "email": "resolved@example.com"})

        # Resolve anonymous identity
        resolve_anonymous_identity(
            anon_id,
            user_id,
            self.profiles,
            self.sessions,
            self.events,
            self.leads,
            self.cart,
            self.wishlist,
            self.features,
            self.db,
        )

        # Features should now be stored under registered user_id, anon doc deleted
        self.assertEqual(self.features.count_documents({"customer_id": anon_id}), 0)
        reg_features = get_customer_features(user_id, self.features)
        self.assertIsNotNone(reg_features)
        self.assertEqual(reg_features["customer_id"], user_id)
        self.assertEqual(reg_features["identity_type"], "registered")
        self.assertEqual(reg_features["sessions_count"], 1)
        self.assertEqual(reg_features["products_viewed"], 1)
        self.assertEqual(reg_features["cart_item_count"], 1)

    # 14. Repeated feature aggregation is idempotent.
    def test_repeated_aggregation_is_idempotent(self):
        user_id = ObjectId()
        self.profiles.insert_one({"_id": user_id, "email": "idempotent@example.com"})
        session_id = ObjectId()
        self.sessions.insert_one({"_id": session_id, "user_id": user_id, "total_time_seconds": 100.0})
        self.events.insert_one({"_id": ObjectId(), "session_id": session_id, "user_id": user_id, "event_type": "page_view"})

        f1 = upsert_customer_features(user_id, self.db)
        f2 = upsert_customer_features(user_id, self.db)
        f3 = upsert_customer_features(user_id, self.db)

        self.assertEqual(self.features.count_documents({"customer_id": user_id}), 1)
        self.assertEqual(f1["sessions_count"], f2["sessions_count"])
        self.assertEqual(f1["total_events"], f3["total_events"])
        self.assertEqual(f1["total_time_spent"], f2["total_time_spent"])

    # 15. Multiple lead documents for the same customer do not create multiple feature documents.
    def test_multiple_leads_do_not_create_multiple_feature_documents(self):
        user_id = ObjectId()
        session_1 = ObjectId()
        session_2 = ObjectId()
        self.profiles.insert_one({"_id": user_id, "email": "leads@example.com"})
        self.sessions.insert_many([
            {"_id": session_1, "user_id": user_id, "visitor_id": "v1"},
            {"_id": session_2, "user_id": user_id, "visitor_id": "v1"},
        ])

        # Process session 1 & 2 into leads collection
        process_session(session_1, self.sessions, self.events, self.leads)
        process_session(session_2, self.sessions, self.events, self.leads)

        self.assertEqual(self.leads.count_documents({"user_id": user_id}), 2)

        # Upsert features for customer
        upsert_customer_features(user_id, self.db)
        self.assertEqual(self.features.count_documents({"customer_id": user_id}), 1)

    # 16. Different customers remain isolated.
    def test_different_customers_remain_isolated(self):
        user_a = ObjectId()
        user_b = ObjectId()
        self.profiles.insert_many([
            {"_id": user_a, "email": "customerA@example.com"},
            {"_id": user_b, "email": "customerB@example.com"},
        ])

        self.cart.insert_one({"_id": ObjectId(), "user_id": user_a, "product_id": self.product_1_id, "quantity": 5})
        self.cart.insert_one({"_id": ObjectId(), "user_id": user_b, "product_id": self.product_2_id, "quantity": 1})

        fa = upsert_customer_features(user_a, self.db)
        fb = upsert_customer_features(user_b, self.db)

        self.assertEqual(fa["cart_item_count"], 5)
        self.assertEqual(fa["cart_value"], 500.0)
        self.assertEqual(fb["cart_item_count"], 1)
        self.assertEqual(fb["cart_value"], 200.0)
        self.assertEqual(self.features.count_documents({}), 2)

    # 17. Invalid identity does not attach data to another customer.
    def test_invalid_identity_handling(self):
        user_id = ObjectId()
        self.profiles.insert_one({"_id": user_id, "email": "valid@example.com"})
        self.sessions.insert_one({"_id": ObjectId(), "user_id": user_id, "total_time_seconds": 60.0})

        # Request feature upsert for non-existent / invalid identity
        invalid_id = ObjectId()
        f_invalid = upsert_customer_features(invalid_id, self.db)
        f_valid = upsert_customer_features(user_id, self.db)

        self.assertEqual(f_invalid["sessions_count"], 0)
        self.assertEqual(f_valid["sessions_count"], 1)
        self.assertEqual(self.features.count_documents({"customer_id": user_id}), 1)
        self.assertEqual(self.features.count_documents({"customer_id": invalid_id}), 1)


if __name__ == "__main__":
    unittest.main()
