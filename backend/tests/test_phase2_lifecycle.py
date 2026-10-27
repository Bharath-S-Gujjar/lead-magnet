"""Phase 2 — Lifecycle & Converted Customer Retention Tests

Verifies:
  1. lifecycle_status is correctly assigned (prospect/converted/repeat_customer)
  2. Converted customers are not_qualified for new-lead pipeline
  3. Converted customers retain Warm/Hot segment via score (floors do NOT apply)
  4. Price-drop pipeline accepts Warm/Hot-to-Warm converted customers
  5. Opportunity engine accepts Hot converted customers (score-based Hot)
  6. Minimum-segment floors do NOT apply to converted customers
  7. Repeat buyer keeps lifecycle_status='repeat_customer'
"""

import os
import sys
import unittest
from datetime import datetime, timezone, timedelta
from bson import ObjectId

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module
from customer_lead_state_service import (
    ensure_customer_lead_state_indexes,
    sync_customer_lead_state,
)
from customer_feature_service import ensure_customer_features_indexes
from behavioral_scoring_service import compute_behavioral_score


def _hours_ago(h):
    return (datetime.now(timezone.utc) - timedelta(hours=h)).isoformat()


def _base_features(customer_id, **overrides):
    doc = {
        "customer_id": customer_id,
        "sessions_count": 1,
        "total_events": 2,
        "total_time_spent": 0.0,
        "average_session_duration": 0.0,
        "page_views_count": 1,
        "days_since_last_activity": 0.0,
        "products_viewed": 0,
        "unique_products_viewed": 0,
        "product_interactions": 0,
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
        "last_checkout_action_at": None,
        "last_cart_action_at": None,
    }
    doc.update(overrides)
    return doc


def _hot_no_order(customer_id):
    """High-intent unconverted customer who should score Hot."""
    return _base_features(
        customer_id,
        sessions_count=10, total_time_spent=1500.0,
        unique_products_viewed=10, products_viewed=15,
        search_count=5, days_since_last_activity=0.2,
        cart_item_count=5, cart_value=999.0, wishlist_item_count=3,
        checkout_attempts=5, orders_count=0, total_order_value=0.0,
        form_submit_count=2, product_interactions=20,
        high_intent_page_visits=3,
        last_checkout_action_at=_hours_ago(3),
        last_cart_action_at=_hours_ago(4),
    )


def _converted_high_engagement(customer_id):
    """Converted customer (1 order) with enough activity to score Warm organically."""
    return _base_features(
        customer_id,
        sessions_count=6, total_time_spent=900.0,
        unique_products_viewed=5, products_viewed=8,
        search_count=3, days_since_last_activity=1.0,
        cart_item_count=2, cart_value=300.0, wishlist_item_count=2,
        checkout_attempts=2, orders_count=1, total_order_value=450.0,
        average_order_value=450.0,
        form_submit_count=1, product_interactions=10,
        high_intent_page_visits=2,
        last_checkout_action_at=None, last_cart_action_at=None,
    )


def _repeat_buyer(customer_id):
    """Repeat buyer (2 orders)."""
    return _base_features(
        customer_id,
        sessions_count=8, total_time_spent=1200.0,
        unique_products_viewed=8, products_viewed=12,
        search_count=4, days_since_last_activity=2.0,
        cart_item_count=3, cart_value=500.0,
        checkout_attempts=3, orders_count=2, total_order_value=900.0,
        average_order_value=450.0,
        last_checkout_action_at=None, last_cart_action_at=None,
    )


class Phase2LifecycleTests(unittest.TestCase):
    """Phase 2: Lifecycle status + converted customer retention path."""

    def setUp(self):
        self.db = app_module.db
        self.features = app_module.customer_features_collection
        self.lead_state = app_module.customer_lead_state_collection
        ensure_customer_features_indexes(self.features)
        ensure_customer_lead_state_indexes(self.lead_state)

    def tearDown(self):
        # Clean up test documents by removing inserted test customer IDs
        if hasattr(self, "_test_ids"):
            for cid in self._test_ids:
                self.features.delete_many({"customer_id": cid})
                self.lead_state.delete_many({"customer_id": cid})
        self._test_ids = []

    def _insert(self, doc):
        cid = doc["customer_id"]
        if not hasattr(self, "_test_ids"):
            self._test_ids = []
        self._test_ids.append(cid)
        self.features.delete_many({"customer_id": cid})
        self.lead_state.delete_many({"customer_id": cid})
        self.features.insert_one(doc)
        return cid

    # -----------------------------------------------------------------------
    # 01. Prospect (no orders) -> lifecycle_status = 'prospect'
    # -----------------------------------------------------------------------
    def test_01_prospect_lifecycle_status(self):
        cid = self._insert(_hot_no_order(ObjectId()))
        state = sync_customer_lead_state(cid, self.db)
        self.assertEqual(state["lifecycle_status"], "prospect")
        self.assertFalse(state["is_converted"])

    # -----------------------------------------------------------------------
    # 02. First-time buyer -> lifecycle_status = 'converted'
    # -----------------------------------------------------------------------
    def test_02_converted_lifecycle_status(self):
        cid = self._insert(_converted_high_engagement(ObjectId()))
        state = sync_customer_lead_state(cid, self.db)
        self.assertEqual(state["lifecycle_status"], "converted")
        self.assertTrue(state["is_converted"])

    # -----------------------------------------------------------------------
    # 03. Repeat buyer -> lifecycle_status = 'repeat_customer'
    # -----------------------------------------------------------------------
    def test_03_repeat_buyer_lifecycle_status(self):
        cid = self._insert(_repeat_buyer(ObjectId()))
        state = sync_customer_lead_state(cid, self.db)
        self.assertEqual(state["lifecycle_status"], "repeat_customer")
        self.assertTrue(state["is_converted"])

    # -----------------------------------------------------------------------
    # 04. Converted customer with active shopping intent IS qualified
    # -----------------------------------------------------------------------
    def test_04_converted_with_active_intent_is_qualified(self):
        cid = self._insert(_converted_high_engagement(ObjectId()))
        state = sync_customer_lead_state(cid, self.db)
        self.assertEqual(state["qualification_status"], "qualified",
            msg="Converted customers with score >= 70, active cart, and recent checkout now qualify as leads")

    # -----------------------------------------------------------------------
    # 05. Unconverted Hot customer IS qualified
    # -----------------------------------------------------------------------
    def test_05_prospect_hot_is_qualified(self):
        cid = self._insert(_hot_no_order(ObjectId()))
        state = sync_customer_lead_state(cid, self.db)
        self.assertEqual(state["lead_segment"], "Hot",
            msg=f"Expected Hot, got {state['lead_segment']} (score={state['lead_score']})")
        self.assertEqual(state["qualification_status"], "qualified")

    # -----------------------------------------------------------------------
    # 06. Cart-72h floor does NOT apply to converted customers (is_converted guard)
    # -----------------------------------------------------------------------
    def test_06_cart_floor_blocked_for_converted(self):
        """A converted customer with a fresh cart in their session should NOT have
        the cart-72h floor applied. Segment is purely score-based."""
        score_result = compute_behavioral_score({
            "sessions_count": 2,
            "cart_item_count": 2,
            "cart_value": 200.0,
            "orders_count": 1,          # converted
            "total_order_value": 200.0,
            "days_since_last_activity": 0.5,
            "last_cart_action_at": _hours_ago(5),
            "checkout_attempts": 0,
            "products_viewed": 0,
            "unique_products_viewed": 0,
            "search_count": 0,
            "wishlist_item_count": 0,
            "total_time_spent": 0,
            "form_submit_count": 0,
            "product_interactions": 0,
            "high_intent_page_visits": 0,
            "last_checkout_action_at": None,
        })
        self.assertTrue(score_result["is_converted"])
        # Segment must NOT have been promoted by a floor rule
        self.assertFalse(
            score_result.get("segment_reason", "").startswith("FLOOR"),
            msg=f"Floor rule must not apply to converted customer; "
                f"segment_reason={score_result.get('segment_reason')!r}",
        )

    # -----------------------------------------------------------------------
    # 07. Converted customer lifecycle transition: prospect -> converted
    # -----------------------------------------------------------------------
    def test_07_lifecycle_transition_prospect_to_converted(self):
        cid = ObjectId()
        if not hasattr(self, "_test_ids"):
            self._test_ids = []
        self._test_ids.append(cid)

        # First sync: no orders
        self.features.insert_one(_hot_no_order(cid))
        state1 = sync_customer_lead_state(cid, self.db)
        self.assertEqual(state1["lifecycle_status"], "prospect")

        # Simulate purchase (order completed, cart cleared)
        self.features.update_one(
            {"customer_id": cid},
            {"$set": {
                "orders_count": 1,
                "total_order_value": 500.0,
                "average_order_value": 500.0,
                "cart_item_count": 0,
                "cart_value": 0.0,
            }},
        )
        state2 = sync_customer_lead_state(cid, self.db)
        self.assertEqual(state2["lifecycle_status"], "converted")
        self.assertTrue(state2["is_converted"])
        # After purchase: cart is empty, so not qualified
        self.assertEqual(state2["qualification_status"], "not_qualified")

    # -----------------------------------------------------------------------
    # 08. lifecycle_status is persisted in lead state document
    # -----------------------------------------------------------------------
    def test_08_lifecycle_status_persisted_in_state(self):
        cid = self._insert(_repeat_buyer(ObjectId()))
        sync_customer_lead_state(cid, self.db)
        stored = self.lead_state.find_one({"customer_id": cid})
        self.assertIsNotNone(stored)
        self.assertIn("lifecycle_status", stored,
            msg="lifecycle_status must be persisted in customer_lead_state document")
        self.assertEqual(stored["lifecycle_status"], "repeat_customer")

    # -----------------------------------------------------------------------
    # 09. Converted customer with score-based Hot stays Hot and qualifies if active
    # -----------------------------------------------------------------------
    def test_09_converted_can_score_hot_organically(self):
        """A repeat buyer with very high activity can still score Hot organically
        (score >= 70). With unconverted restriction removed, active shopping qualifies them."""
        cid = ObjectId()
        if not hasattr(self, "_test_ids"):
            self._test_ids = []
        self._test_ids.append(cid)

        # Repeat buyer with maxed activity
        self.features.insert_one(_base_features(
            cid,
            sessions_count=12, total_time_spent=1800.0,
            unique_products_viewed=12, products_viewed=18,
            search_count=6, days_since_last_activity=0.2,
            cart_item_count=5, cart_value=1200.0, wishlist_item_count=4,
            checkout_attempts=6, orders_count=2, total_order_value=1800.0,
            average_order_value=900.0,
            form_submit_count=3, product_interactions=30,
            high_intent_page_visits=4,
            last_checkout_action_at=_hours_ago(2),
            last_cart_action_at=_hours_ago(3),
        ))
        self._test_ids.append(cid)
        state = sync_customer_lead_state(cid, self.db)

        # Must be Hot by score (not by floor), and qualified (since active cart & recent checkout)
        self.assertEqual(state["lead_segment"], "Hot",
            msg=f"Expected Hot (score-based), got {state['lead_segment']} (score={state['lead_score']})")
        self.assertTrue(state["is_converted"])
        self.assertEqual(state["qualification_status"], "qualified",
            msg="Active repeat buyer with score >= 70, cart, and recent checkout qualifies as lead")


class Phase2PipelineGatingTests(unittest.TestCase):
    """Phase 2 pipeline gating: verify price-drop and opportunity engine behaviour
    for converted customers.

    Key finding (audit): Both pipelines gate on segment/score, NOT on
    qualification_status. This means:
      - A converted customer with Warm segment IS eligible for price-drop
        notifications on wishlist/cart items.
      - A converted customer with Hot segment IS eligible for ALL opportunity
        types (cart discount, wishlist discount, similar items).
      - qualification_status only gates the new-lead marketing automation flow
        (qualification email/whatsapp). It does NOT gate price-drop or opportunities.
    This test codifies that finding so that future changes don't accidentally
    gate price-drop on qualification_status.
    """

    def test_01_price_drop_eligibility_gates_on_segment_not_qualification(self):
        from price_drop_opportunity_service import evaluate_customer_lead_state_eligibility as check_lead_state_eligibility

        # Simulate a converted Warm customer state (not_qualified but Warm segment)
        converted_warm_state = {
            "lead_segment": "Warm",
            "lead_probability": 0.50,
            "lead_score": 50,
            "qualification_status": "not_qualified",
            "is_converted": True,
            "lifecycle_status": "converted",
            "previous_segment": None,
            "previous_probability": None,
            "previous_score": None,
        }
        eligible, reason, _ = check_lead_state_eligibility(
            customer_id="fake_id",
            db=None,
            lead_state_doc=converted_warm_state,
        )
        self.assertTrue(eligible,
            msg=f"Converted Warm customer must be eligible for price-drop. reason={reason}")
        self.assertEqual(reason, "Warm",
            msg=f"Expected reason='Warm', got {reason!r}")

    def test_02_price_drop_hot_converted_customer_eligible(self):
        from price_drop_opportunity_service import evaluate_customer_lead_state_eligibility as check_lead_state_eligibility

        converted_hot_state = {
            "lead_segment": "Hot",
            "lead_probability": 0.75,
            "lead_score": 75,
            "qualification_status": "not_qualified",
            "is_converted": True,
            "lifecycle_status": "repeat_customer",
            "previous_segment": None,
            "previous_probability": None,
            "previous_score": None,
        }
        eligible, reason, _ = check_lead_state_eligibility(
            customer_id="fake_id",
            db=None,
            lead_state_doc=converted_hot_state,
        )
        self.assertTrue(eligible,
            msg=f"Converted Hot customer must be eligible for price-drop. reason={reason}")
        self.assertEqual(reason, "Hot")

    def test_03_price_drop_cold_converted_customer_not_eligible(self):
        from price_drop_opportunity_service import evaluate_customer_lead_state_eligibility as check_lead_state_eligibility

        cold_converted_state = {
            "lead_segment": "Cold",
            "lead_probability": 0.10,
            "lead_score": 10,
            "qualification_status": "not_qualified",
            "is_converted": True,
            "lifecycle_status": "converted",
            "previous_segment": None,
            "previous_probability": None,
            "previous_score": None,
        }
        eligible, reason, _ = check_lead_state_eligibility(
            customer_id="fake_id",
            db=None,
            lead_state_doc=cold_converted_state,
        )
        self.assertFalse(eligible,
            msg=f"Cold converted customer must NOT be eligible for price-drop. reason={reason}")

    # -----------------------------------------------------------------------
    # 04. Provisional & confidence flags: login-only => Cold + provisional
    # -----------------------------------------------------------------------
    def test_04_login_only_is_provisional(self):
        result = compute_behavioral_score({
            "sessions_count": 1,
            "total_events": 2,
            "days_since_last_activity": 0.0,
            "cart_item_count": 0,
            "checkout_attempts": 0,
            "wishlist_item_count": 0,
            "orders_count": 0,
            "search_count": 0,
            "unique_products_viewed": 0,
            "products_viewed": 0,
            "time_spent": 0.0,
        })
        self.assertEqual(result["lead_segment"], "Cold")
        self.assertTrue(result["is_provisional"])
        self.assertEqual(result["confidence"], "low")

    def test_05_meaningful_activity_clears_provisional(self):
        result = compute_behavioral_score({
            "sessions_count": 2,
            "total_events": 10,
            "days_since_last_activity": 0.2,
            "cart_item_count": 1,
            "cart_value": 150.0,
            "checkout_attempts": 0,
            "wishlist_item_count": 0,
            "orders_count": 0,
            "search_count": 1,
            "unique_products_viewed": 2,
            "products_viewed": 3,
            "time_spent": 200.0,
        })
        self.assertFalse(result["is_provisional"])
        self.assertEqual(result["confidence"], "high")

    def test_06_admin_intelligence_surfaces_lifecycle_and_confidence(self):
        from admin_intelligence_service import get_qualified_leads_list, get_lead_distribution

        db = app_module.db
        lead_state = app_module.customer_lead_state_collection

        cid = ObjectId()
        lead_state.insert_one({
            "customer_id": cid,
            "lead_score": 75,
            "lead_probability": 0.75,
            "lead_segment": "Hot",
            "qualification_status": "qualified",
            "lifecycle_status": "prospect",
            "confidence": "high",
            "is_provisional": False,
            "first_qualified_at": datetime.now(timezone.utc).isoformat(),
            "last_scored_at": datetime.now(timezone.utc).isoformat(),
        })
        try:
            res = get_qualified_leads_list(db, qualification_status="qualified", limit=10)
            items = [it for it in res["items"] if it["customer_id"] == str(cid)]
            self.assertTrue(len(items) > 0)
            self.assertEqual(items[0]["lifecycle_status"], "prospect")
            self.assertEqual(items[0]["confidence"], "high")
            self.assertFalse(items[0]["is_provisional"])

            dist = get_lead_distribution(db)
            self.assertIn("lifecycle", dist)
            self.assertIn("prospect", dist["lifecycle"])
        finally:
            lead_state.delete_many({"customer_id": cid})


if __name__ == "__main__":
    unittest.main(verbosity=2)
