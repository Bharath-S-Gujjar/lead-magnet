"""Unit and regression tests for Phase 4B.1: Canonical Session-Termination Scoring.

Verifies:
1. Session termination persists required session data (ended status, duration, profile updates).
2. Customer features are aggregated before rescoring.
3. The canonical active e-commerce scoring service is invoked as intended.
4. Session termination does NOT create a conflicting legacy score record in db["leads"].
5. Anonymous and authenticated customer identity behavior remains correct.
6. The existing endpoint response contract remains compatible with existing callers.
7. Failures in feature aggregation or scoring are handled consistently and do not falsely report success.
"""

import datetime
import os
import sys
import unittest
from unittest.mock import patch
from bson import ObjectId

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module
from app import (
    app,
    db,
    sessions_collection,
    events_collection,
    profiles_collection,
    leads_collection,
    customer_features_collection,
    customer_lead_state_collection,
    lead_score_history_collection,
)
from customer_feature_service import ensure_customer_features_indexes, get_customer_features
from customer_lead_state_service import ensure_customer_lead_state_indexes, get_customer_lead_state
from identity_service import resolve_anonymous_identity
from score_history_service import ensure_score_history_indexes


class CanonicalSessionTerminationScoringTests(unittest.TestCase):
    """Test suite validating canonical session-termination scoring without legacy duplicate leads."""

    def setUp(self):
        self.client = app.test_client()

        # Ensure required collection indexes
        ensure_customer_features_indexes(customer_features_collection)
        ensure_customer_lead_state_indexes(customer_lead_state_collection)
        ensure_score_history_indexes(db)

        self.test_user_ids = []
        self.test_session_ids = []
        self.test_anonymous_ids = []

    def tearDown(self):
        # Clean up any test records created
        if self.test_session_ids:
            sessions_collection.delete_many({"_id": {"$in": self.test_session_ids}})
            events_collection.delete_many({"session_id": {"$in": self.test_session_ids}})
        if self.test_user_ids:
            profiles_collection.delete_many({"_id": {"$in": self.test_user_ids}})
            customer_features_collection.delete_many({"customer_id": {"$in": self.test_user_ids}})
            customer_lead_state_collection.delete_many({"customer_id": {"$in": self.test_user_ids}})
            lead_score_history_collection.delete_many({"customer_id": {"$in": self.test_user_ids}})
        if self.test_anonymous_ids:
            customer_features_collection.delete_many({"customer_id": {"$in": self.test_anonymous_ids}})
            customer_lead_state_collection.delete_many({"customer_id": {"$in": self.test_anonymous_ids}})
            lead_score_history_collection.delete_many({"customer_id": {"$in": self.test_anonymous_ids}})

    def _create_test_session(self, user_id=None, anonymous_id=None, started_minutes_ago=10):
        session_oid = ObjectId()
        anon_id = anonymous_id or f"anon_{session_oid}"
        started_at = datetime.datetime.utcnow() - datetime.timedelta(minutes=started_minutes_ago)

        session_doc = {
            "_id": session_oid,
            "session_id": str(session_oid),
            "visitor_id": anon_id,
            "anonymous_id": anon_id,
            "identity_status": "authenticated" if user_id else "anonymous",
            "started_at": started_at,
            "last_active_at": started_at,
            "total_time_seconds": 0,
            "page_views": 0,
            "status": "active"
        }
        if user_id:
            session_doc["user_id"] = user_id if isinstance(user_id, ObjectId) else ObjectId(user_id)

        sessions_collection.insert_one(session_doc)
        self.test_session_ids.append(session_oid)
        if anonymous_id:
            self.test_anonymous_ids.append(anonymous_id)
        return session_doc

    # -------------------------------------------------------------------------
    # 1. Session termination persists required session data
    # -------------------------------------------------------------------------
    def test_01_session_termination_persists_required_session_data(self):
        """Verify status update to ended, duration computation, and user profile update."""
        user_oid = ObjectId()
        self.test_user_ids.append(user_oid)

        profiles_collection.insert_one({
            "_id": user_oid,
            "user_id": user_oid,
            "email": "test_user_01@example.com",
            "session_count": 0,
            "page_view_count": 0,
            "engagement_score": 0,
        })

        session_doc = self._create_test_session(user_id=user_oid, started_minutes_ago=15)
        session_oid = session_doc["_id"]

        # Insert behavior events for the session
        events_collection.insert_one({
            "session_id": session_oid,
            "user_id": user_oid,
            "event_type": "page_view",
            "page": "/products",
            "timestamp": datetime.datetime.utcnow(),
        })

        res = self.client.post("/api/session/end", json={"session_id": str(session_oid)})
        self.assertEqual(res.status_code, 200)

        # Check session was updated
        updated_session = sessions_collection.find_one({"_id": session_oid})
        self.assertEqual(updated_session["status"], "ended")
        self.assertGreaterEqual(updated_session["total_time_seconds"], 800)  # ~15 minutes (900s)
        self.assertIn("ended_at", updated_session)

        # Check profile was updated with session activity
        profile = profiles_collection.find_one({"_id": user_oid})
        self.assertGreaterEqual(profile.get("session_count", 0), 1)

    # -------------------------------------------------------------------------
    # 2. Customer features are aggregated before rescoring
    # -------------------------------------------------------------------------
    def test_02_customer_features_aggregated_before_rescoring(self):
        """Verify that customer_features receives fresh aggregated data for the customer."""
        user_oid = ObjectId()
        self.test_user_ids.append(user_oid)

        profiles_collection.insert_one({
            "_id": user_oid,
            "email": "test_user_02@example.com",
        })

        session_doc = self._create_test_session(user_id=user_oid, started_minutes_ago=5)
        session_oid = session_doc["_id"]

        events_collection.insert_one({
            "session_id": session_oid,
            "user_id": user_oid,
            "event_type": "page_view",
            "page": "/checkout",
            "timestamp": datetime.datetime.utcnow(),
        })

        res = self.client.post("/api/session/end", json={"session_id": str(session_oid)})
        self.assertEqual(res.status_code, 200)

        feature_doc = get_customer_features(user_oid, customer_features_collection)
        self.assertIsNotNone(feature_doc)
        self.assertGreaterEqual(feature_doc.get("sessions_count", 0), 1)
        self.assertGreaterEqual(feature_doc.get("total_time_spent", 0), 0)
        self.assertIn("high_intent_page_visits", feature_doc)

    # -------------------------------------------------------------------------
    # 3. Canonical scoring service is invoked as intended
    # -------------------------------------------------------------------------
    def test_03_canonical_scoring_service_invoked_as_intended(self):
        """Verify customer_lead_state and lead_score_history are populated with 23-feature score."""
        user_oid = ObjectId()
        self.test_user_ids.append(user_oid)

        profiles_collection.insert_one({
            "_id": user_oid,
            "email": "test_user_03@example.com",
        })

        session_doc = self._create_test_session(user_id=user_oid, started_minutes_ago=8)
        session_oid = session_doc["_id"]

        # Insert shopping behavior events
        events_collection.insert_one({
            "session_id": session_oid,
            "user_id": user_oid,
            "event_type": "page_view",
            "page": "/products",
            "timestamp": datetime.datetime.utcnow(),
        })

        res = self.client.post("/api/session/end", json={"session_id": str(session_oid)})
        self.assertEqual(res.status_code, 200)

        # Check customer_lead_state
        lead_state = get_customer_lead_state(user_oid, customer_lead_state_collection)
        self.assertIsNotNone(lead_state)
        self.assertIn("lead_score", lead_state)
        self.assertIn("lead_probability", lead_state)
        self.assertIn("lead_segment", lead_state)
        self.assertIn("qualification_status", lead_state)
        self.assertEqual(lead_state["model_version"], "v2.0_ecommerce_xgb")

        # Check lead_score_history has an entry
        history_entry = lead_score_history_collection.find_one({"customer_id": user_oid})
        self.assertIsNotNone(history_entry)
        self.assertEqual(history_entry["model_version"], "v2.0_ecommerce_xgb")

    # -------------------------------------------------------------------------
    # 4. Session termination does NOT create a conflicting legacy score record
    # -------------------------------------------------------------------------
    def test_04_session_termination_does_not_create_legacy_lead_record(self):
        """Verify that db["leads"] document count is completely unchanged after session end."""
        initial_leads_count = leads_collection.count_documents({})

        # 1. End an authenticated session
        user_oid = ObjectId()
        self.test_user_ids.append(user_oid)
        profiles_collection.insert_one({"_id": user_oid, "email": "auth_no_legacy@example.com"})

        auth_session = self._create_test_session(user_id=user_oid, started_minutes_ago=10)
        res1 = self.client.post("/api/session/end", json={"session_id": str(auth_session["_id"])})
        self.assertEqual(res1.status_code, 200)

        # 2. End an anonymous session
        anon_session = self._create_test_session(user_id=None, anonymous_id="anon_no_legacy_999")
        res2 = self.client.post("/api/session/end", json={"session_id": str(anon_session["_id"])})
        self.assertEqual(res2.status_code, 200)

        # Assert leads_collection count is strictly unchanged
        final_leads_count = leads_collection.count_documents({})
        self.assertEqual(
            initial_leads_count,
            final_leads_count,
            "Session termination must NOT write duplicate records to the legacy 'leads' collection!"
        )

    # -------------------------------------------------------------------------
    # 5. Anonymous and authenticated customer identity behavior
    # -------------------------------------------------------------------------
    def test_05_anonymous_and_authenticated_identity_behavior(self):
        """Verify anonymous session creates anonymous lead state, and identity resolution merges cleanly."""
        anon_id = f"anon_flow_{ObjectId()}"
        self.test_anonymous_ids.append(anon_id)

        # Step 1: Anonymous session ends
        anon_session = self._create_test_session(user_id=None, anonymous_id=anon_id)
        events_collection.insert_one({
            "session_id": anon_session["_id"],
            "anonymous_id": anon_id,
            "event_type": "page_view",
            "page": "/shop",
            "timestamp": datetime.datetime.utcnow(),
        })

        res_anon = self.client.post("/api/session/end", json={"session_id": str(anon_session["_id"])})
        self.assertEqual(res_anon.status_code, 200)

        # Verify anonymous lead state was generated under anon_id
        anon_state = get_customer_lead_state(anon_id, customer_lead_state_collection)
        self.assertIsNotNone(anon_state)
        self.assertEqual(anon_state["customer_id"], anon_id)

        # Step 2: Customer registers / logs in, resolving identity
        user_oid = ObjectId()
        self.test_user_ids.append(user_oid)
        profiles_collection.insert_one({"_id": user_oid, "email": "registered_from_anon@example.com"})

        resolve_res = resolve_anonymous_identity(
            anonymous_id=anon_id,
            user_id=user_oid,
            users_collection=profiles_collection,
            sessions_collection=sessions_collection,
            events_collection=events_collection,
            leads_collection=leads_collection,
            customer_features_collection=customer_features_collection,
            db=db,
        )
        self.assertGreaterEqual(resolve_res["sessions_merged"], 1)

        # Step 3: Anonymous lead state and features must be removed
        self.assertIsNone(customer_features_collection.find_one({"customer_id": anon_id}))
        self.assertIsNone(customer_lead_state_collection.find_one({"customer_id": anon_id}))

        # Step 4: Registered customer must have canonical lead state
        reg_state = get_customer_lead_state(user_oid, customer_lead_state_collection)
        self.assertIsNotNone(reg_state)
        self.assertEqual(reg_state["customer_id"], user_oid)

    # -------------------------------------------------------------------------
    # 6. Existing endpoint response contract remains compatible
    # -------------------------------------------------------------------------
    def test_06_response_contract_compatibility(self):
        """Verify response payload contains session_id, total_time_seconds, score, segment, next_action, and canonical fields."""
        user_oid = ObjectId()
        self.test_user_ids.append(user_oid)
        profiles_collection.insert_one({"_id": user_oid, "email": "contract_check@example.com"})

        session_doc = self._create_test_session(user_id=user_oid, started_minutes_ago=12)
        session_oid = session_doc["_id"]

        res = self.client.post("/api/session/end", json={"session_id": str(session_oid)})
        self.assertEqual(res.status_code, 200)

        json_data = res.get_json()
        self.assertTrue(json_data["success"])
        self.assertEqual(json_data["message"], "Session ended and lead processed")

        data = json_data["data"]
        # Required legacy contract keys
        self.assertEqual(data["session_id"], str(session_oid))
        self.assertIsInstance(data["total_time_seconds"], (int, float))
        self.assertGreaterEqual(data["total_time_seconds"], 700)
        self.assertIn("score", data)
        self.assertIsInstance(data["score"], float)
        self.assertGreaterEqual(data["score"], 0.0)
        self.assertLessEqual(data["score"], 1.0)
        self.assertIn("segment", data)
        self.assertIn(data["segment"], ["Hot", "Warm", "Cold"])
        self.assertIn("next_action", data)
        self.assertIsInstance(data["next_action"], str)

        # Required canonical active scoring keys
        self.assertIn("lead_score", data)
        self.assertIsInstance(data["lead_score"], int)
        self.assertGreaterEqual(data["lead_score"], 0)
        self.assertLessEqual(data["lead_score"], 100)
        self.assertIn("lead_probability", data)
        self.assertIn("lead_segment", data)
        self.assertIn("qualification_status", data)
        self.assertIn(data["qualification_status"], ["qualified", "not_qualified"])

    # -------------------------------------------------------------------------
    # 7. Failures in feature aggregation or scoring are handled consistently
    # -------------------------------------------------------------------------
    def test_07_failures_in_scoring_handled_consistently_no_false_success(self):
        """Verify that when scoring fails, the endpoint returns HTTP 500 and does NOT falsely report success."""
        user_oid = ObjectId()
        self.test_user_ids.append(user_oid)
        profiles_collection.insert_one({"_id": user_oid, "email": "fail_check@example.com"})

        session_doc = self._create_test_session(user_id=user_oid)
        session_oid = session_doc["_id"]

        with patch("app.rescore_customer", side_effect=RuntimeError("Simulated ML engine crash")):
            res = self.client.post("/api/session/end", json={"session_id": str(session_oid)})
            self.assertEqual(res.status_code, 500)
            json_data = res.get_json()
            self.assertFalse(json_data["success"])
            self.assertIn("Simulated ML engine crash", json_data["message"])


if __name__ == "__main__":
    unittest.main()
