import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import unittest
from bson import ObjectId

from app import app, ensure_product_indexes, products_collection


class ProductsEndpointTests(unittest.TestCase):
    def setUp(self):
        import app as app_mod
        self.client = app.test_client()
        self.orig_col = app_mod.products_collection
        self.test_col = app_mod.db["products_unit_test"]
        app_mod.products_collection = self.test_col
        self.test_col.delete_many({})

    def tearDown(self):
        import app as app_mod
        self.test_col.delete_many({})
        app_mod.products_collection = self.orig_col

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
        self.test_col.insert_one(product_doc)

        r = self.client.get(f"/api/products/{product_id}")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["data"]["name"], "Test Product")

        bad = self.client.get("/api/products/not-a-valid-objectid")
        self.assertEqual(bad.status_code, 404)
        self.assertFalse(bad.get_json()["success"])

    def test_products_category_filter_only_returns_matching_items(self):
        self.test_col.insert_many([
            {"name": "Shirt A", "category": "shirts", "brand": "BrandA", "price": 1200, "image": "https://example.com/shirt.jpg"},
            {"name": "Shirt B", "category": "shirts", "brand": "BrandB", "price": 1500, "image": "https://example.com/shirt2.jpg"},
            {"name": "Shoe A", "category": "shoes", "brand": "BrandC", "price": 2100, "image": "https://example.com/shoe.jpg"},
        ])

        r = self.client.get("/api/products?category=shirts")
        self.assertEqual(r.status_code, 200)
        results = r.get_json()["data"]
        self.assertEqual(len(results), 2)
        self.assertTrue(all(item["category"] == "shirts" for item in results))

    def test_products_pagination_and_query_filters(self):
        self.test_col.insert_many([
            {"product_id": "prod_001", "name": "Roadster Slim Jeans", "category": "Jeans", "brand": "Roadster", "gender": "Men", "price": 999, "rating": 4.2},
            {"product_id": "prod_002", "name": "Roadster Denim Jacket", "category": "Jackets & Coats", "brand": "Roadster", "gender": "Men", "price": 1999, "rating": 4.6},
            {"product_id": "prod_003", "name": "Sangria Printed Kurta", "category": "Kurtas & Kurta Sets", "brand": "Sangria", "gender": "Women", "price": 1299, "rating": 4.5},
            {"product_id": "prod_004", "name": "H&M Cotton T-Shirt", "category": "T-Shirts", "brand": "H&M", "gender": "Men", "price": 599, "rating": 3.8},
        ])

        # Test pagination structure
        r = self.client.get("/api/products?page=1&limit=2")
        self.assertEqual(r.status_code, 200)
        res = r.get_json()
        self.assertEqual(len(res["data"]), 2)
        self.assertEqual(res["pagination"]["page"], 1)
        self.assertEqual(res["pagination"]["limit"], 2)
        self.assertEqual(res["pagination"]["total"], 4)
        self.assertEqual(res["pagination"]["pages"], 2)

        # Test brand filter
        r_brand = self.client.get("/api/products?brand=Roadster")
        self.assertEqual(r_brand.status_code, 200)
        self.assertEqual(len(r_brand.get_json()["data"]), 2)

        # Test search filter
        r_search = self.client.get("/api/products?search=kurta")
        self.assertEqual(r_search.status_code, 200)
        self.assertEqual(len(r_search.get_json()["data"]), 1)
        self.assertEqual(r_search.get_json()["data"][0]["brand"], "Sangria")

        # Test max price filter
        r_price = self.client.get("/api/products?max_price=1000")
        self.assertEqual(r_price.status_code, 200)
        for item in r_price.get_json()["data"]:
            self.assertLessEqual(item["price"], 1000)

        # Test string product_id lookup
        r_str_id = self.client.get("/api/products/prod_003")
        self.assertEqual(r_str_id.status_code, 200)
        self.assertEqual(r_str_id.get_json()["data"]["name"], "Sangria Printed Kurta")


if __name__ == "__main__":
    unittest.main()
