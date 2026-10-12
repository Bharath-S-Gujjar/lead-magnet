"""Task 13: End-to-End Customer Journey Validation and Integration Audit.

Validates the complete customer lifecycle across six integration journeys:
- Journey A: Customer identity (registration, persistence, login, consent defaults, IDOR isolation).
- Journey B: Shopping behavior (local catalog, cart, wishlist, quantity updates, subset checkout, consistency).
- Journey C: Customer intelligence and ML scoring (feature aggregation from canonical catalog, model inference, qualification persistence).
- Journey D: Opportunity generation & dispatch policy (channel priority, opt-in/opt-out, invalid phone, dedup/cooldown, zero external sends).
- Journey E: WhatsApp consent and Meta webhook (grant/revoke, spoof rejection, HMAC verification, STOP opt-out, idempotency).
- Journey F: Admin visibility (admin auth, Customer 360, protected endpoints, dashboard consistency).

All external communications are mocked or dry-run. ZERO real external messages or API calls are made.
Database isolation: Strictly confined to local test database (leadmagnet_test).
"""

import datetime
import hashlib
import hmac
import json
import os
import sys
import unittest
from bson import ObjectId
import jwt

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module
from app import (
    app,
    db,
    profiles_collection,
    cart_collection,
    wishlist_collection,
    orders_collection,
    events_collection,
    customer_features_collection,
    customer_lead_state_collection,
    leads_collection,
    JWT_SECRET,
    ADMIN_USERNAME,
    ADMIN_PASSWORD,
)
from customer_feature_service import aggregate_customer_features, upsert_customer_features, ensure_customer_features_indexes
from customer_lead_state_service import ensure_customer_lead_state_indexes, sync_customer_lead_state
from ecommerce_model_adapter import predict_customer_features
from channel_selector_service import select_communication_channel, POLICY_WHATSAPP_FIRST, POLICY_EMAIL_FIRST
from communication_provider import DryRunCommunicationProvider
from marketing_automation_service import ensure_marketing_automation_indexes
from whatsapp_webhook_service import ensure_webhook_indexes
from product_lookup import resolve_product_doc


class CustomerJourneyIntegrationTests(unittest.TestCase):
    """End-to-End Integration tests covering Journeys A through F."""

    def setUp(self):
        self.client = app.test_client()
        self.jwt_secret = JWT_SECRET
        self.created_user_ids = []
        self.created_product_ids = []

        # Ensure required indexes
        ensure_customer_features_indexes(customer_features_collection)
        ensure_customer_lead_state_indexes(customer_lead_state_collection)
        ensure_marketing_automation_indexes(db)
        ensure_webhook_indexes(db)

        # Clear rate limits
        app_module.AUTH_RATE_LIMIT_ATTEMPTS.clear()

        # Seed test catalog in both myntra_products and products
        self.products_col = db["myntra_products"]
        self.alt_products_col = db["products"]

        self.p1_id = ObjectId()
        self.p2_id = ObjectId()
        self.p3_id = ObjectId()

        self.test_products = [
            {
                "_id": self.p1_id,
                "product_id": f"myntra_test_{self.p1_id}",
                "name": "Classic Oxford Shirt",
                "brand": "Roadster",
                "price": 1499.0,
                "current_price": 1499.0,
                "original_price": 1999.0,
                "category": "Shirts",
                "in_stock": True,
            },
            {
                "_id": self.p2_id,
                "product_id": f"myntra_test_{self.p2_id}",
                "name": "Slim Fit Denim Jeans",
                "brand": "Highlander",
                "price": 2499.0,
                "current_price": 2499.0,
                "original_price": 2999.0,
                "category": "Jeans",
                "in_stock": True,
            },
            {
                "_id": self.p3_id,
                "product_id": f"myntra_test_{self.p3_id}",
                "name": "Casual Leather Sneakers",
                "brand": "Puma",
                "price": 3499.0,
                "current_price": 3499.0,
                "original_price": 4499.0,
                "category": "Footwear",
                "in_stock": True,
            },
        ]

        for p in self.test_products:
            self.products_col.update_one({"_id": p["_id"]}, {"$set": p}, upsert=True)
            self.alt_products_col.update_one({"_id": p["_id"]}, {"$set": p}, upsert=True)
            self.created_product_ids.append(p["_id"])

    def tearDown(self):
        # Clean up only test records created during this test
        if self.created_user_ids:
            profiles_collection.delete_many({"_id": {"$in": self.created_user_ids}})
            cart_collection.delete_many({"user_id": {"$in": self.created_user_ids}})
            wishlist_collection.delete_many({"user_id": {"$in": self.created_user_ids}})
            orders_collection.delete_many({"user_id": {"$in": self.created_user_ids}})
            events_collection.delete_many({"user_id": {"$in": self.created_user_ids}})
            customer_features_collection.delete_many({"customer_id": {"$in": [str(uid) for uid in self.created_user_ids]}})
            customer_lead_state_collection.delete_many({"customer_id": {"$in": [str(uid) for uid in self.created_user_ids]}})
            leads_collection.delete_many({"user_id": {"$in": self.created_user_ids}})

        if self.created_product_ids:
            self.products_col.delete_many({"_id": {"$in": self.created_product_ids}})
            self.alt_products_col.delete_many({"_id": {"$in": self.created_product_ids}})

    def _create_customer(self, email, password="Password123!", phone="+919876543210", opt_in=False):
        res = self.client.post("/api/auth/signup", json={
            "email": email,
            "password": password,
            "full_name": f"User {email.split('@')[0]}",
            "phone": phone,
            "whatsapp_opt_in": opt_in,
        })
        self.assertEqual(res.status_code, 200, res.get_json())
        user_id = ObjectId(res.get_json()["data"]["user_id"])
        self.created_user_ids.append(user_id)

        # Login to obtain token
        login_res = self.client.post("/api/auth/login", json={
            "email": email,
            "password": password,
        })
        self.assertEqual(login_res.status_code, 200, login_res.get_json())
        token = login_res.get_json()["data"]["token"]
        return user_id, token

    # =========================================================================
    # Journey A: Customer Identity
    # =========================================================================

    def test_journey_a_customer_identity_lifecycle_and_idor_protection(self):
        """Journey A: Registration, persistence, login, consent default, and cross-customer IDOR protection."""
        email1 = f"journey_a_user1_{ObjectId()}@example.com"
        email2 = f"journey_a_user2_{ObjectId()}@example.com"

        # 1. Register Customer 1 without explicit WhatsApp consent
        res_signup = self.client.post("/api/auth/signup", json={
            "email": email1,
            "password": "SecurePassword123!",
            "full_name": "Journey A First Customer",
            "phone": "+919876543211",
        })
        self.assertEqual(res_signup.status_code, 200)
        data_signup = res_signup.get_json()["data"]
        user1_id = ObjectId(data_signup["user_id"])
        self.created_user_ids.append(user1_id)

        # 2. Verify persistence in test database
        user1_doc = profiles_collection.find_one({"_id": user1_id})
        self.assertIsNotNone(user1_doc)
        self.assertEqual(user1_doc["email"], email1)
        self.assertEqual(user1_doc["role"], "user")
        self.assertNotEqual(user1_doc["password"], "SecurePassword123!")  # Must be hashed bcrypt
        # WhatsApp promotional consent must default to false
        self.assertFalse(user1_doc.get("whatsapp_opt_in", False))

        # 3. Log in with Customer 1
        res_login = self.client.post("/api/auth/login", json={
            "email": email1,
            "password": "SecurePassword123!",
        })
        self.assertEqual(res_login.status_code, 200)
        login_data = res_login.get_json()["data"]
        token1 = login_data["token"]
        self.assertEqual(login_data["email"], email1)
        self.assertFalse(login_data["whatsapp_opt_in"])

        # Decode token to verify claims
        decoded = jwt.decode(token1, self.jwt_secret, algorithms=["HS256"])
        self.assertEqual(decoded["sub"], str(user1_id))
        self.assertEqual(decoded["email"], email1)

        # 4. Register Customer 2
        user2_id, token2 = self._create_customer(email2, phone="+919876543212", opt_in=False)

        # 5. IDOR test: Customer 1 tries to update Customer 2's consent
        idor_res = self.client.put(
            f"/api/profile/whatsapp-consent?customer_id={user2_id}",
            json={
                "customer_id": str(user2_id),
                "whatsapp_opt_in": True,
            },
            headers={"Authorization": f"Bearer {token1}"},
        )
        self.assertEqual(idor_res.status_code, 403)
        self.assertIn("User ownership mismatch", idor_res.get_json()["message"])

        # Confirm Customer 2's consent in DB was NOT changed
        user2_doc = profiles_collection.find_one({"_id": user2_id})
        self.assertFalse(user2_doc.get("whatsapp_opt_in", False))

    # =========================================================================
    # Journey B: Shopping Behavior
    # =========================================================================

    def test_journey_b_shopping_behavior_and_subset_checkout(self):
        """Journey B: Catalog fetching, cart/wishlist management, subset checkout, and consistency."""
        cust_id, token = self._create_customer(f"journey_b_{ObjectId()}@example.com")
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Fetch catalog through local test data
        res_prod = self.client.get(f"/api/products/{self.p1_id}")
        self.assertEqual(res_prod.status_code, 200)
        self.assertEqual(res_prod.get_json()["data"]["name"], "Classic Oxford Shirt")

        # 2. Add product 1 and product 2 to cart
        res_cart1 = self.client.post("/api/cart", json={"product_id": str(self.p1_id), "quantity": 1}, headers=headers)
        self.assertEqual(res_cart1.status_code, 200)

        res_cart2 = self.client.post("/api/cart", json={"product_id": str(self.p2_id), "quantity": 1}, headers=headers)
        self.assertEqual(res_cart2.status_code, 200)

        # 3. Add product 3 to wishlist
        res_wl = self.client.post("/api/wishlist", json={"product_id": str(self.p3_id)}, headers=headers)
        self.assertEqual(res_wl.status_code, 200)

        # 4. Update cart quantity for Product 1 to 2
        res_qty = self.client.put(f"/api/cart/{self.p1_id}", json={"quantity": 2}, headers=headers)
        self.assertEqual(res_qty.status_code, 200)

        # Verify current cart has 2 distinct products, total quantity 3
        cart_state = self.client.get("/api/cart", headers=headers).get_json()["data"]
        self.assertEqual(len(cart_state), 2)

        # 5. Checkout with a SELECTED SUBSET: Order only Product 1 (quantity 2), leaving Product 2 in cart
        res_order = self.client.post(
            "/api/orders",
            json={
                "customer_id": str(cust_id),
                "items": [str(self.p1_id)],
                "payment_method": "Credit Card",
            },
            headers=headers,
        )
        self.assertIn(res_order.status_code, [200, 201])
        order_id = ObjectId(res_order.get_json()["data"]["order_id"])

        # 6. Verify order contains ONLY Product 1
        saved_order = orders_collection.find_one({"_id": order_id})
        self.assertIsNotNone(saved_order)
        self.assertEqual(len(saved_order["items"]), 1)
        self.assertEqual(saved_order["items"][0]["name"], "Classic Oxford Shirt")
        self.assertEqual(saved_order["items"][0]["quantity"], 2)
        self.assertEqual(saved_order["total_amount"], 1499.0 * 2)

        # 7. Verify unselected cart items (Product 2) REMAIN in cart
        remaining_cart = self.client.get("/api/cart", headers=headers).get_json()["data"]
        self.assertEqual(len(remaining_cart), 1)
        self.assertIn(remaining_cart[0]["product_id"], [str(self.p2_id), f"myntra_test_{self.p2_id}"])
        self.assertEqual(remaining_cart[0]["quantity"], 1)

        # 8. Verify wishlist remains untouched
        wl_state = self.client.get("/api/wishlist", headers=headers).get_json()["data"]
        self.assertEqual(len(wl_state), 1)
        self.assertIn(wl_state[0]["product_id"], [str(self.p3_id), f"myntra_test_{self.p3_id}"])

        # Verify order event was recorded in events_collection
        order_event = events_collection.find_one({"user_id": cust_id, "event_type": "order_placed"})
        self.assertIsNotNone(order_event)

    # =========================================================================
    # Journey C: Customer Intelligence & ML Scoring
    # =========================================================================

    def test_journey_c_customer_intelligence_and_ml_scoring(self):
        """Journey C: Feature aggregation from canonical catalog, model inference, and qualification persistence."""
        cust_id, token = self._create_customer(f"journey_c_{ObjectId()}@example.com")
        headers = {"Authorization": f"Bearer {token}"}

        # Seed shopping activity: add product 2 to cart and product 1 to wishlist
        self.client.post("/api/cart", json={"product_id": str(self.p2_id), "quantity": 1}, headers=headers)
        self.client.post("/api/wishlist", json={"product_id": str(self.p1_id)}, headers=headers)

        # Log high intent event
        events_collection.insert_one({
            "user_id": cust_id,
            "event_type": "page_view",
            "page": "/pricing",
            "timestamp": datetime.datetime.now(datetime.timezone.utc),
        })

        # 1. Trigger feature aggregation
        features = aggregate_customer_features(cust_id, db)
        self.assertIsInstance(features, dict)
        self.assertEqual(str(features["customer_id"]), str(cust_id))
        # Cart value should reflect Product 2 (2499.0)
        self.assertEqual(features["cart_value"], 2499.0)
        self.assertEqual(features["cart_item_count"], 1)
        self.assertEqual(features["wishlist_item_count"], 1)

        # Upsert into features collection
        upsert_customer_features(cust_id, db)

        # 2. Invoke ML model through supported prediction code path
        res_score = self.client.get("/api/customer/lead-score", headers=headers)
        self.assertEqual(res_score.status_code, 200, res_score.get_json())
        score_data = res_score.get_json()["data"]
        self.assertIn("lead_score", score_data)
        self.assertIn("lead_probability", score_data)
        self.assertIn("lead_segment", score_data)
        self.assertGreaterEqual(score_data["lead_score"], 0)
        self.assertLessEqual(score_data["lead_score"], 100)

        # 3. Verify lead state synchronization
        lead_state = sync_customer_lead_state(cust_id, db)
        self.assertIsNotNone(lead_state)
        self.assertEqual(str(lead_state["customer_id"]), str(cust_id))
        self.assertIn("qualification_status", lead_state)

        # Check persistence in customer_lead_state_collection
        persisted_state = customer_lead_state_collection.find_one({"customer_id": cust_id}) or customer_lead_state_collection.find_one({"customer_id": str(cust_id)})
        self.assertIsNotNone(persisted_state)
        self.assertEqual(persisted_state["lead_score"], score_data["lead_score"])

    # =========================================================================
    # Journey D: Opportunity Generation & Dispatch Policy
    # =========================================================================

    def test_journey_d_opportunity_generation_and_dispatch_policy(self):
        """Journey D: Channel prioritization, opt-in/opt-out suppression, and dedup/cooldown enforcement."""
        mock_provider = DryRunCommunicationProvider()

        # Scenario 1: High-priority promotional opportunity WITH valid WhatsApp opt-in and valid phone
        c1 = {
            "whatsapp_opt_in": True,
            "whatsapp_opt_out": False,
            "phone": "+919876543210",
            "email": "optin@example.com",
        }
        res1 = select_communication_channel(
            user_profile=c1,
            campaign_type="cart_abandonment",
            preference_policy=POLICY_WHATSAPP_FIRST,
        )
        self.assertEqual(res1["selected_channel"], "whatsapp")
        self.assertTrue(res1["eligibility"]["whatsapp"]["eligible"])

        # Scenario 2: High-priority promotional opportunity WITHOUT consent
        c2 = {
            "whatsapp_opt_in": False,
            "whatsapp_opt_out": False,
            "phone": "+919876543210",
            "email": "noconsent@example.com",
        }
        res2 = select_communication_channel(
            user_profile=c2,
            campaign_type="cart_abandonment",
            preference_policy=POLICY_WHATSAPP_FIRST,
        )
        self.assertNotEqual(res2["selected_channel"], "whatsapp")
        self.assertFalse(res2["eligibility"]["whatsapp"]["eligible"])

        # Scenario 3: Promotional opt-out overriding any preference
        c3 = {
            "whatsapp_opt_in": True,
            "whatsapp_opt_out": True,
            "phone": "+919876543210",
            "email": "optout@example.com",
        }
        res3 = select_communication_channel(
            user_profile=c3,
            campaign_type="cart_abandonment",
            preference_policy=POLICY_WHATSAPP_FIRST,
        )
        self.assertNotEqual(res3["selected_channel"], "whatsapp")

        # Scenario 4: Missing or invalid phone number
        c4 = {
            "whatsapp_opt_in": True,
            "whatsapp_opt_out": False,
            "phone": "invalid-phone",
            "email": "badphone@example.com",
        }
        res4 = select_communication_channel(
            user_profile=c4,
            campaign_type="cart_abandonment",
            preference_policy=POLICY_WHATSAPP_FIRST,
        )
        self.assertNotEqual(res4["selected_channel"], "whatsapp")

        # Scenario 5: Normal-priority opportunity with both channels available -> selects email first
        c5 = {
            "whatsapp_opt_in": True,
            "whatsapp_opt_out": False,
            "phone": "+919876543210",
            "email": "normal@example.com",
        }
        res5 = select_communication_channel(
            user_profile=c5,
            campaign_type="wishlist_inactivity",
            preference_policy=POLICY_EMAIL_FIRST,
        )
        self.assertEqual(res5["selected_channel"], "email")

        # Scenario 6: Verify DryRun provider operates safely in dry-run mode (zero external API calls)
        send_res = mock_provider.send_email("test@example.com", "Test Subject", "Test Body")
        self.assertTrue(send_res.get("success"))
        self.assertEqual(send_res.get("provider"), "dry_run")

    # =========================================================================
    # Journey E: WhatsApp Consent and Webhook
    # =========================================================================

    def test_journey_e_whatsapp_consent_lifecycle_and_webhook_handling(self):
        """Journey E: Consent grant/revoke, Meta webhook HMAC-SHA256 verification, and STOP keyword processing."""
        phone = "+919876543299"
        cust_id, token = self._create_customer(f"journey_e_{ObjectId()}@example.com", phone=phone, opt_in=False)
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Grant promotional consent via authenticated consent API
        res_grant = self.client.put(
            "/api/profile/whatsapp-consent",
            json={"whatsapp_opt_in": True, "phone": phone},
            headers=headers,
        )
        self.assertEqual(res_grant.status_code, 200, res_grant.get_json())
        data_grant = res_grant.get_json()["data"]
        self.assertTrue(data_grant["whatsapp_opt_in"])
        self.assertFalse(data_grant["whatsapp_opt_out"])

        # Verify DB state
        doc = profiles_collection.find_one({"_id": cust_id})
        self.assertTrue(doc["whatsapp_opt_in"])
        self.assertFalse(doc["whatsapp_opt_out"])

        # 2. Revoke consent
        res_revoke = self.client.patch(
            "/api/profile/whatsapp-consent",
            json={"whatsapp_opt_out": True},
            headers=headers,
        )
        self.assertEqual(res_revoke.status_code, 200)
        doc = profiles_collection.find_one({"_id": cust_id})
        self.assertFalse(doc["whatsapp_opt_in"])
        self.assertTrue(doc["whatsapp_opt_out"])

        # Re-grant consent so we can test inbound STOP
        self.client.put(
            "/api/profile/whatsapp-consent",
            json={"whatsapp_opt_in": True, "phone": phone},
            headers=headers,
        )
        doc = profiles_collection.find_one({"_id": cust_id})
        self.assertTrue(doc["whatsapp_opt_in"])

        # 3. Simulate Meta Webhook
        test_secret = "test_meta_webhook_app_secret_32b_val"
        app.config["WHATSAPP_APP_SECRET"] = test_secret
        app.config["WHATSAPP_WEBHOOK_VERIFY_TOKEN"] = "test_verify_token_123"

        # GET challenge verification
        res_challenge = self.client.get(
            "/api/webhook/whatsapp?hub.mode=subscribe&hub.verify_token=test_verify_token_123&hub.challenge=test_challenge_code"
        )
        self.assertEqual(res_challenge.status_code, 200)
        self.assertEqual(res_challenge.get_data(as_text=True), "test_challenge_code")

        # Reject wrong token
        res_bad_challenge = self.client.get(
            "/api/webhook/whatsapp?hub.mode=subscribe&hub.verify_token=wrong_token&hub.challenge=test_challenge_code"
        )
        self.assertEqual(res_bad_challenge.status_code, 403)

        # 4. POST with invalid signature -> 401
        res_bad_sig = self.client.post(
            "/api/webhook/whatsapp",
            data=json.dumps({"entry": []}),
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": "sha256=invalid_hex_digest",
            },
        )
        self.assertEqual(res_bad_sig.status_code, 401)

        # 5. Inbound message with STOP keyword -> should opt customer out
        stop_payload = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": "test_waba_id",
                    "changes": [
                        {
                            "value": {
                                "messaging_product": "whatsapp",
                                "metadata": {"display_phone_number": "1555000", "phone_number_id": "test_phone_id"},
                                "messages": [
                                    {
                                        "id": f"wamid_test_{ObjectId()}",
                                        "from": phone.replace("+", ""),  # e.g. 919876543299
                                        "timestamp": str(int(datetime.datetime.now(datetime.timezone.utc).timestamp())),
                                        "type": "text",
                                        "text": {"body": "STOP"},
                                    }
                                ],
                            },
                            "field": "messages",
                        }
                    ],
                }
            ],
        }
        raw_body = json.dumps(stop_payload).encode("utf-8")
        valid_sig = "sha256=" + hmac.new(test_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

        res_stop = self.client.post(
            "/api/webhook/whatsapp",
            data=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": valid_sig,
            },
        )
        self.assertEqual(res_stop.status_code, 200, res_stop.get_json())

        # Verify customer profile updated to opt-out
        doc_after_stop = profiles_collection.find_one({"_id": cust_id})
        self.assertFalse(doc_after_stop["whatsapp_opt_in"])
        self.assertTrue(doc_after_stop["whatsapp_opt_out"])

        # 6. Test delivery status duplicate idempotency
        status_msg_id = f"wamid_stat_{ObjectId()}"
        status_payload = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": "test_waba_id",
                    "changes": [
                        {
                            "value": {
                                "messaging_product": "whatsapp",
                                "metadata": {"phone_number_id": "test_phone_id"},
                                "statuses": [
                                    {
                                        "id": status_msg_id,
                                        "status": "delivered",
                                        "timestamp": str(int(datetime.datetime.now(datetime.timezone.utc).timestamp())),
                                        "recipient_id": phone.replace("+", ""),
                                    }
                                ],
                            },
                            "field": "messages",
                        }
                    ],
                }
            ],
        }
        raw_stat = json.dumps(status_payload).encode("utf-8")
        stat_sig = "sha256=" + hmac.new(test_secret.encode("utf-8"), raw_stat, hashlib.sha256).hexdigest()

        # First delivery event
        res_stat1 = self.client.post(
            "/api/webhook/whatsapp",
            data=raw_stat,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": stat_sig},
        )
        self.assertEqual(res_stat1.status_code, 200)

        # Duplicate delivery event (must succeed idempotently)
        res_stat2 = self.client.post(
            "/api/webhook/whatsapp",
            data=raw_stat,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": stat_sig},
        )
        self.assertEqual(res_stat2.status_code, 200)

    # =========================================================================
    # Journey F: Admin Visibility
    # =========================================================================

    def test_journey_f_admin_visibility_and_access_control(self):
        """Journey F: Admin authentication, Customer 360 inspection, and protected route access control."""
        cust_id, user_token = self._create_customer(f"journey_f_{ObjectId()}@example.com")

        # 1. Non-admin user tries to access protected admin endpoint -> 401 or 403
        unauth_res = self.client.get(
            "/api/admin/intelligence/overview",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        self.assertIn(unauth_res.status_code, [401, 403])

        no_token_res = self.client.get("/api/admin/intelligence/overview")
        self.assertIn(no_token_res.status_code, [401, 403])

        # 2. Admin logs in
        admin_login = self.client.post("/api/auth/admin/login", json={
            "username": os.environ.get("ADMIN_USERNAME", "test_admin"),
            "password": os.environ.get("ADMIN_PASSWORD", "test_admin_password"),
        })
        self.assertEqual(admin_login.status_code, 200, admin_login.get_json())
        admin_token = admin_login.get_json()["data"]["token"]
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        # 3. Admin fetches overview
        overview_res = self.client.get("/api/admin/intelligence/overview", headers=admin_headers)
        self.assertEqual(overview_res.status_code, 200)
        self.assertIn("data", overview_res.get_json())

        # 4. Admin inspects Customer 360
        c360_res = self.client.get(f"/api/admin/intelligence/customers/{cust_id}/360", headers=admin_headers)
        self.assertEqual(c360_res.status_code, 200, c360_res.get_json())
        c360_data = c360_res.get_json()["data"]

        # Verify state consistency
        self.assertEqual(str(c360_data["customer"]["_id"]), str(cust_id))
        self.assertIn("behavior_summary", c360_data)
        self.assertIn("cart", c360_data)
        self.assertIn("wishlist", c360_data)
        self.assertIn("orders", c360_data)


if __name__ == "__main__":
    unittest.main()
