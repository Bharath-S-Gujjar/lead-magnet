import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from bson import ObjectId

from lead_processing_service import SessionNotFoundError, process_session


class LeadProcessingServiceTests(unittest.TestCase):
    def setUp(self):
        self.session_id = ObjectId()
        self.session = {"_id": self.session_id, "visitor_id": "visitor-42"}
        self.sessions_collection = Mock()
        self.events_collection = Mock()
        self.leads_collection = Mock()
        self.leads_collection.insert_one.return_value = SimpleNamespace(inserted_id=ObjectId())

    def test_raises_when_session_is_not_found(self):
        self.sessions_collection.find_one.return_value = None

        with self.assertRaises(SessionNotFoundError):
            process_session(
                str(self.session_id),
                self.sessions_collection,
                self.events_collection,
                self.leads_collection,
            )

        self.events_collection.find.assert_not_called()
        self.leads_collection.insert_one.assert_not_called()

    @patch("lead_processing_service.predict_session")
    @patch("lead_processing_service.adapt_behavioral_features")
    @patch("lead_processing_service.aggregate_session_features")
    def test_processes_a_session_with_no_events(self, aggregate, adapt, predict):
        self.sessions_collection.find_one.return_value = self.session
        self.events_collection.find.return_value = []
        aggregate.return_value = {
            "landing_source": "unknown",
            "landing_page": None,
            "event_count": 0,
            "page_views": 0,
            "high_intent_page_visits": 0,
            "form_submit_count": 0,
        }
        adapt.return_value = Mock()
        predict.return_value = {
            "score": 0.25,
            "segment": "Cold",
            "next_action": "Add to nurture list",
            "prediction_time": "2026-08-07T10:00:00+00:00",
            "model_version": "xgb_model.pkl",
        }

        lead = process_session(
            self.session_id,
            self.sessions_collection,
            self.events_collection,
            self.leads_collection,
        )

        aggregate.assert_called_once_with(self.session, [])
        self.assertEqual(lead["feature_snapshot"]["event_count"], 0)
        self.assertEqual(lead["processing_status"], "processed")

    @patch("lead_processing_service.predict_session")
    @patch("lead_processing_service.adapt_behavioral_features")
    @patch("lead_processing_service.aggregate_session_features")
    def test_saves_the_completed_lead_document(self, aggregate, adapt, predict):
        events = [{"session_id": self.session_id, "event_type": "page_view"}]
        self.sessions_collection.find_one.return_value = self.session
        self.events_collection.find.return_value = events
        feature_snapshot = {
            "landing_source": "google",
            "landing_page": "/pricing",
            "event_count": 1,
            "page_views": 1,
            "high_intent_page_visits": 1,
            "form_submit_count": 1,
        }
        aggregate.return_value = feature_snapshot
        model_input = Mock()
        adapt.return_value = model_input
        predict.return_value = {
            "score": 0.82,
            "segment": "Hot",
            "next_action": "Call now + send email",
            "prediction_time": "2026-08-07T10:00:00+00:00",
            "model_version": "xgb_model.pkl",
        }

        lead = process_session(
            str(self.session_id),
            self.sessions_collection,
            self.events_collection,
            self.leads_collection,
        )

        adapt.assert_called_once_with(feature_snapshot)
        predict.assert_called_once_with(model_input)
        saved_lead = self.leads_collection.insert_one.call_args.args[0]
        self.assertEqual(saved_lead["visitor_id"], "visitor-42")
        self.assertEqual(saved_lead["session_id"], self.session_id)
        self.assertEqual(saved_lead["score"], 0.82)
        self.assertEqual(saved_lead["segment"], "Hot")
        self.assertEqual(saved_lead["source_summary"]["landing_page"], "/pricing")
        self.assertEqual(saved_lead["processing_status"], "processed")
        self.assertEqual(lead["_id"], self.leads_collection.insert_one.return_value.inserted_id)


if __name__ == "__main__":
    unittest.main()
