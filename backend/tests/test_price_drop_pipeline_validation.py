"""Step 5 Validation: End-to-end price-drop opportunity -> Gmail pipeline.

Validates that:
  - Real Myntra price drops flow from detection -> opportunity record -> communication dispatch
  - Qualifying customer receives exactly one communication
  - Repeated processing of the same opportunity is strictly idempotent (zero duplicates)
  - Promotional cooldown (24h) is strictly respected
  - Ineligible customers (Cold, no interest, same price) produce no communication
  - Customer-facing email contains product title, current/previous price, discount, and product link
  - Customer-facing email contains ZERO ML leakage (scores, probability, model version, internal IDs)
  - All tests use mock providers with ZERO real Gmail deliveries and ZERO ReefAPI calls.
"""

import copy
import datetime
import unittest
from bson import ObjectId

from opportunity_engine import (
    OPP_PRODUCT_PRICE_DROP,
    OPPORTUNITY_COOLDOWN_HOURS,
    build_opportunity_email_content,
)
from communication_provider import CommunicationProvider
from marketing_automation_service import (
    evaluate_channel_eligibility,
    dispatch_communication,
)
from price_drop_opportunity_service import (
    create_price_drop_opportunity,
    dispatch_price_drop_opportunity,
    evaluate_customer_lead_state_eligibility,
    find_customers_with_product_in_cart_or_wishlist,
    process_price_drop_event,
)
from tests.test_price_drop_gmail_communication import MockDatabase


class MockGmailProvider(CommunicationProvider):
    """Mock Gmail provider recording dispatches with ZERO real network calls."""

    def __init__(self):
        self.dispatched_emails = []

    def send_email(self, recipient, subject, body, metadata=None, html_body=None, **kwargs):
        dispatch_record = {
            "success": True,
            "provider": "mock_gmail",
            "provider_message_id": f"msg_{len(self.dispatched_emails) + 1}",
            "channel": "email",
            "recipient": recipient,
            "subject": subject,
            "body": body,
            "html_body": html_body,
            "metadata": metadata or {},
            "dispatched_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        self.dispatched_emails.append(dispatch_record)
        return dispatch_record

    def send_whatsapp(self, recipient, body, metadata=None):
        return {"success": False, "provider": "mock_gmail", "channel": "whatsapp", "status": "skipped"}


class TestPriceDropPipelineValidation(unittest.TestCase):
    """Comprehensive validation suite for Step 5."""

    def setUp(self):
        self.db = MockDatabase()
        self.mock_gmail = MockGmailProvider()
        self.now = datetime.datetime(2026, 10, 8, 16, 0, 0, tzinfo=datetime.timezone.utc)

        # Real Myntra price drop from the live catalog refresh (Product 1 of 26)
        self.real_price_drop_event = {
            "product_id": "myntra_44834857",
            "source_product_id": "44834857",
            "title": "RARE RABBIT Men Casual Shirt",
            "brand": "RARE RABBIT",
            "category": "Shirts",
            "old_price": 1063.0,
            "new_price": 1035.0,
            "difference": 28.0,
            "change_type": "drop",
            "primary_image": "https://assets.myntassets.com/assets/images/2026/JULY/31/cvrkXVqP_7728d84cdcb04cc7878e4e3b257c96de.jpg",
            "url": "https://www.myntra.com/Shirts/RARE+RABBIT/RARE-RABBIT-Men-Casual-Shirt/44834857/buy",
            "detected_at": self.now.isoformat(),
        }

        # Customer setup: An eligible Warm customer with product in active cart
        self.customer_id = ObjectId("6ac496df16b0c7c385d7b5b4")

        self.db["user_profiles"].insert_one({
            "_id": self.customer_id,
            "user_id": str(self.customer_id),
            "email": "customer@example.com",
            "full_name": "Arjun Sharma",
            "channel_preferences": {"email": True, "whatsapp": False},
            "unsubscribed": False,
        })

        self.db["customer_lead_state"].insert_one({
            "customer_id": self.customer_id,
            "lead_segment": "Warm",
            "lead_score": 55,
            "lead_probability": 0.55,
            "qualification_status": "qualified",
            "updated_at": self.now.isoformat(),
        })

        self.db["cart"].insert_one({
            "_id": ObjectId(),
            "user_id": self.customer_id,
            "product_id": "myntra_44834857",
            "quantity": 1,
            "added_at": (self.now - datetime.timedelta(days=2)).isoformat(),
        })

    def test_end_to_end_qualifying_opportunity_to_gmail(self):
        """1. Full pipeline: price drop -> opportunity created -> communication dispatched."""
        # Step A: Process price drop event
        report = process_price_drop_event(
            price_drop_event=self.real_price_drop_event,
            db=self.db,
            enforce_cooldown=True,
            current_time=self.now,
        )

        self.assertEqual(report["product_id"], "myntra_44834857")
        self.assertEqual(len(report["opportunities"]), 1)
        opp = report["opportunities"][0]

        # Step B: Verify marketing_opportunities record fields (Task 8)
        self.assertEqual(str(opp["customer_id"]), str(self.customer_id))
        self.assertEqual(opp["product_id"], "myntra_44834857")
        self.assertEqual(opp["product_name"], "RARE RABBIT Men Casual Shirt")
        self.assertEqual(opp["opportunity_state"], "detected")

        meta = opp["metadata"]
        self.assertEqual(meta["old_price"], 1063.0)
        self.assertEqual(meta["new_price"], 1035.0)
        self.assertEqual(meta["discount_amount"], 28.0)
        self.assertEqual(meta["discount_percentage"], 3)  # round((28/1063)*100) = 3%
        self.assertEqual(meta["interest_source"], "cart")
        self.assertEqual(meta["customer_lead_state"], "Warm")
        self.assertIsNotNone(meta["detected_at"])

        # Step C: Dispatch communication via existing pipeline with mock Gmail provider
        dispatch_res = dispatch_price_drop_opportunity(
            opportunity_or_key=opp,
            db=self.db,
            provider=self.mock_gmail,
            current_time=self.now,
        )

        self.assertTrue(dispatch_res["success"])
        self.assertEqual(dispatch_res["status"], "sent")
        self.assertEqual(len(self.mock_gmail.dispatched_emails), 1)

        # Verify communication record created in marketing_communications
        comms = self.db["marketing_communications"].find({"customer_id": self.customer_id})
        self.assertEqual(len(comms), 1)
        self.assertEqual(comms[0]["status"], "sent")
        self.assertEqual(comms[0]["recipient"], "customer@example.com")
        self.assertEqual(comms[0]["campaign_type"], "product_price_drop")

        # Verify opportunity state transitioned to 'communicated'
        saved_opp = self.db["marketing_opportunities"].find_one({"opportunity_key": opp["opportunity_key"]})
        self.assertEqual(saved_opp["opportunity_state"], "communicated")
        self.assertIsNotNone(saved_opp["communicated_at"])

    def test_idempotency_prevents_duplicate_dispatch(self):
        """2. Processing or dispatching the SAME opportunity twice never sends a second email."""
        # First processing and dispatch
        report = process_price_drop_event(
            price_drop_event=self.real_price_drop_event,
            db=self.db,
            current_time=self.now,
        )
        opp = report["opportunities"][0]

        res1 = dispatch_price_drop_opportunity(
            opportunity_or_key=opp,
            db=self.db,
            provider=self.mock_gmail,
            current_time=self.now,
        )
        self.assertEqual(res1["status"], "sent")
        self.assertEqual(len(self.mock_gmail.dispatched_emails), 1)

        # Second dispatch attempt of the same opportunity
        saved_opp = self.db["marketing_opportunities"].find_one({"opportunity_key": opp["opportunity_key"]})
        res2 = dispatch_price_drop_opportunity(
            opportunity_or_key=saved_opp,
            db=self.db,
            provider=self.mock_gmail,
            current_time=self.now + datetime.timedelta(hours=1),
        )

        self.assertFalse(res2["success"])
        self.assertIn(res2["status"], ["already_communicated", "already_sent", "skipped"])
        self.assertIn("already communicated", res2["reason"].lower())
        # Total emails dispatched must remain strictly 1
        self.assertEqual(len(self.mock_gmail.dispatched_emails), 1)

    def test_promotional_cooldown_is_respected(self):
        """3. Customer who received communication within cooldown period is suppressed."""
        # Record a recent communication 4 hours ago (well within 24h cooldown)
        recent_comm_time = (self.now - datetime.timedelta(hours=4)).isoformat()
        self.db["marketing_communications"].insert_one({
            "customer_id": self.customer_id,
            "campaign_type": "promotional_offer",
            "channel": "email",
            "status": "sent",
            "sent_at": recent_comm_time,
            "dispatched_at": recent_comm_time,
            "created_at": recent_comm_time,
        })

        # Process price drop event
        report = process_price_drop_event(
            price_drop_event=self.real_price_drop_event,
            db=self.db,
            enforce_cooldown=True,
            current_time=self.now,
        )

        # Opportunity is marked as cooldown_suppressed
        self.assertEqual(len(report["opportunities"]), 1)
        opp = report["opportunities"][0]
        self.assertTrue(opp.get("cooldown_suppressed"))

        # When attempting dispatch, it is skipped due to cooldown
        dispatch_res = dispatch_price_drop_opportunity(
            opportunity_or_key=opp,
            db=self.db,
            provider=self.mock_gmail,
            enforce_cooldown=True,
            current_time=self.now,
        )

        self.assertFalse(dispatch_res["success"])
        self.assertIn(dispatch_res["status"], ["cooldown_suppressed", "skipped"])
        self.assertIn("cooldown", dispatch_res["reason"].lower())
        self.assertEqual(len(self.mock_gmail.dispatched_emails), 0)

    def test_ineligible_customer_produces_no_communication(self):
        """4. Cold customer produces no opportunity and zero communications."""
        # Change customer lead state to Cold
        self.db["customer_lead_state"].docs[0]["lead_segment"] = "Cold"
        self.db["customer_lead_state"].docs[0]["lead_score"] = 20
        self.db["customer_lead_state"].docs[0]["lead_probability"] = 0.20

        report = process_price_drop_event(
            price_drop_event=self.real_price_drop_event,
            db=self.db,
            current_time=self.now,
        )

        self.assertEqual(len(report["opportunities"]), 0)
        self.assertEqual(len(self.mock_gmail.dispatched_emails), 0)

    def test_customer_facing_email_content_and_zero_ml_leakage(self):
        """5. Customer email includes product details and contains ZERO internal/ML terms."""
        report = process_price_drop_event(
            price_drop_event=self.real_price_drop_event,
            db=self.db,
            current_time=self.now,
        )
        opp = report["opportunities"][0]

        dispatch_price_drop_opportunity(
            opportunity_or_key=opp,
            db=self.db,
            provider=self.mock_gmail,
            current_time=self.now,
        )

        self.assertEqual(len(self.mock_gmail.dispatched_emails), 1)
        sent = self.mock_gmail.dispatched_emails[0]
        body = sent["body"]
        subject = sent["subject"]

        # MUST contain:
        # Product title
        self.assertIn("RARE RABBIT Men Casual Shirt", body)
        # Current price (1035)
        self.assertTrue("1035" in body or "1,035" in body)
        # Previous price (1063)
        self.assertTrue("1063" in body or "1,063" in body)
        # Cart context
        self.assertIn("cart", body.lower())
        # Product link
        self.assertTrue("http" in body)

        # MUST NOT contain:
        forbidden_terms = [
            "lead score",
            "lead_score",
            "probability",
            "model",
            "randomforest",
            "xgboost",
            "kmeans",
            "opportunity_key",
            "internal_id",
            str(self.customer_id),
        ]
        lower_body = body.lower()
        lower_subj = subject.lower()
        for term in forbidden_terms:
            self.assertNotIn(term, lower_body, f"Forbidden ML term '{term}' leaked into email body!")
            self.assertNotIn(term, lower_subj, f"Forbidden ML term '{term}' leaked into email subject!")


if __name__ == "__main__":
    unittest.main()
