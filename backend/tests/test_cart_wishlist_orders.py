import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import unittest
from bson import ObjectId
from app import app, products_collection, cart_collection, wishlist_collection


class CartWishlistOrderEndpointTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        # Insert isolated test product fixture
        self.test_product_id = ObjectId()
        products_collection.insert_one({
            "_id": self.test_product_id,
            "name": "Test Shirt",
            "price": 999,
            "category": "shirts",
            "brand": "TestBrand"
        })

    def tearDown(self):
        # Remove test product fixture and test cart/wishlist items
        products_collection.delete_one({"_id": self.test_product_id})
        cart_collection.delete_many({"anonymous_id": "test_anon_cart_user_123"})
        wishlist_collection.delete_many({"anonymous_id": "test_anon_cart_user_123"})

    def test_cart_and_wishlist_flows(self):
        product_id = str(self.test_product_id)
        test_anon_id = "test_anon_cart_user_123"

        # 1. Add to cart
        res_cart = self.client.post("/api/cart", json={
            "product_id": product_id,
            "quantity": 2,
            "anonymous_id": test_anon_id
        })
        self.assertEqual(res_cart.status_code, 200)
        cart_data = res_cart.get_json().get("data", [])
        self.assertTrue(len(cart_data) >= 1)

        # 2. Get cart
        get_cart_res = self.client.get(f"/api/cart?anonymous_id={test_anon_id}")
        self.assertEqual(get_cart_res.status_code, 200)
        self.assertTrue(len(get_cart_res.get_json().get("data", [])) >= 1)

        # 3. Add to wishlist
        res_wish = self.client.post("/api/wishlist", json={
            "product_id": product_id,
            "anonymous_id": test_anon_id
        })
        self.assertEqual(res_wish.status_code, 200)
        wish_data = res_wish.get_json().get("data", [])
        self.assertTrue(len(wish_data) >= 1)

        # 4. Get wishlist
        get_wish_res = self.client.get(f"/api/wishlist?anonymous_id={test_anon_id}")
        self.assertEqual(get_wish_res.status_code, 200)
        self.assertTrue(len(get_wish_res.get_json().get("data", [])) >= 1)

        # 5. Remove from wishlist & clear cart
        del_wish = self.client.delete(f"/api/wishlist/{product_id}?anonymous_id={test_anon_id}")
        self.assertEqual(del_wish.status_code, 200)

        del_cart = self.client.delete(f"/api/cart?anonymous_id={test_anon_id}")
        self.assertEqual(del_cart.status_code, 200)


if __name__ == "__main__":
    unittest.main()
