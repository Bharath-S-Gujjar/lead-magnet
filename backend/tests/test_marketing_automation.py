"""Unit and integration tests for Task 12 Marketing Automation Engine.

Verifies event-driven triggers, idempotency, communication provider abstraction,
channel eligibility policies, status transitions, retries, security & auth rules,
admin diagnostic endpoints, and side-effect isolation.
"""

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
import jwt
from bson import ObjectId

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module
from communication_provider import (
    CommunicationProvider,
    DryRunCommunicationProvider,
    FailingCommunicationProvider,
)
from marketing_automation_service import (
    ensure_marketing_automation_indexes,
    evaluate_channel_eligibility,
    create_automation_event_for_qualification,
    process_marketing_automation_event,
)
from customer_lead_state_service import (
    ensure_customer_lead_state_indexes,
    sync_customer_lead_state,
)
from customer_feature_service import ensure_customer_features_indexes


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


class MarketingAutomationTests(unittest.TestCase):
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

    # 1. Newly qualified customer creates one automation event
    def test_01_newly_qualified_customer_creates_one_automation_event(self):
        customer_id = ObjectId()
        self.profiles.insert_one({
            "_id": customer_id,
            "email": "qualified_test@example.com",
            "full_name": "Qualified Test User",
            "phone": "+15551234567"
        })
        self.features.insert_one(sample_high_intent_features(customer_id))

        state = sync_customer_lead_state(customer_id, self.db)
        self.assertEqual(state["qualification_status"], "qualified")

        event_docs = list(self.events.find({"customer_id": customer_id}))
        self.assertEqual(len(event_docs), 1)
        self.assertEqual(event_docs[0]["event_type"], "lead_qualified")
        self.assertEqual(event_docs[0]["status"], "completed")

    # 2. Repeated processing does not create duplicate events
    def test_02_repeated_processing_does_not_create_duplicate_events(self):
        customer_id = ObjectId()
        self.profiles.insert_one({
            "_id": customer_id,
            "email": "repeat_test@example.com",
            "full_name": "Repeat Test User"
        })
        self.features.insert_one(sample_high_intent_features(customer_id))

        sync_customer_lead_state(customer_id, self.db)
        sync_customer_lead_state(customer_id, self.db)

        event_docs = list(self.events.find({"customer_id": customer_id}))
        self.assertEqual(len(event_docs), 1)

    # 3. Qualified -> qualified does not create a new qualification event
    def test_03_qualified_to_qualified_does_not_create_new_qualification_event(self):
        customer_id = ObjectId()
        self.profiles.insert_one({
            "_id": customer_id,
            "email": "q2q_test@example.com"
        })
        self.features.insert_one(sample_high_intent_features(customer_id))

        sync_customer_lead_state(customer_id, self.db)
        initial_event_count = self.events.count_documents({"customer_id": customer_id})
        self.assertEqual(initial_event_count, 1)

        # Sync again while still qualified
        sync_customer_lead_state(customer_id, self.db)
        second_event_count = self.events.count_documents({"customer_id": customer_id})
        self.assertEqual(second_event_count, 1)

    # 4. Not_qualified -> not_qualified does not create an event
    def test_04_not_qualified_to_not_qualified_does_not_create_event(self):
        customer_id = ObjectId()
        self.profiles.insert_one({
            "_id": customer_id,
            "email": "nq_test@example.com"
        })
        self.features.insert_one(sample_low_intent_features(customer_id))

        sync_customer_lead_state(customer_id, self.db)
        self.assertEqual(self.events.count_documents({"customer_id": customer_id}), 0)

        # Sync again
        sync_customer_lead_state(customer_id, self.db)
        self.assertEqual(self.events.count_documents({"customer_id": customer_id}), 0)

    # 5. Customer without email skips email safely
    def test_05_customer_without_email_skips_email_safely(self):
        customer_id = ObjectId()
        self.profiles.insert_one({
            "_id": customer_id,
            "email": None,
            "phone": "+15559999999"
        })
        self.features.insert_one(sample_high_intent_features(customer_id))

        sync_customer_lead_state(customer_id, self.db)

        comm_docs = list(self.comms.find({"customer_id": customer_id, "channel": "email"}))
        self.assertEqual(len(comm_docs), 1)
        self.assertEqual(comm_docs[0]["status"], "skipped")
        self.assertIn("No valid email", comm_docs[0].get("last_error", ""))

    # 6. Customer without phone skips SMS/WhatsApp safely
    def test_06_customer_without_phone_skips_sms_whatsapp_safely(self):
        customer_id = ObjectId()
        self.profiles.insert_one({
            "_id": customer_id,
            "email": "nophone@example.com",
            "phone": None
        })

        customer = self.profiles.find_one({"_id": customer_id})
        eligibility = evaluate_channel_eligibility(
            customer,
            policy={"sms_enabled": True, "whatsapp_enabled": True}
        )

        self.assertTrue(eligibility["email"]["eligible"])
        self.assertFalse(eligibility["sms"]["eligible"])
        self.assertFalse(eligibility["whatsapp"]["eligible"])
        self.assertIn("No phone number", eligibility["sms"]["reason"])

    # 7. Disabled SMS does not attempt SMS
    def test_07_disabled_sms_does_not_attempt_sms(self):
        customer_id = ObjectId()
        self.profiles.insert_one({
            "_id": customer_id,
            "email": "test_sms_disabled@example.com",
            "phone": "+15558888888"
        })
        customer = self.profiles.find_one({"_id": customer_id})

        eligibility = evaluate_channel_eligibility(
            customer,
            policy={"sms_enabled": False, "whatsapp_enabled": False}
        )

        self.assertFalse(eligibility["sms"]["eligible"])
        self.assertIn("SMS channel disabled", eligibility["sms"]["reason"])

    # 8. Disabled WhatsApp does not attempt WhatsApp
    def test_08_disabled_whatsapp_does_not_attempt_whatsapp(self):
        customer_id = ObjectId()
        self.profiles.insert_one({
            "_id": customer_id,
            "email": "test_wa_disabled@example.com",
            "phone": "+15558888888"
        })
        customer = self.profiles.find_one({"_id": customer_id})

        eligibility = evaluate_channel_eligibility(
            customer,
            policy={"sms_enabled": False, "whatsapp_enabled": False}
        )

        self.assertFalse(eligibility["whatsapp"]["eligible"])
        self.assertIn("WhatsApp channel disabled", eligibility["whatsapp"]["reason"])

    # 9. Dry-run email provider works
    def test_09_dry_run_email_provider_works(self):
        provider = DryRunCommunicationProvider()
        res = provider.send_email("test@example.com", "Test Subject", "Test Body")
        self.assertTrue(res["success"])
        self.assertEqual(res["provider"], "dry_run")
        self.assertTrue(res["provider_message_id"].startswith("dry-run-email-"))

    # 10. Dry-run SMS provider removed per Phase 17A spec
    def test_10_dry_run_sms_provider_removed(self):
        provider = DryRunCommunicationProvider()
        self.assertFalse(hasattr(provider, "send_sms"))

    # 11. Dry-run WhatsApp provider works
    def test_11_dry_run_whatsapp_provider_works(self):
        provider = DryRunCommunicationProvider()
        res = provider.send_whatsapp("+15551234567", "Test WhatsApp message")
        self.assertTrue(res["success"])
        self.assertEqual(res["provider"], "dry_run")
        self.assertTrue(res["provider_message_id"].startswith("dry-run-whatsapp-"))

    # 12. Successful communication becomes sent
    def test_12_successful_communication_becomes_sent(self):
        customer_id = ObjectId()
        self.profiles.insert_one({
            "_id": customer_id,
            "email": "sent_test@example.com"
        })
        self.features.insert_one(sample_high_intent_features(customer_id))

        sync_customer_lead_state(customer_id, self.db)

        comm = self.comms.find_one({"customer_id": customer_id, "channel": "email"})
        self.assertIsNotNone(comm)
        self.assertEqual(comm["status"], "sent")
        self.assertIsNotNone(comm["sent_at"])
        self.assertTrue(comm["provider_message_id"].startswith("dry-run-email-"))

    # 13. Failed provider call becomes failed
    def test_13_failed_provider_call_becomes_failed(self):
        customer_id = ObjectId()
        self.profiles.insert_one({
            "_id": customer_id,
            "email": "fail_provider@example.com"
        })
        self.features.insert_one(sample_high_intent_features(customer_id))

        # Create event manually
        event_doc = create_automation_event_for_qualification(
            customer_id=customer_id,
            lead_score=85,
            lead_probability=0.85,
            lead_segment="Hot",
            model_version="v2.0_ecommerce_xgb",
            qualification_occurrence=1,
            db=self.db
        )

        failing_provider = FailingCommunicationProvider("Network timeout simulated")
        process_marketing_automation_event(
            event_doc["_id"],
            db=self.db,
            provider=failing_provider
        )

        comm = self.comms.find_one({"automation_event_id": event_doc["_id"], "channel": "email"})
        self.assertIsNotNone(comm)
        self.assertEqual(comm["status"], "failed")

    # 14. Provider error is stored
    def test_14_provider_error_is_stored(self):
        customer_id = ObjectId()
        self.profiles.insert_one({
            "_id": customer_id,
            "email": "error_stored@example.com"
        })

        event_doc = create_automation_event_for_qualification(
            customer_id=customer_id,
            lead_score=90,
            lead_probability=0.90,
            lead_segment="Hot",
            model_version="v2.0_ecommerce_xgb",
            qualification_occurrence=1,
            db=self.db
        )

        error_msg = "SMTP server connection refused"
        failing_provider = FailingCommunicationProvider(error_msg)
        process_marketing_automation_event(
            event_doc["_id"],
            db=self.db,
            provider=failing_provider
        )

        comm = self.comms.find_one({"automation_event_id": event_doc["_id"], "channel": "email"})
        self.assertEqual(comm["last_error"], error_msg)

    # 15. Attempt count increments correctly
    def test_15_attempt_count_increments_correctly(self):
        customer_id = ObjectId()
        self.profiles.insert_one({
            "_id": customer_id,
            "email": "retry_count@example.com"
        })

        event_doc = create_automation_event_for_qualification(
            customer_id=customer_id,
            lead_score=90,
            lead_probability=0.90,
            lead_segment="Hot",
            model_version="v2.0_ecommerce_xgb",
            qualification_occurrence=1,
            db=self.db
        )

        failing_provider = FailingCommunicationProvider("Transient error")

        # Attempt 1
        process_marketing_automation_event(
            event_doc["_id"],
            db=self.db,
            provider=failing_provider
        )

        comm = self.comms.find_one({"automation_event_id": event_doc["_id"], "channel": "email"})
        self.assertEqual(comm["attempt_count"], 1)

        # Mark event pending to allow retry test
        self.events.update_one({"_id": event_doc["_id"]}, {"$set": {"status": "pending"}})

        # Attempt 2
        process_marketing_automation_event(
            event_doc["_id"],
            db=self.db,
            provider=failing_provider
        )

        comm2 = self.comms.find_one({"automation_event_id": event_doc["_id"], "channel": "email"})
        self.assertEqual(comm2["attempt_count"], 2)

    # 16. Already-sent communication is never sent twice
    def test_16_already_sent_communication_is_never_sent_twice(self):
        customer_id = ObjectId()
        self.profiles.insert_one({
            "_id": customer_id,
            "email": "sent_once@example.com"
        })
        self.features.insert_one(sample_high_intent_features(customer_id))

        sync_customer_lead_state(customer_id, self.db)

        comm = self.comms.find_one({"customer_id": customer_id, "channel": "email"})
        self.assertEqual(comm["status"], "sent")
        orig_sent_at = comm["sent_at"]

        # Reset event to pending to force re-evaluation of process_marketing_automation_event
        event = self.events.find_one({"customer_id": customer_id})
        self.events.update_one({"_id": event["_id"]}, {"$set": {"status": "pending"}})

        process_marketing_automation_event(event["_id"], db=self.db)

        comm_after = self.comms.find_one({"customer_id": customer_id, "channel": "email"})
        self.assertEqual(comm_after["status"], "sent")
        self.assertEqual(comm_after["sent_at"], orig_sent_at)
        self.assertEqual(comm_after["attempt_count"], 1)

    # 17. Repeated automation processing is idempotent
    def test_17_repeated_automation_processing_is_idempotent(self):
        customer_id = ObjectId()
        self.profiles.insert_one({
            "_id": customer_id,
            "email": "idempotent_proc@example.com"
        })
        self.features.insert_one(sample_high_intent_features(customer_id))

        sync_customer_lead_state(customer_id, self.db)
        event = self.events.find_one({"customer_id": customer_id})

        total_comms_before = self.comms.count_documents({"automation_event_id": event["_id"]})
        self.assertEqual(total_comms_before, 2)  # email, whatsapp records

        process_marketing_automation_event(event["_id"], db=self.db)
        process_marketing_automation_event(event["_id"], db=self.db)

        total_comms_after = self.comms.count_documents({"automation_event_id": event["_id"]})
        self.assertEqual(total_comms_after, 2)
        self.assertEqual(self.comms.count_documents({"automation_event_id": event["_id"], "channel": "email"}), 1)

    # 18. Customer endpoint cannot inspect another customer's automation state
    def test_18_customer_endpoint_cannot_inspect_another_customers_automation_state(self):
        user1_id = ObjectId()
        token = self.make_token(user1_id, role="user")

        response = self.client.get(
            "/api/admin/marketing/automation-events",
            headers={"Authorization": f"Bearer {token}"}
        )
        self.assertEqual(response.status_code, 403)

    # 19. Admin endpoint works
    def test_19_admin_endpoint_works(self):
        admin_id = ObjectId()
        admin_token = self.make_token(admin_id, role="admin")

        response = self.client.get(
            "/api/admin/marketing/automation-events",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data.get("success"))
        self.assertIsInstance(data.get("data"), list)

        res_comms = self.client.get(
            "/api/admin/marketing/communications",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        self.assertEqual(res_comms.status_code, 200)

        res_notif = self.client.get(
            "/api/admin/notifications",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        self.assertEqual(res_notif.status_code, 200)

    # 20. Non-admin receives 403
    def test_20_non_admin_receives_403(self):
        user_id = ObjectId()
        token = self.make_token(user_id, role="user")

        for endpoint in [
            "/api/admin/marketing/automation-events",
            "/api/admin/marketing/communications",
            "/api/admin/notifications",
        ]:
            res = self.client.get(endpoint, headers={"Authorization": f"Bearer {token}"})
            self.assertEqual(res.status_code, 403)

    # 21. No real external provider is contacted by tests
    def test_21_no_real_external_provider_is_contacted_by_tests(self):
        provider = DryRunCommunicationProvider()
        res = provider.send_email("real_email@domain.com", "Subject", "Body")
        self.assertEqual(res["provider"], "dry_run")
        self.assertTrue(res["provider_message_id"].startswith("dry-run-"))

    # 22. Lead-state data remains unchanged by communication processing
    def test_22_lead_state_data_remains_unchanged_by_communication_processing(self):
        customer_id = ObjectId()
        self.profiles.insert_one({
            "_id": customer_id,
            "email": "ls_unchanged@example.com"
        })
        self.features.insert_one(sample_high_intent_features(customer_id))

        state_before = sync_customer_lead_state(customer_id, self.db)

        # Process automation event
        event = self.events.find_one({"customer_id": customer_id})
        process_marketing_automation_event(event["_id"], db=self.db)

        state_after = self.lead_state.find_one({"customer_id": customer_id})

        self.assertEqual(state_before["qualification_status"], state_after["qualification_status"])
        self.assertEqual(state_before["lead_score"], state_after["lead_score"])
        self.assertEqual(state_before["lead_probability"], state_after["lead_probability"])

    # 23. Legacy leads collection remains unchanged
    def test_23_legacy_leads_collection_remains_unchanged(self):
        count_before = self.leads.count_documents({})

        customer_id = ObjectId()
        self.profiles.insert_one({
            "_id": customer_id,
            "email": "legacy_check@example.com"
        })
        self.features.insert_one(sample_high_intent_features(customer_id))

        sync_customer_lead_state(customer_id, self.db)

        count_after = self.leads.count_documents({})
        self.assertEqual(count_before, count_after)


if __name__ == "__main__":
    unittest.main()
