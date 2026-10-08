"""Unit tests for credit-efficient dynamic Myntra catalog refresh service.

Tests all required policies and guardrails:
  1. refresh is skipped when not due
  2. refresh executes when due
  3. configured API call limit is respected
  4. batch search results are deduplicated
  5. price unchanged -> no price-history entry
  6. price changed -> previous/current price updated correctly
  7. existing product images are preserved when new response lacks images
  8. no more than the configured ReefAPI calls are made
  9. no individual detail call is made for every product
 10. no deletion of existing products occurs

Zero network calls, zero ReefAPI credits consumed.
"""

import copy
import datetime
import unittest

from myntra_catalog_refresh_service import (
    DEFAULT_GENERAL_QUERIES,
    DEFAULT_GENERAL_REFRESH_INTERVAL_DAYS,
    METADATA_COLLECTION_NAME,
    METADATA_DOC_ID,
    get_catalog_sync_metadata,
    get_priority_customer_product_ids,
    is_refresh_due,
    run_catalog_refresh,
)


class MockCollection:
    """In-memory collection mock for MongoDB collections."""

    def __init__(self, name="collection"):
        self.name = name
        self.docs = {}
        self.indexes = {}

    def create_index(self, keys, name=None, unique=False, **kwargs):
        idx_name = name or "_".join(f"{k}_{d}" for k, d in keys)
        self.indexes[idx_name] = {"keys": keys, "unique": unique, "name": idx_name}
        return idx_name

    def list_indexes(self):
        return [{"name": name, **meta} for name, meta in self.indexes.items()]

    def count_documents(self, query=None):
        if not query:
            return len(self.docs)
        return len(self.find(query))

    def find_one(self, query=None, sort=None):
        if not query:
            if not self.docs:
                return None
            return copy.deepcopy(next(iter(self.docs.values())))

        # Direct _id match
        if "_id" in query:
            val = query["_id"]
            if val in self.docs:
                return copy.deepcopy(self.docs[val])
            return None

        # Direct product_id match
        p_id = query.get("product_id")
        if p_id and p_id in self.docs:
            return copy.deepcopy(self.docs[p_id])

        # $or match
        if "$or" in query:
            for branch in query["$or"]:
                res = self.find_one(branch)
                if res:
                    return res
            return None

        for doc in self.docs.values():
            match = True
            for k, v in query.items():
                if k == "last_synced_at" and isinstance(v, dict) and "$ne" in v:
                    if doc.get("last_synced_at") == v["$ne"]:
                        match = False
                        break
                elif doc.get(k) != v:
                    match = False
                    break
            if match:
                return copy.deepcopy(doc)
        return None

    def find(self, query=None, projection=None):
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
        key = query.get("_id") or query.get("product_id")
        set_data = update.get("$set", {})
        if key and key in self.docs:
            self.docs[key].update(copy.deepcopy(set_data))
        elif key and upsert:
            new_doc = copy.deepcopy(query)
            new_doc.update(copy.deepcopy(set_data))
            self.docs[key] = new_doc
        elif upsert:
            auto_key = f"mock_{len(self.docs) + 1}"
            new_doc = copy.deepcopy(query)
            new_doc.update(copy.deepcopy(set_data))
            new_doc["_id"] = auto_key
            self.docs[auto_key] = new_doc

    def delete_one(self, query):
        key = query.get("_id") or query.get("product_id")
        if key and key in self.docs:
            del self.docs[key]

    def delete_many(self, query):
        for d in list(self.find(query)):
            k = d.get("_id") or d.get("product_id")
            if k in self.docs:
                del self.docs[k]


class MockDB:
    """Mock MongoDB database returning collections."""

    def __init__(self):
        self.collections = {
            "myntra_products": MockCollection("myntra_products"),
            METADATA_COLLECTION_NAME: MockCollection(METADATA_COLLECTION_NAME),
            "cart": MockCollection("cart"),
            "wishlist": MockCollection("wishlist"),
        }

    def __getitem__(self, item):
        if item not in self.collections:
            self.collections[item] = MockCollection(item)
        return self.collections[item]


class MockReefAPIClient:
    """Mock ReefAPI client tracking search calls and verifying detail is never called."""

    def __init__(self, search_responses=None):
        self.search_calls = []
        self.detail_calls = []
        self.search_responses = search_responses or {}

    def search_products(self, query, limit=50, **kwargs):
        self.search_calls.append({"query": query, "limit": limit})
        if query in self.search_responses:
            return copy.deepcopy(self.search_responses[query])
        # Default mock items
        return {
            "ok": True,
            "products": [
                {
                    "product_id": f"myntra_{query.replace(' ', '_')}_01",
                    "source_product_id": f"{query.replace(' ', '_')}_01",
                    "title": f"Mock Item for {query}",
                    "brand": "Roadster",
                    "category": "Shirts",
                    "price": 899,
                    "mrp": 1599,
                    "primary_image": "https://assets.myntassets.com/img1.jpg",
                    "images": ["https://assets.myntassets.com/img1.jpg"],
                    "url": f"https://www.myntra.com/{query.replace(' ', '-')}/01",
                    "source": "myntra",
                }
            ],
            "total_results": 1,
        }

    def get_product_detail(self, product_id):
        # Tracking detail calls to ensure they are NEVER made
        self.detail_calls.append(product_id)
        return {"ok": True, "product": {}}


class TestMyntraCatalogRefreshService(unittest.TestCase):
    """Test suite for Myntra Catalog Refresh Service."""

    def setUp(self):
        self.mock_db = MockDB()
        self.products_col = self.mock_db["myntra_products"]
        self.meta_col = self.mock_db[METADATA_COLLECTION_NAME]

        # Seed initial catalog with 2 existing products
        self.products_col.docs["myntra_1001"] = {
            "_id": "myntra_1001",
            "product_id": "myntra_1001",
            "source_product_id": "1001",
            "title": "Classic Cotton Shirt",
            "brand": "Roadster",
            "category": "Shirts",
            "price": 999,
            "current_price": 999,
            "previous_price": None,
            "price_history": [],
            "primary_image": "https://assets.myntassets.com/existing_shirt.jpg",
            "images": ["https://assets.myntassets.com/existing_shirt.jpg"],
            "url": "https://www.myntra.com/shirts/1001",
            "last_synced_at": "2026-10-01T12:00:00+00:00",
        }
        self.products_col.docs["myntra_1002"] = {
            "_id": "myntra_1002",
            "product_id": "myntra_1002",
            "source_product_id": "1002",
            "title": "Floral Summer Dress",
            "brand": "Tokyo Talkies",
            "category": "Dresses",
            "price": 1499,
            "current_price": 1499,
            "previous_price": None,
            "price_history": [],
            "primary_image": "https://assets.myntassets.com/existing_dress.jpg",
            "images": ["https://assets.myntassets.com/existing_dress.jpg"],
            "url": "https://www.myntra.com/dresses/1002",
            "last_synced_at": "2026-10-01T12:00:00+00:00",
        }

    def test_refresh_skipped_when_not_due(self):
        """1. When elapsed time < general_interval_days (15d), refresh is skipped."""
        now = datetime.datetime(2026, 10, 8, 12, 0, 0, tzinfo=datetime.timezone.utc)
        # Last refresh was 3 days ago (2026-10-05) -> Not due (12 days remaining)
        self.meta_col.docs[METADATA_DOC_ID] = {
            "_id": METADATA_DOC_ID,
            "last_general_refresh_at": "2026-10-05T12:00:00+00:00",
        }

        due, reason, elapsed = is_refresh_due(db=self.mock_db, now=now, interval_days=15)
        self.assertFalse(due)
        self.assertIn("Refresh skipped", reason)
        self.assertAlmostEqual(elapsed, 3.0, places=1)

        # Execute refresh with force=False -> must skip without calling API
        mock_client = MockReefAPIClient()
        report = run_catalog_refresh(
            force=False,
            api_client=mock_client,
            db=self.mock_db,
            products_collection=self.products_col,
            now=now,
        )

        self.assertEqual(report["status"], "skipped")
        self.assertEqual(report["calls_made"], 0)
        self.assertEqual(report["credits_consumed"], 0)
        self.assertEqual(len(mock_client.search_calls), 0)

    def test_refresh_executes_when_due(self):
        """2. When elapsed time >= 15 days, refresh is due and executes."""
        now = datetime.datetime(2026, 10, 20, 12, 0, 0, tzinfo=datetime.timezone.utc)
        # Last refresh was 19 days ago (2026-10-01) -> Due
        self.meta_col.docs[METADATA_DOC_ID] = {
            "_id": METADATA_DOC_ID,
            "last_general_refresh_at": "2026-10-01T12:00:00+00:00",
        }

        due, reason, elapsed = is_refresh_due(db=self.mock_db, now=now, interval_days=15)
        self.assertTrue(due)
        self.assertIn("Refresh due", reason)

        mock_client = MockReefAPIClient()
        report = run_catalog_refresh(
            force=False,
            max_calls=3,
            api_client=mock_client,
            db=self.mock_db,
            products_collection=self.products_col,
            now=now,
        )

        self.assertEqual(report["status"], "completed")
        self.assertEqual(report["calls_made"], 3)
        self.assertEqual(report["credits_consumed"], 3)
        self.assertEqual(len(mock_client.search_calls), 3)

    def test_configured_api_call_limit_is_respected(self):
        """3. Calling with max_calls=2 makes exactly 2 calls even with 5 queries."""
        mock_client = MockReefAPIClient()
        report = run_catalog_refresh(
            force=True,
            max_calls=2,
            general_queries=DEFAULT_GENERAL_QUERIES,
            api_client=mock_client,
            db=self.mock_db,
            products_collection=self.products_col,
        )

        self.assertEqual(report["calls_made"], 2)
        self.assertEqual(report["credits_consumed"], 2)
        self.assertEqual(len(mock_client.search_calls), 2)

    def test_batch_search_results_are_deduplicated(self):
        """4. Products returned in multiple queries are deduplicated by canonical ID."""
        dup_product = {
            "product_id": "myntra_shared_100",
            "source_product_id": "shared_100",
            "title": "Shared Casual Shirt",
            "brand": "Roadster",
            "category": "Shirts",
            "price": 799,
            "url": "https://www.myntra.com/shared/100",
            "primary_image": "https://assets.myntassets.com/shared.jpg",
            "source": "myntra",
        }

        mock_client = MockReefAPIClient(
            search_responses={
                "q1": {"ok": True, "products": [dup_product]},
                "q2": {"ok": True, "products": [dup_product]},
            }
        )

        report = run_catalog_refresh(
            force=True,
            max_calls=2,
            general_queries=["q1", "q2"],
            api_client=mock_client,
            db=self.mock_db,
            products_collection=self.products_col,
        )

        self.assertEqual(report["products_fetched"], 2)
        self.assertEqual(report["deduplicated_count"], 1)
        self.assertIn("myntra_shared_100", self.products_col.docs)

    def test_price_unchanged_no_price_history_entry(self):
        """5. Refreshed product with exact same price does NOT append to price_history."""
        existing_doc = self.products_col.docs["myntra_1001"]
        self.assertEqual(existing_doc["current_price"], 999)

        mock_client = MockReefAPIClient(
            search_responses={
                "men shirts": {
                    "ok": True,
                    "products": [
                        {
                            "product_id": "myntra_1001",
                            "source_product_id": "1001",
                            "title": "Classic Cotton Shirt",
                            "price": 999,  # Unchanged
                            "url": "https://www.myntra.com/shirts/1001",
                            "source": "myntra",
                        }
                    ],
                }
            }
        )

        report = run_catalog_refresh(
            force=True,
            max_calls=1,
            general_queries=["men shirts"],
            api_client=mock_client,
            db=self.mock_db,
            products_collection=self.products_col,
        )

        self.assertEqual(report["unchanged_count"], 1)
        saved = self.products_col.docs["myntra_1001"]
        self.assertEqual(saved["current_price"], 999)
        self.assertEqual(saved["previous_price"], 999)
        self.assertEqual(len(saved["price_history"]), 0)

    def test_price_changed_updates_previous_current_and_history(self):
        """6. Refreshed product with lower price updates previous/current price and appends history."""
        # Initial: current_price = 999
        mock_client = MockReefAPIClient(
            search_responses={
                "men shirts": {
                    "ok": True,
                    "products": [
                        {
                            "product_id": "myntra_1001",
                            "source_product_id": "1001",
                            "title": "Classic Cotton Shirt",
                            "price": 799,  # Dropped from 999 to 799
                            "url": "https://www.myntra.com/shirts/1001",
                            "source": "myntra",
                        }
                    ],
                }
            }
        )

        report = run_catalog_refresh(
            force=True,
            max_calls=1,
            general_queries=["men shirts"],
            api_client=mock_client,
            db=self.mock_db,
            products_collection=self.products_col,
            notify_price_drops=False,
        )

        self.assertEqual(report["price_drops_detected"], 1)
        saved = self.products_col.docs["myntra_1001"]
        self.assertEqual(saved["previous_price"], 999)
        self.assertEqual(saved["current_price"], 799)
        self.assertEqual(len(saved["price_history"]), 1)
        self.assertEqual(saved["price_history"][0]["old_price"], 999)
        self.assertEqual(saved["price_history"][0]["new_price"], 799)

    def test_existing_images_preserved_when_response_lacks_images(self):
        """7. Refreshed response with missing primary_image / images preserves existing image URLs."""
        # existing doc has https://assets.myntassets.com/existing_shirt.jpg
        mock_client = MockReefAPIClient(
            search_responses={
                "men shirts": {
                    "ok": True,
                    "products": [
                        {
                            "product_id": "myntra_1001",
                            "source_product_id": "1001",
                            "title": "Classic Cotton Shirt",
                            "price": 899,
                            "url": "https://www.myntra.com/shirts/1001",
                            "primary_image": None,  # Missing in new response
                            "images": [],           # Empty in new response
                            "source": "myntra",
                        }
                    ],
                }
            }
        )

        run_catalog_refresh(
            force=True,
            max_calls=1,
            general_queries=["men shirts"],
            api_client=mock_client,
            db=self.mock_db,
            products_collection=self.products_col,
        )

        saved = self.products_col.docs["myntra_1001"]
        self.assertEqual(saved["primary_image"], "https://assets.myntassets.com/existing_shirt.jpg")
        self.assertEqual(saved["images"], ["https://assets.myntassets.com/existing_shirt.jpg"])

    def test_no_more_than_configured_reef_calls_made(self):
        """8. Call count strictly bounded by effective max_calls (hard-capped at 10)."""
        mock_client = MockReefAPIClient()
        report = run_catalog_refresh(
            force=True,
            max_calls=99,  # Attempting runaway value
            general_queries=["q1", "q2", "q3", "q4", "q5", "q6", "q7", "q8", "q9", "q10", "q11", "q12"],
            api_client=mock_client,
            db=self.mock_db,
            products_collection=self.products_col,
        )

        # Must be hard-capped at 10
        self.assertLessEqual(report["calls_made"], 10)
        self.assertLessEqual(len(mock_client.search_calls), 10)

    def test_no_individual_detail_call_is_made_for_any_product(self):
        """9. Ensures ReefAPI /product/detail is NEVER invoked during catalog refresh."""
        mock_client = MockReefAPIClient()
        run_catalog_refresh(
            force=True,
            max_calls=5,
            api_client=mock_client,
            db=self.mock_db,
            products_collection=self.products_col,
        )

        self.assertEqual(len(mock_client.detail_calls), 0, "No product detail calls should ever be made!")

    def test_no_deletion_of_existing_products_occurs(self):
        """10. Unreturned existing products are never deleted from myntra_products."""
        # Initial products: myntra_1001 and myntra_1002
        self.assertEqual(self.products_col.count_documents({}), 2)

        # Search only returns myntra_1001
        mock_client = MockReefAPIClient(
            search_responses={
                "q": {
                    "ok": True,
                    "products": [
                        {
                            "product_id": "myntra_1001",
                            "source_product_id": "1001",
                            "title": "Classic Cotton Shirt",
                            "price": 999,
                            "url": "https://www.myntra.com/shirts/1001",
                            "source": "myntra",
                        }
                    ],
                }
            }
        )

        run_catalog_refresh(
            force=True,
            max_calls=1,
            general_queries=["q"],
            api_client=mock_client,
            db=self.mock_db,
            products_collection=self.products_col,
        )

        # myntra_1002 was NOT in the response, but must NOT be deleted
        self.assertIn("myntra_1001", self.products_col.docs)
        self.assertIn("myntra_1002", self.products_col.docs)
        self.assertEqual(self.products_col.count_documents({}), 2)


if __name__ == "__main__":
    unittest.main()
