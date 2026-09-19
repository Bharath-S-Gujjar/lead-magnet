"""Unit and integration tests for Task 13 Admin Intelligence Dashboard Backend.

Verifies canonical customer aggregation, lead qualification distribution,
customer-level directory listing, filtering, sorting, pagination, customer detail,
admin authorization, backward compatibility, and read-only safety.
"""

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
import jwt
from bson import ObjectId

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module
from admin_intelligence_service import (
    get_intelligence_overview,
    get_qualified_leads_list,
    get_customer_intelligence_detail,
    get_lead_distribution,
    get_recent_leads,
    get_marketing_activity,
    get_admin_notifications_list,
)
from customer_lead_state_service import (
    ensure_customer_lead_state_indexes,
    sync_customer_lead_state,
)
from customer_feature_service import ensure_customer_features_indexes
from marketing_automation_service import ensure_marketing_automation_indexes


def sample_high_intent_features(customer_id):
    return {
        "customer_id": customer_id,
        "sessions_count": 10,
        "total_events": 120,
        "total_time_spent": 1500.0,
        "average_session_duration": 150.0,
        "page_views_count": 60,
        "days_since_last_activity": 0.5,
        "products_viewed": 30,
        "unique_products_viewed": 15,
        "product_interactions": 45,
        "search_count": 5,
        "form_submit_count": 2,
        "high_intent_page_visits": 12,
        "cart_item_count": 5,
        "cart_value": 850.0,
        "wishlist_item_count": 4,
        "checkout_attempts": 8,
        "orders_count": 3,
        "total_order_value": 450.0,
        "average_order_value": 150.0,
    }


def sample_low_intent_features(customer_id):
    return {
        "customer_id": customer_id,
        "sessions_count": 1,
        "total_events": 5,
        "total_time_spent": 30.0,
        "average_session_duration": 30.0,
        "page_views_count": 4,
        "days_since_last_activity": 45.0,
        "products_viewed": 1,
        "unique_products_viewed": 1,
        "product_interactions": 1,
        "search_count": 0,
        "form_submit_count": 0,
        "high_intent_page_visits": 0,
        "cart_item_count": 0,
        "cart_value": 0.0,
        "wishlist_item_count": 0,
        "checkout_attempts": 0,
        "orders_count": 0,
        "total_order_value": 0.0,
        "average_order_value": 0.0,
    }


class AdminIntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.client = app_module.app.test_client()
        self.db = app_module.db
        self.profiles = app_module.profiles_collection
        self.features = app_module.customer_features_collection
        self.lead_state = app_module.customer_lead_state_collection
        self.events = app_module.marketing_automation_events_collection
        self.comms = app_module.marketing_communications_collection
        self.notifications = app_module.admin_notifications_collection
        self.leads = app_module.leads_collection

        ensure_customer_features_indexes(self.features)
        ensure_customer_lead_state_indexes(self.lead_state)
        ensure_marketing_automation_indexes(self.db)

        self.jwt_secret = app_module.JWT_SECRET

    def make_token(self, user_id, role="user"):
        exp_time = datetime.now(timezone.utc) + timedelta(minutes=5)
        return jwt.encode(
            {"sub": str(user_id), "role": role, "exp": exp_time},
            self.jwt_secret,
            algorithm="HS256"
        )

    # 1. Overview requires admin
    def test_01_overview_requires_admin(self):
        res = self.client.get("/api/admin/intelligence/overview")
        self.assertIn(res.status_code, [401, 403])

    # 2. Customer token gets 403
    def test_02_customer_token_gets_403(self):
        user_id = ObjectId()
        token = self.make_token(user_id, role="user")
        res = self.client.get(
            "/api/admin/intelligence/overview",
            headers={"Authorization": f"Bearer {token}"}
        )
        self.assertEqual(res.status_code, 403)

    # 3. Overview returns real customer count
    def test_03_overview_returns_real_customer_count(self):
        c1 = ObjectId()
        c2 = ObjectId()
        self.profiles.insert_one({"_id": c1, "email": "c1@test.com", "role": "user"})
        self.profiles.insert_one({"_id": c2, "email": "c2@test.com", "role": "user"})

        admin_token = self.make_token(ObjectId(), role="admin")
        res = self.client.get(
            "/api/admin/intelligence/overview",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()["data"]
        self.assertEqual(data["customers"]["total"], 2)

    # 4. Qualified lead count is based on customer_lead_state
    def test_04_qualified_lead_count_is_based_on_customer_lead_state(self):
        c1 = ObjectId()
        self.profiles.insert_one({"_id": c1, "email": "c1_q@test.com"})
        self.features.insert_one(sample_high_intent_features(c1))
        sync_customer_lead_state(c1, self.db)

        admin_token = self.make_token(ObjectId(), role="admin")
        res = self.client.get(
            "/api/admin/intelligence/overview",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        data = res.get_json()["data"]
        self.assertEqual(data["leads"]["total_qualified"], 1)

    # 5. Hot/Warm/Cold distribution is correct
    def test_05_hot_warm_cold_distribution_is_correct(self):
        c1 = ObjectId()
        self.profiles.insert_one({"_id": c1, "email": "hot@test.com"})
        self.features.insert_one(sample_high_intent_features(c1))
        sync_customer_lead_state(c1, self.db)

        admin_token = self.make_token(ObjectId(), role="admin")
        res = self.client.get(
            "/api/admin/intelligence/lead-distribution",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        self.assertEqual(res.status_code, 200)
        dist = res.get_json()["data"]
        self.assertEqual(dist["segments"]["hot"], 1)
        self.assertEqual(dist["qualification"]["qualified"], 1)

    # 6. No duplicate customer counting
    def test_06_no_duplicate_customer_counting(self):
        c1 = ObjectId()
        self.profiles.insert_one({"_id": c1, "email": "dup@test.com"})
        self.features.insert_one(sample_high_intent_features(c1))
        sync_customer_lead_state(c1, self.db)
        sync_customer_lead_state(c1, self.db)

        admin_token = self.make_token(ObjectId(), role="admin")
        res = self.client.get(
            "/api/admin/intelligence/overview",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        data = res.get_json()["data"]
        self.assertEqual(data["customers"]["total"], 1)
        self.assertEqual(data["leads"]["total_qualified"], 1)

    # 7. Legacy leads do not affect customer count
    def test_07_legacy_leads_do_not_affect_customer_count(self):
        self.leads.insert_one({"email": "legacy@test.com", "lead_score": 99})

        admin_token = self.make_token(ObjectId(), role="admin")
        res = self.client.get(
            "/api/admin/intelligence/overview",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        data = res.get_json()["data"]
        self.assertEqual(data["customers"]["total"], 0)

    # 8. Qualified lead list returns one row per customer
    def test_08_qualified_lead_list_returns_one_row_per_customer(self):
        c1 = ObjectId()
        self.profiles.insert_one({"_id": c1, "email": "dir@test.com", "full_name": "Directory User"})
        self.features.insert_one(sample_high_intent_features(c1))
        sync_customer_lead_state(c1, self.db)

        admin_token = self.make_token(ObjectId(), role="admin")
        res = self.client.get(
            "/api/admin/intelligence/leads",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        data = res.get_json()["data"]
        self.assertEqual(len(data["items"]), 1)
        self.assertEqual(data["items"][0]["customer_id"], str(c1))
        self.assertEqual(data["items"][0]["name"], "Directory User")

    # 9. Qualified list excludes not_qualified by default
    def test_09_qualified_list_excludes_not_qualified_by_default(self):
        c1 = ObjectId()
        c2 = ObjectId()
        self.profiles.insert_one({"_id": c1, "email": "qual@test.com"})
        self.profiles.insert_one({"_id": c2, "email": "notqual@test.com"})

        self.features.insert_one(sample_high_intent_features(c1))
        self.features.insert_one(sample_low_intent_features(c2))

        sync_customer_lead_state(c1, self.db)
        sync_customer_lead_state(c2, self.db)

        admin_token = self.make_token(ObjectId(), role="admin")
        res = self.client.get(
            "/api/admin/intelligence/leads",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        items = res.get_json()["data"]["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["customer_id"], str(c1))

    # 10. Segment filter works
    def test_10_segment_filter_works(self):
        c1 = ObjectId()
        self.profiles.insert_one({"_id": c1, "email": "seg@test.com"})
        self.features.insert_one(sample_high_intent_features(c1))
        sync_customer_lead_state(c1, self.db)

        admin_token = self.make_token(ObjectId(), role="admin")
        res_hot = self.client.get(
            "/api/admin/intelligence/leads?segment=Hot",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        self.assertEqual(len(res_hot.get_json()["data"]["items"]), 1)

        res_cold = self.client.get(
            "/api/admin/intelligence/leads?segment=Cold",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        self.assertEqual(len(res_cold.get_json()["data"]["items"]), 0)

    # 11. Sorting works
    def test_11_sorting_works(self):
        c1 = ObjectId()
        c2 = ObjectId()
        self.profiles.insert_one({"_id": c1, "email": "high@test.com"})
        self.profiles.insert_one({"_id": c2, "email": "medium@test.com"})

        f1 = sample_high_intent_features(c1)
        f2 = sample_high_intent_features(c2)
        f2["sessions_count"] = 5  # slightly lower

        self.features.insert_one(f1)
        self.features.insert_one(f2)

        sync_customer_lead_state(c1, self.db)
        sync_customer_lead_state(c2, self.db)

        admin_token = self.make_token(ObjectId(), role="admin")
        res_desc = self.client.get(
            "/api/admin/intelligence/leads?sort_by=lead_score&sort_order=desc",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        items_desc = res_desc.get_json()["data"]["items"]
        self.assertGreaterEqual(items_desc[0]["lead_score"], items_desc[1]["lead_score"])

    # 12. Pagination works
    def test_12_pagination_works(self):
        c1 = ObjectId()
        c2 = ObjectId()
        self.profiles.insert_one({"_id": c1, "email": "p1@test.com"})
        self.profiles.insert_one({"_id": c2, "email": "p2@test.com"})

        self.features.insert_one(sample_high_intent_features(c1))
        self.features.insert_one(sample_high_intent_features(c2))

        sync_customer_lead_state(c1, self.db)
        sync_customer_lead_state(c2, self.db)

        admin_token = self.make_token(ObjectId(), role="admin")
        res_p1 = self.client.get(
            "/api/admin/intelligence/leads?page=1&limit=1",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        data_p1 = res_p1.get_json()["data"]
        self.assertEqual(len(data_p1["items"]), 1)
        self.assertEqual(data_p1["total"], 2)
        self.assertEqual(data_p1["pages"], 2)

    # 13. Customer detail works
    def test_13_customer_detail_works(self):
        c1 = ObjectId()
        self.profiles.insert_one({"_id": c1, "email": "detail@test.com", "full_name": "Detail Customer"})
        self.features.insert_one(sample_high_intent_features(c1))
        sync_customer_lead_state(c1, self.db)

        admin_token = self.make_token(ObjectId(), role="admin")
        res = self.client.get(
            f"/api/admin/intelligence/customers/{str(c1)}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()["data"]
        self.assertEqual(data["customer"]["email"], "detail@test.com")
        self.assertIn("behavior", data)
        self.assertIn("lead", data)
        self.assertIn("orders", data)
        self.assertIn("marketing", data)

    # 14. Customer detail does not expose password/hash/secrets
    def test_14_customer_detail_does_not_expose_password_hash_secrets(self):
        c1 = ObjectId()
        self.profiles.insert_one({
            "_id": c1,
            "email": "secret@test.com",
            "password": "plain_password",
            "password_hash": "$2b$12$hash",
            "token": "secret_jwt_token"
        })

        admin_token = self.make_token(ObjectId(), role="admin")
        res = self.client.get(
            f"/api/admin/intelligence/customers/{str(c1)}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        data = res.get_json()["data"]["customer"]
        self.assertNotIn("password", data)
        self.assertNotIn("password_hash", data)
        self.assertNotIn("token", data)

    # 15. Missing customer returns 404
    def test_15_missing_customer_returns_404(self):
        admin_token = self.make_token(ObjectId(), role="admin")
        missing_id = str(ObjectId())
        res = self.client.get(
            f"/api/admin/intelligence/customers/{missing_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        self.assertEqual(res.status_code, 404)

    # 16. Invalid ObjectId is handled safely
    def test_16_invalid_objectid_is_handled_safely(self):
        admin_token = self.make_token(ObjectId(), role="admin")
        res = self.client.get(
            "/api/admin/intelligence/customers/invalid-oid-string",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        self.assertEqual(res.status_code, 400)

    # 17. Recent qualified leads only includes actual qualification transitions
    def test_17_recent_qualified_leads_only_includes_actual_qualification_transitions(self):
        c1 = ObjectId()
        self.profiles.insert_one({"_id": c1, "email": "recent_qual@test.com"})
        self.features.insert_one(sample_high_intent_features(c1))
        sync_customer_lead_state(c1, self.db)

        admin_token = self.make_token(ObjectId(), role="admin")
        res = self.client.get(
            "/api/admin/intelligence/recent-leads",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        self.assertEqual(res.status_code, 200)
        items = res.get_json()["data"]["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["customer_id"], str(c1))

    # 18. Marketing activity reflects real communication records
    def test_18_marketing_activity_reflects_real_communication_records(self):
        c1 = ObjectId()
        self.profiles.insert_one({"_id": c1, "email": "mkt_act@test.com"})
        self.features.insert_one(sample_high_intent_features(c1))
        sync_customer_lead_state(c1, self.db)

        admin_token = self.make_token(ObjectId(), role="admin")
        res = self.client.get(
            "/api/admin/intelligence/marketing-activity",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        self.assertEqual(res.status_code, 200)
        items = res.get_json()["data"]["items"]
        self.assertGreater(len(items), 0)

    # 19. Notification endpoint is admin-only
    def test_19_notification_endpoint_is_admin_only(self):
        user_token = self.make_token(ObjectId(), role="user")
        res_user = self.client.get(
            "/api/admin/intelligence/notifications",
            headers={"Authorization": f"Bearer {user_token}"}
        )
        self.assertEqual(res_user.status_code, 403)

        admin_token = self.make_token(ObjectId(), role="admin")
        res_admin = self.client.get(
            "/api/admin/intelligence/notifications",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        self.assertEqual(res_admin.status_code, 200)

    # 20. Analytics overview remains backward compatible
    def test_20_analytics_overview_remains_backward_compatible(self):
        c1 = ObjectId()
        self.profiles.insert_one({"_id": c1, "email": "legacy_ov@test.com"})
        self.features.insert_one(sample_high_intent_features(c1))
        sync_customer_lead_state(c1, self.db)

        admin_token = self.make_token(ObjectId(), role="admin")
        res = self.client.get(
            "/api/analytics/overview",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()["data"]
        self.assertIn("total_customers", data)
        self.assertIn("total_leads", data)
        self.assertIn("active_customers_today", data)
        self.assertIn("predicted_future_leads", data)

    # 21. Empty database returns safe zero/empty/null values
    def test_21_empty_database_returns_safe_zero_empty_null_values(self):
        admin_token = self.make_token(ObjectId(), role="admin")

        res_ov = self.client.get(
            "/api/admin/intelligence/overview",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        self.assertEqual(res_ov.status_code, 200)
        data_ov = res_ov.get_json()["data"]
        self.assertEqual(data_ov["customers"]["total"], 0)
        self.assertEqual(data_ov["leads"]["total_qualified"], 0)

        res_dist = self.client.get(
            "/api/admin/intelligence/lead-distribution",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        self.assertEqual(res_dist.status_code, 200)
        data_dist = res_dist.get_json()["data"]
        self.assertEqual(data_dist["total"], 0)

        res_leads = self.client.get(
            "/api/admin/intelligence/leads",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        self.assertEqual(res_leads.status_code, 200)
        data_leads = res_leads.get_json()["data"]
        self.assertEqual(data_leads["total"], 0)
        self.assertEqual(len(data_leads["items"]), 0)


if __name__ == "__main__":
    unittest.main()
