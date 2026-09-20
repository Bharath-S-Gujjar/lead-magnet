import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import unittest
from app import app


class SessionEventEndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_session_event(self):
        # Start a session first to get a valid session_id
        start_res = self.client.post(
            "/api/session/start",
            json={"visitor_id": "visitor_event_test"}
        )
        if start_res.status_code == 200:
            session_id = start_res.get_json()["data"]["session_id"]
            r = self.client.post("/api/session/event", json={
                "session_id": session_id,
                "event_type": "page_view",
                "page": "/pricing",
                "metadata": {"scroll_depth": 40}
            })
            self.assertEqual(r.status_code, 200)
            self.assertTrue(r.get_json().get("success"))


if __name__ == "__main__":
    unittest.main()
