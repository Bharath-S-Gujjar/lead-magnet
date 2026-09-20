import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import unittest
from app import app


class PredictEndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_predict_endpoint(self):
        response = self.client.post(
            "/predict",
            json={
                "Lead Origin": "Landing Page Submission",
                "Lead Source": "Google",
                "Total Time Spent on Website": 500,
                "TotalVisits": 3,
                "Page Views Per Visit": 2.5
            }
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("score", data)
        self.assertIn("segment", data)


if __name__ == "__main__":
    unittest.main()
