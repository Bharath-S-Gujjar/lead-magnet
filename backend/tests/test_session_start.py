import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import unittest
from app import app


class SessionStartEndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_session_start(self):
        response = self.client.post(
            "/api/session/start",
            json={"visitor_id": "visitor_test_1"}
        )
        self.assertIn(response.status_code, (200, 503))
        if response.status_code == 200:
            data = response.get_json()
            self.assertTrue(data.get("success"))
            self.assertIn("session_id", data.get("data", {}))


if __name__ == "__main__":
    unittest.main()
