import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import unittest

from model_adapter import adapt_behavioral_features, load_feature_columns


class ModelAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.expected_columns = load_feature_columns()

    def test_output_has_exact_saved_feature_columns_in_saved_order(self):
        frame = adapt_behavioral_features({})

        self.assertEqual(list(frame.columns), self.expected_columns)
        self.assertEqual(frame.shape, (1, len(self.expected_columns)))

    def test_missing_features_default_to_current_zero_imputation(self):
        frame = adapt_behavioral_features({})
        row = frame.iloc[0]

        self.assertEqual(row["TotalVisits"], 0)
        self.assertEqual(row["Total Time Spent on Website"], 0)
        self.assertEqual(row["Page Views Per Visit"], 0)
        self.assertEqual(row["Last Activity_Unknown"], 1)

    def test_common_form_submission_scenario_maps_to_model_features(self):
        frame = adapt_behavioral_features({
            "total_visits": 3,
            "total_time_seconds": 180,
            "page_views_per_visit": 4,
            "landing_source": "google",
            "form_submit_count": 1,
            "last_meaningful_activity": "Form Submitted on Website",
        })
        row = frame.iloc[0]

        self.assertEqual(row["TotalVisits"], 3)
        self.assertEqual(row["Total Time Spent on Website"], 180)
        self.assertEqual(row["Page Views Per Visit"], 4)
        self.assertEqual(row["Lead Source_Google"], 1)
        self.assertEqual(row["Lead Origin_Landing Page Submission"], 1)
        self.assertEqual(row["Last Activity_Form Submitted on Website"], 1)
        self.assertEqual(row["Last Notable Activity_Form Submitted on Website"], 1)
        self.assertEqual(row["Country_India"], 0)

    def test_unknown_visitor_activity_maps_to_the_safe_unknown_category(self):
        frame = adapt_behavioral_features({
            "landing_source": "unknown",
            "last_meaningful_activity": "Unknown",
        })
        row = frame.iloc[0]

        self.assertEqual(row["Lead Source_Unknown"], 1)
        self.assertEqual(row["Last Activity_Unknown"], 1)


if __name__ == "__main__":
    unittest.main()
