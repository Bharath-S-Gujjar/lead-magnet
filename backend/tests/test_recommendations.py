import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import unittest
from app import app


class RecommendationEndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_get_recommendations(self):
        response = self.client.get("/api/recommendations?limit=4")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data.get("success"))
        self.assertIsInstance(data.get("data"), list)


if __name__ == "__main__":
    unittest.main()
