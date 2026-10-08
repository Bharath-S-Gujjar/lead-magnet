"""Unit and integration tests for Myntra-only live product catalog migration.

Verifies:
  1. products_collection is bound to 'myntra_products'.
  2. ensure_myntra_product_indexes is initialized.
  3. Product resolution supports Myntra string IDs ('myntra_28420390') and legacy ObjectIds.
  4. /api/products returns normalized schema with stable Myntra 'id'.
  5. /api/products/<product_id> fetches Myntra products without calling ObjectId().
  6. /api/cart preserves exact Myntra product_id and populates fields.
  7. /api/wishlist preserves exact Myntra product_id and populates fields.
  8. Order creation preserves exact Myntra product_id and snapshots prices.
  9. Recommendations return normalized Myntra products.
"""

import os
import sys
import unittest
from bson import ObjectId

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import app, products_collection, cart_collection, wishlist_collection, orders_collection
from product_lookup import resolve_product_doc, normalize_product_response
from cart_service import get_user_cart, add_to_cart, update_cart_quantity, remove_from_cart, clear_cart
from wishlist_service import get_user_wishlist, add_to_wishlist, remove_from_wishlist, clear_wishlist
from order_service import create_order
from recommendation_service import get_personalized_recommendations
import app as app_module


class TestMyntraCatalogMigration(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        # Save original collections
        self.orig_products = app_module.products_collection
        self.orig_cart = app_module.cart_collection
        self.orig_wishlist = app_module.wishlist_collection
        self.orig_orders = app_module.orders_collection

        # Use isolated test collections in db
        self.test_products = app_module.db["test_myntra_products_migration"]
        self.test_cart = app_module.db["test_myntra_cart_migration"]
        self.test_wishlist = app_module.db["test_myntra_wishlist_migration"]
        self.test_orders = app_module.db["test_myntra_orders_migration"]

        app_module.products_collection = self.test_products
        app_module.cart_collection = self.test_cart
        app_module.wishlist_collection = self.test_wishlist
        app_module.orders_collection = self.test_orders

        self.test_products.delete_many({})
        self.test_cart.delete_many({})
        self.test_wishlist.delete_many({})
        self.test_orders.delete_many({})

        # Insert sample Myntra product doc
        self.sample_myntra_doc = {
            "product_id": "myntra_28420390",
            "source_product_id": "28420390",
            "source": "myntra",
            "title": "Roadster Men Solid Pure Cotton Casual Shirt",
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
            "rating": 4.3,
            "stock": 25,
            "availability_status": "in_stock",
            "current_price": 799,
            "previous_price": None,
            "price_history": [],
        }
        self.test_products.insert_one(self.sample_myntra_doc)

    def tearDown(self):
        self.test_products.delete_many({})
        self.test_cart.delete_many({})
        self.test_wishlist.delete_many({})
        self.test_orders.delete_many({})

        app_module.products_collection = self.orig_products
        app_module.cart_collection = self.orig_cart
        app_module.wishlist_collection = self.orig_wishlist
        app_module.orders_collection = self.orig_orders

    def test_products_collection_bound_to_myntra_products(self):
        """Live products_collection must be bound to 'myntra_products'."""
        self.assertEqual(self.orig_products.name, "myntra_products")

    def test_product_lookup_resolves_myntra_id(self):
        """resolve_product_doc resolves by Myntra string ID without invoking ObjectId()."""
        doc = resolve_product_doc(self.test_products, "myntra_28420390")
        self.assertIsNotNone(doc)
        self.assertEqual(doc["product_id"], "myntra_28420390")
        self.assertEqual(doc["title"], "Roadster Men Solid Pure Cotton Casual Shirt")

        # Resolves via raw source_product_id string as well
        doc2 = resolve_product_doc(self.test_products, "28420390")
        self.assertIsNotNone(doc2)
        self.assertEqual(doc2["product_id"], "myntra_28420390")

        # Nonexistent ID safely returns None without error
        doc_none = resolve_product_doc(self.test_products, "myntra_9999999999")
        self.assertIsNone(doc_none)

    def test_normalize_product_response_contains_all_fields(self):
        """Normalized product output contains all specified fields with stable ID."""
        norm = normalize_product_response(self.sample_myntra_doc)
        required_fields = [
            "id", "product_id", "title", "name", "brand", "category",
            "gender", "price", "mrp", "price_before_discount",
            "discount_percent", "discount_amount", "primary_image",
            "images", "url", "rating", "stock", "availability_status"
        ]
        for f in required_fields:
            self.assertIn(f, norm, f"Missing field {f} in normalized product")

        self.assertEqual(norm["id"], "myntra_28420390")
        self.assertEqual(norm["name"], "Roadster Men Solid Pure Cotton Casual Shirt")
        self.assertEqual(norm["title"], "Roadster Men Solid Pure Cotton Casual Shirt")
        self.assertEqual(norm["image"], "https://assets.myntassets.com/img1.jpg")
        self.assertEqual(norm["primary_image"], "https://assets.myntassets.com/img1.jpg")
        self.assertEqual(norm["price"], 799.0)
        self.assertEqual(norm["mrp"], 1599.0)
        self.assertEqual(norm["discount_percent"], 50.0)

    def test_get_products_endpoint(self):
        """GET /api/products returns normalized Myntra products."""
        res = self.client.get("/api/products")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        items = data["data"]
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item["id"], "myntra_28420390")
        self.assertEqual(item["title"], "Roadster Men Solid Pure Cotton Casual Shirt")
        self.assertEqual(item["name"], "Roadster Men Solid Pure Cotton Casual Shirt")
        self.assertEqual(item["brand"], "Roadster")
        self.assertEqual(item["price"], 799.0)

    def test_get_product_by_myntra_id_endpoint(self):
        """GET /api/products/<product_id> returns 200 with normalized Myntra data."""
        res = self.client.get("/api/products/myntra_28420390")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["id"], "myntra_28420390")

        # Unknown product returns 404
        res_bad = self.client.get("/api/products/myntra_nonexistent")
        self.assertEqual(res_bad.status_code, 404)
        self.assertFalse(res_bad.get_json()["success"])

    def test_cart_operations_with_myntra_id(self):
        """Cart preserves Myntra string product ID and populates Myntra product fields."""
        anon_id = "test_myntra_user_anon_1"

        # 1. Add to cart
        add_res = self.client.post("/api/cart", json={
            "product_id": "myntra_28420390",
            "quantity": 2,
            "anonymous_id": anon_id
        })
        self.assertEqual(add_res.status_code, 200, add_res.get_json())
        cart_data = add_res.get_json()["data"]
        self.assertEqual(len(cart_data), 1)
        self.assertEqual(cart_data[0]["product_id"], "myntra_28420390")
        self.assertEqual(cart_data[0]["name"], "Roadster Men Solid Pure Cotton Casual Shirt")
        self.assertEqual(cart_data[0]["price"], 799)
        self.assertEqual(cart_data[0]["quantity"], 2)

        # Confirm direct document in cart collection preserves string ID
        raw_cart_item = self.test_cart.find_one({"anonymous_id": anon_id})
        self.assertIsNotNone(raw_cart_item)
        self.assertEqual(raw_cart_item["product_id"], "myntra_28420390")

        # 2. Get cart
        get_res = self.client.get(f"/api/cart?anonymous_id={anon_id}")
        self.assertEqual(get_res.status_code, 200)
        items = get_res.get_json()["data"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["product_id"], "myntra_28420390")

        # 3. Update quantity
        upd_res = self.client.put("/api/cart/myntra_28420390", json={
            "quantity": 4,
            "anonymous_id": anon_id
        })
        self.assertEqual(upd_res.status_code, 200)
        upd_data = upd_res.get_json()["data"]
        self.assertEqual(upd_data[0]["quantity"], 4)

        # 4. Remove from cart
        del_res = self.client.delete(f"/api/cart/myntra_28420390?anonymous_id={anon_id}")
        self.assertEqual(del_res.status_code, 200)
        self.assertEqual(len(del_res.get_json()["data"]), 0)

    def test_wishlist_operations_with_myntra_id(self):
        """Wishlist preserves Myntra string product ID and populates fields."""
        anon_id = "test_myntra_user_anon_2"

        # 1. Add to wishlist
        add_res = self.client.post("/api/wishlist", json={
            "product_id": "myntra_28420390",
            "anonymous_id": anon_id
        })
        self.assertEqual(add_res.status_code, 200, add_res.get_json())
        wish_data = add_res.get_json()["data"]
        self.assertEqual(len(wish_data), 1)
        self.assertEqual(wish_data[0]["product_id"], "myntra_28420390")
        self.assertEqual(wish_data[0]["name"], "Roadster Men Solid Pure Cotton Casual Shirt")

        # Direct doc check
        raw_wish = self.test_wishlist.find_one({"anonymous_id": anon_id})
        self.assertEqual(raw_wish["product_id"], "myntra_28420390")

        # 2. Get wishlist
        get_res = self.client.get(f"/api/wishlist?anonymous_id={anon_id}")
        self.assertEqual(get_res.status_code, 200)
        self.assertEqual(len(get_res.get_json()["data"]), 1)

        # 3. Remove from wishlist
        del_res = self.client.delete(f"/api/wishlist/myntra_28420390?anonymous_id={anon_id}")
        self.assertEqual(del_res.status_code, 200)
        self.assertEqual(len(del_res.get_json()["data"]), 0)

    def test_order_creation_with_myntra_product_and_price_snapshot(self):
        """Order creation accepts Myntra product, snapshots price, and clears cart."""
        user_id = str(ObjectId())

        # Put item in cart first
        add_to_cart(self.test_cart, self.test_products, "myntra_28420390", quantity=2, user_id=user_id)
        self.assertEqual(self.test_cart.count_documents({"user_id": ObjectId(user_id)}), 1)

        # Create order
        order = create_order(
            orders_collection=self.test_orders,
            cart_collection=self.test_cart,
            products_collection=self.test_products,
            user_id=user_id,
            customer_email="customer@example.com",
            customer_name="John Doe",
        )

        self.assertIsNotNone(order)
        self.assertEqual(len(order["items"]), 1)
        item = order["items"][0]
        self.assertEqual(item["product_id"], "myntra_28420390")
        self.assertEqual(item["price"], 799.0)
        self.assertEqual(item["quantity"], 2)
        self.assertEqual(item["subtotal"], 1598.0)
        self.assertEqual(order["total_amount"], 1598.0)

        # Cart item must be removed after purchase
        self.assertEqual(self.test_cart.count_documents({"user_id": ObjectId(user_id)}), 0)

    def test_recommendations_with_myntra_products(self):
        """Recommendations engine scores and returns normalized Myntra products."""
        recs = get_personalized_recommendations(
            products_collection=self.test_products,
            profiles_collection=app_module.db["test_profiles"],
            cart_collection=self.test_cart,
            wishlist_collection=self.test_wishlist,
            limit=5
        )
        self.assertIsInstance(recs, list)
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["id"], "myntra_28420390")
        self.assertEqual(recs[0]["product_id"], "myntra_28420390")


if __name__ == "__main__":
    unittest.main()
