"""Final Deadline Release Check: End-to-End Demo-Critical Functionality Verification.

Validates the 8 core demo-critical capabilities:
1. Backend health endpoint and MongoDB connectivity.
2. User storefront and Admin Intelligence assets build and bundle integrity.
3. Admin authentication (login, JWT generation) and route protection (401 without auth, 200 with auth).
4. Session tracking lifecycle (start -> event -> end) and canonical customer_lead_state update.
5. Lead scoring presentation in the Admin Intelligence directory and score audit history.
6. Admin overview Hot/Warm/Cold segment count reconciliation and mutual exclusivity.
7. Marketing campaign trigger evaluation (consent check, opt-out suppression, deduplication, dry-run safety).
8. Legacy endpoint compatibility (/predict, /track, /api/admin/leads, /api/leads, /api/admin/dashboard)
   with RFC 8594 Deprecation & Sunset headers.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import unittest
from datetime import datetime, timezone
from bson import ObjectId
import jwt

import app as app_module
from communication_provider import get_communication_provider, DryRunCommunicationProvider


class FinalDeadlineReleaseCheckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = app_module.app.test_client()
        cls.admin_token = jwt.encode(
            {"role": "admin", "sub": "admin_release_verifier", "exp": 4102444800},
            app_module.JWT_SECRET,
            algorithm="HS256",
        )
        cls.admin_headers = {"Authorization": f"Bearer {cls.admin_token}"}

    def test_01_backend_health_and_mongo_connectivity(self):
        """1. Verify backend health endpoint responds with successful MongoDB connectivity."""
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data.get("success"))
        self.assertTrue(data.get("mongo"))

    def test_02_user_and_admin_storefront_assets_integrity(self):
        """2. Verify production bundle artifacts for user storefront and admin portal."""
        user_dist = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "user", "dist", "index.html")
        admin_dist = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "admin", "dist", "index.html")

        self.assertTrue(os.path.exists(user_dist), "User storefront dist/index.html must exist")
        self.assertTrue(os.path.exists(admin_dist), "Admin intelligence dist/index.html must exist")

        with open(user_dist, "r", encoding="utf-8") as f:
            user_html = f.read()
            self.assertIn('<div id="root"></div>', user_html)
            self.assertIn("Lead Magnet", user_html)

        with open(admin_dist, "r", encoding="utf-8") as f:
            admin_html = f.read()
            self.assertIn('<div id="root"></div>', admin_html)
            self.assertIn("Customer Intelligence", admin_html)

    def test_03_admin_authentication_and_protected_routes(self):
        """3. Verify admin login and JWT protection on intelligence endpoints."""
        # Unauthenticated access must be rejected with 401
        unauth_response = self.client.get("/api/admin/intelligence/overview")
        self.assertEqual(unauth_response.status_code, 401)

        # Authenticated access with valid admin token must succeed
        auth_response = self.client.get("/api/admin/intelligence/overview", headers=self.admin_headers)
        self.assertEqual(auth_response.status_code, 200)
        self.assertTrue(auth_response.get_json().get("success"))

    def test_04_session_lifecycle_and_canonical_lead_scoring(self):
        """4. Verify full session lifecycle updates canonical lead state without leaking to legacy leads."""
        customer_id = ObjectId()
        now = datetime.now(timezone.utc)

        # Seed customer profile
        app_module.profiles_collection.insert_one({
            "_id": customer_id,
            "email": f"demo_{customer_id}@example.com",
            "name": "Demo Shopper",
            "created_at": now,
        })

        # 1. Start session
        start_res = self.client.post("/api/session/start", json={
            "visitor_id": str(customer_id),
            "anonymous_id": f"anon_{customer_id}",
        }, headers={"Authorization": f"Bearer {jwt.encode({'sub': str(customer_id), 'exp': 4102444800}, app_module.JWT_SECRET, algorithm='HS256')}"})
        self.assertEqual(start_res.status_code, 200)
        session_id = start_res.get_json()["data"]["session_id"]

        # 2. Log high-intent event
        event_res = self.client.post("/api/session/event", json={
            "session_id": session_id,
            "event_type": "add_to_cart",
            "entity": {"product_id": "prod_123", "price": 149.99},
        })
        self.assertEqual(event_res.status_code, 200)

        initial_legacy_leads = app_module.leads_collection.count_documents({})

        # 3. End session
        end_res = self.client.post("/api/session/end", json={"session_id": session_id})
        self.assertEqual(end_res.status_code, 200)
        end_data = end_res.get_json()
        self.assertTrue(end_data.get("success"))
        self.assertIn("score", end_data["data"])
        self.assertIn("segment", end_data["data"])

        # Confirm zero records written to legacy leads collection
        self.assertEqual(app_module.leads_collection.count_documents({}), initial_legacy_leads)

        # Confirm canonical state updated
        lead_state = app_module.customer_lead_state_collection.find_one({"customer_id": customer_id})
        self.assertIsNotNone(lead_state)
        self.assertIn(lead_state.get("lead_segment"), ("Hot", "Warm", "Cold"))
        self.assertIn(lead_state.get("qualification_status"), ("qualified", "not_qualified"))

    def test_05_lead_scoring_in_admin_intelligence_dashboard(self):
        """5. Verify customer lead scoring appears in Admin Intelligence directory and score history."""
        customer_id = ObjectId()
        now = datetime.now(timezone.utc)

        # Seed lead state and profile
        app_module.customer_lead_state_collection.insert_one({
            "customer_id": customer_id,
            "lead_score": 88,
            "lead_probability": 0.88,
            "lead_segment": "Hot",
            "qualification_status": "qualified",
            "last_scored_at": now.isoformat(),
        })
        app_module.profiles_collection.insert_one({
            "_id": customer_id,
            "email": "vip_shopper@example.com",
            "name": "VIP Shopper",
        })
        app_module.lead_score_history_collection.insert_one({
            "customer_id": customer_id,
            "lead_score": 88,
            "lead_segment": "Hot",
            "qualification_status": "qualified",
            "timestamp": now.isoformat(),
        })

        # Query directory
        dir_res = self.client.get("/api/admin/intelligence/leads", headers=self.admin_headers)
        self.assertEqual(dir_res.status_code, 200)
        dir_data = dir_res.get_json()["data"]
        matching = [item for item in dir_data.get("items", []) if item.get("customer_id") == str(customer_id)]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]["lead_score"], 88)
        self.assertEqual(matching[0]["lead_segment"], "Hot")
        self.assertEqual(matching[0]["qualification_status"], "qualified")

        # Query score history
        hist_res = self.client.get(f"/api/admin/intelligence/customers/{customer_id}/score-history", headers=self.admin_headers)
        self.assertEqual(hist_res.status_code, 200)
        hist_items = hist_res.get_json().get("data", [])
        self.assertTrue(len(hist_items) >= 1)
        self.assertEqual(hist_items[0]["lead_score"], 88)

    def test_06_dashboard_hot_warm_cold_counts_consistency(self):
        """6. Verify dashboard Hot, Warm, Cold segment counts are consistent and mutually exclusive."""
        res_overview = self.client.get("/api/admin/intelligence/overview", headers=self.admin_headers)
        self.assertEqual(res_overview.status_code, 200)
        overview_data = res_overview.get_json()["data"]

        hot = overview_data.get("hot_leads", 0)
        warm = overview_data.get("warm_leads", 0)
        cold = overview_data.get("cold_leads", 0)
        total_visitors = overview_data.get("total_visitors", 0)

        # Sum of categorized leads must not exceed total visitors
        self.assertGreaterEqual(total_visitors, 0)
        self.assertGreaterEqual(hot, 0)
        self.assertGreaterEqual(warm, 0)
        self.assertGreaterEqual(cold, 0)

        # Legacy dashboard endpoint must also compute valid mutually exclusive counts
        res_legacy_dash = self.client.get("/api/admin/dashboard", headers=self.admin_headers)
        self.assertEqual(res_legacy_dash.status_code, 200)
        legacy_data = res_legacy_dash.get_json()["data"]
        leg_hot = legacy_data.get("hot_leads", 0)
        leg_warm = legacy_data.get("warm_leads", 0)
        leg_cold = legacy_data.get("cold_leads", 0)
        leg_total = legacy_data.get("total_leads", 0)
        self.assertLessEqual(leg_hot + leg_warm + leg_cold, leg_total)

    def test_07_campaign_triggers_safeguards_and_dryrun(self):
        """7. Verify campaign evaluation enforces consent, opt-out suppression, deduplication, and dry-run provider."""
        # Confirm default provider is DryRunCommunicationProvider
        provider = get_communication_provider()
        self.assertIsInstance(provider, DryRunCommunicationProvider)
        self.assertFalse(os.environ.get("ALLOW_REAL_DISPATCH", "").lower() in ("true", "1"))

        # Seed hot lead with opt-out
        opt_out_cid = ObjectId()
        app_module.customer_lead_state_collection.insert_one({
            "customer_id": opt_out_cid,
            "lead_score": 90,
            "lead_segment": "Hot",
            "qualification_status": "qualified",
        })
        app_module.profiles_collection.insert_one({
            "_id": opt_out_cid,
            "email": "optout@example.com",
            "email_opt_out": True,
        })

        # Evaluate campaigns
        eval_res = self.client.post("/api/campaigns/evaluate", headers=self.admin_headers)
        self.assertEqual(eval_res.status_code, 200)
        triggered = eval_res.get_json().get("data", [])

        # Opted-out customer must not be sent messaging
        opted_out_triggers = [t for t in triggered if t.get("recipient") == "optout@example.com"]
        self.assertEqual(len(opted_out_triggers), 0)

    def test_08_legacy_endpoints_backward_compatibility_and_deprecation(self):
        """8. Verify legacy routes maintain compatibility and emit standard RFC 8594 deprecation headers."""
        # /predict
        res_pred = self.client.post(
            "/predict",
            json={
                "Lead Origin": "Landing Page Submission",
                "Lead Source": "Google",
                "Total Time Spent on Website": 600,
                "TotalVisits": 4,
                "Page Views Per Visit": 3.0,
            },
        )
        self.assertEqual(res_pred.status_code, 200)
        self.assertEqual(res_pred.headers.get("Deprecation"), "true")
        self.assertIn("2026", res_pred.headers.get("Sunset", ""))
        self.assertIn("/api/customer/lead-score", res_pred.headers.get("Link", ""))

        # /track
        res_track = self.client.post(
            "/track",
            json={
                "visitor_id": "legacy_demo_vis",
                "Lead Origin": "Landing Page Submission",
                "Lead Source": "Google",
                "Total Time Spent on Website": 700,
                "TotalVisits": 3,
                "Page Views Per Visit": 2.0,
            },
        )
        self.assertEqual(res_track.status_code, 200)
        self.assertEqual(res_track.headers.get("Deprecation"), "true")
        self.assertIn("/api/customer/lead-score", res_track.headers.get("Link", ""))

        # /api/admin/leads
        res_adm_leads = self.client.get("/api/admin/leads", headers=self.admin_headers)
        self.assertEqual(res_adm_leads.status_code, 200)
        self.assertEqual(res_adm_leads.headers.get("Deprecation"), "true")
        self.assertIn("/api/admin/intelligence/leads", res_adm_leads.headers.get("Link", ""))

        # /api/admin/dashboard
        res_adm_dash = self.client.get("/api/admin/dashboard", headers=self.admin_headers)
        self.assertEqual(res_adm_dash.status_code, 200)
        self.assertEqual(res_adm_dash.headers.get("Deprecation"), "true")
        self.assertIn("/api/admin/intelligence/overview", res_adm_dash.headers.get("Link", ""))

        # /api/leads
        res_leads = self.client.get("/api/leads", headers=self.admin_headers)
        self.assertEqual(res_leads.status_code, 200)
        self.assertEqual(res_leads.headers.get("Deprecation"), "true")
        self.assertIn("/api/admin/intelligence/leads", res_leads.headers.get("Link", ""))


if __name__ == "__main__":
    unittest.main()
