import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import unittest
from bson import ObjectId

from app import app, ensure_product_indexes, products_collection


class ProductsEndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        products_collection.delete_many({})

    def test_products_collection_has_safe_indexes(self):
        ensure_product_indexes(products_collection)
        index_names = {index["name"] for index in products_collection.list_indexes()}
        self.assertTrue({"category_1", "name_1", "brand_1"}.issubset(index_names))

    def test_get_products_with_empty_catalog(self):
        r = self.client.get("/api/products")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json().get("data", []), [])

        r2 = self.client.get("/api/products?category=men")
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.get_json().get("data", []), [])

    def test_valid_product_lookup_and_malformed_id(self):
        product_id = ObjectId()
        product_doc = {
            "_id": product_id,
            "name": "Test Product",
            "category": "shirts",
            "brand": "TestBrand",
            "price": 1999,
            "image": "https://example.com/test.jpg",
            "stock": 10,
            "description": "Valid test product",
        }
        products_collection.insert_one(product_doc)

        r = self.client.get(f"/api/products/{product_id}")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["data"]["name"], "Test Product")

        bad = self.client.get("/api/products/not-a-valid-objectid")
        self.assertEqual(bad.status_code, 404)
        self.assertFalse(bad.get_json()["success"])

    def test_products_category_filter_only_returns_matching_items(self):
        products_collection.insert_many([
            {"name": "Shirt A", "category": "shirts", "brand": "BrandA", "price": 1200, "image": "https://example.com/shirt.jpg"},
            {"name": "Shirt B", "category": "shirts", "brand": "BrandB", "price": 1500, "image": "https://example.com/shirt2.jpg"},
            {"name": "Shoe A", "category": "shoes", "brand": "BrandC", "price": 2100, "image": "https://example.com/shoe.jpg"},
        ])

        r = self.client.get("/api/products?category=shirts")
        self.assertEqual(r.status_code, 200)
        results = r.get_json()["data"]
        self.assertEqual(len(results), 2)
        self.assertTrue(all(item["category"] == "shirts" for item in results))


if __name__ == "__main__":
    unittest.main()
