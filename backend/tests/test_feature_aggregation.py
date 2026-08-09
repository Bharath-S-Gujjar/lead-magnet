import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import unittest
from datetime import datetime, timedelta

from feature_aggregation import aggregate_session_features


class FeatureAggregationTests(unittest.TestCase):
    def test_aggregates_completed_session_behavior(self):
        started_at = datetime(2026, 8, 7, 10, 0, 0)
        session = {
            "visitor_id": "visitor-1",
            "started_at": started_at,
            "total_time_seconds": 120,
            "page_views": 3,
            "utm_source": "google",
        }
        events = [
            {
                "event_type": "page_view",
                "page": "/",
                "timestamp": started_at,
                "metadata": {},
            },
            {
                "event_type": "scroll",
                "page": "/",
                "timestamp": started_at + timedelta(seconds=10),
                "metadata": {"scroll_depth": 75},
            },
            {
                "event_type": "page_view",
                "page": "/pricing",
                "timestamp": started_at + timedelta(seconds=30),
                "metadata": {},
            },
            {
                "event_type": "click",
                "page": "/pricing",
                "timestamp": started_at + timedelta(seconds=40),
                "metadata": {"cta_name": "Request demo"},
            },
            {
                "event_type": "form_open",
                "page": "/demo",
                "timestamp": started_at + timedelta(seconds=50),
                "metadata": {},
            },
            {
                "event_type": "form_submit",
                "page": "/demo",
                "timestamp": started_at + timedelta(seconds=60),
                "metadata": {},
            },
        ]

        features = aggregate_session_features(session, events)

        self.assertEqual(features["total_time_seconds"], 120)
        self.assertEqual(features["page_views"], 2)
        self.assertEqual(features["total_visits"], 1)
        self.assertEqual(features["page_views_per_visit"], 2)
        self.assertEqual(features["event_count"], 6)
        self.assertEqual(features["click_count"], 1)
        self.assertEqual(features["cta_click_count"], 1)
        self.assertEqual(features["form_open_count"], 1)
        self.assertEqual(features["form_submit_count"], 1)
        self.assertEqual(features["max_scroll_depth"], 75)
        self.assertEqual(features["high_intent_page_visits"], 1)
        self.assertEqual(features["landing_source"], "google")
        self.assertEqual(features["landing_page"], "/")
        self.assertEqual(features["last_meaningful_event_type"], "form_submit")
        self.assertEqual(features["last_meaningful_activity"], "Form Submitted on Website")

    def test_uses_safe_defaults_for_missing_data(self):
        features = aggregate_session_features({}, [])

        self.assertEqual(features["total_time_seconds"], 0)
        self.assertEqual(features["page_views"], 0)
        self.assertEqual(features["total_visits"], 1)
        self.assertEqual(features["landing_source"], "unknown")
        self.assertEqual(features["last_meaningful_activity"], "Unknown")


if __name__ == "__main__":
    unittest.main()
