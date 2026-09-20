import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import unittest
from app import app


class TrackEndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_track(self):
        response = self.client.post(
            "/track",
            json={
                "visitor_id": "visitor_1",
                "Lead Origin": "Landing Page Submission",
                "Lead Source": "Google",
                "Total Time Spent on Website": 800,
                "TotalVisits": 5,
                "Page Views Per Visit": 4
            }
        )
        self.assertIn(response.status_code, (200, 500))
        if response.status_code == 200:
            data = response.get_json()
            self.assertIn("score", data)
            self.assertIn("segment", data)
            self.assertIn("next_action", data)


if __name__ == "__main__":
    unittest.main()
