import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import unittest
from datetime import datetime

from model_adapter import adapt_behavioral_features
from prediction_service import predict_session


class PredictionServiceTests(unittest.TestCase):
    def test_prediction_runs_and_returns_a_valid_result(self):
        model_input = adapt_behavioral_features({
            "total_visits": 2,
            "total_time_seconds": 180,
            "page_views_per_visit": 3,
            "landing_source": "google",
            "form_submit_count": 1,
            "last_meaningful_activity": "Form Submitted on Website",
        })

        prediction = predict_session(model_input)

        self.assertIsInstance(prediction["score"], float)
        self.assertGreaterEqual(prediction["score"], 0.0)
        self.assertLessEqual(prediction["score"], 1.0)
        self.assertIn(prediction["segment"], {"Hot", "Warm", "Cold"})
        self.assertIn(
            prediction["next_action"],
            {"Call now + send email", "Send email", "Add to nurture list"},
        )
        self.assertEqual(prediction["model_version"], "xgb_model.pkl")
        self.assertIsInstance(datetime.fromisoformat(prediction["prediction_time"]), datetime)


if __name__ == "__main__":
    unittest.main()
