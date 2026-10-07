"""Tests for Opportunity Engine and Targeted Gmail Email Intelligence.

Tests all 23 required scenarios:
1. Hot customer with no opportunity -> no new opportunity email
2. Score changes below Hot threshold -> no Hot qualification email
3. Customer crosses 0.70 -> qualification behavior preserved
4. Hot remains Hot -> no repeated generic qualification email
5. Hot customer + discounted cart item -> targeted opportunity detected
6. Hot customer + discounted wishlist item -> targeted opportunity detected
7. Hot customer + relevant discounted alternative -> similar-product opportunity detected
8. Unrelated discounted product -> no opportunity
9. Same opportunity detected twice -> only one email
10. Different valid opportunity later -> can become eligible
11. Hot -> Warm with insignificant change -> no re-engagement
12. Hot -> Warm with significant decline -> re-engagement opportunity
13. Cart abandonment -> existing behavior preserved
14. Wishlist inactivity -> existing behavior preserved
15. Order confirmation -> existing behavior preserved
16. Provider failure -> communication is not falsely marked sent
17. Internal ML data -> never appears in customer email
18. Discount data -> email contains only real discount information
19. Current cart/wishlist correctness -> recommendations use CURRENT state
20. Gmail/WhatsApp channel isolation -> WhatsApp untouched/postponed, Gmail intact
21. Opportunity cooldown -> suppresses repeated emails within cooldown
22. Opportunity idempotency -> deterministic opportunity key prevents re-sends
23. Global/customer communication safety -> avoids rapid-fire spam
"""

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from bson import ObjectId

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module
from communication_provider import CommunicationProvider
from marketing_automation_service import (
    trigger_registration_communication,
    trigger_lead_qualification_communication,
    trigger_cart_abandonment_communication,
    trigger_wishlist_reminder_communication,
    trigger_order_confirmation_communication,
    trigger_opportunity_communication,
)
from opportunity_engine import (
    ensure_marketing_opportunities_indexes,
    extract_product_discount,
    detect_customer_interests,
    find_similar_discounted_products,
    detect_opportunities_for_customer,
    process_customer_opportunities,
    build_opportunity_email_content,
    OPP_CART_ITEM_DISCOUNT,
    OPP_WISHLIST_ITEM_DISCOUNT,
    OPP_SIMILAR_PRODUCT_DISCOUNT,
    OPP_CART_ABANDONMENT,
    OPP_WISHLIST_INACTIVITY,
    OPP_HOT_TO_WARM_REENGAGEMENT,
)


class MockCommunicationProvider(CommunicationProvider):
    """Test communication provider capturing dispatches."""
    def __init__(self, email_success=True, wa_success=True):
        self.email_success = email_success
        self.wa_success = wa_success
        self.emails_sent = []
        self.whatsapp_sent = []

    def send_email(self, recipient, subject, body, metadata=None):
        self.emails_sent.append({
            "recipient": recipient,
            "subject": subject,
            "body": body,
            "metadata": metadata or {},
        })
        if self.email_success:
            return {
                "success": True,
                "provider": "gmail_smtp",
                "provider_message_id": f"msg_{len(self.emails_sent)}",
            }
        return {
            "success": False,
            "provider": "gmail_smtp",
            "error": "SMTP server connection failed",
        }

    def send_whatsapp(self, recipient, body, metadata=None):
        self.whatsapp_sent.append({
            "recipient": recipient,
            "body": body,
            "metadata": metadata or {},
        })
        if self.wa_success:
            return {
                "success": True,
                "provider": "whatsapp_business",
                "provider_message_id": f"wa_msg_{len(self.whatsapp_sent)}",
            }
        return {
            "success": False,
            "provider": "whatsapp_business",
            "error": "WhatsApp provider failed",
        }


class OpportunityEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = app_module.db
        ensure_marketing_opportunities_indexes(cls.db)

    def setUp(self):
        self.created = defaultdict(list)
        self.provider = MockCommunicationProvider()

    def tearDown(self):
        for col_name, ids in self.created.items():
            if ids:
                self.db[col_name].delete_many({"_id": {"$in": ids}})
                self.db[col_name].delete_many({"customer_id": {"$in": ids}})
                self.db[col_name].delete_many({"user_id": {"$in": ids}})

    def track(self, col_name, doc_id):
        self.created[col_name].append(doc_id)
        return doc_id

    def _create_profile(self, email="hotlead@example.com", name="John Doe", phone="+919876543210"):
        cid = ObjectId()
        self.track("user_profiles", cid)
        self.db["user_profiles"].insert_one({
            "_id": cid,
            "email": email,
            "full_name": name,
            "phone": phone,
        })
        return cid

    def _create_lead_state(self, customer_id, prob=0.85, score=85, segment="Hot", prev_prob=None, prev_score=None, prev_segment=None):
        self.track("customer_lead_state", customer_id)
        doc = {
            "customer_id": customer_id,
            "lead_probability": prob,
            "lead_score": score,
            "lead_segment": segment,
            "qualification_status": "qualified" if prob >= 0.70 else "not_qualified",
            "previous_probability": prev_prob,
            "previous_score": prev_score,
            "previous_segment": prev_segment,
            "first_qualified_at": datetime.now(timezone.utc).isoformat() if prob >= 0.70 else None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self.db["customer_lead_state"].insert_one(doc)
        return doc

    def _create_product(self, name="Nike Hoodie", category="Hoodies", brand="Nike", price=1999, discount=0, gender="Men"):
        pid = ObjectId()
        self.track("products", pid)
        doc = {
            "_id": pid,
            "name": name,
            "category": category,
            "brand": brand,
            "price": price,
            "discount": discount,
            "gender": gender,
            "rating": 4.5,
        }
        self.db["products"].insert_one(doc)
        return doc

    # --------------------------------------------------------------------------
    # 1. Hot customer with no opportunity -> no new opportunity email
    # --------------------------------------------------------------------------
    def test_01_hot_customer_no_opportunity_no_email(self):
        cid = self._create_profile()
        self._create_lead_state(cid, prob=0.85, score=85, segment="Hot")

        res = process_customer_opportunities(cid, self.db, provider=self.provider)
        self.assertEqual(res["detected_count"], 0)
        self.assertEqual(len(res["communicated"]), 0)
        self.assertEqual(len(self.provider.emails_sent), 0)

    # --------------------------------------------------------------------------
    # 2. Score changes below Hot threshold -> no Hot qualification email
    # --------------------------------------------------------------------------
    def test_02_score_below_hot_threshold_no_qualification_email(self):
        cid = self._create_profile()
        state = self._create_lead_state(cid, prob=0.55, score=55, segment="Warm")

        res = trigger_lead_qualification_communication(cid, lead_state_doc=state, db=self.db, provider=self.provider)
        self.assertTrue(res.get("skipped"))
        self.assertEqual(len(self.provider.emails_sent), 0)

    # --------------------------------------------------------------------------
    # 3. Customer crosses 0.70 -> qualification behavior preserved
    # --------------------------------------------------------------------------
    def test_03_customer_crosses_70_qualification_preserved(self):
        cid = self._create_profile()
        state = self._create_lead_state(
            cid, prob=0.75, score=75, segment="Hot",
            prev_prob=0.50, prev_score=50, prev_segment="Warm"
        )
        state["qualification_transition"] = "not_qualified_to_qualified"
        state["is_newly_qualified"] = True

        res = trigger_lead_qualification_communication(cid, lead_state_doc=state, db=self.db, provider=self.provider)
        self.assertIn("email", res)
        self.assertEqual(res["email"].get("status"), "sent")
        self.assertEqual(len(self.provider.emails_sent), 1)

    # --------------------------------------------------------------------------
    # 4. Hot remains Hot -> no repeated generic qualification email
    # --------------------------------------------------------------------------
    def test_04_hot_remains_hot_no_repeated_generic_email(self):
        cid = self._create_profile()
        state = self._create_lead_state(
            cid, prob=0.88, score=88, segment="Hot",
            prev_prob=0.85, prev_score=85, prev_segment="Hot"
        )
        state["qualification_transition"] = "qualified_to_qualified"
        state["is_newly_qualified"] = False

        res = trigger_lead_qualification_communication(cid, lead_state_doc=state, db=self.db, provider=self.provider)
        self.assertTrue(res.get("skipped"))
        self.assertEqual(len(self.provider.emails_sent), 0)

    # --------------------------------------------------------------------------
    # 5. Hot customer + discounted cart item -> targeted opportunity detected
    # --------------------------------------------------------------------------
    def test_05_hot_customer_discounted_cart_item_opportunity(self):
        cid = self._create_profile()
        self._create_lead_state(cid, prob=0.82, score=82, segment="Hot")
        prod = self._create_product("Puma Slim Fit Hoodies", category="Hoodies", price=1600, discount=20)

        # Add to cart
        cart_id = ObjectId()
        self.track("cart", cart_id)
        self.db["cart"].insert_one({
            "_id": cart_id,
            "user_id": cid,
            "product_id": prod["_id"],
            "quantity": 1,
            "added_at": datetime.now(timezone.utc),
        })

        opps = detect_opportunities_for_customer(cid, self.db)
        cart_opps = [o for o in opps if o["opportunity_type"] == OPP_CART_ITEM_DISCOUNT]
        self.assertGreaterEqual(len(cart_opps), 1)
        self.assertEqual(cart_opps[0]["metadata"]["discount_percent"], 20)

        # Process communication
        res = process_customer_opportunities(cid, self.db, provider=self.provider)
        self.assertEqual(len(res["communicated"]), 1)
        self.assertEqual(len(self.provider.emails_sent), 1)
        sent_email = self.provider.emails_sent[0]
        self.assertIn("Price drop", sent_email["subject"])
        self.assertIn("20% off", sent_email["body"])

    # --------------------------------------------------------------------------
    # 6. Hot customer + discounted wishlist item -> targeted opportunity detected
    # --------------------------------------------------------------------------
    def test_06_hot_customer_discounted_wishlist_item_opportunity(self):
        cid = self._create_profile()
        self._create_lead_state(cid, prob=0.79, score=79, segment="Hot")
        prod = self._create_product("Nike Winter Jacket", category="Jackets", price=3200, discount=15)

        wl_id = ObjectId()
        self.track("wishlist", wl_id)
        self.db["wishlist"].insert_one({
            "_id": wl_id,
            "user_id": cid,
            "product_id": prod["_id"],
            "created_at": datetime.now(timezone.utc),
        })

        opps = detect_opportunities_for_customer(cid, self.db)
        wl_opps = [o for o in opps if o["opportunity_type"] == OPP_WISHLIST_ITEM_DISCOUNT]
        self.assertGreaterEqual(len(wl_opps), 1)
        self.assertEqual(wl_opps[0]["metadata"]["discount_percent"], 15)

        res = process_customer_opportunities(cid, self.db, provider=self.provider)
        self.assertGreaterEqual(len(res["communicated"]), 1)
        self.assertEqual(len(self.provider.emails_sent), 1)
        self.assertIn("15% off", self.provider.emails_sent[0]["body"])

    # --------------------------------------------------------------------------
    # 7. Hot customer + relevant discounted alternative -> similar-product detected
    # --------------------------------------------------------------------------
    def test_07_hot_customer_relevant_discounted_alternative(self):
        cid = self._create_profile()
        self._create_lead_state(cid, prob=0.81, score=81, segment="Hot")

        # Customer added non-discounted Nike Hoodie to wishlist
        nike_hoodie = self._create_product("Nike Hoodie", category="Hoodies", brand="Nike", price=2500, discount=0, gender="Men")
        wl_id = ObjectId()
        self.track("wishlist", wl_id)
        self.db["wishlist"].insert_one({
            "_id": wl_id,
            "user_id": cid,
            "product_id": nike_hoodie["_id"],
            "created_at": datetime.now(timezone.utc),
        })

        # Catalog contains discounted Adidas Hoodie in same category
        adidas_hoodie = self._create_product("Adidas Hoodie", category="Hoodies", brand="Adidas", price=1999, discount=25, gender="Men")

        opps = detect_opportunities_for_customer(cid, self.db)
        sim_opps = [o for o in opps if o["opportunity_type"] == OPP_SIMILAR_PRODUCT_DISCOUNT]
        self.assertGreaterEqual(len(sim_opps), 1)
        rec_name = sim_opps[0]["metadata"]["recommended_product_name"]
        self.assertIn("Adidas", rec_name)
        self.assertEqual(sim_opps[0]["metadata"]["discount_percent"], 25)

        # Dispatch
        res = process_customer_opportunities(cid, self.db, provider=self.provider)
        self.assertGreaterEqual(len(res["communicated"]), 1)
        self.assertIn("Adidas", self.provider.emails_sent[0]["body"])
        self.assertIn("25% off", self.provider.emails_sent[0]["body"])

    # --------------------------------------------------------------------------
    # 8. Unrelated discounted product -> no opportunity
    # --------------------------------------------------------------------------
    def test_08_unrelated_discounted_product_no_opportunity(self):
        cid = self._create_profile()
        self._create_lead_state(cid, prob=0.85, score=85, segment="Hot")

        # Customer interested only in Hoodies
        hoodie = self._create_product("Nike Hoodie", category="Hoodies", brand="Nike", price=2500, discount=0)
        wl_id = ObjectId()
        self.track("wishlist", wl_id)
        self.db["wishlist"].insert_one({
            "_id": wl_id,
            "user_id": cid,
            "product_id": hoodie["_id"],
        })

        # Catalog has discounted Sarees and Jeans (unrelated)
        self._create_product("Sangria Silk Saree", category="Sarees", price=4500, discount=30, gender="Women")
        self._create_product("Mufti Denim Jeans", category="Jeans", price=2200, discount=20, gender="Men")

        similar = find_similar_discounted_products(hoodie, self.db)
        self.assertEqual(len(similar), 0)

    # --------------------------------------------------------------------------
    # 9. Same opportunity detected twice -> only one email
    # --------------------------------------------------------------------------
    def test_09_same_opportunity_detected_twice_only_one_email(self):
        cid = self._create_profile()
        self._create_lead_state(cid, prob=0.78, score=78, segment="Hot")
        prod = self._create_product("Puma Sweatshirt", category="Hoodies", price=1800, discount=20)

        wl_id = ObjectId()
        self.track("wishlist", wl_id)
        self.db["wishlist"].insert_one({
            "_id": wl_id,
            "user_id": cid,
            "product_id": prod["_id"],
        })

        # Run 1
        res1 = process_customer_opportunities(cid, self.db, provider=self.provider)
        self.assertEqual(len(res1["communicated"]), 1)
        self.assertEqual(len(self.provider.emails_sent), 1)

        # Run 2 (Same state, cooldown bypassed to test opportunity idempotency)
        res2 = process_customer_opportunities(cid, self.db, provider=self.provider, opportunity_cooldown_hours=0)
        self.assertEqual(len(res2["communicated"]), 0)
        self.assertGreaterEqual(len(res2["skipped"]), 1)
        self.assertEqual(res2["skipped"][0]["reason"], "Opportunity already communicated")
        self.assertEqual(len(self.provider.emails_sent), 1)

    # --------------------------------------------------------------------------
    # 10. Different valid opportunity later -> can become eligible
    # --------------------------------------------------------------------------
    def test_10_different_valid_opportunity_later_eligible(self):
        cid = self._create_profile()
        self._create_lead_state(cid, prob=0.84, score=84, segment="Hot")

        # Opportunity 1: Nike Shirt
        shirt = self._create_product("Nike Classic Shirt", category="Shirts", price=1500, discount=10)
        wl_id = ObjectId()
        self.track("wishlist", wl_id)
        self.db["wishlist"].insert_one({"_id": wl_id, "user_id": cid, "product_id": shirt["_id"]})

        res1 = process_customer_opportunities(cid, self.db, provider=self.provider, opportunity_cooldown_hours=0)
        self.assertEqual(len(res1["communicated"]), 1)
        self.assertEqual(len(self.provider.emails_sent), 1)

        # Later: Customer adds discounted Jacket (Opportunity 2)
        jacket = self._create_product("Wildcraft Hiking Jacket", category="Jackets", price=3500, discount=20)
        cart_id = ObjectId()
        self.track("cart", cart_id)
        self.db["cart"].insert_one({"_id": cart_id, "user_id": cid, "product_id": jacket["_id"], "quantity": 1})

        res2 = process_customer_opportunities(cid, self.db, provider=self.provider, opportunity_cooldown_hours=0)
        self.assertGreaterEqual(len(res2["communicated"]), 1)
        self.assertEqual(len(self.provider.emails_sent), 2)
        self.assertIn("Wildcraft", self.provider.emails_sent[1]["body"])

    # --------------------------------------------------------------------------
    # 11. Hot -> Warm with insignificant change -> no re-engagement
    # --------------------------------------------------------------------------
    def test_11_hot_to_warm_insignificant_change_no_reengagement(self):
        cid = self._create_profile()
        # Tiny change: 0.71 -> 0.69 (drop of only 0.02, 2 score points)
        self._create_lead_state(
            cid, prob=0.69, score=69, segment="Warm",
            prev_prob=0.71, prev_score=71, prev_segment="Hot"
        )

        opps = detect_opportunities_for_customer(cid, self.db)
        reengage_opps = [o for o in opps if o["opportunity_type"] == OPP_HOT_TO_WARM_REENGAGEMENT]
        self.assertEqual(len(reengage_opps), 0)

    # --------------------------------------------------------------------------
    # 12. Hot -> Warm with significant decline -> re-engagement opportunity
    # --------------------------------------------------------------------------
    def test_12_hot_to_warm_significant_decline_reengagement_opportunity(self):
        cid = self._create_profile()
        # Significant drop: 0.82 -> 0.55 (drop of 0.27, 27 score points >= 10 threshold)
        self._create_lead_state(
            cid, prob=0.55, score=55, segment="Warm",
            prev_prob=0.82, prev_score=82, prev_segment="Hot"
        )

        opps = detect_opportunities_for_customer(cid, self.db)
        reengage_opps = [o for o in opps if o["opportunity_type"] == OPP_HOT_TO_WARM_REENGAGEMENT]
        self.assertEqual(len(reengage_opps), 1)
        self.assertIn("score decline", reengage_opps[0]["metadata"]["reason"])

        res = process_customer_opportunities(cid, self.db, provider=self.provider)
        self.assertEqual(len(res["communicated"]), 1)
        self.assertEqual(len(self.provider.emails_sent), 1)
        self.assertIn("miss you", self.provider.emails_sent[0]["subject"].lower())

    # --------------------------------------------------------------------------
    # 13. Cart abandonment -> existing behavior preserved
    # --------------------------------------------------------------------------
    def test_13_cart_abandonment_existing_behavior_preserved(self):
        cid = self._create_profile()
        cart_id = ObjectId()
        self.track("cart", cart_id)
        two_hours_ago = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        self.db["cart"].insert_one({
            "_id": cart_id,
            "user_id": cid,
            "items": [{"title": "Classic Polo", "price": 999, "quantity": 1}],
            "total_amount": 999.0,
            "updated_at": two_hours_ago,
        })

        res = trigger_cart_abandonment_communication(cid, self.db, provider=self.provider, abandonment_delay_hours=1)
        self.assertIn("email", res)
        self.assertEqual(res["email"].get("status"), "sent")

    # --------------------------------------------------------------------------
    # 14. Wishlist inactivity -> existing behavior preserved
    # --------------------------------------------------------------------------
    def test_14_wishlist_inactivity_existing_behavior_preserved(self):
        cid = self._create_profile()
        wl_id = ObjectId()
        self.track("wishlist", wl_id)
        self.db["wishlist"].insert_one({
            "_id": wl_id,
            "user_id": cid,
            "items": [{"title": "Winter Coat", "price": 3499}],
        })

        res = trigger_wishlist_reminder_communication(cid, self.db, provider=self.provider, reminder_delay_days=7)
        self.assertIn("email", res)
        self.assertEqual(res["email"].get("status"), "sent")

    # --------------------------------------------------------------------------
    # 15. Order confirmation -> existing behavior preserved
    # --------------------------------------------------------------------------
    def test_15_order_confirmation_existing_behavior_preserved(self):
        cid = self._create_profile()
        order_id = ObjectId()
        self.track("orders", order_id)
        self.db["orders"].insert_one({
            "_id": order_id,
            "user_id": cid,
            "items": [{"title": "Cotton Kurta", "price": 1299, "quantity": 1}],
            "total_amount": 1299.0,
            "status": "confirmed",
        })

        res = trigger_order_confirmation_communication(order_id, self.db, provider=self.provider)
        self.assertIn("email", res)
        self.assertEqual(res["email"].get("status"), "sent")

    # --------------------------------------------------------------------------
    # 16. Provider failure -> communication is not falsely marked sent
    # --------------------------------------------------------------------------
    def test_16_provider_failure_not_marked_sent(self):
        cid = self._create_profile()
        self._create_lead_state(cid, prob=0.88, score=88, segment="Hot")
        prod = self._create_product("HRX Hoodie", category="Hoodies", price=1200, discount=10)
        wl_id = ObjectId()
        self.track("wishlist", wl_id)
        self.db["wishlist"].insert_one({"_id": wl_id, "user_id": cid, "product_id": prod["_id"]})

        failing_provider = MockCommunicationProvider(email_success=False)
        res = process_customer_opportunities(cid, self.db, provider=failing_provider)
        self.assertEqual(len(res["communicated"]), 0)
        self.assertEqual(len(res["skipped"]), 1)

        # Check DB status
        comm = self.db["marketing_communications"].find_one({"customer_id": cid})
        self.assertIsNotNone(comm)
        self.assertEqual(comm.get("status"), "failed")
        self.assertIsNone(comm.get("sent_at"))

    # --------------------------------------------------------------------------
    # 17. Internal ML data -> never appears in customer email
    # --------------------------------------------------------------------------
    def test_17_internal_ml_data_never_appears_in_customer_email(self):
        cid = self._create_profile(name="Alice Smith")
        self._create_lead_state(cid, prob=0.91234, score=91, segment="Hot")
        prod = self._create_product("Lee Cooper Jeans", category="Jeans", price=2499, discount=20)
        wl_id = ObjectId()
        self.track("wishlist", wl_id)
        self.db["wishlist"].insert_one({"_id": wl_id, "user_id": cid, "product_id": prod["_id"]})

        process_customer_opportunities(cid, self.db, provider=self.provider)
        self.assertEqual(len(self.provider.emails_sent), 1)
        sent = self.provider.emails_sent[0]
        full_content = (sent["subject"] + " " + sent["body"]).lower()

        forbidden_terms = [
            "0.91", "lead score", "lead_score", "probability", "model_version",
            "feature", "vector", "segment", "hot lead", "algorithm",
        ]
        for term in forbidden_terms:
            self.assertNotIn(term, full_content, f"Forbidden internal ML term '{term}' exposed in customer email!")

    # --------------------------------------------------------------------------
    # 18. Discount data -> email contains only real discount information
    # --------------------------------------------------------------------------
    def test_18_discount_data_only_real_information(self):
        cid = self._create_profile()
        self._create_lead_state(cid, prob=0.76, score=76, segment="Hot")
        prod = self._create_product("Flying Machine Jeans", category="Jeans", price=1800, discount=25)
        wl_id = ObjectId()
        self.track("wishlist", wl_id)
        self.db["wishlist"].insert_one({"_id": wl_id, "user_id": cid, "product_id": prod["_id"]})

        process_customer_opportunities(cid, self.db, provider=self.provider)
        sent = self.provider.emails_sent[0]
        self.assertIn("25%", sent["body"])
        self.assertIn("1,800.00", sent["body"])

    # --------------------------------------------------------------------------
    # 19. Current cart/wishlist correctness -> recommendations use CURRENT state
    # --------------------------------------------------------------------------
    def test_19_current_cart_wishlist_correctness(self):
        cid = self._create_profile()
        self._create_lead_state(cid, prob=0.80, score=80, segment="Hot")

        # Old removed product (historical view event only)
        old_prod = self._create_product("Old Removed Product", category="Kurtas", price=1500, discount=20)
        ev_id = ObjectId()
        self.track("events", ev_id)
        self.db["events"].insert_one({
            "_id": ev_id,
            "user_id": cid,
            "event_type": "product_view",
            "product_id": old_prod["_id"],
            "timestamp": (datetime.now(timezone.utc) - timedelta(days=30)).isoformat(),
        })

        # CURRENT wishlist item
        curr_prod = self._create_product("Current Active Kurta", category="Kurtas", price=2100, discount=15)
        wl_id = ObjectId()
        self.track("wishlist", wl_id)
        self.db["wishlist"].insert_one({"_id": wl_id, "user_id": cid, "product_id": curr_prod["_id"]})

        interests = detect_customer_interests(cid, self.db)
        curr_wl_ids = [str(p["_id"]) for p in interests["wishlist_products"]]
        self.assertIn(str(curr_prod["_id"]), curr_wl_ids)
        self.assertNotIn(str(old_prod["_id"]), curr_wl_ids)

    # --------------------------------------------------------------------------
    # 20. Gmail/WhatsApp channel isolation -> WhatsApp untouched, Gmail intact
    # --------------------------------------------------------------------------
    def test_20_gmail_whatsapp_channel_isolation(self):
        cid = self._create_profile(phone="+919876543210")
        self._create_lead_state(cid, prob=0.82, score=82, segment="Hot")
        prod = self._create_product("Puma Jacket", category="Jackets", price=3000, discount=20)
        wl_id = ObjectId()
        self.track("wishlist", wl_id)
        self.db["wishlist"].insert_one({"_id": wl_id, "user_id": cid, "product_id": prod["_id"]})

        res = process_customer_opportunities(cid, self.db, provider=self.provider)
        # Gmail sent
        self.assertEqual(len(self.provider.emails_sent), 1)
        # WhatsApp must be 0 (untouched / postponed)
        self.assertEqual(len(self.provider.whatsapp_sent), 0)

    # --------------------------------------------------------------------------
    # 21. Opportunity cooldown
    # --------------------------------------------------------------------------
    def test_21_opportunity_cooldown_prevents_duplicate_delivery(self):
        cid = self._create_profile()
        self._create_lead_state(cid, prob=0.85, score=85, segment="Hot")

        # Existing sent communication recorded 2 hours ago
        comm_id = ObjectId()
        self.track("marketing_communications", comm_id)
        two_hours_ago = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        self.db["marketing_communications"].insert_one({
            "_id": comm_id,
            "customer_id": cid,
            "channel": "email",
            "status": "sent",
            "sent_at": two_hours_ago,
        })

        # New opportunity exists
        prod = self._create_product("Raymond Suit", category="Shirts", price=4500, discount=20)
        wl_id = ObjectId()
        self.track("wishlist", wl_id)
        self.db["wishlist"].insert_one({"_id": wl_id, "user_id": cid, "product_id": prod["_id"]})

        # Cooldown of 24h should block sending
        res = process_customer_opportunities(cid, self.db, provider=self.provider, opportunity_cooldown_hours=24)
        self.assertEqual(len(res["communicated"]), 0)
        self.assertGreaterEqual(len(res["skipped"]), 1)
        self.assertIn("cooldown", res["skipped"][0]["reason"])
        self.assertEqual(len(self.provider.emails_sent), 0)

    # --------------------------------------------------------------------------
    # 22. Opportunity idempotency
    # --------------------------------------------------------------------------
    def test_22_opportunity_idempotency_key_prevents_duplicate_sends(self):
        cid = self._create_profile()
        self._create_lead_state(cid, prob=0.83, score=83, segment="Hot")
        prod = self._create_product("Mufti Shirt", category="Shirts", price=1200, discount=15)
        wl_id = ObjectId()
        self.track("wishlist", wl_id)
        self.db["wishlist"].insert_one({"_id": wl_id, "user_id": cid, "product_id": prod["_id"]})

        # Send once
        res1 = process_customer_opportunities(cid, self.db, provider=self.provider, opportunity_cooldown_hours=0)
        self.assertEqual(len(res1["communicated"]), 1)

        # Record in marketing_opportunities has opportunity_state == "communicated"
        opp = self.db["marketing_opportunities"].find_one({"customer_id": cid})
        self.assertIsNotNone(opp)
        self.assertEqual(opp["opportunity_state"], "communicated")

        # Second attempt must be skipped by idempotency
        res2 = process_customer_opportunities(cid, self.db, provider=self.provider, opportunity_cooldown_hours=0)
        self.assertEqual(len(res2["communicated"]), 0)
        self.assertEqual(len(self.provider.emails_sent), 1)

    # --------------------------------------------------------------------------
    # 23. Global/customer communication safety
    # --------------------------------------------------------------------------
    def test_23_global_customer_communication_safety(self):
        cid = self._create_profile()
        self._create_lead_state(cid, prob=0.90, score=90, segment="Hot")

        # Customer has multiple opportunities simultaneously
        prod1 = self._create_product("Hoodie A", category="Hoodies", price=1500, discount=20)
        prod2 = self._create_product("Hoodie B", category="Hoodies", price=1700, discount=15)

        cart_id = ObjectId()
        self.track("cart", cart_id)
        self.db["cart"].insert_one({"_id": cart_id, "user_id": cid, "product_id": prod1["_id"], "quantity": 1})

        wl_id = ObjectId()
        self.track("wishlist", wl_id)
        self.db["wishlist"].insert_one({"_id": wl_id, "user_id": cid, "product_id": prod2["_id"]})

        # Process opportunities: should send only 1 email per cycle to prevent spamming
        res = process_customer_opportunities(cid, self.db, provider=self.provider, opportunity_cooldown_hours=24)
        self.assertEqual(len(res["communicated"]), 1)
        self.assertEqual(len(self.provider.emails_sent), 1)


if __name__ == "__main__":
    unittest.main()
