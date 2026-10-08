"""Unit tests for Step 3: Price-drop opportunity detection and customer matching.

Covers all 16 required test scenarios:
  1. Warm customer + cart product price drop -> opportunity created
  2. Warm customer + wishlist product price drop -> opportunity created
  3. Hot customer + cart product price drop -> opportunity created
  4. Hot customer + wishlist product price drop -> opportunity created
  5. Previously Hot but currently Warm + cart price drop -> opportunity created
  6. Cold customer + price drop -> no opportunity
  7. Product not in current cart/wishlist -> no opportunity
  8. Historical cart presence only -> no opportunity
  9. Same price -> no opportunity
  10. Same price-drop event repeated -> no duplicate
  11. Later different price drop -> new opportunity
  12. Image URL is preserved
  13. Product URL is preserved
  14. Correct old/new prices are preserved
  15. Existing opportunity cooldown is respected
  16. No ReefAPI calls are made by these tests

All tests use in-memory/mock data with zero network and zero ReefAPI credits.
"""

import copy
import datetime
import unittest
from unittest.mock import patch
from bson import ObjectId

from opportunity_engine import (
    OPP_PRODUCT_PRICE_DROP,
    OPPORTUNITY_COOLDOWN_HOURS,
    build_opportunity_email_content,
)
from price_drop_opportunity_service import (
    evaluate_customer_lead_state_eligibility,
    find_customers_with_product_in_cart_or_wishlist,
    process_price_drop_event,
)


class MockCollection:
    """In-memory collection mock for MongoDB collections."""

    def __init__(self, name="col"):
        self.name = name
        self.docs = []
        self.indexes = {}

    def create_index(self, keys, name=None, unique=False, **kwargs):
        idx_name = name or "_".join(f"{k}_{d}" for k, d in keys)
        self.indexes[idx_name] = {"keys": keys, "unique": unique, "name": idx_name}
        return idx_name

    def list_indexes(self):
        return [{"name": name, **meta} for name, meta in self.indexes.items()]

    def insert_one(self, doc):
        d = copy.deepcopy(doc)
        if "_id" not in d:
            d["_id"] = ObjectId()
        self.docs.append(d)
        return d

    def find_one(self, query=None, sort=None):
        matches = self.find(query, sort=sort)
        return matches[0] if matches else None

    def find(self, query=None, sort=None):
        if not query:
            res = [copy.deepcopy(d) for d in self.docs]
        else:
            res = []
            for d in self.docs:
                if self._matches(d, query):
                    res.append(copy.deepcopy(d))

        if sort:
            for field, direction in reversed(sort):
                res.sort(key=lambda x: x.get(field, ""), reverse=(direction == -1))
        return res

    def _matches(self, doc, query):
        for k, v in query.items():
            if k == "$or":
                if not any(self._matches(doc, cond) for cond in v):
                    return False
            elif isinstance(v, dict):
                for op, val in v.items():
                    if op == "$in" and doc.get(k) not in val:
                        return False
            elif doc.get(k) != v:
                return False
        return True

    def update_one(self, query, update, upsert=False):
        set_data = update.get("$set", {})
        set_on_insert = update.get("$setOnInsert", {})

        for d in self.docs:
            if self._matches(d, query):
                d.update(copy.deepcopy(set_data))
                return True

        if upsert:
            new_doc = copy.deepcopy(query)
            new_doc.update(copy.deepcopy(set_on_insert))
            new_doc.update(copy.deepcopy(set_data))
            if "_id" not in new_doc:
                new_doc["_id"] = ObjectId()
            self.docs.append(new_doc)
            return True
        return False

    def count_documents(self, query=None):
        return len(self.find(query))

    def delete_many(self, query=None):
        if not query:
            self.docs = []
        else:
            self.docs = [d for d in self.docs if not self._matches(d, query)]


class MockDatabase:
    """Mock database providing dict-style collection access."""

    def __init__(self):
        self.collections = {
            "cart": MockCollection("cart"),
            "wishlist": MockCollection("wishlist"),
            "events": MockCollection("events"),
            "customer_lead_state": MockCollection("customer_lead_state"),
            "marketing_opportunities": MockCollection("marketing_opportunities"),
            "marketing_communications": MockCollection("marketing_communications"),
            "user_profiles": MockCollection("user_profiles"),
        }

    def __contains__(self, name):
        return True

    def __getitem__(self, name):
        if name not in self.collections:
            self.collections[name] = MockCollection(name)
        return self.collections[name]


class TestPriceDropOpportunities(unittest.TestCase):
    """Test suite for price drop opportunities and customer interest matching."""

    def setUp(self):
        self.db = MockDatabase()
        self.product_id = "myntra_28420390"
        self.source_product_id = "28420390"
        self.product_title = "Roadster Men Casual Shirt"
        self.product_url = "https://www.myntra.com/shirts/roadster/28420390/buy"
        self.primary_image = "https://assets.myntassets.com/img1.jpg"

        self.price_drop_event = {
            "product_id": self.product_id,
            "source_product_id": self.source_product_id,
            "title": self.product_title,
            "brand": "Roadster",
            "old_price": 1000.0,
            "new_price": 799.0,
            "primary_image": self.primary_image,
            "url": self.product_url,
            "change_type": "drop",
        }

    # 1. Warm customer + cart product price drop -> opportunity created
    def test_warm_customer_cart_product_price_drop_creates_opportunity(self):
        cid = ObjectId()
        self.db["customer_lead_state"].insert_one({
            "customer_id": cid,
            "lead_segment": "Warm",
            "lead_score": 50,
            "lead_probability": 0.50,
        })
        self.db["cart"].insert_one({
            "user_id": cid,
            "product_id": self.product_id,
            "quantity": 1,
        })

        res = process_price_drop_event(self.price_drop_event, db=self.db, enforce_cooldown=False)
        self.assertEqual(res["opportunities_created"], 1)
        self.assertEqual(len(res["opportunities"]), 1)

        opp = res["opportunities"][0]
        self.assertEqual(opp["opportunity_type"], OPP_PRODUCT_PRICE_DROP)
        self.assertEqual(opp["product_id"], self.product_id)
        self.assertEqual(opp["metadata"]["old_price"], 1000.0)
        self.assertEqual(opp["metadata"]["new_price"], 799.0)
        self.assertEqual(opp["metadata"]["interest_source"], "cart")
        self.assertEqual(opp["metadata"]["customer_lead_state"], "Warm")

    # 2. Warm customer + wishlist product price drop -> opportunity created
    def test_warm_customer_wishlist_product_price_drop_creates_opportunity(self):
        cid = ObjectId()
        self.db["customer_lead_state"].insert_one({
            "customer_id": cid,
            "lead_segment": "Warm",
            "lead_score": 45,
            "lead_probability": 0.45,
        })
        self.db["wishlist"].insert_one({
            "user_id": cid,
            "product_id": self.source_product_id,
        })

        res = process_price_drop_event(self.price_drop_event, db=self.db, enforce_cooldown=False)
        self.assertEqual(res["opportunities_created"], 1)
        opp = res["opportunities"][0]
        self.assertEqual(opp["metadata"]["interest_source"], "wishlist")

    # 3. Hot customer + cart product price drop -> opportunity created
    def test_hot_customer_cart_product_price_drop_creates_opportunity(self):
        cid = ObjectId()
        self.db["customer_lead_state"].insert_one({
            "customer_id": cid,
            "lead_segment": "Hot",
            "lead_score": 85,
            "lead_probability": 0.85,
        })
        self.db["cart"].insert_one({
            "user_id": cid,
            "product_id": self.product_id,
        })

        res = process_price_drop_event(self.price_drop_event, db=self.db, enforce_cooldown=False)
        self.assertEqual(res["opportunities_created"], 1)
        opp = res["opportunities"][0]
        self.assertEqual(opp["metadata"]["customer_lead_state"], "Hot")

    # 4. Hot customer + wishlist product price drop -> opportunity created
    def test_hot_customer_wishlist_product_price_drop_creates_opportunity(self):
        cid = ObjectId()
        self.db["customer_lead_state"].insert_one({
            "customer_id": cid,
            "lead_segment": "Hot",
            "lead_score": 75,
            "lead_probability": 0.75,
        })
        self.db["wishlist"].insert_one({
            "user_id": cid,
            "product_id": self.product_id,
        })

        res = process_price_drop_event(self.price_drop_event, db=self.db, enforce_cooldown=False)
        self.assertEqual(res["opportunities_created"], 1)

    # 5. Previously Hot but currently Warm + cart price drop -> opportunity created
    def test_previously_hot_currently_warm_cart_price_drop_creates_opportunity(self):
        cid = ObjectId()
        self.db["customer_lead_state"].insert_one({
            "customer_id": cid,
            "lead_segment": "Warm",
            "previous_segment": "Hot",
            "lead_score": 55,
            "previous_score": 78,
            "lead_probability": 0.55,
            "previous_probability": 0.78,
        })
        self.db["cart"].insert_one({
            "user_id": cid,
            "product_id": self.product_id,
        })

        res = process_price_drop_event(self.price_drop_event, db=self.db, enforce_cooldown=False)
        self.assertEqual(res["opportunities_created"], 1)
        opp = res["opportunities"][0]
        self.assertEqual(opp["metadata"]["customer_lead_state"], "Hot_to_Warm")

    # 6. Cold customer + price drop -> no opportunity
    def test_cold_customer_price_drop_creates_no_opportunity(self):
        cid = ObjectId()
        self.db["customer_lead_state"].insert_one({
            "customer_id": cid,
            "lead_segment": "Cold",
            "lead_score": 20,
            "lead_probability": 0.20,
        })
        self.db["cart"].insert_one({
            "user_id": cid,
            "product_id": self.product_id,
        })

        res = process_price_drop_event(self.price_drop_event, db=self.db, enforce_cooldown=False)
        self.assertEqual(res["opportunities_created"], 0)
        self.assertEqual(len(res["opportunities"]), 0)
        self.assertEqual(self.db["marketing_opportunities"].count_documents(), 0)

    # 7. Product not in current cart/wishlist -> no opportunity
    def test_product_not_in_current_cart_or_wishlist_creates_no_opportunity(self):
        cid = ObjectId()
        self.db["customer_lead_state"].insert_one({
            "customer_id": cid,
            "lead_segment": "Hot",
            "lead_score": 80,
            "lead_probability": 0.80,
        })
        # Customer cart has a completely different product
        self.db["cart"].insert_one({
            "user_id": cid,
            "product_id": "other_product_9999",
        })

        res = process_price_drop_event(self.price_drop_event, db=self.db, enforce_cooldown=False)
        self.assertEqual(res["opportunities_created"], 0)

    # 8. Historical cart presence only -> no opportunity
    def test_historical_cart_presence_only_creates_no_opportunity(self):
        cid = ObjectId()
        self.db["customer_lead_state"].insert_one({
            "customer_id": cid,
            "lead_segment": "Warm",
            "lead_score": 60,
            "lead_probability": 0.60,
        })
        # Historical event exists in 'events' collection
        self.db["events"].insert_one({
            "user_id": cid,
            "type": "add_to_cart",
            "product_id": self.product_id,
            "timestamp": "2026-10-01T10:00:00Z",
        })
        # But CURRENT 'cart' and 'wishlist' are empty!

        res = process_price_drop_event(self.price_drop_event, db=self.db, enforce_cooldown=False)
        self.assertEqual(res["opportunities_created"], 0)

    # 9. Same price -> no opportunity
    def test_same_price_creates_no_opportunity(self):
        cid = ObjectId()
        self.db["customer_lead_state"].insert_one({
            "customer_id": cid,
            "lead_segment": "Hot",
            "lead_score": 85,
        })
        self.db["cart"].insert_one({
            "user_id": cid,
            "product_id": self.product_id,
        })

        same_price_event = dict(self.price_drop_event)
        same_price_event["old_price"] = 799.0
        same_price_event["new_price"] = 799.0

        res = process_price_drop_event(same_price_event, db=self.db, enforce_cooldown=False)
        self.assertEqual(res["opportunities_created"], 0)
        self.assertFalse(res["valid_price_drop"])

    # 10. Same price-drop event repeated -> no duplicate
    def test_same_price_drop_event_repeated_creates_no_duplicates(self):
        cid = ObjectId()
        self.db["customer_lead_state"].insert_one({
            "customer_id": cid,
            "lead_segment": "Warm",
            "lead_score": 50,
        })
        self.db["cart"].insert_one({
            "user_id": cid,
            "product_id": self.product_id,
        })

        # Process twice
        res1 = process_price_drop_event(self.price_drop_event, db=self.db, enforce_cooldown=False)
        res2 = process_price_drop_event(self.price_drop_event, db=self.db, enforce_cooldown=False)

        # Count in marketing_opportunities collection is strictly 1
        count = self.db["marketing_opportunities"].count_documents()
        self.assertEqual(count, 1)

    # 11. Later different price drop -> new opportunity
    def test_later_different_price_drop_creates_new_opportunity(self):
        cid = ObjectId()
        self.db["customer_lead_state"].insert_one({
            "customer_id": cid,
            "lead_segment": "Warm",
            "lead_score": 50,
        })
        self.db["cart"].insert_one({
            "user_id": cid,
            "product_id": self.product_id,
        })

        # Drop 1: 1000 -> 800
        event1 = dict(self.price_drop_event, old_price=1000.0, new_price=800.0)
        process_price_drop_event(event1, db=self.db, enforce_cooldown=False)

        # Drop 2: 800 -> 650
        event2 = dict(self.price_drop_event, old_price=800.0, new_price=650.0)
        process_price_drop_event(event2, db=self.db, enforce_cooldown=False)

        # Both opportunities exist distinctly
        count = self.db["marketing_opportunities"].count_documents()
        self.assertEqual(count, 2)

    # 12. Image URL is preserved
    def test_image_url_is_preserved_in_opportunity(self):
        cid = ObjectId()
        self.db["customer_lead_state"].insert_one({
            "customer_id": cid,
            "lead_segment": "Warm",
            "lead_score": 50,
        })
        self.db["cart"].insert_one({"user_id": cid, "product_id": self.product_id})

        res = process_price_drop_event(self.price_drop_event, db=self.db, enforce_cooldown=False)
        opp = res["opportunities"][0]
        self.assertEqual(opp["metadata"]["primary_image"], self.primary_image)

    # 13. Product URL is preserved
    def test_product_url_is_preserved_in_opportunity(self):
        cid = ObjectId()
        self.db["customer_lead_state"].insert_one({
            "customer_id": cid,
            "lead_segment": "Hot",
            "lead_score": 80,
        })
        self.db["cart"].insert_one({"user_id": cid, "product_id": self.product_id})

        res = process_price_drop_event(self.price_drop_event, db=self.db, enforce_cooldown=False)
        opp = res["opportunities"][0]
        self.assertEqual(opp["metadata"]["product_url"], self.product_url)
        self.assertEqual(opp["metadata"]["url"], self.product_url)

    # 14. Correct old/new prices are preserved
    def test_correct_old_new_prices_and_discounts_preserved(self):
        cid = ObjectId()
        self.db["customer_lead_state"].insert_one({
            "customer_id": cid,
            "lead_segment": "Warm",
            "lead_score": 50,
        })
        self.db["cart"].insert_one({"user_id": cid, "product_id": self.product_id})

        event = dict(self.price_drop_event, old_price=500.0, new_price=300.0)
        res = process_price_drop_event(event, db=self.db, enforce_cooldown=False)
        opp = res["opportunities"][0]

        self.assertEqual(opp["metadata"]["old_price"], 500.0)
        self.assertEqual(opp["metadata"]["new_price"], 300.0)
        self.assertEqual(opp["metadata"]["discount_amount"], 200.0)
        self.assertEqual(opp["metadata"]["discount_percentage"], 40)

    # 15. Existing opportunity cooldown is respected
    def test_opportunity_cooldown_is_respected(self):
        cid = ObjectId()
        self.db["customer_lead_state"].insert_one({
            "customer_id": cid,
            "lead_segment": "Hot",
            "lead_score": 90,
        })
        self.db["cart"].insert_one({"user_id": cid, "product_id": self.product_id})

        # Simulate recent email sent within cooldown period
        recent_sent = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=2)
        self.db["marketing_communications"].insert_one({
            "customer_id": cid,
            "channel": "email",
            "status": "sent",
            "sent_at": recent_sent.isoformat(),
        })

        # Process with cooldown enforcement
        res = process_price_drop_event(self.price_drop_event, db=self.db, enforce_cooldown=True)
        # Should record that customer is within cooldown
        self.assertTrue(any("cooldown" in str(s).lower() for s in res["skipped_reasons"]))
        if res["opportunities"]:
            self.assertTrue(res["opportunities"][0].get("cooldown_suppressed"))

    # 16. No ReefAPI calls are made by these tests (Unit tests execute 100% offline)
    def test_no_reefapi_calls_made(self):
        """Confirms that price drop processing does not interact with ReefAPI."""
        with patch("reef_api_client.requests.post") as mock_post:
            cid = ObjectId()
            self.db["customer_lead_state"].insert_one({
                "customer_id": cid,
                "lead_segment": "Warm",
                "lead_score": 50,
            })
            self.db["cart"].insert_one({"user_id": cid, "product_id": self.product_id})

            process_price_drop_event(self.price_drop_event, db=self.db, enforce_cooldown=False)
            mock_post.assert_not_called()

    def test_email_template_content_customer_facing(self):
        """Validates that email template content does not expose ML scores or internal data."""
        opp = {
            "opportunity_type": OPP_PRODUCT_PRICE_DROP,
            "metadata": {
                "product_title": "Classic Cotton Shirt",
                "old_price": 500.0,
                "new_price": 300.0,
                "interest_source": "cart",
                "product_url": "https://www.myntra.com/shirts/123",
            },
        }
        subject, body = build_opportunity_email_content(opp, "Bharath", "http://localhost:3001")

        self.assertIn("Classic Cotton Shirt", subject)
        self.assertIn("300", subject)
        self.assertIn("Good news! The Classic Cotton Shirt in your cart is now ₹300, down from ₹500.", body)
        self.assertIn("https://www.myntra.com/shirts/123", body)

        # Confirm ZERO internal ML/scoring leak
        forbidden_terms = ["score", "probability", "model", "segment", "internal", "vector", "opp:"]
        for term in forbidden_terms:
            self.assertNotIn(term, subject.lower())
            self.assertNotIn(term, body.lower())


if __name__ == "__main__":
    unittest.main()
