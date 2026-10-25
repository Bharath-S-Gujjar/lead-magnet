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
        self.lead_state_collection = Mock()
        self.collection_patch = patch.object(
            app_module, "customer_lead_state_collection", self.lead_state_collection
        )
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
        self.lead_state_collection.find.return_value.sort.return_value = [{
            "_id": lead_id,
            "customer_id": ObjectId(),
            "session_id": session_id,
            "visitor_id": "visitor-1",
            "score": 0.82,
            "lead_probability": 0.82,
            "lead_score": 82,
            "lead_segment": "Hot",
            "segment": "Hot",
            "next_action": "Call now + send email",
            "last_scored_at": "2026-08-07T10:00:00+00:00",
        }]

        response = self.client.get("/api/admin/leads", headers=self.headers)

        self.assertEqual(response.status_code, 200)
        self.lead_state_collection.find.return_value.sort.assert_called_once_with("last_scored_at", -1)
        lead = response.get_json()["data"][0]
        self.assertEqual(lead["_id"], str(lead_id))
        self.assertEqual(lead["session_id"], str(session_id))
        self.assertEqual(lead["score"], 0.82)
        self.assertEqual(lead["segment"], "Hot")
        self.assertEqual(lead["lead_score"], 82)
        self.assertEqual(lead["lead_segment"], "Hot")

    def test_get_single_lead_returns_the_lead_and_404_when_absent(self):
        lead_id = ObjectId()
        self.lead_state_collection.find_one.return_value = {
            "_id": lead_id,
            "customer_id": ObjectId(),
            "visitor_id": "visitor-2",
            "score": 0.42,
            "lead_probability": 0.42,
            "lead_score": 42,
            "lead_segment": "Warm",
            "segment": "Warm",
            "next_action": "Send email",
            "last_scored_at": "2026-08-07T10:00:00+00:00",
        }

        success_response = self.client.get(f"/api/admin/leads/{lead_id}", headers=self.headers)

        self.assertEqual(success_response.status_code, 200)
        self.assertEqual(success_response.get_json()["data"]["_id"], str(lead_id))

        self.lead_state_collection.find_one.return_value = None
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

        self.lead_state_collection.update_one.return_value = SimpleNamespace(matched_count=1)
        response = self.client.put(
            f"/api/admin/leads/{lead_id}/status",
            json={"status": "Qualified"},
            headers=self.headers,
        )

        self.assertEqual(response.status_code, 200)
        update_call = self.lead_state_collection.update_one.call_args
        self.assertEqual(update_call.args[0], {"_id": lead_id})
        self.assertEqual(update_call.args[1]["$set"]["status"], "Qualified")
        self.assertIn("updated_at", update_call.args[1]["$set"])
        self.assertEqual(response.get_json()["data"]["status"], "Qualified")

    def test_dashboard_returns_summary_counts_and_average_score(self):
        self.lead_state_collection.aggregate.return_value = [{
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

