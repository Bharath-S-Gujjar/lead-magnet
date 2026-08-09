import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from bson import ObjectId
import jwt

import app as app_module


class AdminDashboardRouteTests(unittest.TestCase):
    def setUp(self):
        self.leads_collection = Mock()
        self.collection_patch = patch.object(app_module, "leads_collection", self.leads_collection)
        self.collection_patch.start()
        self.client = app_module.app.test_client()
        token = jwt.encode(
            {"role": "admin", "exp": 4102444800},
            app_module.JWT_SECRET,
            algorithm="HS256",
        )
        self.headers = {"Authorization": f"Bearer {token}"}

    def tearDown(self):
        self.collection_patch.stop()

    def test_get_leads_sorts_descending_and_serializes_object_ids(self):
        lead_id = ObjectId()
        session_id = ObjectId()
        self.leads_collection.find.return_value.sort.return_value = [{
            "_id": lead_id,
            "session_id": session_id,
            "visitor_id": "visitor-1",
            "score": 0.82,
            "segment": "Hot",
            "next_action": "Call now + send email",
            "prediction_time": "2026-08-07T10:00:00+00:00",
        }]

        response = self.client.get("/api/admin/leads", headers=self.headers)

        self.assertEqual(response.status_code, 200)
        self.leads_collection.find.return_value.sort.assert_called_once_with("prediction_time", -1)
        lead = response.get_json()["data"][0]
        self.assertEqual(lead["_id"], str(lead_id))
        self.assertEqual(lead["session_id"], str(session_id))
        self.assertEqual(lead["score"], 0.82)

    def test_get_single_lead_returns_the_lead_and_404_when_absent(self):
        lead_id = ObjectId()
        self.leads_collection.find_one.return_value = {
            "_id": lead_id,
            "visitor_id": "visitor-2",
            "score": 0.42,
            "segment": "Warm",
            "next_action": "Send email",
            "prediction_time": "2026-08-07T10:00:00+00:00",
        }

        success_response = self.client.get(f"/api/admin/leads/{lead_id}", headers=self.headers)

        self.assertEqual(success_response.status_code, 200)
        self.assertEqual(success_response.get_json()["data"]["_id"], str(lead_id))

        self.leads_collection.find_one.return_value = None
        response = self.client.get(f"/api/admin/leads/{lead_id}", headers=self.headers)

        self.assertEqual(response.status_code, 404)
        self.assertFalse(response.get_json()["success"])

    def test_update_lead_status_validates_and_updates_supported_status(self):
        lead_id = ObjectId()
        invalid_response = self.client.put(
            f"/api/admin/leads/{lead_id}/status",
            json={"status": "Pending"},
            headers=self.headers,
        )
        self.assertEqual(invalid_response.status_code, 400)

        self.leads_collection.update_one.return_value = SimpleNamespace(matched_count=1)
        response = self.client.put(
            f"/api/admin/leads/{lead_id}/status",
            json={"status": "Qualified"},
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 200)
        self.leads_collection.update_one.assert_called_once_with(
            {"_id": lead_id}, {"$set": {"status": "Qualified"}}
        )
        self.assertEqual(response.get_json()["data"]["status"], "Qualified")

    def test_dashboard_returns_summary_counts_and_average_score(self):
        self.leads_collection.aggregate.return_value = [{
            "total_leads": 10,
            "hot_leads": 3,
            "warm_leads": 4,
            "cold_leads": 3,
            "average_score": 0.54,
        }]

        response = self.client.get("/api/admin/dashboard", headers=self.headers)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["data"], {
            "total_leads": 10,
            "hot_leads": 3,
            "warm_leads": 4,
            "cold_leads": 3,
            "average_score": 0.54,
        })


if __name__ == "__main__":
    unittest.main()
