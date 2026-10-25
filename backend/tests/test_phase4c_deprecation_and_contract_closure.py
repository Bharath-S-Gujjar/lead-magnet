"""Phase 4C Fast-Track: Deprecation and Contract Closure Regression Tests.

Validates:
1. POST /predict returns status 200, valid legacy payload, and RFC 8594 Deprecation/Sunset headers.
2. POST /track returns status 200, valid legacy payload, and RFC 8594 Deprecation/Sunset headers.
3. Legacy admin endpoints (GET /api/admin/leads, GET /api/leads, GET /api/admin/dashboard)
   return 200 with canonical data and RFC 8594 Deprecation headers pointing to /api/admin/intelligence/*.
4. Active canonical routes (e.g. /api/health, /api/admin/intelligence/overview, /api/admin/intelligence/leads)
   do NOT carry Deprecation headers.
5. process_session() docstring notes deprecation and points to lead_scoring_engine.rescore_customer,
   and app.py no longer imports process_session.
6. POST /api/session/end updates customer_lead_state without writing duplicate records to leads collection.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import unittest
from unittest.mock import Mock, patch
from bson import ObjectId
import jwt

import app as app_module
from lead_processing_service import process_session


class Phase4CDeprecationContractTests(unittest.TestCase):
    def setUp(self):
        self.client = app_module.app.test_client()
        token = jwt.encode(
            {"role": "admin", "sub": "admin_test", "exp": 4102444800},
            app_module.JWT_SECRET,
            algorithm="HS256",
        )
        self.admin_headers = {"Authorization": f"Bearer {token}"}

    def test_01_predict_endpoint_contract_and_deprecation_headers(self):
        """POST /predict must return 200, score/segment/reason, and RFC 8594 headers."""
        response = self.client.post(
            "/predict",
            json={
                "Lead Origin": "Landing Page Submission",
                "Lead Source": "Google",
                "Total Time Spent on Website": 500,
                "TotalVisits": 3,
                "Page Views Per Visit": 2.5,
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("score", data)
        self.assertIn("segment", data)
        self.assertIn("reason", data)

        # RFC 8594 Deprecation & Sunset headers
        self.assertEqual(response.headers.get("Deprecation"), "true")
        self.assertIn("2026", response.headers.get("Sunset", ""))
        self.assertIn("/api/customer/lead-score", response.headers.get("Link", ""))
        self.assertIn('rel="successor-version"', response.headers.get("Link", ""))

    def test_02_track_endpoint_contract_and_deprecation_headers(self):
        """POST /track must return 200, score/segment/next_action, and RFC 8594 headers."""
        response = self.client.post(
            "/track",
            json={
                "visitor_id": "phase4c_visitor",
                "Lead Origin": "Landing Page Submission",
                "Lead Source": "Google",
                "Total Time Spent on Website": 800,
                "TotalVisits": 5,
                "Page Views Per Visit": 4.0,
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data.get("visitor_id"), "phase4c_visitor")
        self.assertIn("score", data)
        self.assertIn("segment", data)
        self.assertIn("next_action", data)

        # RFC 8594 Deprecation & Sunset headers
        self.assertEqual(response.headers.get("Deprecation"), "true")
        self.assertIn("2026", response.headers.get("Sunset", ""))
        self.assertIn("/api/customer/lead-score", response.headers.get("Link", ""))
        self.assertIn('rel="successor-version"', response.headers.get("Link", ""))

    def test_03_legacy_admin_lead_routes_carry_deprecation_headers(self):
        """GET /api/admin/leads, GET /api/leads, and GET /api/admin/dashboard must carry deprecation headers."""
        test_col = Mock()
        test_col.find.return_value.sort.return_value = [
            {
                "_id": ObjectId(),
                "customer_id": ObjectId(),
                "visitor_id": "vis-4c",
                "lead_score": 75,
                "lead_probability": 0.75,
                "lead_segment": "Hot",
                "qualification_status": "qualified",
                "last_scored_at": "2026-10-23T18:00:00+00:00",
            }
        ]

        with patch.object(app_module, "customer_lead_state_collection", test_col):
            # GET /api/admin/leads
            res_admin_leads = self.client.get("/api/admin/leads", headers=self.admin_headers)
            self.assertEqual(res_admin_leads.status_code, 200)
            self.assertEqual(res_admin_leads.headers.get("Deprecation"), "true")
            self.assertIn("/api/admin/intelligence/leads", res_admin_leads.headers.get("Link", ""))

            # GET /api/leads
            res_leads = self.client.get("/api/leads", headers=self.admin_headers)
            self.assertEqual(res_leads.status_code, 200)
            self.assertEqual(res_leads.headers.get("Deprecation"), "true")
            self.assertIn("/api/admin/intelligence/leads", res_leads.headers.get("Link", ""))

            # GET /api/admin/dashboard
            res_dash = self.client.get("/api/admin/dashboard", headers=self.admin_headers)
            self.assertEqual(res_dash.status_code, 200)
            self.assertEqual(res_dash.headers.get("Deprecation"), "true")
            self.assertIn("/api/admin/intelligence/overview", res_dash.headers.get("Link", ""))

    def test_04_canonical_active_routes_do_not_carry_deprecation_headers(self):
        """Active modern API routes must NOT carry Deprecation headers."""
        # /api/health
        res_health = self.client.get("/api/health")
        self.assertIn(res_health.status_code, (200, 503))
        self.assertNotIn("Deprecation", res_health.headers)

        # /api/admin/intelligence/overview
        res_overview = self.client.get(
            "/api/admin/intelligence/overview",
            headers=self.admin_headers,
        )
        self.assertEqual(res_overview.status_code, 200)
        self.assertNotIn("Deprecation", res_overview.headers)

        # /api/admin/intelligence/leads
        res_intel_leads = self.client.get(
            "/api/admin/intelligence/leads",
            headers=self.admin_headers,
        )
        self.assertEqual(res_intel_leads.status_code, 200)
        self.assertNotIn("Deprecation", res_intel_leads.headers)

    def test_05_process_session_deprecation_documentation_and_dead_import_removal(self):
        """process_session() must document deprecation, and app.py must not import it."""
        # Verify docstring
        doc = process_session.__doc__ or ""
        self.assertIn("deprecated", doc.lower())
        self.assertIn("lead_scoring_engine.rescore_customer", doc)
        self.assertIn("customer_lead_state", doc)

        # Verify app.py does not import process_session
        import inspect
        app_source = inspect.getsource(app_module)
        self.assertNotIn("from lead_processing_service import process_session", app_source)
        self.assertNotIn("import process_session", app_source)

    def test_06_session_end_writes_canonical_state_without_legacy_leads_leak(self):
        """POST /api/session/end must rescore canonical state and leave leads collection untouched."""
        test_session_id = ObjectId()
        test_user_id = ObjectId()

        # Seed test session
        app_module.sessions_collection.insert_one({
            "_id": test_session_id,
            "user_id": test_user_id,
            "visitor_id": "test_visitor_4c",
            "started_at": "2026-10-23T18:00:00.000000+00:00",
            "status": "active",
        })

        initial_leads_count = app_module.leads_collection.count_documents({})

        response = self.client.post(
            "/api/session/end",
            json={"session_id": str(test_session_id)},
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data.get("success"))

        # Verify leads collection has zero new records
        final_leads_count = app_module.leads_collection.count_documents({})
        self.assertEqual(final_leads_count, initial_leads_count)

        # Verify customer_lead_state was created/updated
        lead_state = app_module.customer_lead_state_collection.find_one({"customer_id": test_user_id})
        self.assertIsNotNone(lead_state)
        self.assertIn("lead_score", lead_state)
        self.assertIn("lead_segment", lead_state)


if __name__ == "__main__":
    unittest.main()
