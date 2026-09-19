import os
import sys
import unittest

from bson import ObjectId

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import app, cart_collection, events_collection, orders_collection, products_collection


class OrderCheckoutTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.product_one = ObjectId()
        self.product_two = ObjectId()
        products_collection.insert_many([
            {"_id": self.product_one, "name": "Order One", "price": 125},
            {"_id": self.product_two, "name": "Order Two", "price": 80},
        ])

    def _user(self, email):
        signup = self.client.post("/api/auth/signup", json={
            "email": email, "password": "SecurePassword123"
        })
        self.assertEqual(signup.status_code, 200, signup.get_json())
        user_id = signup.get_json()["data"]["user_id"]
        login = self.client.post("/api/auth/login", json={
            "email": email, "password": "SecurePassword123"
        })
        self.assertEqual(login.status_code, 200, login.get_json())
        return user_id, login.get_json()["data"]["token"]

    def _add_cart_item(self, user_id, token, product_id, quantity):
        response = self.client.post("/api/cart", json={
            "user_id": user_id, "product_id": str(product_id), "quantity": quantity
        }, headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(response.status_code, 200, response.get_json())

    def test_authenticated_checkout_uses_database_prices_and_clears_cart(self):
        user_id, token = self._user("order-owner@example.com")
        self._add_cart_item(user_id, token, self.product_one, 2)
        self._add_cart_item(user_id, token, self.product_two, 3)

        checkout = self.client.post("/api/orders", json={
            "customer_id": user_id,
            "customer_email": "attacker@example.com",
            "items": [{"product_id": "fake", "price": 1, "quantity": 1}],
            "total_amount": 1,
        }, headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(checkout.status_code, 201, checkout.get_json())
        order_id = checkout.get_json()["data"]["order_id"]
        order = orders_collection.find_one({"_id": ObjectId(order_id)})
        self.assertEqual(order["user_id"], ObjectId(user_id))
        self.assertEqual(order["customer_email"], "order-owner@example.com")
        self.assertEqual(order["total_amount"], 490)
        self.assertEqual([(item["price"], item["quantity"], item["subtotal"]) for item in order["items"]], [(125, 2, 250), (80, 3, 240)])
        self.assertEqual(cart_collection.count_documents({"user_id": ObjectId(user_id)}), 0)
        self.assertEqual(events_collection.count_documents({"user_id": ObjectId(user_id), "event_type": "order_placed"}), 1)

        duplicate = self.client.post("/api/orders", json={"customer_id": user_id}, headers={
            "Authorization": f"Bearer {token}"
        })
        self.assertEqual(duplicate.status_code, 400)
        self.assertEqual(orders_collection.count_documents({"user_id": ObjectId(user_id)}), 1)

    def test_empty_and_unauthenticated_checkout_are_rejected(self):
        user_id, token = self._user("empty-order@example.com")
        empty = self.client.post("/api/orders", json={"customer_id": user_id}, headers={
            "Authorization": f"Bearer {token}"
        })
        self.assertEqual(empty.status_code, 400)
        self.assertEqual(orders_collection.count_documents({}), 0)
        self.assertEqual(self.client.post("/api/orders", json={}).status_code, 401)
        self.assertEqual(self.client.get("/api/orders").status_code, 401)

    def test_invalid_cart_state_does_not_create_order(self):
        user_id, token = self._user("invalid-order@example.com")
        cart_collection.insert_one({
            "user_id": ObjectId(user_id), "product_id": ObjectId(), "quantity": 1
        })
        invalid_product = self.client.post("/api/orders", json={"customer_id": user_id}, headers={
            "Authorization": f"Bearer {token}"
        })
        self.assertEqual(invalid_product.status_code, 400)
        self.assertEqual(orders_collection.count_documents({}), 0)

        cart_collection.delete_many({"user_id": ObjectId(user_id)})
        cart_collection.insert_one({
            "user_id": ObjectId(user_id), "product_id": self.product_one, "quantity": -1
        })
        invalid_quantity = self.client.post("/api/orders", json={"customer_id": user_id}, headers={
            "Authorization": f"Bearer {token}"
        })
        self.assertEqual(invalid_quantity.status_code, 400)
        self.assertEqual(orders_collection.count_documents({}), 0)

    def test_order_history_and_detail_are_owner_scoped(self):
        user_a, token_a = self._user("history-a@example.com")
        user_b, token_b = self._user("history-b@example.com")
        self._add_cart_item(user_a, token_a, self.product_one, 1)
        checkout = self.client.post("/api/orders", json={"customer_id": user_a}, headers={
            "Authorization": f"Bearer {token_a}"
        })
        order_id = checkout.get_json()["data"]["order_id"]

        own_history = self.client.get(f"/api/orders?user_id={user_a}", headers={
            "Authorization": f"Bearer {token_a}"
        })
        other_history = self.client.get(f"/api/orders?user_id={user_a}", headers={
            "Authorization": f"Bearer {token_b}"
        })
        own_detail = self.client.get(f"/api/orders/{order_id}?user_id={user_a}", headers={
            "Authorization": f"Bearer {token_a}"
        })
        other_detail = self.client.get(f"/api/orders/{order_id}?user_id={user_a}", headers={
            "Authorization": f"Bearer {token_b}"
        })
        malformed_detail = self.client.get("/api/orders/not-an-object-id", headers={
            "Authorization": f"Bearer {token_a}"
        })
        self.assertEqual(own_history.status_code, 200)
        self.assertEqual(len(own_history.get_json()["data"]), 1)
        self.assertEqual(other_history.status_code, 403)
        self.assertEqual(own_detail.status_code, 200)
        self.assertEqual(other_detail.status_code, 403)
        self.assertEqual(malformed_detail.status_code, 404)
        self.assertNotEqual(user_a, user_b)


if __name__ == "__main__":
    unittest.main()
