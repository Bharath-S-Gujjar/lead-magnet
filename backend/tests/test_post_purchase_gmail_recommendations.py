import os
import sys
import unittest
from datetime import datetime, timezone, timedelta
from bson import ObjectId

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module
from marketing_automation_service import (
    send_post_purchase_smart_recommendation_email,
    evaluate_periodic_post_purchase_recommendations,
)
from communication_provider import DryRunCommunicationProvider


class PostPurchaseSmartRecommendationEmailTests(unittest.TestCase):
    def setUp(self):
        self.client = app_module.app.test_client()
        self.db = app_module.db
        self.profiles = app_module.profiles_collection
        self.products = app_module.products_collection
        self.orders = app_module.orders_collection
        self.lead_state = app_module.customer_lead_state_collection
        self.comms = self.db["marketing_communications"]
        self.notifs = self.db["admin_notifications"]
        self.provider = DryRunCommunicationProvider()
        self.test_ids = []

    def tearDown(self):
        for tid in self.test_ids:
            self.profiles.delete_many({"_id": tid})
            self.lead_state.delete_many({"customer_id": tid})
            self.orders.delete_many({"user_id": tid})
            self.comms.delete_many({"customer_id": tid})
            self.notifs.delete_many({"customer_id": str(tid)})
            self.products.delete_many({"_id": tid})

    def test_post_purchase_recommendation_email_same_brand_and_lower_price_alternative(self):
        """Test sending post-purchase recommendations:
        - Customer ordered 'RARE RABBIT Men Casual Shirt' (₹1035, brand RARE RABBIT, category Shirts)
        - Recommends:
          1. Same brand choice: Another shirt from RARE RABBIT
          2. Different brand choice: High-quality shirt from Highlander at ₹699 (lower price)
        """
        customer_id = ObjectId()
        self.test_ids.append(customer_id)

        # 1. Profile with email
        self.profiles.insert_one({
            "_id": customer_id,
            "email": "fashion_lover@example.com",
            "full_name": "Kiran Patel",
        })

        # 2. Seed products in Shirts category
        pid_ordered = ObjectId()
        pid_same_brand = ObjectId()
        pid_lower_price = ObjectId()
        self.test_ids.extend([pid_ordered, pid_same_brand, pid_lower_price])

        self.products.insert_one({
            "_id": pid_ordered,
            "product_id": "shirt_ordered_01",
            "title": "RARE RABBIT Men Casual Shirt",
            "category": "Shirts",
            "brand": "RARE RABBIT",
            "price": 1035.0,
            "rating": 4.4,
        })
        self.products.insert_one({
            "_id": pid_same_brand,
            "product_id": "shirt_same_brand_02",
            "title": "RARE RABBIT Oxford Cotton Shirt",
            "category": "Shirts",
            "brand": "RARE RABBIT",
            "price": 1079.0,
            "rating": 4.5,
        })
        self.products.insert_one({
            "_id": pid_lower_price,
            "product_id": "shirt_lower_price_03",
            "title": "Highlander Regular Fit Casual Shirt",
            "category": "Shirts",
            "brand": "Highlander",
            "price": 649.0,
            "rating": 4.3,
        })

        # 3. Customer completed order for RARE RABBIT Men Casual Shirt
        self.orders.insert_one({
            "_id": ObjectId(),
            "user_id": customer_id,
            "status": "delivered",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "items": [
                {
                    "product_id": "shirt_ordered_01",
                    "name": "RARE RABBIT Men Casual Shirt",
                    "category": "Shirts",
                    "brand": "RARE RABBIT",
                    "price": 1035.0,
                }
            ],
            "total_amount": 1035.0,
        })

        # 4. Dispatch post-purchase smart recommendation email
        res = send_post_purchase_smart_recommendation_email(
            customer_id=customer_id,
            db=self.db,
            provider=self.provider,
            force=True,
        )

        self.assertEqual(res["status"], "sent")
        self.assertEqual(res["ordered_item"]["brand"], "RARE RABBIT")
        self.assertEqual(res["ordered_item"]["category"], "Shirts")

        # Verify same-brand recommendation
        same_brand = res["same_brand_recommendation"]
        self.assertEqual(same_brand["brand"], "RARE RABBIT")
        self.assertEqual(same_brand["product_id"], "shirt_same_brand_02")

        # Verify lower-price recommendation
        lower_price = res["lower_price_recommendation"]
        self.assertEqual(lower_price["brand"], "Highlander")
        self.assertEqual(lower_price["product_id"], "shirt_lower_price_03")
        self.assertLess(lower_price["price"], 1035.0)
        self.assertGreater(res["savings_amount"], 0)
        self.assertEqual(res["savings_amount"], 1035.0 - 649.0)

        # Verify communication record in db
        comm = self.comms.find_one({"customer_id": customer_id, "campaign_type": "post_purchase_smart_recommendations"})
        self.assertIsNotNone(comm)
        self.assertEqual(comm["status"], "sent")
        self.assertEqual(comm["recipient"], "fashion_lover@example.com")
        self.assertIn("RARE RABBIT", comm["subject"])

        # Verify admin notification recorded
        notif = self.notifs.find_one({"customer_id": str(customer_id), "type": "post_purchase_smart_recommendations"})
        self.assertIsNotNone(notif)
        self.assertIn("RARE RABBIT", notif["message"])

    def test_periodic_post_purchase_evaluation(self):
        """Test scanning converted customers and running batch evaluation."""
        customer_id = ObjectId()
        self.test_ids.append(customer_id)

        self.profiles.insert_one({
            "_id": customer_id,
            "email": "periodic_buyer@example.com",
            "full_name": "Pooja Hegde",
        })

        self.lead_state.insert_one({
            "customer_id": customer_id,
            "lifecycle_status": "converted",
            "qualification_status": "not_qualified",
        })

        self.orders.insert_one({
            "_id": ObjectId(),
            "user_id": customer_id,
            "status": "delivered",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "items": [
                {
                    "product_id": "dress_01",
                    "name": "aayu Ruffled Chiffon Maxi Dress",
                    "category": "Dresses",
                    "brand": "aayu",
                    "price": 789.0,
                }
            ],
            "total_amount": 789.0,
        })

        batch_res = evaluate_periodic_post_purchase_recommendations(
            db=self.db,
            provider=self.provider,
            max_customers=10,
        )

        self.assertEqual(batch_res["status"], "completed")
        self.assertGreaterEqual(batch_res["converted_customers_scanned"], 1)

    def test_trigger_post_purchase_email_api_route(self):
        """Test POST /api/marketing/trigger-post-purchase-email endpoint."""
        customer_id = ObjectId()
        self.test_ids.append(customer_id)

        self.profiles.insert_one({
            "_id": customer_id,
            "email": "api_buyer@example.com",
            "full_name": "Siddharth Roy",
        })
        self.orders.insert_one({
            "_id": ObjectId(),
            "user_id": customer_id,
            "status": "delivered",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "items": [
                {
                    "product_id": "test_jacket_01",
                    "name": "Roadster Biker Jacket",
                    "category": "Jackets",
                    "brand": "Roadster",
                    "price": 2999.0,
                }
            ],
            "total_amount": 2999.0,
        })

        resp = self.client.post(
            "/api/marketing/trigger-post-purchase-email",
            json={"customer_id": str(customer_id), "force": True},
        )
        self.assertEqual(resp.status_code, 200, resp.get_json())
        data = resp.get_json()
        self.assertTrue(data["success"])


if __name__ == "__main__":
    unittest.main()
