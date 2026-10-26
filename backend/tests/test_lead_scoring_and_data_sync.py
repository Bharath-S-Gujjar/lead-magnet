"""Comprehensive End-to-End Data Synchronization and Lead Scoring Test Suite.
=============================================================================

Validates the 17 core requirements across behavioral scoring, data sync,
order filtering, deduplication, lead qualification, and admin intelligence.
"""

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from bson import ObjectId

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module
from behavioral_scoring_service import compute_behavioral_score
from ecommerce_model_adapter import predict_customer_features
from customer_feature_service import (
    aggregate_customer_features,
    ensure_customer_features_indexes,
    is_completed_order,
)
from customer_lead_state_service import (
    sync_customer_lead_state,
    get_customer_lead_state,
    ensure_customer_lead_state_indexes,
)
from admin_intelligence_service import (
    get_qualified_leads_list,
    get_customer_intelligence_detail,
    get_intelligence_overview,
)
from scoring_constants import HOT, WARM


def _utc_hours_ago(hours: float):
    return datetime.now(timezone.utc) - timedelta(hours=hours)


def _utc_days_ago(days: float):
    return datetime.now(timezone.utc) - timedelta(days=days)


class LeadScoringAndDataSyncTests(unittest.TestCase):
    def setUp(self):
        self.client = app_module.app.test_client()
        self.db = app_module.db
        self.profiles = app_module.profiles_collection
        self.features = app_module.customer_features_collection
        self.lead_state = app_module.customer_lead_state_collection
        self.sessions = app_module.sessions_collection
        self.events = app_module.events_collection
        self.orders = app_module.orders_collection
        self.cart = app_module.cart_collection
        self.wishlist = app_module.wishlist_collection

        ensure_customer_features_indexes(self.features)
        ensure_customer_lead_state_indexes(self.lead_state)

    # -------------------------------------------------------------------------
    # Scenario 1: New customer signup / empty state
    # -------------------------------------------------------------------------
    def test_01_new_customer_empty_state_is_cold_unqualified_prospect(self):
        user_id = ObjectId()
        self.profiles.insert_one({
            "_id": user_id,
            "email": "newbie@test.com",
            "username": "newbie",
            "created_at": datetime.now(timezone.utc),
        })

        feat = aggregate_customer_features(user_id, self.db)
        self.features.insert_one(feat)
        state = sync_customer_lead_state(user_id, self.db)

        self.assertEqual(state["lead_segment"], "Cold")
        self.assertLess(state["lead_score"], WARM)
        self.assertEqual(state["qualification_status"], "not_qualified")
        self.assertEqual(state["lifecycle_status"], "prospect")
        self.assertFalse(state["is_converted"])

    # -------------------------------------------------------------------------
    # Scenario 2: Browsing products (views & searches) produces honest score
    # -------------------------------------------------------------------------
    def test_02_browsing_products_increases_score_honestly_without_hot(self):
        user_id = ObjectId()
        sess_id = ObjectId()
        now = datetime.now(timezone.utc)

        self.profiles.insert_one({"_id": user_id, "email": "browser@test.com"})
        self.sessions.insert_one({
            "_id": sess_id,
            "user_id": user_id,
            "started_at": now,
            "last_active_at": now,
            "total_time_seconds": 400,
            "page_views": 6,
        })

        # 3 distinct product views + 2 searches
        for i in range(3):
            self.events.insert_one({
                "session_id": sess_id,
                "user_id": user_id,
                "event_type": "product_view",
                "entity": {"id": f"prod_{i+1}", "type": "product"},
                "timestamp": now,
            })
        for i in range(2):
            self.events.insert_one({
                "session_id": sess_id,
                "user_id": user_id,
                "event_type": "search",
                "metadata": {"query": f"shoes {i}"},
                "timestamp": now,
            })

        feat = aggregate_customer_features(user_id, self.db)
        self.assertEqual(feat["unique_products_viewed"], 3)
        self.assertEqual(feat["search_count"], 2)

        self.features.insert_one(feat)
        state = sync_customer_lead_state(user_id, self.db)

        # Browsing alone should not jump to Hot, score is honest
        self.assertLess(state["lead_score"], HOT)
        self.assertEqual(state["qualification_status"], "not_qualified")
        self.assertEqual(state["lifecycle_status"], "prospect")

    # -------------------------------------------------------------------------
    # Scenario 3: Adding item to cart increases score, does NOT jump to Hot
    # -------------------------------------------------------------------------
    def test_03_adding_to_cart_increments_score_honestly_not_hot(self):
        user_id = ObjectId()
        self.profiles.insert_one({"_id": user_id, "email": "cartuser@test.com"})
        self.cart.insert_one({
            "user_id": user_id,
            "product_id": "prod_100",
            "quantity": 1,
            "price": 250.0,
            "added_at": datetime.now(timezone.utc),
        })

        feat = aggregate_customer_features(user_id, self.db)
        self.assertEqual(feat["cart_item_count"], 1)

        self.features.insert_one(feat)
        state = sync_customer_lead_state(user_id, self.db)

        # 1 item in cart without checkout should NEVER make a customer Hot
        self.assertNotEqual(state["lead_segment"], "Hot")
        self.assertLess(state["lead_score"], HOT)
        self.assertEqual(state["qualification_status"], "not_qualified")

    # -------------------------------------------------------------------------
    # Scenario 4: Multiple items in cart provide bonus points
    # -------------------------------------------------------------------------
    def test_04_multiple_cart_items_bonus(self):
        user_id = ObjectId()
        self.profiles.insert_one({"_id": user_id, "email": "multicart@test.com"})
        self.cart.insert_one({"user_id": user_id, "product_id": "p1", "quantity": 3, "added_at": datetime.now(timezone.utc)})

        feat = aggregate_customer_features(user_id, self.db)
        score_res = compute_behavioral_score(feat)
        reasons_str = " ".join(score_res["score_reasons"])
        self.assertIn("Multiple cart items", reasons_str)

    # -------------------------------------------------------------------------
    # Scenario 5: Starting checkout with active cart yields Hot & Qualified
    # -------------------------------------------------------------------------
    def test_05_checkout_within_24h_with_active_cart_is_hot_and_qualified(self):
        user_id = ObjectId()
        sess_id = ObjectId()
        now = datetime.now(timezone.utc)

        self.profiles.insert_one({"_id": user_id, "email": "qualified_lead@test.com"})
        self.sessions.insert_one({
            "_id": sess_id,
            "user_id": user_id,
            "started_at": now,
            "last_active_at": now,
            "total_time_seconds": 600,
            "page_views": 8,
        })

        # Cart with items
        self.cart.insert_one({"user_id": user_id, "product_id": "prod_1", "quantity": 2, "added_at": now})

        # Checkout started within last 24h
        self.events.insert_one({
            "session_id": sess_id,
            "user_id": user_id,
            "event_type": "checkout_start",
            "timestamp": now - timedelta(hours=2),
        })

        # Product views (with repeat views)
        for p in ["p1", "p2", "p3", "p1", "p2"]:
            self.events.insert_one({
                "session_id": sess_id,
                "user_id": user_id,
                "event_type": "product_view",
                "entity": {"id": p},
                "timestamp": now,
            })
        for _ in range(5):
            self.events.insert_one({
                "session_id": sess_id,
                "user_id": user_id,
                "event_type": "product_click",
                "timestamp": now,
            })
        self.events.insert_one({
            "session_id": sess_id,
            "user_id": user_id,
            "event_type": "form_submit",
            "timestamp": now,
        })
        # Wishlist, search, high-intent page, and repeat session to reach genuine score >= 70 (Hot)
        self.wishlist.insert_one({"user_id": user_id, "product_id": "prod_2", "added_at": now})
        self.events.insert_one({
            "session_id": sess_id,
            "user_id": user_id,
            "event_type": "search",
            "metadata": {"query": "clothing"},
            "timestamp": now,
        })
        self.events.insert_one({
            "session_id": sess_id,
            "user_id": user_id,
            "event_type": "page_view",
            "page": "/pricing",
            "timestamp": now,
        })
        self.sessions.insert_one({
            "user_id": user_id,
            "started_at": now - timedelta(hours=1),
            "last_active_at": now - timedelta(hours=1),
            "total_time_seconds": 300,
            "page_views": 4,
        })

        feat = aggregate_customer_features(user_id, self.db)
        self.assertEqual(feat["cart_item_count"], 2)
        self.assertEqual(feat["checkout_attempts"], 1)
        self.assertTrue(feat["checkout_started_within_24h"])

        self.features.insert_one(feat)
        state = sync_customer_lead_state(user_id, self.db)

        self.assertGreaterEqual(state["lead_score"], 70)
        self.assertEqual(state["lead_segment"], "Hot")
        self.assertEqual(state["qualification_status"], "qualified")
        self.assertEqual(state["lifecycle_status"], "prospect")
        self.assertIsNotNone(state["first_qualified_at"])

    # -------------------------------------------------------------------------
    # Scenario 6: Cart quantity update updates features and supports cart_update
    # -------------------------------------------------------------------------
    def test_06_cart_quantity_update_supported(self):
        from behavior_event_service import SUPPORTED_EVENT_TYPES
        self.assertIn("cart_update", SUPPORTED_EVENT_TYPES)
        self.assertEqual(SUPPORTED_EVENT_TYPES["cart_update"], ("commerce", "update"))

    # -------------------------------------------------------------------------
    # Scenario 7: Removing item from cart decreases score
    # -------------------------------------------------------------------------
    def test_07_removing_from_cart_clears_cart_points(self):
        features_with_cart = {
            "sessions_count": 2,
            "cart_item_count": 2,
            "cart_value": 300.0,
            "days_since_last_activity": 0.1,
        }
        features_empty_cart = {
            "sessions_count": 2,
            "cart_item_count": 0,
            "cart_value": 0.0,
            "days_since_last_activity": 0.1,
        }
        res_with = compute_behavioral_score(features_with_cart)
        res_without = compute_behavioral_score(features_empty_cart)

        self.assertGreater(res_with["lead_score"], res_without["lead_score"])

    # -------------------------------------------------------------------------
    # Scenario 8: Completing purchase marks customer converted & not_qualified
    # -------------------------------------------------------------------------
    def test_08_completed_purchase_transitions_to_converted_and_not_qualified(self):
        user_id = ObjectId()
        now = datetime.now(timezone.utc)

        self.profiles.insert_one({"_id": user_id, "email": "buyer@test.com"})
        self.orders.insert_one({
            "_id": ObjectId(),
            "user_id": user_id,
            "status": "placed",
            "total_amount": 599.0,
            "created_at": now,
        })

        feat = aggregate_customer_features(user_id, self.db)
        self.assertEqual(feat["orders_count"], 1)
        self.assertEqual(feat["total_order_value"], 599.0)

        self.features.insert_one(feat)
        state = sync_customer_lead_state(user_id, self.db)

        self.assertTrue(state["is_converted"])
        self.assertEqual(state["lifecycle_status"], "converted")
        self.assertEqual(state["qualification_status"], "not_qualified")

    # -------------------------------------------------------------------------
    # Scenario 9: Completed purchase does NOT drop customer to Cold
    # -------------------------------------------------------------------------
    def test_09_completed_purchase_does_not_drop_customer_to_cold(self):
        user_id = ObjectId()
        sess_id1 = ObjectId()
        sess_id2 = ObjectId()
        now = datetime.now(timezone.utc)

        self.profiles.insert_one({"_id": user_id, "email": "warm_buyer@test.com"})
        self.sessions.insert_one({
            "_id": sess_id1,
            "user_id": user_id,
            "started_at": now - timedelta(days=1),
            "last_active_at": now - timedelta(days=1),
            "total_time_seconds": 400,
            "page_views": 6,
        })
        self.sessions.insert_one({
            "_id": sess_id2,
            "user_id": user_id,
            "started_at": now,
            "last_active_at": now,
            "total_time_seconds": 350,
            "page_views": 8,
        })

        for i in range(4):
            self.events.insert_one({
                "session_id": sess_id2,
                "user_id": user_id,
                "event_type": "product_view",
                "entity": {"id": f"item_{i}"},
                "timestamp": now,
            })

        for i in range(2):
            self.events.insert_one({
                "session_id": sess_id2,
                "user_id": user_id,
                "event_type": "search",
                "timestamp": now,
            })

        self.wishlist.insert_one({
            "user_id": user_id,
            "product_id": "fav_item",
            "created_at": now,
        })

        self.orders.insert_one({
            "_id": ObjectId(),
            "user_id": user_id,
            "status": "completed",
            "total_amount": 1200.0,
            "created_at": now,
        })

        feat = aggregate_customer_features(user_id, self.db)
        prediction = predict_customer_features(feat)

        # Buyer has order history (+15), searches (+6), views (+6), wishlist (+5), sessions (+3), time (+4)
        # Score must NOT be dropped to Cold!
        self.assertGreaterEqual(prediction["lead_score"], WARM)
        self.assertIn(prediction["lead_segment"], ["Warm", "Hot"])
        self.assertTrue(prediction["is_converted"])

    # -------------------------------------------------------------------------
    # Scenario 10: Repeat purchase transitions lifecycle to repeat_customer
    # -------------------------------------------------------------------------
    def test_10_repeat_purchase_transitions_to_repeat_customer(self):
        user_id = ObjectId()
        now = datetime.now(timezone.utc)

        self.profiles.insert_one({"_id": user_id, "email": "loyal@test.com"})
        for i in range(2):
            self.orders.insert_one({
                "_id": ObjectId(),
                "user_id": user_id,
                "status": "delivered",
                "total_amount": 500.0,
                "created_at": now - timedelta(days=i * 2),
            })

        feat = aggregate_customer_features(user_id, self.db)
        self.assertEqual(feat["orders_count"], 2)
        self.assertEqual(feat["total_order_value"], 1000.0)

        self.features.insert_one(feat)
        state = sync_customer_lead_state(user_id, self.db)

        self.assertEqual(state["lifecycle_status"], "repeat_customer")
        self.assertTrue(state["is_converted"])
        self.assertEqual(state["qualification_status"], "not_qualified")

    # -------------------------------------------------------------------------
    # Scenario 11: Cancelled, pending, and failed orders are NOT counted
    # -------------------------------------------------------------------------
    def test_11_cancelled_and_failed_orders_are_excluded(self):
        user_id = ObjectId()
        now = datetime.now(timezone.utc)

        self.profiles.insert_one({"_id": user_id, "email": "unhappy@test.com"})
        self.orders.insert_one({"_id": ObjectId(), "user_id": user_id, "status": "cancelled", "total_amount": 1000.0, "created_at": now})
        self.orders.insert_one({"_id": ObjectId(), "user_id": user_id, "status": "failed", "total_amount": 500.0, "created_at": now})
        self.orders.insert_one({"_id": ObjectId(), "user_id": user_id, "status": "pending", "total_amount": 750.0, "created_at": now})
        # Only 1 valid completed order
        self.orders.insert_one({"_id": ObjectId(), "user_id": user_id, "status": "placed", "total_amount": 350.0, "created_at": now})

        feat = aggregate_customer_features(user_id, self.db)
        self.assertEqual(feat["orders_count"], 1)
        self.assertEqual(feat["total_order_value"], 350.0)

    # -------------------------------------------------------------------------
    # Scenario 12: Order deduplication prevents double-counting across $or
    # -------------------------------------------------------------------------
    def test_12_order_deduplication_by_id(self):
        user_id = ObjectId()
        email = "dedup@test.com"
        anon_id = "anon_dedup_1"
        now = datetime.now(timezone.utc)

        self.profiles.insert_one({
            "_id": user_id,
            "email": email,
            "anonymous_ids": [anon_id],
        })

        # Order has matching user_id, anonymous_id, and customer_email
        order_id = ObjectId()
        self.orders.insert_one({
            "_id": order_id,
            "user_id": user_id,
            "anonymous_id": anon_id,
            "customer_email": email,
            "status": "placed",
            "total_amount": 420.0,
            "created_at": now,
        })

        feat = aggregate_customer_features(user_id, self.db)
        # Even though $or matches on 3 fields, order must only be counted ONCE
        self.assertEqual(feat["orders_count"], 1)
        self.assertEqual(feat["total_order_value"], 420.0)

    # -------------------------------------------------------------------------
    # Scenario 13: Recency decay decays ephemeral signals
    # -------------------------------------------------------------------------
    def test_13_recency_decay_reduces_old_cart_intent(self):
        recent_feat = {
            "sessions_count": 2,
            "cart_item_count": 2,
            "cart_value": 200.0,
            "days_since_last_activity": 0.1,
            "last_cart_action_at": datetime.now(timezone.utc).isoformat(),
        }
        old_feat = {
            "sessions_count": 2,
            "cart_item_count": 2,
            "cart_value": 200.0,
            "days_since_last_activity": 12.0,
            "last_cart_action_at": (datetime.now(timezone.utc) - timedelta(days=12)).isoformat(),
        }
        res_recent = compute_behavioral_score(recent_feat)
        res_old = compute_behavioral_score(old_feat)

        self.assertGreater(res_recent["lead_score"], res_old["lead_score"])
        self.assertEqual(res_old["lead_segment"], "Cold")

    # -------------------------------------------------------------------------
    # Scenario 14: Qualification strictly requires all 4 conditions
    # -------------------------------------------------------------------------
    def test_14_qualification_four_condition_enforcement(self):
        user_id = ObjectId()

        # Base high-intent unconverted customer:
        # score >= 70, cart > 0, checkout within 24h, unconverted (orders = 0)
        def base_doc(**overrides):
            doc = {
                "customer_id": user_id,
                "sessions_count": 6,
                "total_events": 80,
                "cart_item_count": 2,
                "cart_value": 400.0,
                "checkout_attempts": 2,
                "orders_count": 0,
                "total_order_value": 0.0,
                "unique_products_viewed": 4,
                "products_viewed": 6,
                "wishlist_item_count": 1,
                "search_count": 2,
                "high_intent_page_visits": 3,
                "total_time_spent": 600.0,
                "days_since_last_activity": 0.2,
                "checkout_started_within_24h": True,
                "last_checkout_action_at": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
            }
            doc.update(overrides)
            return doc

        # Permutation 1: All 4 satisfied -> qualified
        self.features.delete_many({})
        self.features.insert_one(base_doc())
        st1 = sync_customer_lead_state(user_id, self.db)
        self.assertEqual(st1["qualification_status"], "qualified")

        # Permutation 2: Converted customer without active post-order checkout -> not_qualified
        self.features.delete_many({})
        self.features.insert_one(base_doc(
            orders_count=1,
            total_order_value=200.0,
            checkout_attempts=0,
            checkout_started_within_24h=False,
            last_checkout_action_at=None,
        ))
        st2 = sync_customer_lead_state(user_id, self.db)
        self.assertEqual(st2["qualification_status"], "not_qualified")
        self.assertEqual(st2["lifecycle_status"], "converted")

        # Dynamic Re-qualification: Converted customer returns with new active checkout & cart -> dynamically qualified!
        self.features.delete_many({})
        self.features.insert_one(base_doc(orders_count=1, total_order_value=200.0, checkout_started_within_24h=True))
        st2_re = sync_customer_lead_state(user_id, self.db)
        self.assertEqual(st2_re["qualification_status"], "qualified")
        self.assertEqual(st2_re["lifecycle_status"], "converted")

        # Permutation 3: Empty cart (cart_item_count = 0) -> NOT qualified
        self.features.delete_many({})
        self.features.insert_one(base_doc(cart_item_count=0, cart_value=0.0))
        st3 = sync_customer_lead_state(user_id, self.db)
        self.assertEqual(st3["qualification_status"], "not_qualified")

        # Permutation 4: Checkout older than 24h -> NOT qualified
        self.features.delete_many({})
        self.features.insert_one(base_doc(
            checkout_started_within_24h=False,
            days_since_last_activity=3.0,
            last_checkout_action_at=(datetime.now(timezone.utc) - timedelta(hours=48)).isoformat(),
        ))
        st4 = sync_customer_lead_state(user_id, self.db)
        self.assertEqual(st4["qualification_status"], "not_qualified")

    # -------------------------------------------------------------------------
    # Scenario 15: Directory filtering supports all status categories
    # -------------------------------------------------------------------------
    def test_15_directory_status_filtering(self):
        self.lead_state.delete_many({})

        # Insert 1 qualified lead
        c_qual = ObjectId()
        self.lead_state.insert_one({
            "customer_id": c_qual,
            "qualification_status": "qualified",
            "lifecycle_status": "prospect",
            "lead_segment": "Hot",
            "lead_score": 85,
        })
        # Insert 1 unqualified prospect
        c_not_qual = ObjectId()
        self.lead_state.insert_one({
            "customer_id": c_not_qual,
            "qualification_status": "not_qualified",
            "lifecycle_status": "prospect",
            "lead_segment": "Cold",
            "lead_score": 20,
        })
        # Insert 1 converted customer (1 order)
        c_conv = ObjectId()
        self.lead_state.insert_one({
            "customer_id": c_conv,
            "qualification_status": "not_qualified",
            "lifecycle_status": "converted",
            "lead_segment": "Warm",
            "lead_score": 45,
        })
        # Insert 1 repeat customer (2+ orders)
        c_rep = ObjectId()
        self.lead_state.insert_one({
            "customer_id": c_rep,
            "qualification_status": "not_qualified",
            "lifecycle_status": "repeat_customer",
            "lead_segment": "Warm",
            "lead_score": 55,
        })

        # Test "all"
        res_all = get_qualified_leads_list(self.db, qualification_status="all")
        self.assertEqual(res_all["total"], 4)

        # Test "qualified"
        res_q = get_qualified_leads_list(self.db, qualification_status="qualified")
        self.assertEqual(res_q["total"], 1)
        self.assertEqual(res_q["items"][0]["customer_id"], str(c_qual))

        # Test "not_qualified"
        res_nq = get_qualified_leads_list(self.db, qualification_status="not_qualified")
        self.assertEqual(res_nq["total"], 1)
        self.assertEqual(res_nq["items"][0]["customer_id"], str(c_not_qual))

        # Test "converted"
        res_c = get_qualified_leads_list(self.db, qualification_status="converted")
        self.assertEqual(res_c["total"], 1)
        self.assertEqual(res_c["items"][0]["customer_id"], str(c_conv))

        # Test "repeat_customer"
        res_r = get_qualified_leads_list(self.db, qualification_status="repeat_customer")
        self.assertEqual(res_r["total"], 1)
        self.assertEqual(res_r["items"][0]["customer_id"], str(c_rep))

    # -------------------------------------------------------------------------
    # Scenario 16: Independent segment filtering
    # -------------------------------------------------------------------------
    def test_16_independent_segment_filtering(self):
        self.lead_state.delete_many({})
        self.lead_state.insert_one({"customer_id": ObjectId(), "lead_segment": "Hot", "lead_score": 85})
        self.lead_state.insert_one({"customer_id": ObjectId(), "lead_segment": "Warm", "lead_score": 50})
        self.lead_state.insert_one({"customer_id": ObjectId(), "lead_segment": "Warm", "lead_score": 60})
        self.lead_state.insert_one({"customer_id": ObjectId(), "lead_segment": "Cold", "lead_score": 20})

        res_hot = get_qualified_leads_list(self.db, qualification_status="all", segment="Hot")
        self.assertEqual(res_hot["total"], 1)

        res_warm = get_qualified_leads_list(self.db, qualification_status="all", segment="Warm")
        self.assertEqual(res_warm["total"], 2)

        res_cold = get_qualified_leads_list(self.db, qualification_status="all", segment="Cold")
        self.assertEqual(res_cold["total"], 1)

    # -------------------------------------------------------------------------
    # Scenario 17: Admin customer detail consistency
    # -------------------------------------------------------------------------
    def test_17_admin_customer_detail_authoritative_consistency(self):
        user_id = ObjectId()
        now = datetime.now(timezone.utc)

        self.profiles.insert_one({"_id": user_id, "email": "detail_test@test.com", "username": "detail_user"})
        self.cart.insert_one({"user_id": user_id, "product_id": "p_cart", "quantity": 3, "added_at": now})
        self.wishlist.insert_one({"user_id": user_id, "product_id": "p_wish", "created_at": now})
        self.orders.insert_one({"_id": ObjectId(), "user_id": user_id, "status": "completed", "total_amount": 899.0, "created_at": now})

        detail = get_customer_intelligence_detail(self.db, user_id)
        self.assertIsNotNone(detail)
        summary = detail["behavior_summary"]

        self.assertEqual(summary["orders_count"], 1)
        self.assertEqual(summary["cart_total_quantity"], 3)
        self.assertEqual(summary["wishlist_current_count"], 1)
        self.assertEqual(detail["customer"]["email"], "detail_test@test.com")


if __name__ == "__main__":
    unittest.main()
