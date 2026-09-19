"""Full End-to-End Regression Test Suite for Lead Magnet System (Task 16).

Verifies the complete pipeline:
Ecommerce customer -> Authentication / canonical identity -> Behavioral activity ->
Customer feature store -> ML lead scoring -> Customer lead state -> Qualification transition ->
Marketing automation -> Communication record -> Admin notification -> Admin intelligence APIs.
"""

import datetime
import os
import time
import unittest
from bson import ObjectId

import jwt

import app as app_module
from app import app
from customer_feature_service import ensure_customer_features_indexes
from customer_lead_state_service import (
    ensure_customer_lead_state_indexes,
    sync_customer_lead_state,
)
from behavior_event_service import log_behavior_event
from marketing_automation_service import (
    ensure_marketing_automation_indexes,
    process_marketing_automation_event,
)


class FullE2ELeadMagnetTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.jwt_secret = app_module.JWT_SECRET

        # Ensure database is clean before test run
        app_module.profiles_collection.delete_many({})
        app_module.customer_features_collection.delete_many({})
        app_module.customer_lead_state_collection.delete_many({})
        app_module.sessions_collection.delete_many({})
        app_module.events_collection.delete_many({})
        app_module.leads_collection.delete_many({})
        app_module.orders_collection.delete_many({})
        app_module.cart_collection.delete_many({})
        app_module.wishlist_collection.delete_many({})
        app_module.marketing_automation_events_collection.delete_many({})
        app_module.marketing_communications_collection.delete_many({})
        app_module.admin_notifications_collection.delete_many({})

        # Ensure indexes
        ensure_customer_features_indexes(app_module.customer_features_collection)
        ensure_customer_lead_state_indexes(app_module.customer_lead_state_collection)
        ensure_marketing_automation_indexes(app_module.db)

        # Clear rate limit state
        app_module.AUTH_RATE_LIMIT_ATTEMPTS.clear()

        # Seed products for e-commerce testing
        self.p1_id = str(ObjectId())
        self.p2_id = str(ObjectId())
        app_module.products_collection.insert_one({
            "_id": ObjectId(self.p1_id),
            "name": "E2E Oxford Cotton Shirt",
            "category": "Shirts",
            "price": 1499.0,
            "brand": "LeadMagnet Apparel",
            "gender": "Men",
        })
        app_module.products_collection.insert_one({
            "_id": ObjectId(self.p2_id),
            "name": "E2E Slim Fit Denim Jeans",
            "category": "Jeans",
            "price": 2499.0,
            "brand": "LeadMagnet Denim",
            "gender": "Men",
        })

    def make_token(self, user_id, role="user", email="user@example.com"):
        exp_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)
        return jwt.encode(
            {"sub": str(user_id), "role": role, "email": email, "exp": exp_time},
            self.jwt_secret,
            algorithm="HS256"
        )

    # --- 1. FULL E2E PIPELINE TEST ---

    def test_full_e2e_lead_magnet_pipeline(self):
        """Complete end-to-end verification of the Lead Magnet pipeline."""
        # -------------------------------------------------------------
        # STEP 1: Anonymous Session & Identity Resolution
        # -------------------------------------------------------------
        anon_res = self.client.post("/api/session/start", json={"visitor_id": "e2e_anon_1001"})
        self.assertEqual(anon_res.status_code, 200)
        anon_data = anon_res.get_json()["data"]
        session_id_1 = anon_data["session_id"]

        # Log anonymous behavior event
        self.client.post("/api/session/event", json={
            "session_id": session_id_1,
            "event_type": "product_view",
            "entity": {"type": "product", "id": self.p1_id}
        })

        # Register customer and resolve anonymous identity
        signup_res = self.client.post("/api/auth/signup", json={
            "email": "e2e_customer@example.com",
            "password": "SecurePassword123!",
            "fullName": "E2E Verification Customer",
            "phone": "+919876543210",
            "anonymous_id": "e2e_anon_1001"
        })
        self.assertEqual(signup_res.status_code, 200)
        user_id = signup_res.get_json()["data"]["user_id"]
        self.assertTrue(ObjectId.is_valid(user_id))

        # Login customer and obtain JWT
        login_res = self.client.post("/api/auth/login", json={
            "email": "e2e_customer@example.com",
            "password": "SecurePassword123!",
            "anonymous_id": "e2e_anon_1001"
        })
        self.assertEqual(login_res.status_code, 200)
        customer_token = login_res.get_json()["data"]["token"]
        auth_headers = {"Authorization": f"Bearer {customer_token}"}

        # -------------------------------------------------------------
        # STEP 2: Customer Behavioral Activity & Feature Store
        # -------------------------------------------------------------
        # Add to cart
        cart_res = self.client.post(
            "/api/cart",
            headers=auth_headers,
            json={"user_id": user_id, "product_id": self.p1_id, "quantity": 2, "session_id": session_id_1}
        )
        self.assertEqual(cart_res.status_code, 200)

        # Add to wishlist
        wish_res = self.client.post(
            "/api/wishlist",
            headers=auth_headers,
            json={"user_id": user_id, "product_id": self.p2_id, "session_id": session_id_1}
        )
        self.assertEqual(wish_res.status_code, 200)

        # Place order
        order_res = self.client.post(
            "/api/orders",
            headers=auth_headers,
            json={
                "customer_id": user_id,
                "shipping_address": "123 Tech Park, Bangalore",
                "payment_method": "UPI",
                "session_id": session_id_1
            }
        )
        self.assertEqual(order_res.status_code, 201)

        # Log high-intent behavior events (page views, checkout attempts, product views)
        for page in ["/products", "/pricing", "/checkout", "/checkout"]:
            log_behavior_event({
                "session_id": session_id_1,
                "event_type": "page_view",
                "page": page,
                "user_id": user_id
            }, app_module.sessions_collection, app_module.events_collection)

        for _ in range(3):
            log_behavior_event({
                "session_id": session_id_1,
                "event_type": "checkout_start",
                "user_id": user_id
            }, app_module.sessions_collection, app_module.events_collection)

        for pid in [self.p1_id, self.p2_id, self.p1_id]:
            log_behavior_event({
                "session_id": session_id_1,
                "event_type": "product_view",
                "entity": {"type": "product", "id": pid},
                "user_id": user_id
            }, app_module.sessions_collection, app_module.events_collection)

        # End session
        self.client.post("/api/session/end", json={"session_id": session_id_1})

        # Retrieve customer feature store record
        feat_res = self.client.get(f"/api/customer/features?user_id={user_id}", headers=auth_headers)
        self.assertEqual(feat_res.status_code, 200)
        features = feat_res.get_json()["data"]
        self.assertEqual(features["customer_id"], user_id)
        self.assertGreaterEqual(features["sessions_count"], 1)

        # Verify exactly 1 feature record exists
        count = app_module.customer_features_collection.count_documents({"customer_id": ObjectId(user_id)})
        self.assertEqual(count, 1)

        # -------------------------------------------------------------
        # STEP 3: ML Lead Scoring Inference
        # -------------------------------------------------------------
        score_res = self.client.get("/api/customer/lead-score", headers=auth_headers)
        self.assertEqual(score_res.status_code, 200)
        ml_data = score_res.get_json()["data"]
        self.assertIn("lead_probability", ml_data)
        self.assertIn("lead_score", ml_data)
        self.assertIn("lead_segment", ml_data)
        self.assertGreaterEqual(ml_data["lead_probability"], 0.0)
        self.assertLessEqual(ml_data["lead_probability"], 1.0)
        self.assertGreaterEqual(ml_data["lead_score"], 0)
        self.assertLessEqual(ml_data["lead_score"], 100)
        self.assertEqual(ml_data["model_version"], "v2.0_ecommerce_xgb")

        # -------------------------------------------------------------
        # STEP 4: Customer Lead State & Qualification Transition
        # -------------------------------------------------------------
        sync_res = self.client.post("/api/customer/lead-state/sync", headers=auth_headers)
        self.assertEqual(sync_res.status_code, 200)
        lead_state = sync_res.get_json()["data"]
        self.assertEqual(lead_state["customer_id"], user_id)
        self.assertEqual(lead_state["qualification_status"], "qualified")
        self.assertIsNotNone(lead_state["first_qualified_at"])
        self.assertIsNotNone(lead_state["last_qualified_at"])

        # -------------------------------------------------------------
        # STEP 5: Marketing Automation & Communication Records
        # -------------------------------------------------------------
        # Verify 1 marketing automation event was generated for qualification
        auto_events = list(app_module.marketing_automation_events_collection.find({"customer_id": ObjectId(user_id)}))
        self.assertEqual(len(auto_events), 1)
        event_doc = auto_events[0]
        self.assertEqual(event_doc["lead_state_transition"], "not_qualified_to_qualified")

        # Process marketing automation event
        proc_result = process_marketing_automation_event(event_doc["_id"], app_module.db)
        self.assertEqual(proc_result["status"], "completed")

        # Verify communication records created (email sent, sms/whatsapp skipped/or according to policy)
        comms = list(app_module.marketing_communications_collection.find({"customer_id": ObjectId(user_id)}))
        self.assertGreaterEqual(len(comms), 1)
        email_comm = next((c for c in comms if c["channel"] == "email"), None)
        self.assertIsNotNone(email_comm)
        self.assertEqual(email_comm["status"], "sent")

        # Verify admin notification created
        notifs = list(app_module.admin_notifications_collection.find({"type": "lead_qualified"}))
        self.assertGreaterEqual(len(notifs), 1)

        # -------------------------------------------------------------
        # STEP 6: Idempotency Verification
        # -------------------------------------------------------------
        # Re-sync lead state
        sync_res2 = self.client.post("/api/customer/lead-state/sync", headers=auth_headers)
        self.assertEqual(sync_res2.status_code, 200)

        # Re-process automation event
        proc_result_2 = process_marketing_automation_event(event_doc["_id"], app_module.db)
        self.assertEqual(proc_result_2["status"], "completed")

        # Verify counts remain unchanged (1 automation event, 3 channel records: 1 sent, 2 skipped)
        self.assertEqual(app_module.marketing_automation_events_collection.count_documents({"customer_id": ObjectId(user_id)}), 1)
        self.assertEqual(app_module.marketing_communications_collection.count_documents({"customer_id": ObjectId(user_id)}), 3)

        # -------------------------------------------------------------
        # STEP 7: Admin Intelligence APIs & Dashboard Verification
        # -------------------------------------------------------------
        admin_login = self.client.post("/api/auth/admin/login", json={"username": "admin", "password": "admin12345"})
        self.assertEqual(admin_login.status_code, 200)
        admin_token = admin_login.get_json()["data"]["token"]
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        # GET /api/admin/intelligence/overview
        ov_res = self.client.get("/api/admin/intelligence/overview", headers=admin_headers)
        self.assertEqual(ov_res.status_code, 200)
        ov_data = ov_res.get_json()["data"]
        self.assertGreaterEqual(ov_data["customers"]["total"], 1)
        self.assertGreaterEqual(ov_data["leads"]["total_qualified"], 1)

        # GET /api/admin/intelligence/leads (1 row = 1 customer)
        leads_res = self.client.get("/api/admin/intelligence/leads", headers=admin_headers)
        self.assertEqual(leads_res.status_code, 200)
        leads_data = leads_res.get_json()["data"]
        self.assertGreaterEqual(leads_data["total"], 1)
        found = any(row["customer_id"] == user_id for row in leads_data["items"])
        self.assertTrue(found)

        # GET /api/admin/intelligence/customers/<customer_id>
        detail_res = self.client.get(f"/api/admin/intelligence/customers/{user_id}", headers=admin_headers)
        self.assertEqual(detail_res.status_code, 200)
        detail_data = detail_res.get_json()["data"]
        self.assertEqual(detail_data["customer"]["_id"], user_id)
        self.assertNotIn("password", detail_data["customer"])
        self.assertNotIn("password_hash", detail_data["customer"])

        # GET /api/admin/intelligence/lead-distribution
        dist_res = self.client.get("/api/admin/intelligence/lead-distribution", headers=admin_headers)
        self.assertEqual(dist_res.status_code, 200)
        dist_data = dist_res.get_json()["data"]
        self.assertIn("segments", dist_data)
        self.assertIn("qualification", dist_data)

        # GET /api/admin/intelligence/recent-leads
        recent_res = self.client.get("/api/admin/intelligence/recent-leads", headers=admin_headers)
        self.assertEqual(recent_res.status_code, 200)

        # GET /api/admin/intelligence/marketing-activity
        mkt_res = self.client.get("/api/admin/intelligence/marketing-activity", headers=admin_headers)
        self.assertEqual(mkt_res.status_code, 200)
        self.assertGreaterEqual(mkt_res.get_json()["data"]["total"], 1)

        # GET /api/admin/intelligence/notifications
        notif_res = self.client.get("/api/admin/intelligence/notifications", headers=admin_headers)
        self.assertEqual(notif_res.status_code, 200)

    # --- 2. NEGATIVE QUALIFICATION CASE TEST ---

    def test_negative_qualification_case_no_automation(self):
        """Low intent customer who remains not_qualified must NOT trigger marketing automation."""
        signup_res = self.client.post("/api/auth/signup", json={
            "email": "low_intent@example.com",
            "password": "SecurePassword123!",
            "fullName": "Low Intent Customer"
        })
        user_id = signup_res.get_json()["data"]["user_id"]
        token = self.make_token(user_id=user_id, email="low_intent@example.com")
        auth_headers = {"Authorization": f"Bearer {token}"}

        # Start 1 minimal session
        s_res = self.client.post("/api/session/start", json={"visitor_id": "low_intent_anon"})
        sid = s_res.get_json()["data"]["session_id"]
        self.client.post("/api/session/event", json={"session_id": sid, "event_type": "page_view"})

        # Populate features for low intent customer
        feat_res = self.client.get(f"/api/customer/features?user_id={user_id}", headers=auth_headers)
        self.assertEqual(feat_res.status_code, 200)

        # Sync lead state
        sync_res = self.client.post("/api/customer/lead-state/sync", headers=auth_headers)
        self.assertEqual(sync_res.status_code, 200)
        state = sync_res.get_json()["data"]

        # Verify customer is NOT qualified
        self.assertEqual(state["qualification_status"], "not_qualified")

        # Verify NO marketing automation events or communications were created
        auto_count = app_module.marketing_automation_events_collection.count_documents({"customer_id": ObjectId(user_id)})
        comm_count = app_module.marketing_communications_collection.count_documents({"customer_id": ObjectId(user_id)})
        self.assertEqual(auto_count, 0)
        self.assertEqual(comm_count, 0)

    # --- 3. CUSTOMER ISOLATION & AUTHORIZATION TEST ---

    def test_customer_isolation_and_admin_authorization(self):
        """Cross-customer isolation and admin route protection."""
        user1_token = self.make_token(user_id=str(ObjectId()), email="user1@example.com")
        user2_id = str(ObjectId())

        # Customer 1 cannot access Customer 2 detail
        res = self.client.get(f"/api/profile?user_id={user2_id}", headers={"Authorization": f"Bearer {user1_token}"})
        self.assertEqual(res.status_code, 403)

        # Customer 1 cannot access Admin Intelligence
        res_admin = self.client.get("/api/admin/intelligence/overview", headers={"Authorization": f"Bearer {user1_token}"})
        self.assertEqual(res_admin.status_code, 403)

        # Unauthenticated request rejected
        res_unauth = self.client.get("/api/admin/intelligence/overview")
        self.assertEqual(res_unauth.status_code, 401)


if __name__ == "__main__":
    unittest.main()
