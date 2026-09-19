import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import unittest

import jwt

from app import JWT_SECRET, app, campaigns_collection


class MarketingEndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_get_campaigns_seeds_defaults_when_empty(self):
        campaigns_collection.delete_many({})

        res_camp = self.client.get("/api/campaigns")
        self.assertEqual(res_camp.status_code, 200)
        camps = res_camp.get_json().get("data", [])
        self.assertGreaterEqual(len(camps), 1)
        self.assertIn("Abandoned Cart Recovery", [campaign.get("name") for campaign in camps])

    def test_campaign_evaluation_requires_admin_access(self):
        res_anon = self.client.post("/api/campaigns/evaluate")
        self.assertEqual(res_anon.status_code, 401)

        token = jwt.encode({"role": "admin", "exp": 4102444800}, JWT_SECRET, algorithm="HS256")
        res_admin = self.client.post("/api/campaigns/evaluate", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res_admin.status_code, 200)

    def test_get_campaigns_and_evaluate(self):
        token = jwt.encode({"role": "admin", "exp": 4102444800}, JWT_SECRET, algorithm="HS256")
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Fetch campaigns
        res_camp = self.client.get("/api/campaigns")
        self.assertEqual(res_camp.status_code, 200)
        camps = res_camp.get_json().get("data", [])
        self.assertTrue(len(camps) >= 1)

        # 2. Evaluate triggers
        res_eval = self.client.post("/api/campaigns/evaluate", headers=headers)
        self.assertEqual(res_eval.status_code, 200)

        # 3. Get campaign logs
        res_logs = self.client.get("/api/campaigns/logs", headers=headers)
        self.assertEqual(res_logs.status_code, 200)
        self.assertIsInstance(res_logs.get_json().get("data"), list)


if __name__ == "__main__":
    unittest.main()
