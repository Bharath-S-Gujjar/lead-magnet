import json
import os
import sys
import unittest
import joblib
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


class EcommerceMLPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        cls.dataset_path = os.path.join(repo_root, "data", "ml", "ecommerce_customer_behavior.csv")
        if not os.path.exists(cls.dataset_path):
            cls.dataset_path = os.path.join("data", "ml", "ecommerce_customer_behavior.csv")

        cls.model_dir = os.path.join(repo_root, "model")
        if not os.path.exists(cls.model_dir):
            cls.model_dir = "model"

        cls.model_path = os.path.join(cls.model_dir, "ecommerce_xgb_model.pkl")
        cls.scaler_path = os.path.join(cls.model_dir, "ecommerce_scaler.pkl")
        cls.cols_path = os.path.join(cls.model_dir, "ecommerce_feature_columns.pkl")
        cls.meta_path = os.path.join(cls.model_dir, "ecommerce_model_metadata.json")

    def test_dataset_schema_and_size(self):
        self.assertTrue(os.path.exists(self.dataset_path), "Dataset CSV missing")
        df = pd.read_csv(self.dataset_path)
        self.assertGreaterEqual(len(df), 5000, "Dataset must have >= 5000 rows")
        self.assertEqual(len(df.columns), 25, "Dataset must have 25 columns")
        self.assertIn("customer_id", df.columns)
        self.assertIn("converted_in_window", df.columns)

    def test_target_label_validity(self):
        df = pd.read_csv(self.dataset_path)
        unique_targets = set(df["converted_in_window"].unique())
        self.assertTrue(unique_targets.issubset({0, 1}))

    def test_artifacts_exist(self):
        self.assertTrue(os.path.exists(self.model_path))
        self.assertTrue(os.path.exists(self.scaler_path))
        self.assertTrue(os.path.exists(self.cols_path))
        self.assertTrue(os.path.exists(self.meta_path))

    def test_artifact_loading_and_types(self):
        model = joblib.load(self.model_path)
        scaler = joblib.load(self.scaler_path)
        cols = joblib.load(self.cols_path)
        with open(self.meta_path, "r") as f:
            meta = json.load(f)

        self.assertTrue(hasattr(model, "predict_proba"))
        self.assertTrue(hasattr(scaler, "transform"))
        self.assertIsInstance(cols, list)
        self.assertEqual(len(cols), 23)
        self.assertEqual(meta["model_version"], "v2.0_ecommerce_xgb")

    def test_feature_column_order(self):
        scaler = joblib.load(self.scaler_path)
        cols = joblib.load(self.cols_path)

        self.assertEqual(list(scaler.feature_names_in_), cols)
        self.assertEqual(len(cols), 23)

    def test_probability_range(self):
        model = joblib.load(self.model_path)
        scaler = joblib.load(self.scaler_path)
        cols = joblib.load(self.cols_path)

        dummy_data = pd.DataFrame([{col: 1.0 for col in cols}])
        scaled = scaler.transform(dummy_data)
        prob = model.predict_proba(scaled)[0][1]

        self.assertGreaterEqual(prob, 0.0)
        self.assertLessEqual(prob, 1.0)

    def test_score_calculation(self):
        model = joblib.load(self.model_path)
        scaler = joblib.load(self.scaler_path)
        cols = joblib.load(self.cols_path)

        dummy_data = pd.DataFrame([{col: 2.0 for col in cols}])
        scaled = scaler.transform(dummy_data)
        prob = float(model.predict_proba(scaled)[0][1])
        lead_score = int(round(prob * 100))

        self.assertGreaterEqual(lead_score, 0)
        self.assertLessEqual(lead_score, 100)

    def test_deterministic_inference(self):
        model = joblib.load(self.model_path)
        scaler = joblib.load(self.scaler_path)
        cols = joblib.load(self.cols_path)

        sample = pd.DataFrame([{col: float(i) for i, col in enumerate(cols)}])
        scaled = scaler.transform(sample)

        prob1 = model.predict_proba(scaled)[0][1]
        prob2 = model.predict_proba(scaled)[0][1]

        self.assertEqual(prob1, prob2)

    def test_zero_feature_handling(self):
        model = joblib.load(self.model_path)
        scaler = joblib.load(self.scaler_path)
        cols = joblib.load(self.cols_path)

        zero_data = pd.DataFrame([{col: 0.0 for col in cols}])
        scaled = scaler.transform(zero_data)
        prob = float(model.predict_proba(scaled)[0][1])

        self.assertGreaterEqual(prob, 0.0)
        self.assertLessEqual(prob, 1.0)


if __name__ == "__main__":
    unittest.main()
