"""Unit tests for Myntra product synchronization service.

Tests first insertion, existing update, unchanged price, price decrease/increase,
image persistence, duplicate prevention, and previous/current price tracking.
All tests use mock/in-memory data with zero ReefAPI credits or network calls.
"""

import copy
import unittest
from unittest.mock import patch

from myntra_product_sync_service import (
    MyntraProductSyncService,
    ensure_myntra_product_indexes,
    sync_myntra_products,
    sync_single_product,
)


class MockCollection:
    """In-memory collection mock implementing MongoDB collection methods."""

    def __init__(self):
        self.docs = {}
        self.indexes = {}

    def create_index(self, keys, name=None, unique=False, **kwargs):
        idx_name = name or "_".join(f"{k}_{d}" for k, d in keys)
        self.indexes[idx_name] = {"keys": keys, "unique": unique, "name": idx_name}
        return idx_name

    def list_indexes(self):
        return [{"name": name, **meta} for name, meta in self.indexes.items()]

    def find_one(self, query):
        p_id = query.get("product_id")
        if p_id in self.docs:
            return copy.deepcopy(self.docs[p_id])
        return None

    def find(self, query=None):
        if not query:
            return [copy.deepcopy(d) for d in self.docs.values()]
        results = []
        for d in self.docs.values():
            match = True
            for k, v in query.items():
                if d.get(k) != v:
                    match = False
                    break
            if match:
                results.append(copy.deepcopy(d))
        return results

    def update_one(self, query, update, upsert=False):
        p_id = query.get("product_id")
        set_data = update.get("$set", {})
        if p_id in self.docs:
            self.docs[p_id].update(copy.deepcopy(set_data))
        elif upsert:
            self.docs[p_id] = copy.deepcopy(set_data)
        return True

    def count_documents(self, query=None):
        return len(self.find(query))


class TestMyntraProductSyncService(unittest.TestCase):
    """Test suite for live Myntra product synchronization."""

    def setUp(self):
        self.collection = MockCollection()
        ensure_myntra_product_indexes(self.collection)
        self.sync_service = MyntraProductSyncService(collection=self.collection)

        self.sample_product = {
            "product_id": "myntra_28420390",
            "source_product_id": "28420390",
            "source": "myntra",
            "title": "Pure Cotton Casual Shirt",
            "brand": "Roadster",
            "category": "Shirts",
            "gender": "men",
            "url": "https://www.myntra.com/shirts/roadster/28420390/buy",
            "primary_image": "https://assets.myntassets.com/img1.jpg",
            "images": [
                "https://assets.myntassets.com/img1.jpg",
                "https://assets.myntassets.com/img2.jpg",
            ],
            "price": 799,
            "mrp": 1599,
            "price_before_discount": 1599,
            "discount_amount": 800,
            "discount_percent": 50,
            "currency": "INR",
            "rating": 4.2,
            "stock": 25,
            "availability_status": "in_stock",
        }

    def test_first_product_insertion(self):
        """First sync: previous_price=null, current_price=fetched price, no price drop."""
        report = self.sync_service.sync_products([self.sample_product])

        self.assertEqual(report["inserted_count"], 1)
        self.assertEqual(report["updated_count"], 0)
        self.assertEqual(len(report["price_drops"]), 0)
        self.assertEqual(len(report["price_increases"]), 0)

        saved = self.collection.find_one({"product_id": "myntra_28420390"})
        self.assertIsNotNone(saved)
        self.assertIsNone(saved["previous_price"])
        self.assertEqual(saved["current_price"], 799)
        self.assertEqual(saved["price_history"], [])
        self.assertIsNotNone(saved["first_seen_at"])
        self.assertIsNotNone(saved["last_synced_at"])
        self.assertEqual(saved["title"], "Pure Cotton Casual Shirt")

    def test_existing_product_update(self):
        """Updating existing product updates details without resetting first_seen_at."""
        self.sync_service.sync_products([self.sample_product])
        first_doc = self.collection.find_one({"product_id": "myntra_28420390"})
        original_first_seen = first_doc["first_seen_at"]

        # Update product title and stock
        updated_input = copy.deepcopy(self.sample_product)
        updated_input["title"] = "Updated Premium Shirt"
        updated_input["stock"] = 10

        report = self.sync_service.sync_products([updated_input])
        self.assertEqual(report["inserted_count"], 0)
        self.assertEqual(report["updated_count"], 1)

        saved = self.collection.find_one({"product_id": "myntra_28420390"})
        self.assertEqual(saved["title"], "Updated Premium Shirt")
        self.assertEqual(saved["stock"], 10)
        self.assertEqual(saved["first_seen_at"], original_first_seen)

    def test_unchanged_price(self):
        """When price is unchanged, no price history entry is added."""
        # 1. First sync
        self.sync_service.sync_products([self.sample_product])

        # 2. Second sync with exact same price
        report = self.sync_service.sync_products([self.sample_product])
        self.assertEqual(report["updated_count"], 1)
        self.assertEqual(report["unchanged_count"], 1)
        self.assertEqual(len(report["price_drops"]), 0)
        self.assertEqual(len(report["price_increases"]), 0)

        saved = self.collection.find_one({"product_id": "myntra_28420390"})
        self.assertEqual(saved["current_price"], 799)
        self.assertEqual(saved["previous_price"], 799)
        self.assertEqual(saved["price_history"], [])

    def test_price_decrease(self):
        """Detects price decrease, updates previous/current price, and logs history."""
        # Initial price: 1000
        p1 = copy.deepcopy(self.sample_product)
        p1["price"] = 1000
        self.sync_service.sync_products([p1])

        # Later sync: price drops to 799
        p2 = copy.deepcopy(self.sample_product)
        p2["price"] = 799
        report = self.sync_service.sync_products([p2])

        self.assertEqual(len(report["price_drops"]), 1)
        drop_event = report["price_drops"][0]
        self.assertEqual(drop_event["product_id"], "myntra_28420390")
        self.assertEqual(drop_event["old_price"], 1000)
        self.assertEqual(drop_event["new_price"], 799)
        self.assertEqual(drop_event["change_type"], "drop")

        saved = self.collection.find_one({"product_id": "myntra_28420390"})
        self.assertEqual(saved["previous_price"], 1000)
        self.assertEqual(saved["current_price"], 799)
        self.assertEqual(len(saved["price_history"]), 1)
        self.assertEqual(saved["price_history"][0]["old_price"], 1000)
        self.assertEqual(saved["price_history"][0]["new_price"], 799)

    def test_price_increase(self):
        """Detects price increase, updates previous/current price, and logs history."""
        # Initial price: 600
        p1 = copy.deepcopy(self.sample_product)
        p1["price"] = 600
        self.sync_service.sync_products([p1])

        # Later sync: price rises to 850
        p2 = copy.deepcopy(self.sample_product)
        p2["price"] = 850
        report = self.sync_service.sync_products([p2])

        self.assertEqual(len(report["price_increases"]), 1)
        inc_event = report["price_increases"][0]
        self.assertEqual(inc_event["product_id"], "myntra_28420390")
        self.assertEqual(inc_event["old_price"], 600)
        self.assertEqual(inc_event["new_price"], 850)
        self.assertEqual(inc_event["change_type"], "increase")

        saved = self.collection.find_one({"product_id": "myntra_28420390"})
        self.assertEqual(saved["previous_price"], 600)
        self.assertEqual(saved["current_price"], 850)
        self.assertEqual(len(saved["price_history"]), 1)
        self.assertEqual(saved["price_history"][0]["old_price"], 600)
        self.assertEqual(saved["price_history"][0]["new_price"], 850)

    def test_image_persistence(self):
        """Primary image and fallback preservation."""
        self.sync_service.sync_products([self.sample_product])
        saved = self.collection.find_one({"product_id": "myntra_28420390"})
        self.assertEqual(saved["primary_image"], "https://assets.myntassets.com/img1.jpg")

        # Sync again with empty images field (e.g. sparse detail response)
        sparse = copy.deepcopy(self.sample_product)
        sparse["primary_image"] = None
        sparse["images"] = []
        self.sync_service.sync_products([sparse])

        # Verify images were NOT lost
        resaved = self.collection.find_one({"product_id": "myntra_28420390"})
        self.assertEqual(resaved["primary_image"], "https://assets.myntassets.com/img1.jpg")
        self.assertEqual(len(resaved["images"]), 2)

    def test_multiple_images_persistence(self):
        """Preserves complete image array in original order."""
        images_list = [
            "https://assets.myntassets.com/img1.jpg",
            "https://assets.myntassets.com/img2.jpg",
            "https://assets.myntassets.com/img3.jpg",
            "https://assets.myntassets.com/img4.jpg",
            "https://assets.myntassets.com/img5.jpg",
        ]
        multi_img_prod = copy.deepcopy(self.sample_product)
        multi_img_prod["images"] = images_list
        multi_img_prod["primary_image"] = images_list[0]

        self.sync_service.sync_products([multi_img_prod])
        saved = self.collection.find_one({"product_id": "myntra_28420390"})
        self.assertEqual(saved["images"], images_list)
        self.assertEqual(saved["primary_image"], images_list[0])

    def test_duplicate_product_prevention(self):
        """Syncing the same product multiple times does not create duplicates."""
        for _ in range(3):
            self.sync_service.sync_products([self.sample_product])

        count = self.collection.count_documents({"product_id": "myntra_28420390"})
        self.assertEqual(count, 1)

    def test_previous_price_current_price_multi_step_progression(self):
        """Full lifecycle price progression tracking across multiple sync iterations."""
        pid = "myntra_28420390"

        # Step 1: Initial sync @ 1200
        p = copy.deepcopy(self.sample_product)
        p["price"] = 1200
        self.sync_service.sync_products([p])
        doc = self.collection.find_one({"product_id": pid})
        self.assertIsNone(doc["previous_price"])
        self.assertEqual(doc["current_price"], 1200)
        self.assertEqual(len(doc["price_history"]), 0)

        # Step 2: Drop to 1000
        p["price"] = 1000
        self.sync_service.sync_products([p])
        doc = self.collection.find_one({"product_id": pid})
        self.assertEqual(doc["previous_price"], 1200)
        self.assertEqual(doc["current_price"], 1000)
        self.assertEqual(len(doc["price_history"]), 1)

        # Step 3: Unchanged @ 1000
        self.sync_service.sync_products([p])
        doc = self.collection.find_one({"product_id": pid})
        self.assertEqual(doc["previous_price"], 1000)
        self.assertEqual(doc["current_price"], 1000)
        self.assertEqual(len(doc["price_history"]), 1)

        # Step 4: Drop to 850
        p["price"] = 850
        self.sync_service.sync_products([p])
        doc = self.collection.find_one({"product_id": pid})
        self.assertEqual(doc["previous_price"], 1000)
        self.assertEqual(doc["current_price"], 850)
        self.assertEqual(len(doc["price_history"]), 2)

        # Step 5: Increase to 950
        p["price"] = 950
        self.sync_service.sync_products([p])
        doc = self.collection.find_one({"product_id": pid})
        self.assertEqual(doc["previous_price"], 850)
        self.assertEqual(doc["current_price"], 950)
        self.assertEqual(len(doc["price_history"]), 3)

        # Validate history entries order and values
        history = doc["price_history"]
        self.assertEqual(history[0]["old_price"], 1200)
        self.assertEqual(history[0]["new_price"], 1000)
        self.assertEqual(history[1]["old_price"], 1000)
        self.assertEqual(history[1]["new_price"], 850)
        self.assertEqual(history[2]["old_price"], 850)
        self.assertEqual(history[2]["new_price"], 950)

    def test_raw_reefapi_data_sync(self):
        """Sync accepts raw ReefAPI search results and normalizes them automatically."""
        raw_reef_item = {
            "product_id": "999888",
            "title": "Raw ReefAPI Cotton Hoodie",
            "brand": "HRX",
            "price": 1299,
            "mrp": 2599,
            "image": "https://assets.myntassets.com/raw_hoodie.jpg",
        }
        report = self.sync_service.sync_products([raw_reef_item])
        self.assertEqual(report["inserted_count"], 1)

        saved = self.collection.find_one({"product_id": "myntra_999888"})
        self.assertIsNotNone(saved)
        self.assertEqual(saved["source"], "myntra")
        self.assertEqual(saved["source_product_id"], "999888")
        self.assertEqual(saved["primary_image"], "https://assets.myntassets.com/raw_hoodie.jpg")
        self.assertEqual(saved["current_price"], 1299)
        self.assertIsNone(saved["previous_price"])

    def test_indexes_registered(self):
        """Indexes for source_product_id, category, brand, current_price, last_synced_at exist."""
        idx_names = {idx["name"] for idx in self.collection.list_indexes()}
        expected = {
            "product_id_1",
            "source_product_id_1",
            "category_1",
            "brand_1",
            "current_price_1",
            "last_synced_at_-1",
        }
        self.assertTrue(expected.issubset(idx_names))

    def test_sync_search_queries_deduplication_and_stats(self):
        """Tests sync_search_queries executes queries, deduplicates by canonical ID, and upserts."""
        class MockReefClient:
            def __init__(self):
                self.calls = []

            def search_products(self, query, limit=50):
                self.calls.append((query, limit))
                if query == "query1":
                    return {
                        "ok": True,
                        "products": [
                            {"product_id": "myntra_101", "source_product_id": "101", "title": "Shirt 1", "price": 500, "source": "myntra"},
                            {"product_id": "myntra_102", "source_product_id": "102", "title": "Shirt 2", "price": 600, "source": "myntra"},
                        ],
                    }
                elif query == "query2":
                    return {
                        "ok": True,
                        "products": [
                            # Duplicate of 101 from query1
                            {"product_id": "myntra_101", "source_product_id": "101", "title": "Shirt 1", "price": 500, "source": "myntra"},
                            {"product_id": "myntra_103", "source_product_id": "103", "title": "Dress 1", "price": 900, "source": "myntra"},
                        ],
                    }
                return {"ok": True, "products": []}

        mock_client = MockReefClient()
        report = self.sync_service.sync_search_queries(
            api_client=mock_client,
            queries=["query1", "query2"],
            limit=50,
        )

        self.assertEqual(report["search_calls_made"], 2)
        self.assertEqual(report["credits_consumed"], 2)
        self.assertEqual(report["total_products_fetched"], 4)
        self.assertEqual(report["deduplicated_count"], 3)
        self.assertEqual(report["inserted_count"], 3)
        self.assertEqual(report["updated_count"], 0)
        self.assertEqual(len(report["failures"]), 0)

        # Confirm all 3 unique items exist in collection
        self.assertIsNotNone(self.collection.find_one({"product_id": "myntra_101"}))
        self.assertIsNotNone(self.collection.find_one({"product_id": "myntra_102"}))
        self.assertIsNotNone(self.collection.find_one({"product_id": "myntra_103"}))


if __name__ == "__main__":
    unittest.main()

