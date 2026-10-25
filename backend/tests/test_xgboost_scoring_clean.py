"""Clean XGBoost Lead Scoring Tests
=================================

Validates:
1. Pure XGBoost model is the direct, authoritative lead scorer.
2. Login-only new accounts score Cold (score <= 10) with low confidence / provisional.
3. Active-checkout override within 24h promotes segment to Hot with score honest.
4. Converted customers are marked is_converted=True and qualification_status='not_qualified'.
5. High-activity customers score Warm/Hot organically based on XGBoost inference.
"""

import os
import sys
import unittest
from datetime import datetime, timezone, timedelta
from bson import ObjectId

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ecommerce_model_adapter import predict_customer_features
from customer_lead_state_service import sync_customer_lead_state, ensure_customer_lead_state_indexes
from customer_feature_service import ensure_customer_features_indexes
import app as app_module


def _base_features(**overrides):
    base = {
        "sessions_count": 1,
        "total_events": 2,
        "total_time_spent": 0.0,
        "average_session_duration": 0.0,
        "page_views_count": 1,
        "days_since_last_activity": 0.0,
        "products_viewed": 0,
        "unique_products_viewed": 0,
        "product_interactions": 0,
        "search_count": 0,
        "form_submit_count": 0,
        "high_intent_page_visits": 0,
        "cart_item_count": 0,
        "cart_value": 0.0,
        "wishlist_item_count": 0,
        "checkout_attempts": 0,
        "orders_count": 0,
        "total_order_value": 0.0,
        "average_order_value": 0.0,
        "last_checkout_action_at": None,
        "last_cart_action_at": None,
    }
    base.update(overrides)
    return base


class CleanXGBoostScoringTests(unittest.TestCase):
    """Test pure XGBoost inference without complex rule baggage."""

    def test_01_login_only_new_customer_scores_cold(self):
        """A customer who only logged in must score Cold and be marked provisional."""
        features = _base_features(sessions_count=1, days_since_last_activity=0.0)
        res = predict_customer_features(features)

        self.assertEqual(res["lead_segment"], "Cold")
        self.assertLessEqual(res["lead_score"], 10)
        self.assertTrue(res["is_provisional"])
        self.assertEqual(res["confidence"], "low")
        self.assertEqual(res["scoring_method"], "xgboost_direct_ml_model")

    def test_02_active_checkout_override_promotes_to_hot(self):
        """Checkout within 24h promotes segment to Hot while keeping score honest."""
        features = _base_features(
            sessions_count=2,
            cart_item_count=2,
            cart_value=400.0,
            checkout_attempts=1,
            days_since_last_activity=0.2,
        )
        res = predict_customer_features(features)

        self.assertEqual(res["lead_segment"], "Hot")
        self.assertTrue(res["active_checkout_override"])
        self.assertIn("OVERRIDE", res["segment_reason"])
        self.assertFalse(res["is_provisional"])

    def test_03_browsing_only_scores_cold(self):
        """Browsing a few products without purchase intent remains Cold."""
        features = _base_features(
            sessions_count=1,
            products_viewed=3,
            unique_products_viewed=3,
            days_since_last_activity=0.5,
        )
        res = predict_customer_features(features)
        self.assertEqual(res["lead_segment"], "Cold")
        self.assertLessEqual(res["lead_score"], 34)

    def test_04_repeat_order_scores_high_and_marks_converted(self):
        """Customer who completed purchase is converted."""
        features = _base_features(
            sessions_count=5,
            cart_item_count=3,
            cart_value=600.0,
            checkout_attempts=2,
            orders_count=2,
            total_order_value=900.0,
            average_order_value=450.0,
            days_since_last_activity=0.1,
        )
        res = predict_customer_features(features)
        self.assertTrue(res["is_converted"])
        self.assertGreaterEqual(res["lead_score"], 70)
        self.assertEqual(res["lead_segment"], "Hot")

    def test_05_customer_lead_state_sync_with_xgboost(self):
        """Test full sync_customer_lead_state pipeline with XGBoost."""
        db = app_module.db
        features_col = app_module.customer_features_collection
        state_col = app_module.customer_lead_state_collection
        ensure_customer_features_indexes(features_col)
        ensure_customer_lead_state_indexes(state_col)

        cid = ObjectId()
        features_col.insert_one(_base_features(customer_id=cid))
        try:
            state = sync_customer_lead_state(cid, db)
            self.assertEqual(state["lead_segment"], "Cold")
            self.assertEqual(state["qualification_status"], "not_qualified")
            self.assertEqual(state["lifecycle_status"], "prospect")
            self.assertTrue(state["is_provisional"])
            self.assertEqual(state["confidence"], "low")
        finally:
            features_col.delete_many({"customer_id": cid})
            state_col.delete_many({"customer_id": cid})


if __name__ == "__main__":
    unittest.main(verbosity=2)
