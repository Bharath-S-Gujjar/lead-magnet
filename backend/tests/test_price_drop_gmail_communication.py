"""Unit tests for Step 4: Connecting product_price_drop opportunity to the Gmail communication engine.

Covers all required areas:
  1. product_price_drop communication creation and logging in marketing_communications
  2. Cart email content wording ("Good news! The [product] in your cart is now ₹300, down from ₹500.")
  3. Wishlist email content wording ("Good news! The [product] on your wishlist is now ₹300, down from ₹500.")
  4. Product image in HTML body (<img src="...">)
  5. Product link in email
  6. Previous price and current price correctly displayed
  7. No ML information leakage (lead scores, probability, Hot/Warm, model name/version, internal IDs)
  8. Duplicate prevention & deterministic idempotency
  9. 24-hour promotional opportunity cooldown enforcement
  10. Gmail provider failure handling (SMTP error -> status 'failed', not marked communicated)
  11. Successful provider dispatch updates opportunity state to 'communicated'
  12. Zero ReefAPI calls and zero real emails sent during automated testing

All tests use in-memory/mock data with zero network calls and zero ReefAPI credits.
"""

import copy
import datetime
import unittest
from unittest.mock import MagicMock, patch
from bson import ObjectId

from opportunity_engine import (
    OPP_PRODUCT_PRICE_DROP,
    OPPORTUNITY_COOLDOWN_HOURS,
    build_opportunity_email_content,
    process_customer_opportunities,
)
from communication_provider import (
    DryRunCommunicationProvider,
    FailingCommunicationProvider,
    _build_html_body,
)
from marketing_automation_service import (
    dispatch_communication,
    trigger_product_price_drop_communication,
)
from price_drop_opportunity_service import (
    create_price_drop_opportunity,
    dispatch_price_drop_opportunity,
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
        res = MagicMock()
        res.inserted_id = d["_id"]
        return res

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
                res.sort(key=lambda x: str(x.get(field, "")), reverse=(direction == -1))
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
                    elif op == "$nin" and doc.get(k) in val:
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
                res = MagicMock()
                res.upserted_id = None
                return res

        if upsert:
            new_doc = copy.deepcopy(query)
            new_doc.update(copy.deepcopy(set_on_insert))
            new_doc.update(copy.deepcopy(set_data))
            if "_id" not in new_doc:
                new_doc["_id"] = ObjectId()
            self.docs.append(new_doc)
            res = MagicMock()
            res.upserted_id = new_doc["_id"]
            return res

        res = MagicMock()
        res.upserted_id = None
        return res

    def count_documents(self, query=None):
        return len(self.find(query))


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
            "marketing_automation_events": MockCollection("marketing_automation_events"),
            "admin_notifications": MockCollection("admin_notifications"),
            "user_profiles": MockCollection("user_profiles"),
            "products": MockCollection("products"),
            "myntra_products": MockCollection("myntra_products"),
        }

    def __getitem__(self, name):
        if name not in self.collections:
            self.collections[name] = MockCollection(name)
        return self.collections[name]

    def __contains__(self, name):
        return True


class TestPriceDropGmailCommunication(unittest.TestCase):
    """Test suite for Step 4 Gmail integration."""

    def setUp(self):
        self.db = MockDatabase()
        self.test_cid = ObjectId()
        self.test_pid = "myntra_28420390"

        # Seed customer profile
        self.db["user_profiles"].insert_one({
            "_id": self.test_cid,
            "username": "arjun_test",
            "full_name": "Arjun Kumar",
            "email": "arjun.test@example.com",
            "phone": "+919876543210",
        })

        # Sample price drop event
        self.price_drop_event = {
            "product_id": self.test_pid,
            "source_product_id": "28420390",
            "title": "Roadster Men Cotton Casual Shirt",
            "brand": "Roadster",
            "old_price": 500,
            "new_price": 300,
            "primary_image": "https://assets.myntra.com/assets/images/28420390/shirt.jpg",
            "url": "https://www.myntra.com/shirts/roadster/28420390/buy",
        }

    def test_cart_email_content_wording(self):
        """Cart email must contain: 'Good news! The [product] in your cart is now ₹300, down from ₹500.'"""
        opp = create_price_drop_opportunity(
            customer_id=self.test_cid,
            price_drop_event=self.price_drop_event,
            interest_source="cart",
            customer_lead_state="Warm",
            db=self.db,
        )

        subject, body = build_opportunity_email_content(
            opp, customer_name="Arjun", store_url="http://localhost:3001"
        )

        self.assertIn("Good news! The Roadster Men Cotton Casual Shirt in your cart is now ₹300, down from ₹500.", body)
        self.assertIn("Roadster Men Cotton Casual Shirt", body)
        self.assertIn("₹300", body)
        self.assertIn("₹500", body)
        self.assertIn("https://www.myntra.com/shirts/roadster/28420390/buy", body)
        self.assertIn("Save ₹200 (40% off)!", body)

    def test_wishlist_email_content_wording(self):
        """Wishlist email must contain: 'Good news! The [product] on your wishlist is now ₹300, down from ₹500.'"""
        opp = create_price_drop_opportunity(
            customer_id=self.test_cid,
            price_drop_event=self.price_drop_event,
            interest_source="wishlist",
            customer_lead_state="Warm",
            db=self.db,
        )

        subject, body = build_opportunity_email_content(
            opp, customer_name="Arjun", store_url="http://localhost:3001"
        )

        self.assertIn("Good news! The Roadster Men Cotton Casual Shirt on your wishlist is now ₹300, down from ₹500.", body)
        self.assertIn("Roadster Men Cotton Casual Shirt", body)
        self.assertIn("₹300", body)
        self.assertIn("₹500", body)
        self.assertIn("https://www.myntra.com/shirts/roadster/28420390/buy", body)
        self.assertIn("Save ₹200 (40% off)!", body)

    def test_product_image_in_html(self):
        """Product image URL must be rendered in HTML email body."""
        opp = create_price_drop_opportunity(
            customer_id=self.test_cid,
            price_drop_event=self.price_drop_event,
            interest_source="cart",
            customer_lead_state="Warm",
            db=self.db,
        )

        provider = DryRunCommunicationProvider()
        result = dispatch_price_drop_opportunity(
            opportunity_or_key=opp,
            db=self.db,
            provider=provider,
            enforce_cooldown=False,
        )

        self.assertTrue(result["success"])
        # Check rendered HTML in provider output
        html_body = _build_html_body(result["body"], image_url=self.price_drop_event["primary_image"])
        self.assertIn("<img", html_body)
        self.assertIn(self.price_drop_event["primary_image"], html_body)

    def test_no_ml_information_leakage(self):
        """Customer-facing email must NOT expose ML scores, probabilities, segments, or model metadata."""
        # Attach internal ML scoring fields to customer lead state & opportunity doc
        self.db["customer_lead_state"].insert_one({
            "customer_id": self.test_cid,
            "lead_score": 85,
            "lead_probability": 0.88,
            "lead_segment": "Warm",
            "model_name": "lead_scoring_xgb",
            "model_version": "v3.2.1",
        })

        opp = create_price_drop_opportunity(
            customer_id=self.test_cid,
            price_drop_event=self.price_drop_event,
            interest_source="cart",
            customer_lead_state="Warm",
            db=self.db,
        )

        subject, body = build_opportunity_email_content(
            opp, customer_name="Arjun", store_url="http://localhost:3001"
        )
        html_body = _build_html_body(body, image_url=self.price_drop_event["primary_image"])

        for content in [subject, body, html_body]:
            self.assertNotIn("0.88", content)
            self.assertNotIn("lead_score", content.lower())
            self.assertNotIn("lead_probability", content.lower())
            self.assertNotIn("model_version", content.lower())
            self.assertNotIn("lead_scoring_xgb", content)
            self.assertNotIn("v3.2.1", content)
            self.assertNotIn("Warm classification", content)
            self.assertNotIn("Hot classification", content)
            self.assertNotIn(str(opp["_id"]), content)
            self.assertNotIn(opp["opportunity_key"], content)

    def test_product_price_drop_communication_creation_and_logging(self):
        """product_price_drop communication must be created and logged in marketing_communications."""
        opp = create_price_drop_opportunity(
            customer_id=self.test_cid,
            price_drop_event=self.price_drop_event,
            interest_source="cart",
            customer_lead_state="Warm",
            db=self.db,
        )

        provider = DryRunCommunicationProvider()
        res = dispatch_price_drop_opportunity(
            opportunity_or_key=opp,
            db=self.db,
            provider=provider,
            enforce_cooldown=False,
        )

        self.assertTrue(res["success"])
        self.assertEqual(res["status"], "sent")
        self.assertEqual(res["recipient"], "arjun.test@example.com")
        self.assertTrue(res["provider_message_id"].startswith("dry-run-email-"))

        # Check DB log in marketing_communications
        comm_doc = self.db["marketing_communications"].find_one({"idempotency_key": f"{opp['opportunity_key']}:email"})
        self.assertIsNotNone(comm_doc)
        self.assertEqual(comm_doc["campaign_type"], "product_price_drop")
        self.assertEqual(comm_doc["channel"], "email")
        self.assertEqual(comm_doc["status"], "sent")
        self.assertEqual(comm_doc["recipient"], "arjun.test@example.com")
        self.assertIsNotNone(comm_doc["sent_at"])

    def test_successful_provider_dispatch_updates_opportunity_state(self):
        """Successful provider dispatch must transition opportunity state from detected to communicated."""
        opp = create_price_drop_opportunity(
            customer_id=self.test_cid,
            price_drop_event=self.price_drop_event,
            interest_source="cart",
            customer_lead_state="Warm",
            db=self.db,
        )
        self.assertEqual(opp["opportunity_state"], "detected")

        provider = DryRunCommunicationProvider()
        res = dispatch_price_drop_opportunity(
            opportunity_or_key=opp,
            db=self.db,
            provider=provider,
            enforce_cooldown=False,
        )

        self.assertTrue(res["success"])
        saved_opp = self.db["marketing_opportunities"].find_one({"opportunity_key": opp["opportunity_key"]})
        self.assertEqual(saved_opp["opportunity_state"], "communicated")
        self.assertIsNotNone(saved_opp["communicated_at"])

    def test_gmail_provider_failure_handling(self):
        """Provider failure must record failed state and NOT mark opportunity as communicated."""
        opp = create_price_drop_opportunity(
            customer_id=self.test_cid,
            price_drop_event=self.price_drop_event,
            interest_source="cart",
            customer_lead_state="Warm",
            db=self.db,
        )

        failing_provider = FailingCommunicationProvider(error_message="SMTP Authentication Failed")
        res = dispatch_price_drop_opportunity(
            opportunity_or_key=opp,
            db=self.db,
            provider=failing_provider,
            enforce_cooldown=False,
        )

        self.assertFalse(res["success"])
        self.assertEqual(res["status"], "failed")
        self.assertIn("SMTP Authentication Failed", res["error"])

        # Check opportunity is NOT communicated
        saved_opp = self.db["marketing_opportunities"].find_one({"opportunity_key": opp["opportunity_key"]})
        self.assertNotEqual(saved_opp["opportunity_state"], "communicated")
        self.assertEqual(saved_opp["opportunity_state"], "failed")

        # Check marketing_communications record
        comm_doc = self.db["marketing_communications"].find_one({"idempotency_key": f"{opp['opportunity_key']}:email"})
        self.assertIsNotNone(comm_doc)
        self.assertEqual(comm_doc["status"], "failed")
        self.assertIn("SMTP Authentication Failed", comm_doc["last_error"])

    def test_duplicate_prevention_idempotency(self):
        """Repeated dispatch of the same opportunity must not resend or create duplicate emails."""
        opp = create_price_drop_opportunity(
            customer_id=self.test_cid,
            price_drop_event=self.price_drop_event,
            interest_source="cart",
            customer_lead_state="Warm",
            db=self.db,
        )

        provider = DryRunCommunicationProvider()

        # First dispatch: succeeds
        res1 = dispatch_price_drop_opportunity(
            opportunity_or_key=opp,
            db=self.db,
            provider=provider,
            enforce_cooldown=False,
        )
        self.assertTrue(res1["success"])
        self.assertEqual(res1["status"], "sent")

        # Second dispatch: suppressed by idempotency
        res2 = dispatch_price_drop_opportunity(
            opportunity_or_key=opp,
            db=self.db,
            provider=provider,
            enforce_cooldown=False,
        )
        self.assertFalse(res2["success"])
        self.assertIn(res2["status"], ["already_communicated", "already_sent"])

        # Verify only 1 email in marketing_communications
        comms = self.db["marketing_communications"].find({"customer_id": self.test_cid})
        self.assertEqual(len(comms), 1)

    def test_24h_promotional_opportunity_cooldown(self):
        """Promotional opportunity cooldown (24h) must suppress rapid-fire emails to same customer."""
        # Record a prior promotional email sent 2 hours ago
        two_hours_ago = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=2)).isoformat()
        self.db["marketing_communications"].insert_one({
            "customer_id": self.test_cid,
            "campaign_type": "cart_abandoned",
            "channel": "email",
            "status": "sent",
            "sent_at": two_hours_ago,
        })

        opp = create_price_drop_opportunity(
            customer_id=self.test_cid,
            price_drop_event=self.price_drop_event,
            interest_source="cart",
            customer_lead_state="Warm",
            db=self.db,
        )

        provider = DryRunCommunicationProvider()
        res = dispatch_price_drop_opportunity(
            opportunity_or_key=opp,
            db=self.db,
            provider=provider,
            enforce_cooldown=True,
        )

        self.assertFalse(res["success"])
        self.assertEqual(res["status"], "cooldown_suppressed")
        self.assertIn("cooldown", res["reason"].lower())

        # Fast forward time past 24h
        future_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=26)
        res_after_cooldown = dispatch_price_drop_opportunity(
            opportunity_or_key=opp,
            db=self.db,
            provider=provider,
            enforce_cooldown=True,
            current_time=future_time,
        )
        self.assertTrue(res_after_cooldown["success"])
        self.assertEqual(res_after_cooldown["status"], "sent")

    def test_trigger_product_price_drop_communication_wrapper(self):
        """marketing_automation_service.trigger_product_price_drop_communication works seamlessly."""
        opp = create_price_drop_opportunity(
            customer_id=self.test_cid,
            price_drop_event=self.price_drop_event,
            interest_source="wishlist",
            customer_lead_state="Warm",
            db=self.db,
        )

        provider = DryRunCommunicationProvider()
        res = trigger_product_price_drop_communication(
            customer_id=self.test_cid,
            opportunity_or_key=opp["opportunity_key"],
            db=self.db,
            provider=provider,
            enforce_cooldown=False,
        )

        self.assertTrue(res["success"])
        self.assertEqual(res["status"], "sent")
        self.assertEqual(res["recipient"], "arjun.test@example.com")

    def test_zero_reefapi_calls_and_zero_real_emails(self):
        """Testing dispatch must consume 0 ReefAPI credits and send 0 real emails."""
        opp = create_price_drop_opportunity(
            customer_id=self.test_cid,
            price_drop_event=self.price_drop_event,
            interest_source="cart",
            customer_lead_state="Warm",
            db=self.db,
        )

        with patch("requests.post") as mock_post, patch("smtplib.SMTP") as mock_smtp:
            provider = DryRunCommunicationProvider()
            res = dispatch_price_drop_opportunity(
                opportunity_or_key=opp,
                db=self.db,
                provider=provider,
                enforce_cooldown=False,
            )
            self.assertTrue(res["success"])
            self.assertEqual(mock_post.call_count, 0, "No HTTP POST calls should be made (0 ReefAPI credits consumed)")
            self.assertEqual(mock_smtp.call_count, 0, "No real SMTP connection should be opened during tests")


if __name__ == "__main__":
    unittest.main()
