"""Regression and unit test suite for Phase 4B.2: Canonical Lead Data Compatibility Migration.

Verifies:
1. /api/leads and /api/admin/leads compatibility with canonical customer_lead_state.
2. /api/admin/dashboard aggregation counts and statistics from canonical records.
3. Canonical Hot/Warm/Cold segmentation independent of qualification status.
4. Marketing trigger selection from canonical records with consent and eligibility verification.
5. Marketing trigger suppression for ineligible leads (no consent, opt-out, anonymous without contact).
6. Deduplication and safe handling of missing/malformed customer fields.
7. Authentication and authorization enforcement across all migrated endpoints.
8. Regression prevention for the Phase 4B.1 session-end flow and immediate visibility in admin views.
"""

import datetime
import os
import sys
import unittest
from bson import ObjectId
import jwt

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module
from app import (
    app,
    db,
    JWT_SECRET,
    sessions_collection,
    events_collection,
    profiles_collection,
    leads_collection,
    customer_lead_state_collection,
    customer_features_collection,
    campaigns_collection,
    campaign_logs_collection,
    cart_collection,
)
from customer_lead_state_service import ensure_customer_lead_state_indexes
from marketing_service import seed_campaigns_if_empty, evaluate_campaign_triggers


class Phase4B2CanonicalMigrationTests(unittest.TestCase):
    """Test suite validating canonical lead data compatibility migration."""

    def setUp(self):
        self.client = app.test_client()

        # Admin auth headers
        token = jwt.encode(
            {"role": "admin", "exp": 4102444800},
            JWT_SECRET,
            algorithm="HS256"
        )
        self.admin_headers = {"Authorization": f"Bearer {token}"}

        # Customer auth headers
        cust_token = jwt.encode(
            {"role": "customer", "user_id": str(ObjectId()), "exp": 4102444800},
            JWT_SECRET,
            algorithm="HS256"
        )
        self.customer_headers = {"Authorization": f"Bearer {cust_token}"}

        ensure_customer_lead_state_indexes(customer_lead_state_collection)
        seed_campaigns_if_empty(campaigns_collection)

        self.test_user_ids = []
        self.test_lead_ids = []
        self.test_session_ids = []
        self.test_campaign_log_ids = []

    def tearDown(self):
        if self.test_lead_ids:
            customer_lead_state_collection.delete_many({"_id": {"$in": self.test_lead_ids}})
        if self.test_user_ids:
            profiles_collection.delete_many({"_id": {"$in": self.test_user_ids}})
            customer_lead_state_collection.delete_many({"customer_id": {"$in": self.test_user_ids}})
            customer_features_collection.delete_many({"customer_id": {"$in": self.test_user_ids}})
        if self.test_session_ids:
            sessions_collection.delete_many({"_id": {"$in": self.test_session_ids}})
            events_collection.delete_many({"session_id": {"$in": self.test_session_ids}})
        if self.test_campaign_log_ids:
            campaign_logs_collection.delete_many({"_id": {"$in": self.test_campaign_log_ids}})

    # -------------------------------------------------------------------------
    # 1. /api/leads and /api/admin/leads compatibility
    # -------------------------------------------------------------------------
    def test_01_api_leads_and_admin_leads_compatibility(self):
        """Verify /api/leads and /api/admin/leads return canonical data formatted in the legacy shape."""
        user_oid = ObjectId()
        self.test_user_ids.append(user_oid)

        profiles_collection.insert_one({
            "_id": user_oid,
            "full_name": "Test Compatibility Shopper",
            "email": "compat_shopper@example.com",
            "phone": "+919876543210"
        })

        lead_oid = ObjectId()
        self.test_lead_ids.append(lead_oid)
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        customer_lead_state_collection.insert_one({
            "_id": lead_oid,
            "customer_id": user_oid,
            "visitor_id": str(user_oid),
            "lead_probability": 0.88,
            "lead_score": 88,
            "lead_segment": "Hot",
            "qualification_status": "qualified",
            "model_version": "v2.0_ecommerce_xgb",
            "last_scored_at": now_iso,
            "created_at": now_iso,
            "updated_at": now_iso,
        })

        # Test GET /api/admin/leads
        res_admin = self.client.get("/api/admin/leads", headers=self.admin_headers)
        self.assertEqual(res_admin.status_code, 200)
        data_admin = res_admin.get_json()
        self.assertTrue(data_admin["success"])
        self.assertEqual(data_admin["message"], "Leads fetched")
        leads_list = data_admin["data"]
        self.assertGreaterEqual(len(leads_list), 1)

        target_lead = next((l for l in leads_list if str(l["_id"]) == str(lead_oid)), None)
        self.assertIsNotNone(target_lead)
        self.assertEqual(target_lead["customer_id"], str(user_oid))
        self.assertEqual(target_lead["score"], 0.88)
        self.assertEqual(target_lead["lead_score"], 88)
        self.assertEqual(target_lead["lead_probability"], 0.88)
        self.assertEqual(target_lead["segment"], "Hot")
        self.assertEqual(target_lead["lead_segment"], "Hot")
        self.assertEqual(target_lead["qualification_status"], "qualified")
        self.assertEqual(target_lead["status"], "Qualified")
        self.assertEqual(target_lead["next_action"], "Call now + send email")
        self.assertEqual(target_lead["email"], "compat_shopper@example.com")
        self.assertEqual(target_lead["full_name"], "Test Compatibility Shopper")

        # Test GET /api/leads
        res_leads = self.client.get("/api/leads", headers=self.admin_headers)
        self.assertEqual(res_leads.status_code, 200)
        data_leads = res_leads.get_json()
        self.assertTrue(data_leads["success"])
        leads_raw = data_leads["data"]
        target_raw = next((l for l in leads_raw if str(l["_id"]) == str(lead_oid)), None)
        self.assertIsNotNone(target_raw)
        self.assertEqual(target_raw["score"], 0.88)
        self.assertEqual(target_raw["segment"], "Hot")

        # Test GET /api/admin/leads/<lead_id>
        res_single = self.client.get(f"/api/admin/leads/{lead_oid}", headers=self.admin_headers)
        self.assertEqual(res_single.status_code, 200)
        single_doc = res_single.get_json()["data"]
        self.assertEqual(single_doc["_id"], str(lead_oid))
        self.assertEqual(single_doc["lead_score"], 88)

        # Test PUT /api/admin/leads/<lead_id>/status
        res_status = self.client.put(
            f"/api/admin/leads/{lead_oid}/status",
            json={"status": "Contacted"},
            headers=self.admin_headers
        )
        self.assertEqual(res_status.status_code, 200)
        self.assertEqual(res_status.get_json()["data"]["status"], "Contacted")

        # Verify status updated on fetch
        res_after = self.client.get(f"/api/admin/leads/{lead_oid}", headers=self.admin_headers)
        self.assertEqual(res_after.get_json()["data"]["status"], "Contacted")

    # -------------------------------------------------------------------------
    # 2. /api/admin/dashboard counts and statistics
    # -------------------------------------------------------------------------
    def test_02_admin_dashboard_counts_and_statistics(self):
        """Verify /api/admin/dashboard computes totals, segment counts, and average_score from customer_lead_state."""
        # Clear any existing lead state for exact count verification
        customer_lead_state_collection.delete_many({})

        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        records = [
            {"customer_id": ObjectId(), "lead_segment": "Hot", "lead_probability": 0.90, "lead_score": 90, "last_scored_at": now_iso},
            {"customer_id": ObjectId(), "lead_segment": "Hot", "lead_probability": 0.80, "lead_score": 80, "last_scored_at": now_iso},
            {"customer_id": ObjectId(), "lead_segment": "Warm", "lead_probability": 0.60, "lead_score": 60, "last_scored_at": now_iso},
            {"customer_id": ObjectId(), "lead_segment": "Warm", "lead_probability": 0.50, "lead_score": 50, "last_scored_at": now_iso},
            {"customer_id": ObjectId(), "lead_segment": "Warm", "lead_probability": 0.40, "lead_score": 40, "last_scored_at": now_iso},
            {"customer_id": ObjectId(), "lead_segment": "Cold", "lead_probability": 0.20, "lead_score": 20, "last_scored_at": now_iso},
        ]
        inserted = customer_lead_state_collection.insert_many(records)
        self.test_lead_ids.extend(inserted.inserted_ids)

        res = self.client.get("/api/admin/dashboard", headers=self.admin_headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()["data"]

        self.assertEqual(data["total_leads"], 6)
        self.assertEqual(data["hot_leads"], 2)
        self.assertEqual(data["warm_leads"], 3)
        self.assertEqual(data["cold_leads"], 1)
        self.assertEqual(data["total_leads"], data["hot_leads"] + data["warm_leads"] + data["cold_leads"])
        self.assertAlmostEqual(data["average_score"], 0.5667, places=2)

    # -------------------------------------------------------------------------
    # 3. Canonical Hot/Warm/Cold segmentation independent of qualification
    # -------------------------------------------------------------------------
    def test_03_canonical_hot_warm_cold_segmentation_independent_of_qualification(self):
        """Verify Warm and Cold counts use lead_segment consistently and are NOT zeroed or excluded by qualification status."""
        customer_lead_state_collection.delete_many({})

        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        records = [
            {"customer_id": ObjectId(), "lead_segment": "Hot", "lead_probability": 0.85, "qualification_status": "qualified", "last_scored_at": now_iso},
            {"customer_id": ObjectId(), "lead_segment": "Warm", "lead_probability": 0.55, "qualification_status": "not_qualified", "last_scored_at": now_iso},
            {"customer_id": ObjectId(), "lead_segment": "Cold", "lead_probability": 0.25, "qualification_status": "not_qualified", "last_scored_at": now_iso},
        ]
        inserted = customer_lead_state_collection.insert_many(records)
        self.test_lead_ids.extend(inserted.inserted_ids)

        res = self.client.get("/api/admin/dashboard", headers=self.admin_headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()["data"]

        # Warm and Cold counts MUST be populated even though qualification_status == "not_qualified"
        self.assertEqual(data["hot_leads"], 1)
        self.assertEqual(data["warm_leads"], 1)
        self.assertEqual(data["cold_leads"], 1)
        self.assertEqual(data["total_leads"], 3)

    # -------------------------------------------------------------------------
    # 4. Marketing trigger selection from canonical records with consent
    # -------------------------------------------------------------------------
    def test_04_marketing_trigger_selection_from_canonical_records_with_consent(self):
        """Verify evaluate_campaign_triggers targets canonical Hot leads having valid phone and promotional consent."""
        user_oid = ObjectId()
        self.test_user_ids.append(user_oid)

        profiles_collection.insert_one({
            "_id": user_oid,
            "full_name": "VIP Consented Shopper",
            "email": "vip_consented@example.com",
            "phone": "+919988776655",
            "whatsapp_promotional_consent": True,
            "whatsapp_opt_out": False
        })

        lead_oid = ObjectId()
        self.test_lead_ids.append(lead_oid)
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        customer_lead_state_collection.insert_one({
            "_id": lead_oid,
            "customer_id": user_oid,
            "lead_probability": 0.92,
            "lead_score": 92,
            "lead_segment": "Hot",
            "qualification_status": "qualified",
            "last_scored_at": now_iso
        })

        res = self.client.post("/api/campaigns/evaluate", headers=self.admin_headers)
        self.assertEqual(res.status_code, 200)
        json_data = res.get_json()
        self.assertTrue(json_data["success"])

        # Check logs for the triggered action
        log = campaign_logs_collection.find_one({"recipient": "+919988776655"})
        self.assertIsNotNone(log)
        self.test_campaign_log_ids.append(log["_id"])
        self.assertEqual(log["trigger_type"], "hot_lead")
        self.assertEqual(log["channel"], "whatsapp")
        self.assertEqual(log["customer_id"], str(user_oid))
        self.assertEqual(log["status"], "Sent")

    # -------------------------------------------------------------------------
    # 5. Marketing trigger suppression for ineligible leads
    # -------------------------------------------------------------------------
    def test_05_marketing_trigger_suppresses_ineligible_leads(self):
        """Verify Hot leads without consent, with opt-out, or anonymous without contact info are NOT targeted."""
        # 1. Anonymous Hot lead with no profile and no phone
        anon_lead_id = ObjectId()
        self.test_lead_ids.append(anon_lead_id)
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        customer_lead_state_collection.insert_one({
            "_id": anon_lead_id,
            "customer_id": f"anon_no_profile_{anon_lead_id}",
            "lead_probability": 0.95,
            "lead_segment": "Hot",
            "last_scored_at": now_iso
        })

        # 2. Registered Hot lead with opt-out = True
        user_optout = ObjectId()
        self.test_user_ids.append(user_optout)
        profiles_collection.insert_one({
            "_id": user_optout,
            "phone": "+919900000001",
            "whatsapp_opt_out": True,
            "whatsapp_promotional_consent": True
        })
        customer_lead_state_collection.insert_one({
            "customer_id": user_optout,
            "lead_probability": 0.91,
            "lead_segment": "Hot",
            "last_scored_at": now_iso
        })

        # 3. Registered Hot lead with no consent (consent = False)
        user_noconsent = ObjectId()
        self.test_user_ids.append(user_noconsent)
        profiles_collection.insert_one({
            "_id": user_noconsent,
            "phone": "+919900000002",
            "whatsapp_opt_out": False,
            "whatsapp_promotional_consent": False
        })
        customer_lead_state_collection.insert_one({
            "customer_id": user_noconsent,
            "lead_probability": 0.93,
            "lead_segment": "Hot",
            "last_scored_at": now_iso
        })

        res = self.client.post("/api/campaigns/evaluate", headers=self.admin_headers)
        self.assertEqual(res.status_code, 200)

        # Assert zero logs were generated for any of the ineligible leads
        self.assertIsNone(campaign_logs_collection.find_one({"recipient": f"anon_no_profile_{anon_lead_id}"}))
        self.assertIsNone(campaign_logs_collection.find_one({"recipient": "+919900000001"}))
        self.assertIsNone(campaign_logs_collection.find_one({"recipient": "+919900000002"}))

    # -------------------------------------------------------------------------
    # 6. Deduplication and missing customer fields
    # -------------------------------------------------------------------------
    def test_06_deduplication_and_missing_customer_fields(self):
        """Verify that customer lead directory deduplicates repeated records and handles missing fields safely."""
        customer_lead_state_collection.delete_many({})

        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        user_oid = ObjectId()
        self.test_user_ids.append(user_oid)

        # Insert duplicate records for the same customer
        customer_lead_state_collection.insert_many([
            {
                "customer_id": user_oid,
                "lead_probability": 0.75,
                "lead_segment": "Warm",
                "last_scored_at": now_iso,
            },
            {
                "customer_id": str(user_oid),
                "lead_probability": 0.75,
                "lead_segment": "Warm",
                "last_scored_at": now_iso,
            },
            # Lead with missing fields
            {
                "customer_id": "anon_missing_fields_123",
                # No lead_probability, no score, no segment
                "last_scored_at": now_iso,
            }
        ])

        res = self.client.get("/api/admin/leads", headers=self.admin_headers)
        self.assertEqual(res.status_code, 200)
        leads = res.get_json()["data"]

        # User must appear exactly once despite two records with same ID
        user_matches = [l for l in leads if l["customer_id"] == str(user_oid)]
        self.assertEqual(len(user_matches), 1)

        # Missing-fields lead should have safe defaults without crashing
        missing_lead = next(l for l in leads if l["customer_id"] == "anon_missing_fields_123")
        self.assertEqual(missing_lead["score"], 0.0)
        self.assertEqual(missing_lead["lead_score"], 0)
        self.assertEqual(missing_lead["segment"], "Cold")
        self.assertEqual(missing_lead["qualification_status"], "not_qualified")
        self.assertIn("next_action", missing_lead)

    # -------------------------------------------------------------------------
    # 7. Authentication and authorization requirements
    # -------------------------------------------------------------------------
    def test_07_authentication_and_authorization_requirements(self):
        """Verify unauthenticated requests return 401 and customer tokens return 403 on admin routes."""
        endpoints = [
            ("GET", "/api/leads"),
            ("GET", "/api/admin/leads"),
            ("GET", f"/api/admin/leads/{ObjectId()}"),
            ("PUT", f"/api/admin/leads/{ObjectId()}/status"),
            ("GET", "/api/admin/dashboard"),
            ("POST", "/api/campaigns/evaluate"),
        ]

        for method, url in endpoints:
            # 1. Unauthenticated -> 401
            res_unauth = self.client.open(method=method, path=url)
            self.assertEqual(res_unauth.status_code, 401, f"{method} {url} must require authentication")

            # 2. Customer token -> 403
            res_cust = self.client.open(method=method, path=url, headers=self.customer_headers)
            self.assertEqual(res_cust.status_code, 403, f"{method} {url} must require admin role")

    # -------------------------------------------------------------------------
    # 8. Regression prevention for Phase 4B.1 session-end flow
    # -------------------------------------------------------------------------
    def test_08_phase4b1_session_end_regression_prevention(self):
        """Verify session termination updates canonical lead state, leaves legacy collection empty, and reflects in dashboard."""
        initial_legacy_leads = leads_collection.count_documents({})

        user_oid = ObjectId()
        self.test_user_ids.append(user_oid)
        profiles_collection.insert_one({"_id": user_oid, "email": "session_end_p4b2@example.com"})

        session_oid = ObjectId()
        self.test_session_ids.append(session_oid)
        started_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=10)

        sessions_collection.insert_one({
            "_id": session_oid,
            "session_id": str(session_oid),
            "user_id": user_oid,
            "started_at": started_at,
            "last_active_at": started_at,
            "status": "active"
        })

        events_collection.insert_one({
            "session_id": session_oid,
            "user_id": user_oid,
            "event_type": "page_view",
            "page": "/products",
            "timestamp": datetime.datetime.now(datetime.timezone.utc)
        })

        # End session
        res_end = self.client.post("/api/session/end", json={"session_id": str(session_oid)})
        self.assertEqual(res_end.status_code, 200)

        # Legacy collection must have ZERO new records
        self.assertEqual(leads_collection.count_documents({}), initial_legacy_leads)

        # Canonical lead state must exist for the customer
        lead_state = customer_lead_state_collection.find_one({"customer_id": user_oid})
        self.assertIsNotNone(lead_state)
        self.assertIn("lead_score", lead_state)

        # Customer must immediately be visible in /api/admin/leads
        res_leads = self.client.get("/api/admin/leads", headers=self.admin_headers)
        self.assertEqual(res_leads.status_code, 200)
        found_lead = next((l for l in res_leads.get_json()["data"] if l["customer_id"] == str(user_oid)), None)
        self.assertIsNotNone(found_lead)

        # Dashboard must include this customer in total_leads
        res_dash = self.client.get("/api/admin/dashboard", headers=self.admin_headers)
        self.assertEqual(res_dash.status_code, 200)
        self.assertGreaterEqual(res_dash.get_json()["data"]["total_leads"], 1)

    # -------------------------------------------------------------------------
    # 9. Marketing precedence: Warm canonical with stale Hot legacy is not selected
    # -------------------------------------------------------------------------
    def test_09_marketing_precedence_warm_with_stale_hot_not_selected(self):
        """Verify that lead_segment='Warm', segment='Hot' is NOT selected for Hot VIP marketing."""
        user_oid = ObjectId()
        self.test_user_ids.append(user_oid)
        profiles_collection.insert_one({
            "_id": user_oid,
            "full_name": "Warm Shopper Stale Hot",
            "phone": "+919988112233",
            "whatsapp_promotional_consent": True,
            "whatsapp_opt_out": False
        })

        lead_oid = ObjectId()
        self.test_lead_ids.append(lead_oid)
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        customer_lead_state_collection.insert_one({
            "_id": lead_oid,
            "customer_id": user_oid,
            "lead_segment": "Warm",
            "segment": "Hot",
            "lead_probability": 0.55,
            "lead_score": 55,
            "qualification_status": "not_qualified",
            "last_scored_at": now_iso
        })

        res = self.client.post("/api/campaigns/evaluate", headers=self.admin_headers)
        self.assertEqual(res.status_code, 200)

        # Assert no campaign log created for this recipient
        log = campaign_logs_collection.find_one({"recipient": "+919988112233"})
        self.assertIsNone(log, "Warm lead with stale Hot segment must NOT be targeted for Hot campaign")

    # -------------------------------------------------------------------------
    # 10. Marketing precedence: Cold canonical with stale Hot legacy is not selected
    # -------------------------------------------------------------------------
    def test_10_marketing_precedence_cold_with_stale_hot_not_selected(self):
        """Verify that lead_segment='Cold', segment='Hot' is NOT selected for Hot VIP marketing."""
        user_oid = ObjectId()
        self.test_user_ids.append(user_oid)
        profiles_collection.insert_one({
            "_id": user_oid,
            "full_name": "Cold Shopper Stale Hot",
            "phone": "+919988112244",
            "whatsapp_promotional_consent": True,
            "whatsapp_opt_out": False
        })

        lead_oid = ObjectId()
        self.test_lead_ids.append(lead_oid)
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        customer_lead_state_collection.insert_one({
            "_id": lead_oid,
            "customer_id": user_oid,
            "lead_segment": "Cold",
            "segment": "Hot",
            "lead_probability": 0.20,
            "lead_score": 20,
            "qualification_status": "not_qualified",
            "last_scored_at": now_iso
        })

        res = self.client.post("/api/campaigns/evaluate", headers=self.admin_headers)
        self.assertEqual(res.status_code, 200)

        log = campaign_logs_collection.find_one({"recipient": "+919988112244"})
        self.assertIsNone(log, "Cold lead with stale Hot segment must NOT be targeted for Hot campaign")

    # -------------------------------------------------------------------------
    # 11. Marketing legacy fallback: Missing canonical segment uses legacy segment
    # -------------------------------------------------------------------------
    def test_11_marketing_legacy_fallback_when_canonical_missing(self):
        """Verify that genuine legacy records missing the lead_segment field fall back to legacy segment."""
        user_oid = ObjectId()
        self.test_user_ids.append(user_oid)
        profiles_collection.insert_one({
            "_id": user_oid,
            "full_name": "Legacy Pure Hot Shopper",
            "phone": "+919988112255",
            "whatsapp_promotional_consent": True,
            "whatsapp_opt_out": False
        })

        lead_oid = ObjectId()
        self.test_lead_ids.append(lead_oid)
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        # Genuine legacy record: no "lead_segment" key in document
        customer_lead_state_collection.insert_one({
            "_id": lead_oid,
            "customer_id": user_oid,
            "segment": "Hot",
            "score": 0.85,
            "last_scored_at": now_iso
        })

        res = self.client.post("/api/campaigns/evaluate", headers=self.admin_headers)
        self.assertEqual(res.status_code, 200)

        log = campaign_logs_collection.find_one({"recipient": "+919988112255"})
        self.assertIsNotNone(log, "Legacy record missing lead_segment must use legacy fallback")
        self.test_campaign_log_ids.append(log["_id"])
        self.assertEqual(log["trigger_type"], "hot_lead")

    # -------------------------------------------------------------------------
    # 12. Marketing null or invalid canonical segment cannot be promoted to Hot
    # -------------------------------------------------------------------------
    def test_12_marketing_null_or_invalid_canonical_not_promoted_by_stale_hot(self):
        """Verify that null, empty, or invalid canonical segment values are NOT promoted to Hot by stale legacy fields."""
        # Candidate 1: null canonical segment
        user_null = ObjectId()
        self.test_user_ids.append(user_null)
        profiles_collection.insert_one({
            "_id": user_null,
            "phone": "+919988112261",
            "whatsapp_promotional_consent": True,
            "whatsapp_opt_out": False
        })
        lead_null = ObjectId()
        self.test_lead_ids.append(lead_null)
        customer_lead_state_collection.insert_one({
            "_id": lead_null,
            "customer_id": user_null,
            "lead_segment": None,
            "segment": "Hot",
            "last_scored_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
        })

        # Candidate 2: empty string canonical segment
        user_empty = ObjectId()
        self.test_user_ids.append(user_empty)
        profiles_collection.insert_one({
            "_id": user_empty,
            "phone": "+919988112262",
            "whatsapp_promotional_consent": True,
            "whatsapp_opt_out": False
        })
        lead_empty = ObjectId()
        self.test_lead_ids.append(lead_empty)
        customer_lead_state_collection.insert_one({
            "_id": lead_empty,
            "customer_id": user_empty,
            "lead_segment": "",
            "segment": "Hot",
            "last_scored_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
        })

        # Candidate 3: invalid canonical segment string
        user_invalid = ObjectId()
        self.test_user_ids.append(user_invalid)
        profiles_collection.insert_one({
            "_id": user_invalid,
            "phone": "+919988112263",
            "whatsapp_promotional_consent": True,
            "whatsapp_opt_out": False
        })
        lead_invalid = ObjectId()
        self.test_lead_ids.append(lead_invalid)
        customer_lead_state_collection.insert_one({
            "_id": lead_invalid,
            "customer_id": user_invalid,
            "lead_segment": "unrecognized_segment_foo",
            "segment": "Hot",
            "last_scored_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
        })

        res = self.client.post("/api/campaigns/evaluate", headers=self.admin_headers)
        self.assertEqual(res.status_code, 200)

        # Assert none of the 3 candidates were dispatched
        self.assertIsNone(campaign_logs_collection.find_one({"recipient": "+919988112261"}))
        self.assertIsNone(campaign_logs_collection.find_one({"recipient": "+919988112262"}))
        self.assertIsNone(campaign_logs_collection.find_one({"recipient": "+919988112263"}))

    # -------------------------------------------------------------------------
    # 13. Dashboard: Conflicting segment fields increment only canonical counter
    # -------------------------------------------------------------------------
    def test_13_dashboard_conflicting_segment_increments_only_canonical_counter(self):
        """Verify conflicting segment fields increment ONLY the canonical counter in dashboard aggregation."""
        customer_lead_state_collection.delete_many({})
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        records = [
            # 1. Warm canonical with stale Hot
            {"customer_id": ObjectId(), "lead_segment": "Warm", "segment": "Hot", "lead_probability": 0.55, "last_scored_at": now_iso},
            # 2. Cold canonical with stale Hot
            {"customer_id": ObjectId(), "lead_segment": "Cold", "segment": "Hot", "lead_probability": 0.20, "last_scored_at": now_iso},
            # 3. Hot canonical with stale Warm
            {"customer_id": ObjectId(), "lead_segment": "Hot", "segment": "Warm", "lead_probability": 0.85, "last_scored_at": now_iso},
        ]
        inserted = customer_lead_state_collection.insert_many(records)
        self.test_lead_ids.extend(inserted.inserted_ids)

        res = self.client.get("/api/admin/dashboard", headers=self.admin_headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()["data"]

        self.assertEqual(data["total_leads"], 3)
        self.assertEqual(data["hot_leads"], 1, "Only record 3 is canonically Hot")
        self.assertEqual(data["warm_leads"], 1, "Only record 1 is canonically Warm")
        self.assertEqual(data["cold_leads"], 1, "Only record 2 is canonically Cold")
        self.assertEqual(data["total_leads"], data["hot_leads"] + data["warm_leads"] + data["cold_leads"])

    # -------------------------------------------------------------------------
    # 14. Dashboard: Each valid record contributes to at most one segment counter
    # -------------------------------------------------------------------------
    def test_14_dashboard_each_valid_record_contributes_to_at_most_one_counter(self):
        """Verify mixed canonical, legacy, conflicting, and null records maintain internal count consistency."""
        customer_lead_state_collection.delete_many({})
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

        records = [
            # Valid canonical Hot
            {"customer_id": ObjectId(), "lead_segment": "Hot", "segment": "Hot", "lead_probability": 0.90, "last_scored_at": now_iso},
            # Valid canonical Warm with stale Hot
            {"customer_id": ObjectId(), "lead_segment": "Warm", "segment": "Hot", "lead_probability": 0.60, "last_scored_at": now_iso},
            # Valid canonical Cold with stale Hot
            {"customer_id": ObjectId(), "lead_segment": "Cold", "segment": "Hot", "lead_probability": 0.20, "last_scored_at": now_iso},
            # Pure legacy Hot (no lead_segment key)
            {"customer_id": ObjectId(), "segment": "Hot", "score": 0.85, "last_scored_at": now_iso},
            # Pure legacy Warm (no lead_segment key)
            {"customer_id": ObjectId(), "segment": "Warm", "score": 0.50, "last_scored_at": now_iso},
            # Null canonical with stale Hot
            {"customer_id": ObjectId(), "lead_segment": None, "segment": "Hot", "last_scored_at": now_iso},
            # Invalid canonical with stale Hot
            {"customer_id": ObjectId(), "lead_segment": "invalid", "segment": "Hot", "last_scored_at": now_iso},
            # Empty canonical with stale Hot
            {"customer_id": ObjectId(), "lead_segment": "", "segment": "Hot", "last_scored_at": now_iso},
        ]
        inserted = customer_lead_state_collection.insert_many(records)
        self.test_lead_ids.extend(inserted.inserted_ids)

        res = self.client.get("/api/admin/dashboard", headers=self.admin_headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()["data"]

        self.assertEqual(data["total_leads"], 8)
        self.assertEqual(data["hot_leads"], 2)   # Valid canonical Hot (1) + Legacy Hot (1)
        self.assertEqual(data["warm_leads"], 2)  # Valid canonical Warm (1) + Legacy Warm (1)
        self.assertEqual(data["cold_leads"], 1)  # Valid canonical Cold (1)
        # Sum of segment counters must equal 5 and never exceed total_leads (8)
        self.assertEqual(data["hot_leads"] + data["warm_leads"] + data["cold_leads"], 5)
        self.assertLessEqual(data["hot_leads"] + data["warm_leads"] + data["cold_leads"], data["total_leads"])


if __name__ == "__main__":
    unittest.main()
