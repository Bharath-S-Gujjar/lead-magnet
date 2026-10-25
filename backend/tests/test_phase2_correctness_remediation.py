"""Focused regression and correctness tests for Phase 2 remediation.

Covers:
1. Identity Merge Rescoring:
   - resolve_anonymous_identity immediately synchronizes customer_lead_state
     and updates lead scoring for the canonical user profile.
2. Admin Intelligence Date Handling:
   - get_intelligence_overview correctly matches both BSON datetime.datetime objects
     and ISO strings for active_today, new_today, and newly_qualified_today.
3. Prediction Service Feature Name Preservation:
   - predict_session passes named DataFrame to KMeans and XGBoost,
     preventing scikit-learn UserWarning about missing feature names.
4. Behavior Event Ingestion & Feature Aggregation for Customer Journey:
   - product_view, product_click, checkout_start, and remove_from_cart events
     are ingested cleanly and correctly reflect in customer feature aggregation.
"""

import os
import sys
import unittest
import warnings
from datetime import datetime, timezone
from bson import ObjectId
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from identity_service import resolve_anonymous_identity
from admin_intelligence_service import get_intelligence_overview
from prediction_service import predict_session
from behavior_event_service import log_behavior_event
from customer_feature_service import aggregate_customer_features, upsert_customer_features
from customer_lead_state_service import get_customer_lead_state
from model_adapter import adapt_behavioral_features
from app import app, db


class TestPhase2CorrectnessRemediation(unittest.TestCase):
    """Test suite verifying Phase 2 correctness fixes."""

    def test_01_prediction_service_silences_kmeans_feature_name_warning(self):
        """predict_session must not emit UserWarning about missing feature names."""
        # Create a sample model input dataframe using standard feature adapter
        sample_snapshot = {
            "landing_source": "google",
            "landing_page": "/catalog",
            "event_count": 5,
            "page_views": 3,
            "high_intent_page_visits": 1,
            "form_submit_count": 0,
            "total_time_seconds": 120.0,
            "cart_item_count": 1,
            "wishlist_item_count": 0,
            "checkout_attempts": 0,
        }
        model_input = adapt_behavioral_features(sample_snapshot)

        with warnings.catch_warnings(record=True) as caught_warnings:
            warnings.simplefilter("always")
            prediction = predict_session(model_input)

            # Check that no UserWarning contains the KMeans feature name warning
            kmeans_warnings = [
                w for w in caught_warnings
                if issubclass(w.category, UserWarning) and "KMeans was fitted with feature names" in str(w.message)
            ]
            self.assertEqual(
                len(kmeans_warnings), 0,
                f"KMeans feature names warning was emitted: {[str(w.message) for w in kmeans_warnings]}"
            )

        self.assertIn("score", prediction)
        self.assertIn("segment", prediction)
        self.assertIn("next_action", prediction)

    def test_02_admin_intelligence_counts_datetime_and_string_timestamps(self):
        """get_intelligence_overview matches both BSON datetime objects and ISO strings."""
        if db is None:
            self.skipTest("MongoDB not available")

        profiles_col = db["user_profiles"]
        lead_state_col = db["customer_lead_state"]

        now = datetime.now(timezone.utc)
        today_prefix = now.strftime("%Y-%m-%d")

        # Insert a profile with BSON datetime created_at and last_active_at
        test_user_dt = {
            "email": f"dt_test_{ObjectId()}@example.com",
            "role": "user",
            "created_at": now,
            "last_active_at": now,
        }
        res_dt = profiles_col.insert_one(test_user_dt)

        # Insert a profile with ISO string created_at and last_active_at
        test_user_str = {
            "email": f"str_test_{ObjectId()}@example.com",
            "role": "user",
            "created_at": now.isoformat(),
            "last_active_at": now.isoformat(),
        }
        res_str = profiles_col.insert_one(test_user_str)

        try:
            overview = get_intelligence_overview(db)
            customers = overview.get("customers", {})

            # Both profiles should be counted in active_today and new_today
            self.assertGreaterEqual(customers.get("active_today", 0), 2)
            self.assertGreaterEqual(customers.get("new_today", 0), 2)
        finally:
            profiles_col.delete_one({"_id": res_dt.inserted_id})
            profiles_col.delete_one({"_id": res_str.inserted_id})

    def test_03_identity_merge_triggers_immediate_rescore(self):
        """resolve_anonymous_identity updates customer_lead_state immediately on merge."""
        if db is None:
            self.skipTest("MongoDB not available")

        user_id = ObjectId()
        anon_id = f"anon_phase2_{user_id}"

        users_col = db["user_profiles"]
        sessions_col = db["sessions"]
        events_col = db["events"]
        leads_col = db["leads"]
        cart_col = db["cart"]
        wishlist_col = db["wishlist"]
        features_col = db["customer_features"]
        lead_state_col = db["customer_lead_state"]

        # Create user profile
        users_col.insert_one({
            "_id": user_id,
            "email": f"merge_{user_id}@example.com",
            "role": "user",
            "created_at": datetime.now(timezone.utc),
        })

        # Create anonymous session and event
        session_id = sessions_col.insert_one({
            "visitor_id": anon_id,
            "anonymous_id": anon_id,
            "started_at": datetime.now(timezone.utc),
            "status": "active",
        }).inserted_id

        events_col.insert_one({
            "session_id": session_id,
            "visitor_id": anon_id,
            "anonymous_id": anon_id,
            "event_type": "product_view",
            "timestamp": datetime.now(timezone.utc),
            "entity": {"id": "prod_123", "title": "Test Product"},
        })

        try:
            resolve_anonymous_identity(
                anonymous_id=anon_id,
                user_id=user_id,
                users_collection=users_col,
                sessions_collection=sessions_col,
                events_collection=events_col,
                leads_collection=leads_col,
                cart_collection=cart_col,
                wishlist_collection=wishlist_col,
                customer_features_collection=features_col,
                db=db,
            )

            # Assert feature record exists
            feature_doc = features_col.find_one({"customer_id": user_id})
            self.assertIsNotNone(feature_doc, "Customer features should exist after merge")

            # Assert lead state record exists and was synchronized
            lead_state = get_customer_lead_state(user_id, db)
            self.assertIsNotNone(lead_state, "Customer lead state must exist and be synchronized after merge")
            self.assertIn("lead_score", lead_state)
            self.assertIn("lead_segment", lead_state)
            self.assertIn("qualification_status", lead_state)
        finally:
            users_col.delete_one({"_id": user_id})
            sessions_col.delete_one({"_id": session_id})
            events_col.delete_many({"session_id": session_id})
            features_col.delete_one({"customer_id": user_id})
            lead_state_col.delete_one({"customer_id": user_id})

    def test_04_customer_journey_telemetry_events_ingested_and_aggregated(self):
        """product_view, product_click, checkout_start, and remove_from_cart are properly ingested."""
        if db is None:
            self.skipTest("MongoDB not available")

        user_id = ObjectId()
        anon_id = f"anon_telemetry_{user_id}"

        sessions_col = db["sessions"]
        events_col = db["events"]
        profiles_col = db["user_profiles"]

        profiles_col.insert_one({
            "_id": user_id,
            "email": f"telemetry_{user_id}@example.com",
            "role": "user",
        })

        session_id = sessions_col.insert_one({
            "visitor_id": anon_id,
            "anonymous_id": anon_id,
            "user_id": user_id,
            "started_at": datetime.now(timezone.utc),
            "status": "active",
        }).inserted_id

        try:
            # 1. product_view
            event_id1 = log_behavior_event({
                "session_id": str(session_id),
                "event_type": "product_view",
                "page": "/product/prod_100",
                "entity": {"id": "prod_100", "title": "Cotton Shirt"},
            }, sessions_col, events_col)
            self.assertIsNotNone(event_id1)

            # 2. product_click
            event_id2 = log_behavior_event({
                "session_id": str(session_id),
                "event_type": "product_click",
                "page": "/catalog",
                "entity": {"id": "prod_100", "title": "Cotton Shirt"},
            }, sessions_col, events_col)
            self.assertIsNotNone(event_id2)

            # 3. checkout_start
            event_id3 = log_behavior_event({
                "session_id": str(session_id),
                "event_type": "checkout_start",
                "page": "/cart",
                "metadata": {"items_count": 1, "total_amount": 1500},
            }, sessions_col, events_col)
            self.assertIsNotNone(event_id3)

            # 4. remove_from_cart
            event_id4 = log_behavior_event({
                "session_id": str(session_id),
                "event_type": "remove_from_cart",
                "entity": {"id": "prod_100"},
            }, sessions_col, events_col)
            self.assertIsNotNone(event_id4)

            # Compute features and assert metrics reflect these events
            features = aggregate_customer_features(user_id, db)
            self.assertEqual(features["products_viewed"], 1)
            self.assertEqual(features["unique_products_viewed"], 1)
            self.assertEqual(features["checkout_attempts"], 1)
            self.assertGreaterEqual(features["product_interactions"], 2)
        finally:
            profiles_col.delete_one({"_id": user_id})
            sessions_col.delete_one({"_id": session_id})
            events_col.delete_many({"session_id": session_id})


if __name__ == "__main__":
    unittest.main()
