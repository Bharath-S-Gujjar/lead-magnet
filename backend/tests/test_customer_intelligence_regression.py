"""Regression tests for Customer Intelligence fixes:
1. Journey timeline order deduplication
2. Unknown product price handling
3. Model explainability top driving factors
4. Retention churn risk level signal
"""

import unittest
from datetime import datetime, timezone
from bson import ObjectId

import app as app_module
from admin_intelligence_service import _build_journey_timeline, _resolve_cart
from model_explainability_service import explain_lead_score
from retention_service import compute_retention_signals
from tests.test_phase17a_intelligence import _make_sample_features


class TestCustomerIntelligenceRegression(unittest.TestCase):
    def setUp(self):
        self.db = app_module.db

    def tearDown(self):
        pass

    def test_journey_timeline_order_deduplication(self):
        """Verify that when both an order document and an order_placed event exist for the same order,
        the timeline only contains ONE canonical order entry and does not remove unrelated events."""
        customer_id = ObjectId()
        order_id = ObjectId()
        ts = datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone.utc)

        # 1. Real order in orders collection
        self.db["orders"].insert_one({
            "_id": order_id,
            "user_id": customer_id,
            "total_amount": 1499.0,
            "created_at": ts,
        })

        # 2. Duplicate order_placed event for the same order
        self.db["events"].insert_one({
            "_id": ObjectId(),
            "user_id": customer_id,
            "event_type": "order_placed",
            "page": "/orders",
            "timestamp": ts,
            "entity": {"type": "order", "id": str(order_id)},
            "metadata": {"total_amount": 1499.0},
        })

        # 3. Unrelated behavior event
        self.db["events"].insert_one({
            "_id": ObjectId(),
            "user_id": customer_id,
            "event_type": "page_view",
            "page": "/products",
            "timestamp": datetime(2026, 10, 1, 11, 55, 0, tzinfo=timezone.utc),
        })

        timeline = _build_journey_timeline(customer_id, self.db)

        # Count occurrences of order entries
        order_entries = [item for item in timeline if item.get("type") == "order"]
        event_orders = [item for item in timeline if item.get("event_type") in ("order", "order_placed", "purchase")]
        page_views = [item for item in timeline if item.get("event_type") == "page_view"]

        # Exactly 1 canonical order entry
        self.assertEqual(len(order_entries), 1)
        self.assertEqual(order_entries[0]["order_id"], str(order_id))
        self.assertEqual(order_entries[0]["total_amount"], 1499.0)

        # Zero duplicate order_placed events
        self.assertEqual(len(event_orders), 0)

        # Unrelated events preserved
        self.assertEqual(len(page_views), 1)
        self.assertEqual(page_views[0]["page"], "/products")

    def test_unknown_product_price_handling(self):
        """Verify that products without usable price have price=None and subtotal=None,
        never fabricated as 0."""
        customer_id = ObjectId()
        prod_id = ObjectId()

        # Product document has no price or price_inr
        self.db["products"].insert_one({
            "_id": prod_id,
            "name": "Boys Slim Fit Jeans",
            "brand": "H&M",
            "category": "Jeans",
            "price": None,
            "price_inr": None,
        })

        # Cart collection entry
        self.db["cart"].insert_one({
            "user_id": customer_id,
            "product_id": str(prod_id),
            "quantity": 2,
        })

        cart_items = _resolve_cart(customer_id, self.db)
        self.assertEqual(len(cart_items), 1)
        item = cart_items[0]

        self.assertIsNone(item["price"])
        self.assertIsNone(item["subtotal"])
        self.assertEqual(item["name"], "Boys Slim Fit Jeans")
        self.assertEqual(item["quantity"], 2)

    def test_explainability_top_driving_factors(self):
        """Verify that explain_lead_score returns top_driving_factors with all required fields."""
        features = _make_sample_features(
            ObjectId(),
            checkout_attempts=2,
            cart_value=2500.0,
            products_viewed=15,
            orders_count=3,
            total_order_value=5000.0,
        )

        explanation = explain_lead_score(features)
        self.assertIn("top_driving_factors", explanation)
        factors = explanation["top_driving_factors"]
        self.assertIsInstance(factors, list)
        self.assertGreater(len(factors), 0)

        first = factors[0]
        self.assertIn("feature", first)
        self.assertIn("value", first)
        self.assertIn("contribution", first)
        self.assertIn("direction", first)
        self.assertIn("weight", first)
        self.assertIn("label", first)
        self.assertIn(first["direction"], ("positive", "negative"))
        self.assertIsInstance(first["contribution"], (int, float))

    def test_retention_churn_risk_level(self):
        """Verify that compute_retention_signals returns churn_risk_level matching inactivity_risk."""
        customer_id = ObjectId()
        self.db["customer_features"].insert_one(_make_sample_features(
            customer_id,
            days_since_last_activity=35.0
        ))

        retention = compute_retention_signals(customer_id, self.db)
        self.assertEqual(retention["inactivity_risk"], "high")
        self.assertEqual(retention["churn_risk_level"], "High")

        # Test low risk
        low_cust_id = ObjectId()
        self.db["customer_features"].insert_one(_make_sample_features(
            low_cust_id,
            days_since_last_activity=2.0
        ))
        low_retention = compute_retention_signals(low_cust_id, self.db)
        self.assertEqual(low_retention["inactivity_risk"], "none")
        self.assertEqual(low_retention["churn_risk_level"], "Low")

    def test_analytics_endpoints_require_admin(self):
        """Unauthenticated requests to /api/analytics/summary and /top-events must return 401."""
        client = app_module.app.test_client()
        res1 = client.get("/api/analytics/summary")
        self.assertEqual(res1.status_code, 401)
        res2 = client.get("/api/analytics/top-events")
        self.assertEqual(res2.status_code, 401)

    def test_json_error_handlers(self):
        """404 and 405 error responses must return JSON instead of HTML error pages."""
        client = app_module.app.test_client()
        res_404 = client.get("/api/nonexistent-route-for-testing")
        self.assertEqual(res_404.status_code, 404)
        self.assertTrue(res_404.is_json)
        self.assertFalse(res_404.get_json()["success"])

        res_405 = client.post("/api/health")
        self.assertEqual(res_405.status_code, 405)
        self.assertTrue(res_405.is_json)
        self.assertFalse(res_405.get_json()["success"])


if __name__ == "__main__":
    unittest.main()
