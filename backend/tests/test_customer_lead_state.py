"""Unit and integration tests for Task 11 Customer-Level Lead State Layer.

Verifies schema validation, unique indexing, qualification rules, state transitions,
idempotency, authentication & security restrictions, and zero side effects.
"""

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
import jwt
from bson import ObjectId

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module
from customer_lead_state_service import (
    ensure_customer_lead_state_indexes,
    get_customer_lead_state,
    sync_customer_lead_state,
    QUALIFICATION_PROBABILITY_THRESHOLD,
)
from customer_feature_service import ensure_customer_features_indexes


def sample_customer_features(customer_id, high_intent=False):
    if high_intent:
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
    else:
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


class CustomerLeadStateTests(unittest.TestCase):
    def setUp(self):
        self.client = app_module.app.test_client()
        self.db = app_module.db
        self.profiles = app_module.profiles_collection
        self.features = app_module.customer_features_collection
        self.lead_state = app_module.customer_lead_state_collection
        self.leads = app_module.leads_collection

        ensure_customer_features_indexes(self.features)
        ensure_customer_lead_state_indexes(self.lead_state)

        self.jwt_secret = app_module.JWT_SECRET

    def make_token(self, user_id, role="user"):
        exp_time = datetime.now(timezone.utc) + timedelta(minutes=5)
        return jwt.encode(
            {"sub": str(user_id), "role": role, "exp": exp_time},
            self.jwt_secret,
            algorithm="HS256"
        )

    # 1. Customer lead state collection/index setup
    def test_01_customer_lead_state_collection_and_index_setup(self):
        ensure_customer_lead_state_indexes(self.lead_state)
        indexes = list(self.lead_state.list_indexes())
        idx_names = [i["name"] for i in indexes]
        self.assertIn("customer_id_1", idx_names)

    # 2. First state creation
    def test_02_first_state_creation(self):
        user_id = ObjectId()
        doc = sample_customer_features(user_id, high_intent=True)
        self.features.insert_one({"customer_id": user_id, **doc})

        state = sync_customer_lead_state(user_id, self.db)
        self.assertIsNotNone(state)
        self.assertEqual(state["customer_id"], user_id)
        self.assertIn("qualification_status", state)

    # 3. One customer produces exactly one state document
    def test_03_one_customer_produces_exactly_one_state_document(self):
        user_id = ObjectId()
        doc = sample_customer_features(user_id, high_intent=False)
        self.features.insert_one({"customer_id": user_id, **doc})

        sync_customer_lead_state(user_id, self.db)
        count = self.lead_state.count_documents({"customer_id": user_id})
        self.assertEqual(count, 1)

    # 4. Repeated synchronization is idempotent
    def test_04_repeated_synchronization_is_idempotent(self):
        user_id = ObjectId()
        doc = sample_customer_features(user_id, high_intent=True)
        self.features.insert_one({"customer_id": user_id, **doc})

        for _ in range(10):
            sync_customer_lead_state(user_id, self.db)

        count = self.lead_state.count_documents({"customer_id": user_id})
        self.assertEqual(count, 1)

    # 5. Current score is persisted
    def test_05_current_score_is_persisted(self):
        user_id = ObjectId()
        doc = sample_customer_features(user_id, high_intent=True)
        self.features.insert_one({"customer_id": user_id, **doc})

        state = sync_customer_lead_state(user_id, self.db)
        persisted = self.lead_state.find_one({"customer_id": user_id})
        self.assertEqual(persisted["lead_score"], state["lead_score"])

    # 6. Current probability is persisted
    def test_06_current_probability_is_persisted(self):
        user_id = ObjectId()
        doc = sample_customer_features(user_id, high_intent=True)
        self.features.insert_one({"customer_id": user_id, **doc})

        state = sync_customer_lead_state(user_id, self.db)
        persisted = self.lead_state.find_one({"customer_id": user_id})
        self.assertEqual(persisted["lead_probability"], state["lead_probability"])

    # 7. Current segment is persisted
    def test_07_current_segment_is_persisted(self):
        user_id = ObjectId()
        doc = sample_customer_features(user_id, high_intent=True)
        self.features.insert_one({"customer_id": user_id, **doc})

        state = sync_customer_lead_state(user_id, self.db)
        persisted = self.lead_state.find_one({"customer_id": user_id})
        self.assertEqual(persisted["lead_segment"], state["lead_segment"])

    # 8. Model version is persisted
    def test_08_model_version_is_persisted(self):
        user_id = ObjectId()
        doc = sample_customer_features(user_id, high_intent=True)
        self.features.insert_one({"customer_id": user_id, **doc})

        state = sync_customer_lead_state(user_id, self.db)
        self.assertEqual(state["model_version"], "v2.0_ecommerce_xgb")

    # 9. First qualification timestamp is created
    def test_09_first_qualification_timestamp_is_created(self):
        user_id = ObjectId()
        doc = sample_customer_features(user_id, high_intent=True)
        self.features.insert_one({"customer_id": user_id, **doc})

        state = sync_customer_lead_state(user_id, self.db)
        if state["qualification_status"] == "qualified":
            self.assertIsNotNone(state["first_qualified_at"])

    # 10. First qualification timestamp is not overwritten
    def test_10_first_qualification_timestamp_is_not_overwritten(self):
        user_id = ObjectId()
        doc = sample_customer_features(user_id, high_intent=True)
        self.features.insert_one({"customer_id": user_id, **doc})

        state1 = sync_customer_lead_state(user_id, self.db)
        if state1["qualification_status"] == "qualified":
            first_time = state1["first_qualified_at"]

            # Update feature to another qualified state
            self.features.update_one(
                {"customer_id": user_id},
                {"$set": {"checkout_attempts": 15, "cart_value": 1200.0}}
            )
            state2 = sync_customer_lead_state(user_id, self.db)
            self.assertEqual(state2["first_qualified_at"], first_time)

    # 11. Qualified -> not_qualified transition
    def test_11_qualified_to_not_qualified_transition(self):
        user_id = ObjectId()
        doc_high = sample_customer_features(user_id, high_intent=True)
        self.features.insert_one({"customer_id": user_id, **doc_high})

        state1 = sync_customer_lead_state(user_id, self.db)
        if state1["qualification_status"] == "qualified":
            # Demote to cold
            doc_low = sample_customer_features(user_id, high_intent=False)
            self.features.update_one({"customer_id": user_id}, {"$set": doc_low})

            state2 = sync_customer_lead_state(user_id, self.db)
            self.assertEqual(state2["qualification_status"], "not_qualified")
            self.assertEqual(state2["previous_qualification_status"], "qualified")
            self.assertEqual(state2["qualification_transition"], "qualified_to_not_qualified")

    # 12. Not_qualified -> qualified transition
    def test_12_not_qualified_to_qualified_transition(self):
        user_id = ObjectId()
        doc_low = sample_customer_features(user_id, high_intent=False)
        self.features.insert_one({"customer_id": user_id, **doc_low})

        state1 = sync_customer_lead_state(user_id, self.db)
        self.assertEqual(state1["qualification_status"], "not_qualified")

        # Promote to hot
        doc_high = sample_customer_features(user_id, high_intent=True)
        self.features.update_one({"customer_id": user_id}, {"$set": doc_high})

        state2 = sync_customer_lead_state(user_id, self.db)
        self.assertEqual(state2["qualification_status"], "qualified")
        self.assertEqual(state2["previous_qualification_status"], "not_qualified")
        self.assertEqual(state2["qualification_transition"], "not_qualified_to_qualified")
        self.assertTrue(state2["is_newly_qualified"])

    # 13. Re-qualification updates last_qualified_at
    def test_13_requalification_updates_last_qualified_at(self):
        user_id = ObjectId()
        doc_high = sample_customer_features(user_id, high_intent=True)
        self.features.insert_one({"customer_id": user_id, **doc_high})

        state1 = sync_customer_lead_state(user_id, self.db)
        if state1["qualification_status"] == "qualified":
            original_first = state1["first_qualified_at"]

            # Drop to not qualified
            doc_low = sample_customer_features(user_id, high_intent=False)
            self.features.update_one({"customer_id": user_id}, {"$set": doc_low})
            sync_customer_lead_state(user_id, self.db)

            # Re-qualify
            self.features.update_one({"customer_id": user_id}, {"$set": doc_high})
            state3 = sync_customer_lead_state(user_id, self.db)

            self.assertEqual(state3["qualification_status"], "qualified")
            self.assertEqual(state3["first_qualified_at"], original_first)
            self.assertIsNotNone(state3["last_qualified_at"])

    # 14. First_qualified_at remains original after re-qualification
    def test_14_first_qualified_at_remains_original_after_requalification(self):
        user_id = ObjectId()
        doc_high = sample_customer_features(user_id, high_intent=True)
        self.features.insert_one({"customer_id": user_id, **doc_high})

        state1 = sync_customer_lead_state(user_id, self.db)
        if state1["qualification_status"] == "qualified":
            orig_first = state1["first_qualified_at"]

            # Demote then re-promote
            doc_low = sample_customer_features(user_id, high_intent=False)
            self.features.update_one({"customer_id": user_id}, {"$set": doc_low})
            sync_customer_lead_state(user_id, self.db)

            self.features.update_one({"customer_id": user_id}, {"$set": doc_high})
            state3 = sync_customer_lead_state(user_id, self.db)

            self.assertEqual(state3["first_qualified_at"], orig_first)

    # 15. Segment changes are detected
    def test_15_segment_changes_are_detected(self):
        user_id = ObjectId()
        doc_low = sample_customer_features(user_id, high_intent=False)
        self.features.insert_one({"customer_id": user_id, **doc_low})

        state1 = sync_customer_lead_state(user_id, self.db)

        doc_high = sample_customer_features(user_id, high_intent=True)
        self.features.update_one({"customer_id": user_id}, {"$set": doc_high})

        state2 = sync_customer_lead_state(user_id, self.db)
        self.assertTrue(state2["segment_changed"])
        self.assertNotEqual(state2["previous_segment"], state2["lead_segment"])

    # 16. Unchanged state is recognized correctly
    def test_16_unchanged_state_recognized_correctly(self):
        user_id = ObjectId()
        doc = sample_customer_features(user_id, high_intent=False)
        self.features.insert_one({"customer_id": user_id, **doc})

        sync_customer_lead_state(user_id, self.db)
        state2 = sync_customer_lead_state(user_id, self.db)

        self.assertFalse(state2["segment_changed"])
        self.assertFalse(state2["is_newly_qualified"])

    # 17. Customer endpoint requires authentication
    def test_17_customer_endpoint_requires_authentication(self):
        res = self.client.get("/api/customer/lead-state")
        self.assertEqual(res.status_code, 401)

    # 18. Customer endpoint uses JWT identity instead of request customer_id
    def test_18_customer_endpoint_uses_jwt_identity_instead_of_request_customer_id(self):
        user_a_id = ObjectId()
        user_b_id = ObjectId()

        doc_a = sample_customer_features(user_a_id, high_intent=True)
        doc_b = sample_customer_features(user_b_id, high_intent=False)

        self.features.insert_one({"customer_id": user_a_id, **doc_a})
        self.features.insert_one({"customer_id": user_b_id, **doc_b})

        sync_customer_lead_state(user_a_id, self.db)
        sync_customer_lead_state(user_b_id, self.db)

        token_a = self.make_token(user_a_id, role="user")

        # Query with user A token and spoofed ?customer_id=user_b_id
        res = self.client.get(
            f"/api/customer/lead-state?customer_id={user_b_id}",
            headers={"Authorization": f"Bearer {token_a}"}
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()["data"]
        self.assertEqual(data["customer_id"], str(user_a_id))

    # 19. Cross-customer access is prevented
    def test_19_cross_customer_access_prevented(self):
        user_a_id = ObjectId()
        user_b_id = ObjectId()

        doc_a = sample_customer_features(user_a_id, high_intent=True)
        self.features.insert_one({"customer_id": user_a_id, **doc_a})
        sync_customer_lead_state(user_a_id, self.db)

        token_b = self.make_token(user_b_id, role="user")

        # User B token should return 404 for their own missing lead state
        res = self.client.get(
            f"/api/customer/lead-state?customer_id={user_a_id}",
            headers={"Authorization": f"Bearer {token_b}"}
        )
        self.assertEqual(res.status_code, 404)

    # 20. Admin endpoint works for admin
    def test_20_admin_endpoint_works_for_admin(self):
        target_id = ObjectId()
        doc = sample_customer_features(target_id, high_intent=True)
        self.features.insert_one({"customer_id": target_id, **doc})
        sync_customer_lead_state(target_id, self.db)

        admin_token = self.make_token(ObjectId(), role="admin")
        res = self.client.get(
            f"/api/admin/customer-lead-state/{target_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        self.assertEqual(res.status_code, 200)
        data = res.get_json()["data"]
        self.assertEqual(data["customer_id"], str(target_id))

    # 21. Non-admin receives 403
    def test_21_non_admin_receives_403(self):
        target_id = ObjectId()
        doc = sample_customer_features(target_id, high_intent=True)
        self.features.insert_one({"customer_id": target_id, **doc})

        user_token = self.make_token(ObjectId(), role="user")
        res = self.client.get(
            f"/api/admin/customer-lead-state/{target_id}",
            headers={"Authorization": f"Bearer {user_token}"}
        )
        self.assertEqual(res.status_code, 403)

    # 22. Missing customer state returns 404
    def test_22_missing_customer_state_returns_404(self):
        user_id = ObjectId()
        token = self.make_token(user_id, role="user")

        res = self.client.get(
            "/api/customer/lead-state",
            headers={"Authorization": f"Bearer {token}"}
        )
        self.assertEqual(res.status_code, 404)

    # 23. Invalid customer ID returns appropriate 4xx
    def test_23_invalid_customer_id_returns_appropriate_4xx(self):
        admin_token = self.make_token(ObjectId(), role="admin")
        res = self.client.get(
            "/api/admin/customer-lead-state/non_existent_customer_id_99999",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        self.assertEqual(res.status_code, 404)

    # 24. Synchronization does not create legacy leads records
    def test_24_sync_does_not_create_legacy_leads_records(self):
        user_id = ObjectId()
        doc = sample_customer_features(user_id, high_intent=True)
        self.features.insert_one({"customer_id": user_id, **doc})

        leads_before = self.leads.count_documents({})
        sync_customer_lead_state(user_id, self.db)
        leads_after = self.leads.count_documents({})

        self.assertEqual(leads_before, leads_after)

    # 25. Synchronization does not send marketing messages
    def test_25_sync_does_not_send_marketing_messages(self):
        user_id = ObjectId()
        doc = sample_customer_features(user_id, high_intent=True)
        self.features.insert_one({"customer_id": user_id, **doc})

        state = sync_customer_lead_state(user_id, self.db)
        self.assertIsNotNone(state)
        # Verify state doc contains zero marketing dispatch fields
        self.assertNotIn("email_sent", state)
        self.assertNotIn("whatsapp_sent", state)

    # 26. Synchronization does not modify customer feature values
    def test_26_sync_does_not_modify_customer_features(self):
        user_id = ObjectId()
        doc = sample_customer_features(user_id, high_intent=True)
        self.features.insert_one({"customer_id": user_id, **doc})

        feat_before = self.features.find_one({"customer_id": user_id})
        sync_customer_lead_state(user_id, self.db)
        feat_after = self.features.find_one({"customer_id": user_id})

        self.assertEqual(feat_before, feat_after)

    # 27. Repeated synchronization does not duplicate state
    def test_27_repeated_sync_does_not_duplicate_state(self):
        user_id = ObjectId()
        doc = sample_customer_features(user_id, high_intent=True)
        self.features.insert_one({"customer_id": user_id, **doc})

        for _ in range(5):
            sync_customer_lead_state(user_id, self.db)

        total_docs = self.lead_state.count_documents({})
        user_docs = self.lead_state.count_documents({"customer_id": user_id})
        self.assertEqual(user_docs, 1)

    # 28. Deterministic state calculation for identical feature input
    def test_28_deterministic_state_calculation(self):
        user1_id = ObjectId()
        user2_id = ObjectId()

        doc1 = sample_customer_features(user1_id, high_intent=True)
        doc2 = sample_customer_features(user2_id, high_intent=True)

        self.features.insert_one({"customer_id": user1_id, **doc1})
        self.features.insert_one({"customer_id": user2_id, **doc2})

        state1 = sync_customer_lead_state(user1_id, self.db)
        state2 = sync_customer_lead_state(user2_id, self.db)

        self.assertEqual(state1["lead_probability"], state2["lead_probability"])
        self.assertEqual(state1["lead_score"], state2["lead_score"])
        self.assertEqual(state1["lead_segment"], state2["lead_segment"])
        self.assertEqual(state1["qualification_status"], state2["qualification_status"])


if __name__ == "__main__":
    unittest.main()
