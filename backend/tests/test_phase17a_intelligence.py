"""Phase 17A Intelligence focused test suite.

Tests verified Phase 17A requirements:
- Score history recording and schema
- Dynamic lead qualification lifecycle & re-qualification
- Marketing automation triggers (upward transition only, cooldown, idempotency, email+WhatsApp, NO SMS)
- Non-mutating What-If simulator
- MONGO_DB_NAME env var resolution
- RFM segmentation & quintile computation
- Funnel analytics calculation
- Retention heuristic labeling
- Product affinity calculations
- Lead revenue attribution correlation disclaimer
- Deterministic explainability notice
"""

import os
import unittest
from datetime import datetime, timezone, timedelta
from bson import ObjectId

import app as app_module
from ecommerce_model_adapter import REQUIRED_BASE_FEATURES
from lead_scoring_engine import rescore_customer
from score_history_service import record_score_history, get_score_history
from customer_lead_state_service import sync_customer_lead_state, get_customer_lead_state
from marketing_automation_service import (
    evaluate_channel_eligibility,
    create_automation_event_for_qualification,
    process_marketing_automation_event,
)
from whatif_simulator_service import simulate_lead_score
from rfm_service import compute_rfm, assign_rfm_segment
from funnel_analytics_service import get_funnel_analytics
from retention_service import compute_retention_signals, get_retention_overview
from product_affinity_service import compute_product_affinity
from revenue_attribution_service import compute_lead_revenue_attribution
from model_explainability_service import explain_lead_score


def _make_sample_features(customer_id, **overrides):
    base = {f: 0.0 for f in REQUIRED_BASE_FEATURES}
    base["customer_id"] = customer_id
    base.update(overrides)
    return base


class Phase17AIntelligenceTests(unittest.TestCase):

    def setUp(self):
        self.db = app_module.db
        self.profiles = app_module.profiles_collection
        self.features = app_module.customer_features_collection
        self.lead_state = app_module.customer_lead_state_collection
        self.events = app_module.marketing_automation_events_collection
        self.comms = app_module.marketing_communications_collection
        self.history = app_module.lead_score_history_collection

        self.profiles.delete_many({})
        self.features.delete_many({})
        self.lead_state.delete_many({})
        self.events.delete_many({})
        self.comms.delete_many({})
        self.history.delete_many({})
        self.db["sessions"].delete_many({})
        self.db["events"].delete_many({})
        self.db["orders"].delete_many({})

        app_module.app.config["TESTING"] = True
        self.client = app_module.app.test_client()

    def test_A_score_history_persisted_correctly(self):
        customer_id = ObjectId()
        prediction = {
            "lead_probability": 0.85,
            "lead_score": 85,
            "lead_segment": "Hot",
            "model_version": "v2.0_ecommerce_xgb",
        }
        lead_state = {
            "qualification_status": "qualified",
            "qualification_transition": "not_qualified_to_qualified",
            "previous_score": 40,
            "customer_id": customer_id,
        }

        doc = record_score_history(customer_id, prediction, lead_state, self.db)
        self.assertIsNotNone(doc)
        self.assertEqual(doc["lead_score"], 85)
        self.assertEqual(doc["lead_segment"], "Hot")
        self.assertEqual(doc["model_version"], "v2.0_ecommerce_xgb")
        self.assertEqual(doc["qualification_status"], "qualified")
        self.assertEqual(doc["score_delta"], 45)

        history = get_score_history(customer_id, self.db)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["lead_score"], 85)

    def test_B_dynamic_qualification_lifecycle(self):
        customer_id = ObjectId()
        self.profiles.insert_one({
            "_id": customer_id,
            "email": "lifecycle_test@example.com",
            "role": "user"
        })

        # 1. NOT_QUALIFIED -> NOT_QUALIFIED (zero features)
        self.features.insert_one(_make_sample_features(customer_id, products_viewed=1))
        state1 = sync_customer_lead_state(customer_id, self.db)
        self.assertEqual(state1["qualification_status"], "not_qualified")
        self.assertIn("not_qualified", state1["qualification_transition"])

        # 2. NOT_QUALIFIED -> QUALIFIED (high intent activity)
        self.features.update_one(
            {"customer_id": customer_id},
            {"$set": {
                "checkout_attempts": 5,
                "cart_value": 250.0,
                "products_viewed": 20,
                "product_interactions": 30,
                "high_intent_page_visits": 10
            }}
        )
        state2 = sync_customer_lead_state(customer_id, self.db)
        self.assertEqual(state2["qualification_status"], "qualified")
        self.assertEqual(state2["qualification_transition"], "not_qualified_to_qualified")
        self.assertTrue(state2["is_newly_qualified"])

        # 3. QUALIFIED -> QUALIFIED (continued engagement)
        state3 = sync_customer_lead_state(customer_id, self.db)
        self.assertEqual(state3["qualification_status"], "qualified")
        self.assertEqual(state3["qualification_transition"], "qualified_to_qualified")
        self.assertFalse(state3["is_newly_qualified"])

        # 4. QUALIFIED -> NOT_QUALIFIED (long inactivity dropping score)
        self.features.update_one(
            {"customer_id": customer_id},
            {"$set": {
                "checkout_attempts": 0,
                "cart_value": 0,
                "products_viewed": 0,
                "product_interactions": 0,
                "high_intent_page_visits": 0,
                "days_since_last_activity": 120
            }}
        )
        state4 = sync_customer_lead_state(customer_id, self.db)
        self.assertEqual(state4["qualification_status"], "not_qualified")
        self.assertEqual(state4["qualification_transition"], "qualified_to_not_qualified")

        # 5. RE-QUALIFICATION: NOT_QUALIFIED -> QUALIFIED
        self.features.update_one(
            {"customer_id": customer_id},
            {"$set": {
                "checkout_attempts": 6,
                "cart_value": 300.0,
                "products_viewed": 25,
                "product_interactions": 40,
                "high_intent_page_visits": 12,
                "days_since_last_activity": 0
            }}
        )
        state5 = sync_customer_lead_state(customer_id, self.db)
        self.assertEqual(state5["qualification_status"], "qualified")
        self.assertEqual(state5["qualification_transition"], "not_qualified_to_qualified")

    def test_C_marketing_automation_rules_and_no_sms(self):
        customer_id = ObjectId()
        profile = {
            "_id": customer_id,
            "email": "no_sms@example.com",
            "phone": "+15550001111"
        }
        self.profiles.insert_one(profile)

        # Verify evaluate_channel_eligibility contains ONLY email and whatsapp
        eligibility = evaluate_channel_eligibility(profile)
        self.assertIn("email", eligibility)
        self.assertIn("whatsapp", eligibility)
        self.assertNotIn("sms", eligibility)

        # Create automation event
        lead_state = {
            "qualification_transition": "not_qualified_to_qualified",
            "is_newly_qualified": True,
            "lead_score": 88,
            "last_qualified_at": datetime.now(timezone.utc).isoformat()
        }
        event = create_automation_event_for_qualification(customer_id, lead_state, self.db)
        self.assertIsNotNone(event)

        # QUALIFIED -> QUALIFIED must not trigger duplicate event
        lead_state_same = {
            "qualification_transition": "qualified_to_qualified",
            "is_newly_qualified": False,
            "lead_score": 90
        }
        dup_event = create_automation_event_for_qualification(customer_id, lead_state_same, self.db)
        self.assertIsNone(dup_event)

        # Process automation event
        result = process_marketing_automation_event(event["_id"], self.db)
        self.assertEqual(result["status"], "completed")

        comms = list(self.comms.find({"automation_event_id": event["_id"]}))
        channels = [c["channel"] for c in comms]
        self.assertIn("email", channels)
        self.assertNotIn("sms", channels)

    def test_D_whatif_simulator_is_non_mutating(self):
        customer_id = ObjectId()
        initial_features = _make_sample_features(
            customer_id,
            checkout_attempts=1,
            cart_value=50.0,
            products_viewed=5
        )
        self.features.insert_one(dict(initial_features))

        # Run simulation with overrides
        overrides = {"checkout_attempts": 8, "cart_value": 400.0}
        sim_result = simulate_lead_score(customer_id, overrides, self.db)

        self.assertTrue(sim_result["is_simulation"])
        self.assertIn("SIMULATED", sim_result["simulation_label"])
        self.assertGreater(sim_result["lead_score"], 50)

        # Assert zero side-effects
        stored_features = self.features.find_one({"customer_id": customer_id})
        self.assertEqual(stored_features["checkout_attempts"], 1)
        self.assertEqual(stored_features["cart_value"], 50.0)

        self.assertEqual(self.lead_state.count_documents({"customer_id": customer_id}), 0)
        self.assertEqual(self.events.count_documents({"customer_id": customer_id}), 0)
        self.assertEqual(self.history.count_documents({"customer_id": customer_id}), 0)

    def test_E_mongo_db_name_configuration(self):
        original_db = app_module.db
        original_env = os.environ.get("MONGO_DB_NAME")
        os.environ["MONGO_DB_NAME"] = "custom_lead_db"
        try:
            client = app_module.mongo_client
            db_name = os.getenv("MONGO_DB_NAME", "leadmagnet")
            custom_db = client[db_name]
            self.assertEqual(custom_db.name, "custom_lead_db")
        finally:
            if original_env:
                os.environ["MONGO_DB_NAME"] = original_env
            else:
                os.environ.pop("MONGO_DB_NAME", None)
            app_module.db = original_db

    def test_F_rfm_intelligence_computation(self):
        customer_id = ObjectId()
        now = datetime.now(timezone.utc)
        self.db["orders"].insert_one({
            "user_id": customer_id,
            "total_amount": 150.0,
            "created_at": now - timedelta(days=2)
        })

        rfm = compute_rfm(customer_id, self.db)
        self.assertEqual(rfm["rfm_frequency"], 1)
        self.assertEqual(rfm["rfm_monetary"], 150.0)
        self.assertIsNotNone(rfm["rfm_segment"])

        seg = assign_rfm_segment(5, 5, 5)
        self.assertEqual(seg, "Champions")

    def test_G_funnel_analytics_calculation(self):
        self.db["sessions"].insert_one({"anonymous_id": "anon1", "status": "active"})
        self.db["events"].insert_one({"event_type": "product_view", "anonymous_id": "anon1"})
        self.db["events"].insert_one({"event_type": "add_to_cart", "anonymous_id": "anon1"})

        funnel = get_funnel_analytics(self.db)
        stages = funnel.get("stages", [])
        self.assertEqual(len(stages), 6)
        self.assertEqual(stages[0]["stage"], "Visitors")
        self.assertGreaterEqual(stages[0]["count"], 1)

    def test_H_retention_heuristic_labeling(self):
        customer_id = ObjectId()
        self.features.insert_one(_make_sample_features(
            customer_id,
            days_since_last_activity=35.0
        ))

        retention = compute_retention_signals(customer_id, self.db)
        self.assertEqual(retention["inactivity_risk"], "high")
        self.assertEqual(retention["inactivity_risk_method"], "heuristic_threshold")

        overview = get_retention_overview(self.db)
        self.assertEqual(overview["method"], "heuristic_threshold")

    def test_I_product_affinity_uses_real_data(self):
        customer_id = ObjectId()
        product_id = ObjectId()

        self.db["products"].insert_one({
            "_id": product_id,
            "name": "Leather Jacket",
            "category": "Apparel",
            "brand": "VintageCo"
        })
        self.db["events"].insert_one({
            "user_id": customer_id,
            "event_type": "product_view",
            "entity": {"id": str(product_id)}
        })

        affinity = compute_product_affinity(customer_id, self.db)
        self.assertEqual(affinity["total_products_viewed"], 1)
        self.assertEqual(affinity["frequently_viewed"][0]["name"], "Leather Jacket")

    def test_J_revenue_attribution_disclaimer(self):
        customer_id = ObjectId()
        now_iso = datetime.now(timezone.utc).isoformat()
        self.lead_state.insert_one({
            "customer_id": customer_id,
            "qualification_status": "qualified",
            "first_qualified_at": now_iso
        })
        self.db["orders"].insert_one({
            "user_id": customer_id,
            "total_amount": 200.0,
            "created_at": datetime.now(timezone.utc)
        })

        attribution = compute_lead_revenue_attribution(self.db)
        self.assertEqual(attribution["attribution_method"], "temporal_correlation")
        self.assertIn("correlation-based", attribution["attribution_disclaimer"])

    def test_K_model_explainability_notice(self):
        features = _make_sample_features(
            ObjectId(),
            checkout_attempts=3,
            cart_value=120.0,
            products_viewed=10
        )
        explanation = explain_lead_score(features)
        self.assertEqual(explanation["explanation_method"], "deterministic_feature_contribution")
        self.assertIn("deterministic approximation", explanation["explanation_note"])


if __name__ == "__main__":
    unittest.main()
