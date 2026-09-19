"""Tests for Task 10 Phase 2B E-Commerce Lead Scoring Inference.

Verifies model artifact loading, feature order preservation, inference prediction contract,
input validation & rejection, auth ownership protection, admin diagnostic access, and database immutability.
"""

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
import jwt
import math
from bson import ObjectId

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module
from ecommerce_model_adapter import (
    load_ecommerce_model,
    load_ecommerce_scaler,
    load_ecommerce_feature_columns,
    load_ecommerce_metadata,
    predict_customer_features,
)
from customer_feature_service import ensure_customer_features_indexes


def sample_valid_customer_features(customer_id="cust_test_123"):
    return {
        "customer_id": customer_id,
        "sessions_count": 5,
        "total_events": 45,
        "total_time_spent": 600.0,
        "average_session_duration": 120.0,
        "page_views_count": 25,
        "days_since_last_activity": 2.5,
        "products_viewed": 10,
        "unique_products_viewed": 6,
        "product_interactions": 15,
        "search_count": 3,
        "form_submit_count": 1,
        "high_intent_page_visits": 4,
        "cart_item_count": 2,
        "cart_value": 150.0,
        "wishlist_item_count": 1,
        "checkout_attempts": 2,
        "orders_count": 1,
        "total_order_value": 80.0,
        "average_order_value": 80.0,
    }


class EcommerceLeadInferenceTests(unittest.TestCase):
    def setUp(self):
        self.client = app_module.app.test_client()
        self.db = app_module.db
        self.profiles = app_module.profiles_collection
        self.features = app_module.customer_features_collection
        self.leads = app_module.leads_collection

        ensure_customer_features_indexes(self.features)

        self.jwt_secret = app_module.JWT_SECRET

    def make_token(self, user_id, role="user"):
        exp_time = datetime.now(timezone.utc) + timedelta(minutes=5)
        return jwt.encode(
            {"sub": str(user_id), "role": role, "exp": exp_time},
            self.jwt_secret,
            algorithm="HS256"
        )

    # 1. Model artifacts load
    def test_01_model_artifacts_load(self):
        model = load_ecommerce_model()
        scaler = load_ecommerce_scaler()
        cols = load_ecommerce_feature_columns()
        meta = load_ecommerce_metadata()

        self.assertIsNotNone(model)
        self.assertIsNotNone(scaler)
        self.assertEqual(len(cols), 23)
        self.assertIn("model_version", meta)

    # 2. Feature column order is preserved
    def test_02_feature_column_order_preserved(self):
        cols = load_ecommerce_feature_columns()
        expected = [
            "sessions_count",
            "total_events",
            "total_time_spent",
            "average_session_duration",
            "page_views_count",
            "days_since_last_activity",
            "products_viewed",
            "unique_products_viewed",
            "product_interactions",
            "search_count",
            "form_submit_count",
            "high_intent_page_visits",
            "cart_item_count",
            "cart_value",
            "wishlist_item_count",
            "checkout_attempts",
            "orders_count",
            "total_order_value",
            "average_order_value",
            "cart_to_session_ratio",
            "checkout_to_cart_ratio",
            "high_intent_ratio",
            "product_interaction_density",
        ]
        self.assertEqual(list(cols), expected)

    # 3. Valid customer_features produces probability
    def test_03_valid_customer_features_produces_probability(self):
        feat = sample_valid_customer_features()
        res = predict_customer_features(feat)
        self.assertIn("lead_probability", res)
        self.assertIsInstance(res["lead_probability"], float)

    # 4. Probability is between 0 and 1
    def test_04_probability_between_0_and_1(self):
        feat = sample_valid_customer_features()
        res = predict_customer_features(feat)
        self.assertGreaterEqual(res["lead_probability"], 0.0)
        self.assertLessEqual(res["lead_probability"], 1.0)

    # 5. lead_score is between 0 and 100
    def test_05_lead_score_between_0_and_100(self):
        feat = sample_valid_customer_features()
        res = predict_customer_features(feat)
        self.assertIsInstance(res["lead_score"], int)
        self.assertGreaterEqual(res["lead_score"], 0)
        self.assertLessEqual(res["lead_score"], 100)
        self.assertEqual(res["lead_score"], int(round(res["lead_probability"] * 100)))

    # 6. Segment calculation works
    def test_06_segment_calculation_thresholds(self):
        feat_high = sample_valid_customer_features()
        feat_high.update({"checkout_attempts": 10, "cart_value": 1000.0, "high_intent_page_visits": 15})
        res_high = predict_customer_features(feat_high)
        if res_high["lead_probability"] >= 0.70:
            self.assertEqual(res_high["lead_segment"], "Hot")

        feat_low = sample_valid_customer_features()
        feat_low.update({"checkout_attempts": 0, "cart_value": 0.0, "high_intent_page_visits": 0, "days_since_last_activity": 60.0})
        res_low = predict_customer_features(feat_low)
        if res_low["lead_probability"] < 0.35:
            self.assertEqual(res_low["lead_segment"], "Cold")

    # 7. Missing required feature is rejected
    def test_07_missing_required_feature_rejected(self):
        feat = sample_valid_customer_features()
        del feat["sessions_count"]
        with self.assertRaises(ValueError):
            predict_customer_features(feat)

    # 8. Invalid numeric value is rejected
    def test_08_invalid_numeric_value_rejected(self):
        feat1 = sample_valid_customer_features()
        feat1["cart_value"] = "invalid_string"
        with self.assertRaises(ValueError):
            predict_customer_features(feat1)

        feat2 = sample_valid_customer_features()
        feat2["checkout_attempts"] = float("nan")
        with self.assertRaises(ValueError):
            predict_customer_features(feat2)

        feat3 = sample_valid_customer_features()
        feat3["total_events"] = True
        with self.assertRaises(ValueError):
            predict_customer_features(feat3)

    # 9. Extra fields do not alter model feature ordering
    def test_09_extra_fields_do_not_alter_model_feature_ordering(self):
        feat_base = sample_valid_customer_features()
        res_base = predict_customer_features(feat_base)

        feat_extra = sample_valid_customer_features()
        feat_extra.update({"extra_unrelated_column": "hello", "random_tag": 999})
        res_extra = predict_customer_features(feat_extra)

        self.assertEqual(res_base["lead_probability"], res_extra["lead_probability"])
        self.assertEqual(res_base["lead_score"], res_extra["lead_score"])

    # 10. Same input produces deterministic output
    def test_10_deterministic_output(self):
        feat = sample_valid_customer_features()
        res1 = predict_customer_features(feat)
        res2 = predict_customer_features(feat)

        self.assertEqual(res1["lead_probability"], res2["lead_probability"])
        self.assertEqual(res1["lead_score"], res2["lead_score"])
        self.assertEqual(res1["lead_segment"], res2["lead_segment"])

    # 11. Authenticated customer cannot request another customer's score
    def test_11_authenticated_customer_cannot_request_another_customer_score(self):
        user_a_id = ObjectId()
        user_b_id = ObjectId()

        doc_a = sample_valid_customer_features(str(user_a_id))
        doc_b = sample_valid_customer_features(str(user_b_id))
        doc_b["cart_value"] = 999.0

        self.features.insert_one({"customer_id": user_a_id, **doc_a})
        self.features.insert_one({"customer_id": user_b_id, **doc_b})

        token_a = self.make_token(user_a_id, role="user")

        # Requesting /api/customer/lead-score with User A token and spoofed ?customer_id=user_b_id
        res = self.client.get(
            f"/api/customer/lead-score?customer_id={user_b_id}",
            headers={"Authorization": f"Bearer {token_a}"}
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()["data"]
        # Must return User A's score, NOT User B's score!
        self.assertEqual(data["customer_id"], str(user_a_id))

    # 12. Admin can inspect a valid customer
    def test_12_admin_can_inspect_valid_customer(self):
        target_id = ObjectId()
        doc = sample_valid_customer_features(str(target_id))
        self.features.insert_one({"customer_id": target_id, **doc})

        admin_id = ObjectId()
        admin_token = self.make_token(admin_id, role="admin")

        res = self.client.get(
            f"/api/admin/customer-lead-score/{target_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()["data"]
        self.assertEqual(data["customer_id"], str(target_id))
        self.assertIn("lead_score", data)

    # 13. Non-admin cannot access admin diagnostic endpoint
    def test_13_non_admin_cannot_access_admin_diagnostic_endpoint(self):
        target_id = ObjectId()
        doc = sample_valid_customer_features(str(target_id))
        self.features.insert_one({"customer_id": target_id, **doc})

        user_token = self.make_token(ObjectId(), role="user")

        res = self.client.get(
            f"/api/admin/customer-lead-score/{target_id}",
            headers={"Authorization": f"Bearer {user_token}"}
        )
        self.assertEqual(res.status_code, 403)

    # 14. Missing customer feature document returns 404
    def test_14_missing_customer_feature_document_returns_404(self):
        user_id = ObjectId()
        token = self.make_token(user_id, role="user")

        res = self.client.get(
            "/api/customer/lead-score",
            headers={"Authorization": f"Bearer {token}"}
        )
        self.assertEqual(res.status_code, 404)

        admin_token = self.make_token(ObjectId(), role="admin")
        res_admin = self.client.get(
            f"/api/admin/customer-lead-score/{user_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        self.assertEqual(res_admin.status_code, 404)

    # 15. Inference does not modify MongoDB
    def test_15_inference_does_not_modify_mongodb(self):
        user_id = ObjectId()
        doc = sample_valid_customer_features(str(user_id))
        self.features.insert_one({"customer_id": user_id, **doc})

        leads_before = self.leads.count_documents({})
        features_before = self.features.find_one({"customer_id": user_id})

        token = self.make_token(user_id, role="user")
        res = self.client.get(
            "/api/customer/lead-score",
            headers={"Authorization": f"Bearer {token}"}
        )
        self.assertEqual(res.status_code, 200)

        leads_after = self.leads.count_documents({})
        features_after = self.features.find_one({"customer_id": user_id})

        self.assertEqual(leads_before, leads_after)
        self.assertEqual(features_before, features_after)


if __name__ == "__main__":
    unittest.main()
