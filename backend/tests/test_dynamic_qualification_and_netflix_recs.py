import os
import sys
import unittest
from datetime import datetime, timezone, timedelta
from bson import ObjectId

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module
from customer_lead_state_service import sync_customer_lead_state, get_customer_lead_state
from recommendation_service import get_post_purchase_recommendations, get_netflix_style_recommendations
from marketing_automation_service import (
    send_qualified_lead_category_best_recovery_email,
    evaluate_qualified_leads_inactivity_cart_recovery,
)
from communication_provider import DryRunCommunicationProvider


class DynamicQualificationAndNetflixRecsTests(unittest.TestCase):
    def setUp(self):
        self.client = app_module.app.test_client()
        self.db = app_module.db
        self.profiles = app_module.profiles_collection
        self.products = app_module.products_collection
        self.orders = app_module.orders_collection
        self.cart = app_module.cart_collection
        self.events = app_module.events_collection
        self.features = app_module.customer_features_collection
        self.lead_state = app_module.customer_lead_state_collection
        self.comms = self.db["marketing_communications"]
        self.notifs = self.db["admin_notifications"]
        self.provider = DryRunCommunicationProvider()
        self.test_ids = []

    def tearDown(self):
        for tid in self.test_ids:
            self.profiles.delete_many({"_id": tid})
            self.features.delete_many({"customer_id": tid})
            self.lead_state.delete_many({"customer_id": tid})
            self.cart.delete_many({"user_id": tid})
            self.orders.delete_many({"user_id": tid})
            self.events.delete_many({"user_id": tid})
            self.comms.delete_many({"customer_id": tid})
            self.notifs.delete_many({"customer_id": str(tid)})

    # -------------------------------------------------------------------------
    # 1. Strict Qualified Lead Conditions & Dynamic Activity Transitions
    # -------------------------------------------------------------------------
    def test_strict_qualified_lead_rules_and_rahul_example(self):
        """Test strict Qualified Lead rules:
        Meaning: Customer has not purchased anything yet, but shows strong buying intent.
        All three conditions must be true:
        1. Score is at least 70.
        2. Cart contains at least one item.
        3. Checkout was started within the last 24 hours.
        Example: Rahul has a score of 80, two items in his cart, and started checkout 10 minutes ago.
        He hasn't purchased yet -> Result: Qualified Lead.
        """
        customer_id = ObjectId()
        self.test_ids.append(customer_id)

        self.profiles.insert_one({
            "_id": customer_id,
            "email": "rahul@example.com",
            "full_name": "Rahul Sharma",
        })

        # Rahul: Score 80, 2 items in cart, started checkout 10 mins ago, hasn't purchased yet (orders_count == 0)
        ten_mins_ago = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        self.features.insert_one({
            "customer_id": customer_id,
            "sessions_count": 4,
            "total_events": 50,
            "cart_item_count": 2,
            "cart_value": 2400.0,
            "checkout_attempts": 1,
            "checkout_started_within_24h": True,
            "last_checkout_action_at": ten_mins_ago,
            "orders_count": 0,
            "total_order_value": 0.0,
            "days_since_last_activity": 0.01,
            "unique_products_viewed": 3,
            "products_viewed": 5,
            "wishlist_item_count": 1,
            "search_count": 2,
            "high_intent_page_visits": 2,
            "total_time_spent": 400.0,
        })

        rahul_state = sync_customer_lead_state(customer_id, self.db)
        # Rahul has score >= 70, 2 items in cart, checkout within 24h, orders_count == 0 -> Qualified Lead!
        self.assertGreaterEqual(rahul_state["lead_score"], 70)
        self.assertEqual(rahul_state["lifecycle_status"], "prospect")
        self.assertEqual(rahul_state["qualification_status"], "qualified")

        # Dynamic transition 1: Rahul removes items from his cart (cart_item_count == 0)
        self.features.update_one(
            {"customer_id": customer_id},
            {"$set": {"cart_item_count": 0, "cart_value": 0.0}}
        )
        state_empty_cart = sync_customer_lead_state(customer_id, self.db)
        # Cart has 0 items -> dynamically disqualified
        self.assertEqual(state_empty_cart["qualification_status"], "not_qualified")

        # Dynamic transition 2: Rahul adds items back, but checkout was > 24 hours ago
        two_days_ago = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        self.features.update_one(
            {"customer_id": customer_id},
            {"$set": {
                "cart_item_count": 2,
                "cart_value": 2400.0,
                "checkout_started_within_24h": False,
                "last_checkout_action_at": two_days_ago,
                "days_since_last_activity": 2.1,
            }}
        )
        state_stale_checkout = sync_customer_lead_state(customer_id, self.db)
        # Checkout was not within 24h -> dynamically disqualified
        self.assertEqual(state_stale_checkout["qualification_status"], "not_qualified")

        # Dynamic transition 3: Customer has purchased before (orders_count == 1) but is actively shopping
        # (unconverted restriction removed; converted customer with active cart + fresh checkout qualifies)
        fresh_checkout = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        self.features.update_one(
            {"customer_id": customer_id},
            {"$set": {
                "orders_count": 1,
                "total_order_value": 1500.0,
                "cart_item_count": 1,
                "checkout_started_within_24h": True,
                "last_checkout_action_at": fresh_checkout,
            }}
        )
        state_converted = sync_customer_lead_state(customer_id, self.db)
        self.assertEqual(state_converted["lifecycle_status"], "converted")
        self.assertEqual(state_converted["qualification_status"], "qualified")

        # Dynamic transition 4: Customer empties cart after purchase
        self.features.update_one(
            {"customer_id": customer_id},
            {"$set": {"cart_item_count": 0, "cart_value": 0.0}}
        )
        state_empty = sync_customer_lead_state(customer_id, self.db)
        self.assertEqual(state_empty["qualification_status"], "not_qualified")

    # -------------------------------------------------------------------------
    # 2. Qualified Leads Category Best-Rated Item Inactivity Email (4 Hours)
    # -------------------------------------------------------------------------
    def test_inactivity_cart_recovery_picks_best_rated_item_in_same_category(self):
        customer_id = ObjectId()
        self.test_ids.append(customer_id)

        # Seed profile
        self.profiles.insert_one({
            "_id": customer_id,
            "email": "shopper_cart@example.com",
            "full_name": "Alex Carter",
            "whatsapp_opt_in": False,
        })

        # Mark lead as qualified
        self.lead_state.insert_one({
            "customer_id": customer_id,
            "qualification_status": "qualified",
            "lead_segment": "Hot",
            "lead_score": 82,
        })

        # Seed catalog products in the SAME category (Shirts) with different ratings
        p_avg = ObjectId()
        p_best = ObjectId()
        self.test_ids.extend([p_avg, p_best])
        self.products.insert_one({
            "_id": p_avg,
            "product_id": "shirt_avg_01",
            "title": "Casual Cotton Shirt",
            "category": "Shirts",
            "brand": "Roadster",
            "price": 899.0,
            "rating": 4.1,
            "rating_count": 80,
            "primary_image": "http://img.example/shirt_avg.jpg",
        })
        self.products.insert_one({
            "_id": p_best,
            "product_id": "shirt_best_01",
            "title": "Premium Oxford Shirt",
            "category": "Shirts",
            "brand": "Roadster",
            "price": 1299.0,
            "rating": 4.8,
            "rating_count": 250,
            "primary_image": "http://img.example/shirt_best.jpg",
        })

        # Seed cart with BOTH shirts (multiple items of the SAME category)
        now_dt = datetime.now(timezone.utc)
        five_hours_ago = (now_dt - timedelta(hours=5)).isoformat()

        self.cart.insert_one({
            "user_id": customer_id,
            "product_id": "shirt_avg_01",
            "quantity": 1,
            "added_at": five_hours_ago,
            "updated_at": five_hours_ago,
        })
        self.cart.insert_one({
            "user_id": customer_id,
            "product_id": "shirt_best_01",
            "quantity": 1,
            "added_at": five_hours_ago,
            "updated_at": five_hours_ago,
        })

        # Test Case A: Customer was active only 1 hour ago (< 4h inactivity required)
        one_hour_ago = (now_dt - timedelta(hours=1)).isoformat()
        self.features.insert_one({
            "customer_id": customer_id,
            "last_active_at": one_hour_ago,
            "cart_item_count": 2,
        })

        res_too_soon = send_qualified_lead_category_best_recovery_email(
            customer_id=customer_id,
            db=self.db,
            provider=self.provider,
            inactivity_hours=4.0,
            force=False,
            current_time=now_dt,
        )
        self.assertTrue(res_too_soon.get("skipped"))
        self.assertIn("requires >= 4.0h", res_too_soon.get("reason", ""))

        # Test Case B: Customer has been inactive for 5 hours (>= 4h inactivity)
        self.features.update_one(
            {"customer_id": customer_id},
            {"$set": {"last_active_at": five_hours_ago, "updated_at": five_hours_ago}}
        )

        res_sent = send_qualified_lead_category_best_recovery_email(
            customer_id=customer_id,
            db=self.db,
            provider=self.provider,
            inactivity_hours=4.0,
            force=False,
            current_time=now_dt,
        )

        self.assertEqual(res_sent.get("status"), "sent")
        self.assertEqual(res_sent.get("featured_category"), "Shirts")
        # Confirms the HIGHEST-RATED item (rating 4.8) was chosen over rating 4.1
        self.assertEqual(res_sent["featured_product"]["product_id"], "shirt_best_01")
        self.assertEqual(res_sent["featured_product"]["rating"], 4.8)

        # Check recorded communication
        comm = self.comms.find_one({"customer_id": customer_id, "campaign_type": "qualified_cart_category_best"})
        self.assertIsNotNone(comm)
        self.assertEqual(comm["status"], "sent")
        self.assertEqual(comm["recipient"], "shopper_cart@example.com")
        self.assertIn("4.8", comm["body"])
        self.assertIn("Premium Oxford Shirt", comm["body"])

        # Check admin notification created
        notif = self.notifs.find_one({"customer_id": str(customer_id), "type": "qualified_cart_category_best"})
        self.assertIsNotNone(notif)
        self.assertIn("Shirts", notif["title"])

        # Test Case C: Idempotency check prevents duplicate dispatch within 24h
        res_dup = send_qualified_lead_category_best_recovery_email(
            customer_id=customer_id,
            db=self.db,
            provider=self.provider,
            inactivity_hours=4.0,
            force=False,
            current_time=now_dt + timedelta(hours=1),
        )
        self.assertTrue(res_dup.get("skipped"))
        self.assertIn("already sent within 24h", res_dup.get("reason", ""))

    # -------------------------------------------------------------------------
    # 3. Netflix-Style Post-Purchase Recommendations for Excluded/Converted Leads
    # -------------------------------------------------------------------------
    def test_netflix_style_recommendations_based_on_purchases(self):
        user_id = ObjectId()
        self.test_ids.append(user_id)

        # Seed catalog products
        p_purchased_id = ObjectId()
        p_rec_bomber_id = ObjectId()
        p_rec_jeans_id = ObjectId()
        self.test_ids.extend([p_purchased_id, p_rec_bomber_id, p_rec_jeans_id])

        p_purchased = {
            "_id": p_purchased_id,
            "product_id": "prod_purchased_jacket",
            "title": "Roadster Leather Biker Jacket",
            "category": "Jackets",
            "brand": "Roadster",
            "price": 3499.0,
            "rating": 4.6,
        }
        p_rec_same_cat = {
            "_id": p_rec_bomber_id,
            "product_id": "prod_rec_bomber",
            "title": "Roadster Suede Bomber Jacket",
            "category": "Jackets",
            "brand": "Roadster",
            "price": 2799.0,
            "rating": 4.7,
        }
        p_rec_other_cat = {
            "_id": p_rec_jeans_id,
            "product_id": "prod_rec_jeans",
            "title": "Levis Denim Straight Jeans",
            "category": "Jeans",
            "brand": "Levis",
            "price": 1999.0,
            "rating": 4.4,
        }
        self.products.insert_many([p_purchased, p_rec_same_cat, p_rec_other_cat])

        # User has completed an order with the biker jacket
        self.orders.insert_one({
            "_id": ObjectId(),
            "user_id": user_id,
            "status": "delivered",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "items": [
                {
                    "product_id": "prod_purchased_jacket",
                    "title": "Roadster Leather Biker Jacket",
                    "category": "Jackets",
                    "brand": "Roadster",
                    "price": 3499.0,
                }
            ],
            "total_amount": 3499.0,
        })

        recs = get_netflix_style_recommendations(
            products_collection=self.products,
            orders_collection=self.orders,
            user_id=user_id,
            limit_per_anchor=4,
            max_anchors=2,
        )

        self.assertTrue(recs["has_purchases"])
        self.assertGreater(recs["anchor_count"], 0)
        self.assertEqual(len(recs["carousels"]), 1)

        carousel = recs["carousels"][0]
        # Headline format: "Because you purchased '{Product name}':"
        self.assertEqual(carousel["headline"], "Because you purchased 'Roadster Leather Biker Jacket':")
        self.assertEqual(carousel["anchor_category"], "Jackets")

        rec_ids = [p["product_id"] for p in carousel["recommendations"]]
        # Already purchased product is STRICTLY EXCLUDED!
        self.assertNotIn("prod_purchased_jacket", rec_ids)
        # Recommended complementary items from same category/brand are included!
        self.assertIn("prod_rec_bomber", rec_ids)

        # Test API route GET /api/recommendations/post-purchase
        resp_post = self.client.get(f"/api/recommendations/post-purchase?user_id={user_id}")
        self.assertEqual(resp_post.status_code, 200)
        data_post = resp_post.get_json()["data"]
        self.assertTrue(data_post["has_purchases"])
        self.assertEqual(data_post["carousels"][0]["headline"], "Because you purchased 'Roadster Leather Biker Jacket':")

        # Also test backwards compatibility route GET /api/recommendations/netflix-style
        resp_legacy = self.client.get(f"/api/recommendations/netflix-style?user_id={user_id}")
        self.assertEqual(resp_legacy.status_code, 200)


if __name__ == "__main__":
    unittest.main()
