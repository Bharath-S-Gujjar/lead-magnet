"""Targeted regression and validation test suite for Phase 3B remediations.

Verifies:
1. Admin overview segment counts (C-1): Hot, Warm, Cold correctly counted without
   being zeroed out by qualification status filters, empty dataset safety, unexpected
   segment handling, and independence between qualification status and segment counts.
2. Model explainability direction and heuristic transparency (C-2): Correct negative
   contribution for high inactivity, positive contribution for low inactivity, and
   heuristic metadata disclosures.
3. Model metadata safety (M-1): Retraining metadata generation preserves uncalibrated
   synthetic disclosure, model purpose, dynamic environment versions, and threshold rationale.
4. Model artifact preservation: Confirms production model artifacts were not modified.
"""

import json
import os
import sys
import unittest
from datetime import datetime, timezone
from bson import ObjectId

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "scripts")))

import app as app_module
from admin_intelligence_service import get_intelligence_overview, get_lead_distribution
from model_explainability_service import explain_lead_score, FEATURE_POLARITY
from train_ecommerce_model import build_model_metadata


class Phase3BRemediationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        cls.model_dir = os.path.join(cls.repo_root, "model")
        cls.metadata_path = os.path.join(cls.model_dir, "ecommerce_model_metadata.json")
        cls.model_path = os.path.join(cls.model_dir, "ecommerce_xgb_model.pkl")

    def setUp(self):
        self.client = app_module.app.test_client()
        self.db = app_module.db
        self.profiles = app_module.profiles_collection
        self.lead_state = app_module.customer_lead_state_collection
        self.features = app_module.customer_features_collection

        # Clear test collections
        self.profiles.delete_many({})
        self.lead_state.delete_many({})
        self.features.delete_many({})

    def tearDown(self):
        self.profiles.delete_many({})
        self.lead_state.delete_many({})
        self.features.delete_many({})

    # -------------------------------------------------------------------------
    # Area 1: Fix C-1 — Admin Overview Segment Counts
    # -------------------------------------------------------------------------

    def test_01_overview_counts_hot_warm_and_cold_leads_accurately(self):
        """Overview must report non-zero counts for Hot, Warm, and Cold leads."""
        now_iso = datetime.now(timezone.utc).isoformat()

        # Insert 2 Hot (qualified), 3 Warm (not_qualified), 4 Cold (not_qualified) leads
        for i in range(2):
            self.lead_state.insert_one({
                "customer_id": ObjectId(),
                "lead_probability": 0.85,
                "lead_score": 85,
                "lead_segment": "Hot",
                "qualification_status": "qualified",
                "created_at": now_iso,
            })

        for i in range(3):
            self.lead_state.insert_one({
                "customer_id": ObjectId(),
                "lead_probability": 0.55,
                "lead_score": 55,
                "lead_segment": "Warm",
                "qualification_status": "not_qualified",
                "created_at": now_iso,
            })

        for i in range(4):
            self.lead_state.insert_one({
                "customer_id": ObjectId(),
                "lead_probability": 0.20,
                "lead_score": 20,
                "lead_segment": "Cold",
                "qualification_status": "not_qualified",
                "created_at": now_iso,
            })

        overview = get_intelligence_overview(self.db)
        leads = overview["leads"]

        # Hot, Warm, and Cold must reflect actual document counts
        self.assertEqual(leads["hot"], 2, "Hot lead count must equal 2")
        self.assertEqual(leads["warm"], 3, "Warm lead count must equal 3 (not zero)")
        self.assertEqual(leads["cold"], 4, "Cold lead count must equal 4 (not zero)")
        self.assertEqual(leads["total_qualified"], 2, "Only Hot leads have qualification_status='qualified'")

    def test_02_overview_handles_empty_dataset_gracefully(self):
        """Overview must return zeros when lead_state collection is completely empty."""
        overview = get_intelligence_overview(self.db)
        leads = overview["leads"]

        self.assertEqual(leads["total_qualified"], 0)
        self.assertEqual(leads["hot"], 0)
        self.assertEqual(leads["warm"], 0)
        self.assertEqual(leads["cold"], 0)
        self.assertEqual(leads["newly_qualified_today"], 0)

    def test_03_overview_and_distribution_segment_consistency(self):
        """Overview segment counts must match get_lead_distribution segment totals."""
        now_iso = datetime.now(timezone.utc).isoformat()

        self.lead_state.insert_one({
            "customer_id": ObjectId(),
            "lead_segment": "Hot",
            "qualification_status": "qualified",
            "created_at": now_iso,
        })
        self.lead_state.insert_one({
            "customer_id": ObjectId(),
            "lead_segment": "Warm",
            "qualification_status": "not_qualified",
            "created_at": now_iso,
        })
        self.lead_state.insert_one({
            "customer_id": ObjectId(),
            "lead_segment": "Cold",
            "qualification_status": "not_qualified",
            "created_at": now_iso,
        })

        overview = get_intelligence_overview(self.db)
        distribution = get_lead_distribution(self.db)

        self.assertEqual(overview["leads"]["hot"], distribution["segments"]["hot"])
        self.assertEqual(overview["leads"]["warm"], distribution["segments"]["warm"])
        self.assertEqual(overview["leads"]["cold"], distribution["segments"]["cold"])
        self.assertEqual(overview["leads"]["total_qualified"], distribution["qualification"]["qualified"])

    def test_04_overview_handles_unexpected_segment_values(self):
        """Documents with null or unexpected segment values must not break counts."""
        now_iso = datetime.now(timezone.utc).isoformat()

        self.lead_state.insert_one({
            "customer_id": ObjectId(),
            "lead_segment": "UnknownSegment",
            "qualification_status": "not_qualified",
            "created_at": now_iso,
        })
        self.lead_state.insert_one({
            "customer_id": ObjectId(),
            "lead_segment": None,
            "qualification_status": "not_qualified",
            "created_at": now_iso,
        })
        self.lead_state.insert_one({
            "customer_id": ObjectId(),
            "lead_segment": "Hot",
            "qualification_status": "qualified",
            "created_at": now_iso,
        })

        overview = get_intelligence_overview(self.db)
        leads = overview["leads"]

        self.assertEqual(leads["hot"], 1)
        self.assertEqual(leads["warm"], 0)
        self.assertEqual(leads["cold"], 0)
        self.assertEqual(leads["total_qualified"], 1)

    def test_05_qualification_status_independence(self):
        """Qualification status remains independent of segment counts."""
        now_iso = datetime.now(timezone.utc).isoformat()

        # Edge case: A lead with Warm segment that was manually marked qualified
        self.lead_state.insert_one({
            "customer_id": ObjectId(),
            "lead_segment": "Warm",
            "qualification_status": "qualified",
            "created_at": now_iso,
        })

        overview = get_intelligence_overview(self.db)
        leads = overview["leads"]

        self.assertEqual(leads["warm"], 1, "Warm segment count accurately records 1")
        self.assertEqual(leads["total_qualified"], 1, "Total qualified accurately records 1")
        self.assertEqual(leads["hot"], 0, "Hot segment count remains 0")

    # -------------------------------------------------------------------------
    # Area 2: Fix C-2 — Model Explainability Direction & Heuristic Transparency
    # -------------------------------------------------------------------------

    def _sample_features(self, days_since_last_activity=2.0):
        return {
            "customer_id": "cust_test_exp",
            "sessions_count": 5,
            "total_events": 50,
            "total_time_spent": 800.0,
            "average_session_duration": 160.0,
            "page_views_count": 25,
            "days_since_last_activity": days_since_last_activity,
            "products_viewed": 10,
            "unique_products_viewed": 5,
            "product_interactions": 15,
            "search_count": 2,
            "form_submit_count": 0,
            "high_intent_page_visits": 3,
            "cart_item_count": 2,
            "cart_value": 150.0,
            "wishlist_item_count": 1,
            "checkout_attempts": 2,
            "orders_count": 1,
            "total_order_value": 80.0,
            "average_order_value": 80.0,
        }

    def test_06_high_inactivity_produces_negative_direction(self):
        """Customer with high inactivity (60 days) must have negative direction for days_since_last_activity."""
        features = self._sample_features(days_since_last_activity=60.0)
        explanation = explain_lead_score(features)

        self.assertIn("top_driving_factors", explanation)
        inactivity_factors = [
            f for f in explanation["top_driving_factors"]
            if f["feature"] == "days_since_last_activity"
        ]

        if inactivity_factors:
            factor = inactivity_factors[0]
            self.assertEqual(factor["direction"], "negative", "Prolonged inactivity must be a negative factor")
            self.assertLess(factor["contribution"], 0.0, "Inactivity contribution score must be negative")

        # Also verify in negative_contributors list
        negative_features = [f["feature"] for f in explanation["negative_contributors"]]
        self.assertIn("days_since_last_activity", negative_features)

    def test_07_low_inactivity_produces_positive_direction(self):
        """Customer active today (0.1 days) must have positive direction for days_since_last_activity."""
        features = self._sample_features(days_since_last_activity=0.1)
        explanation = explain_lead_score(features)

        inactivity_factors = [
            f for f in explanation["top_driving_factors"]
            if f["feature"] == "days_since_last_activity"
        ]

        if inactivity_factors:
            factor = inactivity_factors[0]
            self.assertEqual(factor["direction"], "positive", "Recent activity must be a positive factor")
            self.assertGreater(factor["contribution"], 0.0, "Recent activity contribution score must be positive")

        positive_features = [f["feature"] for f in explanation["positive_contributors"]]
        self.assertIn("days_since_last_activity", positive_features)

    def test_08_explainability_discloses_heuristic_nature(self):
        """Explainability output must include is_heuristic and heuristic_basis metadata."""
        features = self._sample_features(days_since_last_activity=5.0)
        explanation = explain_lead_score(features)

        self.assertTrue(explanation.get("is_heuristic"), "Must disclose is_heuristic=True")
        self.assertEqual(explanation.get("heuristic_basis"), "importance_weighted_zscore")
        self.assertEqual(explanation.get("explanation_method"), "deterministic_feature_contribution")
        self.assertIn("deterministic approximation", explanation.get("explanation_note", ""))
        self.assertIn("inverse polarity", explanation.get("explanation_note", ""))

    def test_09_polarity_map_includes_inactivity(self):
        """FEATURE_POLARITY must define days_since_last_activity as -1.0."""
        self.assertIn("days_since_last_activity", FEATURE_POLARITY)
        self.assertEqual(FEATURE_POLARITY["days_since_last_activity"], -1.0)

    # -------------------------------------------------------------------------
    # Area 3: Fix M-1 — Retraining Metadata Safety
    # -------------------------------------------------------------------------

    def test_10_build_model_metadata_preserves_safety_disclosures(self):
        """build_model_metadata must include all required safety fields and uncalibrated status."""
        cols = ["sessions_count", "total_events", "cart_value"]
        feat_imp = [("cart_value", 0.6), ("sessions_count", 0.3), ("total_events", 0.1)]

        meta = build_model_metadata(
            total_samples=1000,
            train_samples=700,
            val_samples=150,
            test_samples=150,
            feature_cols=cols,
            baseline_lr_metrics={"val_roc_auc": 0.95, "test_roc_auc": 0.94},
            primary_xgb_metrics={"val_roc_auc": 0.97, "test_roc_auc": 0.96},
            feat_imp=feat_imp,
        )

        # Safety disclosures must be present and verified
        self.assertEqual(meta["calibration_status"], "uncalibrated_synthetic")
        self.assertEqual(meta["model_purpose"], "conversion_propensity_prediction")
        self.assertIn("calibration_disclaimer", meta)
        self.assertIn("synthetic log-odds", meta["calibration_disclaimer"])
        self.assertIn("training_environment", meta)
        self.assertIn("python", meta["training_environment"])
        self.assertIn("scikit-learn", meta["training_environment"])
        self.assertIn("xgboost", meta["training_environment"])
        self.assertEqual(meta["recommended_thresholds"]["hot_segment_min_prob"], 0.70)
        self.assertEqual(meta["recommended_thresholds"]["warm_segment_min_prob"], 0.35)
        self.assertEqual(meta["recommended_thresholds"]["cold_segment_max_prob"], 0.35)
        self.assertEqual(meta["recommended_thresholds"]["threshold_selection_method"], "precision_at_top_k")
        self.assertIn("threshold_calibration_rationale", meta["recommended_thresholds"])

    def test_11_production_model_artifacts_remain_unmodified(self):
        """Confirm that production model binary and metadata file exist and were not overwritten."""
        self.assertTrue(os.path.exists(self.model_path), "Production model binary must exist")
        self.assertTrue(os.path.exists(self.metadata_path), "Production model metadata must exist")

        with open(self.metadata_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)

        self.assertEqual(metadata["model_version"], "v2.0_ecommerce_xgb")
        self.assertEqual(metadata["calibration_status"], "uncalibrated_synthetic")
        self.assertEqual(len(metadata["feature_columns"]), 23)


if __name__ == "__main__":
    unittest.main()
