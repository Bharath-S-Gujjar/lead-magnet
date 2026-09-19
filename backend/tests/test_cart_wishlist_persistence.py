import os
import sys
import unittest

from bson import ObjectId

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import (
    app,
    cart_collection,
    profiles_collection,
    products_collection,
    wishlist_collection,
)


class CartWishlistPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.product_one = ObjectId()
        self.product_two = ObjectId()
        products_collection.insert_many([
            {"_id": self.product_one, "name": "Product One", "price": 100},
            {"_id": self.product_two, "name": "Product Two", "price": 200},
        ])

    def _signup_and_login(self, email):
        signup = self.client.post("/api/auth/signup", json={
            "email": email,
            "password": "SecurePassword123",
        })
        self.assertEqual(signup.status_code, 200, signup.get_json())
        user_id = signup.get_json()["data"]["user_id"]
        login = self.client.post("/api/auth/login", json={
            "email": email,
            "password": "SecurePassword123",
        })
        self.assertEqual(login.status_code, 200, login.get_json())
        return user_id, login.get_json()["data"]["token"]

    def test_anonymous_cart_lifecycle_and_duplicate_quantity(self):
        anonymous_id = "anon_cart_lifecycle"
        product_id = str(self.product_one)
        add = self.client.post("/api/cart", json={
            "anonymous_id": anonymous_id, "product_id": product_id, "quantity": 2
        })
        self.assertEqual(add.status_code, 200)
        duplicate = self.client.post("/api/cart", json={
            "anonymous_id": anonymous_id, "product_id": product_id, "quantity": 3
        })
        self.assertEqual(duplicate.status_code, 200)
        self.assertEqual(duplicate.get_json()["data"][0]["quantity"], 5)
        self.assertEqual(cart_collection.count_documents({"anonymous_id": anonymous_id}), 1)

        update = self.client.put(f"/api/cart/{product_id}", json={
            "anonymous_id": anonymous_id, "quantity": 4
        })
        self.assertEqual(update.status_code, 200)
        self.assertEqual(update.get_json()["data"][0]["quantity"], 4)
        remove = self.client.delete(f"/api/cart/{product_id}?anonymous_id={anonymous_id}")
        self.assertEqual(remove.status_code, 200)
        self.assertEqual(remove.get_json()["data"], [])
        clear = self.client.delete(f"/api/cart?anonymous_id={anonymous_id}")
        self.assertEqual(clear.status_code, 200)

    def test_wishlist_duplicate_remove_and_clear(self):
        anonymous_id = "anon_wishlist_lifecycle"
        product_id = str(self.product_one)
        add = self.client.post("/api/wishlist", json={
            "anonymous_id": anonymous_id, "product_id": product_id
        })
        duplicate = self.client.post("/api/wishlist", json={
            "anonymous_id": anonymous_id, "product_id": product_id
        })
        self.assertEqual(add.status_code, 200)
        self.assertEqual(duplicate.status_code, 200)
        self.assertEqual(len(duplicate.get_json()["data"]), 1)
        self.assertEqual(wishlist_collection.count_documents({"anonymous_id": anonymous_id}), 1)
        remove = self.client.delete(f"/api/wishlist/{product_id}?anonymous_id={anonymous_id}")
        self.assertEqual(remove.status_code, 200)
        self.assertEqual(remove.get_json()["data"], [])
        self.client.post("/api/wishlist", json={
            "anonymous_id": anonymous_id, "product_id": product_id
        })
        clear = self.client.delete(f"/api/wishlist?anonymous_id={anonymous_id}")
        self.assertEqual(clear.status_code, 200)
        self.assertEqual(wishlist_collection.count_documents({"anonymous_id": anonymous_id}), 0)

    def test_invalid_inputs_and_missing_products_are_controlled(self):
        anonymous_id = "anon_invalid_inputs"
        missing_product = str(ObjectId())
        for payload in [
            {"anonymous_id": anonymous_id, "product_id": "not-an-object-id"},
            {"anonymous_id": anonymous_id, "product_id": missing_product},
            {"anonymous_id": anonymous_id, "product_id": str(self.product_one), "quantity": 0},
            {"anonymous_id": anonymous_id, "product_id": str(self.product_one), "quantity": -1},
            {"anonymous_id": anonymous_id, "product_id": str(self.product_one), "quantity": "many"},
        ]:
            response = self.client.post("/api/cart", json=payload)
            self.assertEqual(response.status_code, 400, response.get_json())
        self.assertEqual(self.client.post("/api/cart", data="bad", content_type="text/plain").status_code, 400)
        self.assertEqual(self.client.post("/api/wishlist", json={
            "anonymous_id": anonymous_id, "product_id": "bad"
        }).status_code, 400)
        self.assertEqual(self.client.post("/api/wishlist", json={
            "anonymous_id": anonymous_id, "product_id": missing_product
        }).status_code, 400)
        self.assertEqual(self.client.put(f"/api/cart/{missing_product}", json={
            "anonymous_id": anonymous_id, "quantity": 2
        }).status_code, 400)
        self.assertEqual(self.client.get("/api/cart").status_code, 400)
        self.assertEqual(self.client.get("/api/wishlist").status_code, 400)

    def test_user_ownership_isolation_requires_matching_token(self):
        user_a, token_a = self._signup_and_login("cart-owner-a@example.com")
        user_b, token_b = self._signup_and_login("cart-owner-b@example.com")
        product_id = str(self.product_one)
        add = self.client.post("/api/cart", json={
            "user_id": user_b, "product_id": product_id, "quantity": 2
        }, headers={"Authorization": f"Bearer {token_b}"})
        self.assertEqual(add.status_code, 200, add.get_json())

        forged_get = self.client.get(f"/api/cart?user_id={user_b}", headers={
            "Authorization": f"Bearer {token_a}"
        })
        self.assertEqual(forged_get.status_code, 403)
        forged_delete = self.client.delete(f"/api/cart/{product_id}?user_id={user_b}", headers={
            "Authorization": f"Bearer {token_a}"
        })
        self.assertEqual(forged_delete.status_code, 403)
        own_get = self.client.get(f"/api/cart?user_id={user_b}", headers={
            "Authorization": f"Bearer {token_b}"
        })
        self.assertEqual(own_get.status_code, 200)
        self.assertEqual(len(own_get.get_json()["data"]), 1)
        wishlist_add = self.client.post("/api/wishlist", json={
            "user_id": user_b, "product_id": product_id
        }, headers={"Authorization": f"Bearer {token_b}"})
        self.assertEqual(wishlist_add.status_code, 200)
        forged_wishlist = self.client.get(f"/api/wishlist?user_id={user_b}", headers={
            "Authorization": f"Bearer {token_a}"
        })
        self.assertEqual(forged_wishlist.status_code, 403)
        own_wishlist = self.client.get(f"/api/wishlist?user_id={user_b}", headers={
            "Authorization": f"Bearer {token_b}"
        })
        self.assertEqual(own_wishlist.status_code, 200)
        self.assertEqual(len(own_wishlist.get_json()["data"]), 1)
        self.assertEqual(user_a != user_b, True)

    def test_anonymous_carts_and_wishlists_are_separate(self):
        product_id = str(self.product_one)
        self.client.post("/api/cart", json={"anonymous_id": "anon-a", "product_id": product_id})
        self.client.post("/api/wishlist", json={"anonymous_id": "anon-a", "product_id": product_id})
        cart_b = self.client.get("/api/cart?anonymous_id=anon-b")
        wishlist_b = self.client.get("/api/wishlist?anonymous_id=anon-b")
        self.assertEqual(cart_b.status_code, 200)
        self.assertEqual(wishlist_b.status_code, 200)
        self.assertEqual(cart_b.get_json()["data"], [])
        self.assertEqual(wishlist_b.get_json()["data"], [])

    def test_authenticated_cart_and_wishlist_merge_is_idempotent(self):
        user_id, token = self._signup_and_login("merge-cart-owner@example.com")
        anonymous_id = "anon-merge-cart-owner"
        product_one = str(self.product_one)
        product_two = str(self.product_two)
        self.client.post("/api/cart", json={
            "anonymous_id": anonymous_id, "product_id": product_one, "quantity": 2
        })
        self.client.post("/api/cart", json={
            "anonymous_id": anonymous_id, "product_id": product_two, "quantity": 1
        })
        self.client.post("/api/wishlist", json={
            "anonymous_id": anonymous_id, "product_id": product_two
        })
        self.client.post("/api/cart", json={
            "user_id": user_id, "product_id": product_one, "quantity": 3
        }, headers={"Authorization": f"Bearer {token}"})
        self.client.post("/api/auth/login", json={
            "email": "merge-cart-owner@example.com",
            "password": "SecurePassword123",
            "anonymous_id": anonymous_id,
        })
        self.assertEqual(cart_collection.count_documents({"user_id": ObjectId(user_id)}), 2)
        self.assertEqual(wishlist_collection.count_documents({"user_id": ObjectId(user_id)}), 1)
        self.assertEqual(cart_collection.find_one({"user_id": ObjectId(user_id), "product_id": self.product_one})["quantity"], 5)
        self.assertEqual(cart_collection.count_documents({"anonymous_id": anonymous_id}), 0)
        self.assertEqual(wishlist_collection.count_documents({"anonymous_id": anonymous_id}), 0)

        self.client.post("/api/auth/login", json={
            "email": "merge-cart-owner@example.com",
            "password": "SecurePassword123",
            "anonymous_id": anonymous_id,
        })
        self.assertEqual(cart_collection.count_documents({"user_id": ObjectId(user_id)}), 2)
        self.assertEqual(wishlist_collection.count_documents({"user_id": ObjectId(user_id)}), 1)


if __name__ == "__main__":
    unittest.main()
