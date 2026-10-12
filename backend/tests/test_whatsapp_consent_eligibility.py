"""Focused unit tests for WhatsApp consent and channel-eligibility layer.

Validates Task 1 requirements:
1. Customer with no WhatsApp consent defaults to promotional opt-in = False.
2. Customer explicitly opted in is eligible for promotional WhatsApp.
3. Customer opted out is immediately ineligible (overrides prior opt-in).
4. Opt-out also blocks transactional WhatsApp messaging.
5. Missing or unusable phone numbers are rejected for WhatsApp.
6. Gmail eligibility remains unaffected when WhatsApp is ineligible.
7. Existing transactional eligibility rules (registration, order confirmation) remain intact.
8. Customer profile signup persists explicit WhatsApp consent fields with defaults.
"""

import os
import sys
import unittest
from bson import ObjectId

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from marketing_automation_service import (
    evaluate_channel_eligibility,
    trigger_registration_communication,
    trigger_order_confirmation_communication,
    trigger_lead_qualification_communication,
)
from communication_provider import CommunicationProvider
import app as app_module


class MockTestProvider(CommunicationProvider):
    def __init__(self, email_success=True, wa_success=True):
        self.email_success = email_success
        self.wa_success = wa_success
        self.emails_sent = []
        self.whatsapp_sent = []

    def send_email(self, recipient, subject, body, metadata=None, html_body=None, **kwargs):
        self.emails_sent.append({"recipient": recipient, "subject": subject, "body": body})
        return {"success": self.email_success, "provider": "mock", "provider_message_id": "em_1"}

    def send_whatsapp(self, recipient, body, metadata=None):
        self.whatsapp_sent.append({"recipient": recipient, "body": body})
        return {"success": self.wa_success, "provider": "mock", "provider_message_id": "wa_1"}


class TestWhatsAppConsentEligibility(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = app_module.app.test_client()
        cls.db = app_module.db

    # --------------------------------------------------------------------------
    # 1. No Consent -> Promotional Ineligible, Email Preserved
    # --------------------------------------------------------------------------
    def test_no_consent_defaults_to_ineligible_for_promotional(self):
        """Customer with valid phone and email but no consent is ineligible for promotional WhatsApp."""
        profile = {
            "email": "user@example.com",
            "phone": "+919876543210",
            "full_name": "No Consent User",
        }
        # Inferred promotional by default
        eligibility = evaluate_channel_eligibility(profile)
        self.assertTrue(eligibility["email"]["eligible"])
        self.assertEqual(eligibility["email"]["recipient"], "user@example.com")
        self.assertFalse(eligibility["whatsapp"]["eligible"])
        self.assertIn("not opted in", eligibility["whatsapp"]["reason"])

        # Explicit promotional campaign
        eligibility_promo = evaluate_channel_eligibility(profile, campaign_type="lead_qualified")
        self.assertTrue(eligibility_promo["email"]["eligible"])
        self.assertFalse(eligibility_promo["whatsapp"]["eligible"])
        self.assertIn("not opted in to promotional WhatsApp", eligibility_promo["whatsapp"]["reason"])

    # --------------------------------------------------------------------------
    # 2. Explicit Opt-In -> Promotional Eligible
    # --------------------------------------------------------------------------
    def test_explicit_opt_in_allows_promotional_whatsapp(self):
        """Customer with whatsapp_opt_in=True is eligible for promotional WhatsApp."""
        profile = {
            "email": "opted_in@example.com",
            "phone": "+919876543210",
            "whatsapp_opt_in": True,
            "whatsapp_opt_out": False,
        }
        eligibility = evaluate_channel_eligibility(profile, campaign_type="cart_abandoned")
        self.assertTrue(eligibility["email"]["eligible"])
        self.assertTrue(eligibility["whatsapp"]["eligible"])
        self.assertEqual(eligibility["whatsapp"]["reason"], "eligible")
        self.assertEqual(eligibility["whatsapp"]["recipient"], "+919876543210")

    # --------------------------------------------------------------------------
    # 3. Opt-Out Overrides Opt-In
    # --------------------------------------------------------------------------
    def test_opt_out_overrides_opt_in_immediately(self):
        """Customer who opted out is ineligible, even if whatsapp_opt_in is True."""
        profile = {
            "email": "opted_out@example.com",
            "phone": "+919876543210",
            "whatsapp_opt_in": True,
            "whatsapp_opt_out": True,
        }
        eligibility = evaluate_channel_eligibility(profile, campaign_type="cart_abandoned")
        self.assertTrue(eligibility["email"]["eligible"])
        self.assertFalse(eligibility["whatsapp"]["eligible"])
        self.assertIn("opted out", eligibility["whatsapp"]["reason"])

    def test_opt_out_overrides_transactional_messages(self):
        """Customer who opted out of WhatsApp cannot receive transactional messages on WhatsApp."""
        profile = {
            "email": "opted_out_tx@example.com",
            "phone": "+919876543210",
            "whatsapp_opt_in": False,
            "whatsapp_opt_out": True,
        }
        eligibility_reg = evaluate_channel_eligibility(profile, campaign_type="registration")
        self.assertTrue(eligibility_reg["email"]["eligible"])
        self.assertFalse(eligibility_reg["whatsapp"]["eligible"])
        self.assertIn("opted out", eligibility_reg["whatsapp"]["reason"])

        eligibility_order = evaluate_channel_eligibility(profile, campaign_type="order_confirmation")
        self.assertTrue(eligibility_order["email"]["eligible"])
        self.assertFalse(eligibility_order["whatsapp"]["eligible"])
        self.assertIn("opted out", eligibility_order["whatsapp"]["reason"])

    # --------------------------------------------------------------------------
    # 4. Transactional Messaging Does Not Require Promotional Opt-In
    # --------------------------------------------------------------------------
    def test_transactional_messaging_allowed_without_promotional_opt_in(self):
        """Transactional messages (registration, order_confirmation) allow WhatsApp with valid phone and no opt-out."""
        profile = {
            "email": "buyer@example.com",
            "phone": "+919876543210",
            "whatsapp_opt_in": False,
            "whatsapp_opt_out": False,
        }
        # Registration (transactional)
        elig_reg = evaluate_channel_eligibility(profile, campaign_type="registration")
        self.assertTrue(elig_reg["whatsapp"]["eligible"])
        self.assertEqual(elig_reg["whatsapp"]["reason"], "eligible")
        self.assertTrue(elig_reg["email"]["eligible"])

        # Order confirmation (transactional)
        elig_order = evaluate_channel_eligibility(profile, campaign_type="order_confirmation")
        self.assertTrue(elig_order["whatsapp"]["eligible"])
        self.assertEqual(elig_order["whatsapp"]["reason"], "eligible")
        self.assertTrue(elig_order["email"]["eligible"])

        # Explicit classification parameter
        elig_explicit_tx = evaluate_channel_eligibility(profile, classification="transactional")
        self.assertTrue(elig_explicit_tx["whatsapp"]["eligible"])

    # --------------------------------------------------------------------------
    # 5. Missing Phone Number
    # --------------------------------------------------------------------------
    def test_missing_phone_number_ineligible(self):
        """Missing or empty phone makes WhatsApp ineligible while keeping Gmail eligible."""
        for empty_val in [None, "", "   "]:
            profile = {
                "email": "nophone@example.com",
                "phone": empty_val,
                "whatsapp_opt_in": True,
            }
            eligibility = evaluate_channel_eligibility(profile)
            self.assertTrue(eligibility["email"]["eligible"])
            self.assertFalse(eligibility["whatsapp"]["eligible"])
            self.assertIn("No phone number", eligibility["whatsapp"]["reason"])
            self.assertIsNone(eligibility["whatsapp"]["recipient"])

    # --------------------------------------------------------------------------
    # 6. Invalid / Unusable Phone Numbers
    # --------------------------------------------------------------------------
    def test_national_number_without_country_code_rejected(self):
        """National 10-digit number without international country code is unusable and rejected."""
        profile = {
            "email": "national@example.com",
            "phone": "9876543210",
            "whatsapp_opt_in": True,
        }
        eligibility = evaluate_channel_eligibility(profile)
        self.assertTrue(eligibility["email"]["eligible"])
        self.assertFalse(eligibility["whatsapp"]["eligible"])
        self.assertIn("lacks international country code", eligibility["whatsapp"]["reason"])

    def test_non_digit_phone_rejected(self):
        """Phone string with no valid digits is rejected."""
        profile = {
            "email": "invalidphone@example.com",
            "phone": "not-a-valid-phone",
            "whatsapp_opt_in": True,
        }
        eligibility = evaluate_channel_eligibility(profile)
        self.assertTrue(eligibility["email"]["eligible"])
        self.assertFalse(eligibility["whatsapp"]["eligible"])
        self.assertIn("Invalid WhatsApp phone number", eligibility["whatsapp"]["reason"])

    # --------------------------------------------------------------------------
    # 7. Policy Disablement
    # --------------------------------------------------------------------------
    def test_policy_disablement_overrides_consent(self):
        """Policy whatsapp_enabled=False takes precedence and renders WhatsApp ineligible."""
        profile = {
            "email": "policy_test@example.com",
            "phone": "+919876543210",
            "whatsapp_opt_in": True,
        }
        eligibility = evaluate_channel_eligibility(profile, policy={"whatsapp_enabled": False})
        self.assertTrue(eligibility["email"]["eligible"])
        self.assertFalse(eligibility["whatsapp"]["eligible"])
        self.assertEqual(eligibility["whatsapp"]["reason"], "WhatsApp channel disabled by policy")

    # --------------------------------------------------------------------------
    # 8. Profile Handling: Signup Defaults and Explicit Consent
    # --------------------------------------------------------------------------
    def test_signup_with_explicit_opt_in_persists_fields(self):
        """Signup endpoint correctly captures and records whatsapp_opt_in and timestamp."""
        test_email = f"wa_optin_{ObjectId()}@example.com"
        resp = self.client.post("/api/auth/signup", json={
            "email": test_email,
            "password": "Password123!",
            "phone": "+919876543210",
            "whatsapp_opt_in": True,
            "whatsapp_opt_in_source": "signup_checkbox",
        })
        self.assertEqual(resp.status_code, 200)
        user_id = resp.get_json()["data"]["user_id"]

        user_doc = self.db["user_profiles"].find_one({"_id": ObjectId(user_id)})
        self.assertIsNotNone(user_doc)
        self.assertTrue(user_doc.get("whatsapp_opt_in"))
        self.assertFalse(user_doc.get("whatsapp_opt_out"))
        self.assertIsNotNone(user_doc.get("whatsapp_opt_in_at"))
        self.assertEqual(user_doc.get("whatsapp_opt_in_source"), "signup_checkbox")

    def test_signup_without_consent_defaults_to_false(self):
        """Signup endpoint defaults whatsapp_opt_in to False when omitted."""
        test_email = f"wa_default_{ObjectId()}@example.com"
        resp = self.client.post("/api/auth/signup", json={
            "email": test_email,
            "password": "Password123!",
            "phone": "+919876543210",
        })
        self.assertEqual(resp.status_code, 200)
        user_id = resp.get_json()["data"]["user_id"]

        user_doc = self.db["user_profiles"].find_one({"_id": ObjectId(user_id)})
        self.assertIsNotNone(user_doc)
        self.assertFalse(user_doc.get("whatsapp_opt_in"))
        self.assertFalse(user_doc.get("whatsapp_opt_out"))
        self.assertIsNone(user_doc.get("whatsapp_opt_in_at"))

    # --------------------------------------------------------------------------
    # 9. Existing / Legacy Customers with No Recorded Consent
    # --------------------------------------------------------------------------
    def test_existing_legacy_customer_in_db_defaults_to_ineligible_promotional(self):
        """Existing customer in user_profiles collection with no consent fields defaults to promotional WhatsApp ineligible."""
        legacy_id = ObjectId()
        self.db["user_profiles"].insert_one({
            "_id": legacy_id,
            "email": "legacy_cust@example.com",
            "phone": "+919876543210",
            "full_name": "Legacy Customer",
        })

        cust = self.db["user_profiles"].find_one({"_id": legacy_id})
        # Verify no consent keys exist on the raw document
        self.assertNotIn("whatsapp_opt_in", cust)
        self.assertNotIn("whatsapp_opt_out", cust)

        # Evaluated for promotional campaigns
        for promo_type in ["lead_qualified", "lead_qualification", "cart_abandoned", "wishlist_reminder", "opportunity", "product_price_drop"]:
            elig = evaluate_channel_eligibility(cust, campaign_type=promo_type)
            self.assertTrue(elig["email"]["eligible"], f"Email should be eligible for {promo_type}")
            self.assertFalse(elig["whatsapp"]["eligible"], f"WhatsApp should be ineligible for {promo_type}")
            self.assertIn("not opted in", elig["whatsapp"]["reason"])

        # Evaluated for transactional campaigns
        for tx_type in ["registration", "order_confirmation"]:
            elig_tx = evaluate_channel_eligibility(cust, campaign_type=tx_type)
            self.assertTrue(elig_tx["email"]["eligible"])
            self.assertTrue(elig_tx["whatsapp"]["eligible"])
            self.assertEqual(elig_tx["whatsapp"]["reason"], "eligible")

    # --------------------------------------------------------------------------
    # 10. E.164 Phone Length Boundaries
    # --------------------------------------------------------------------------
    def test_invalid_e164_lengths_rejected(self):
        """Phone numbers with invalid E.164 lengths (<8 or >15 digits) are rejected."""
        # Too short (< 8 digits)
        profile_short = {
            "email": "short@example.com",
            "phone": "+12345",
            "whatsapp_opt_in": True,
        }
        elig_short = evaluate_channel_eligibility(profile_short)
        self.assertTrue(elig_short["email"]["eligible"])
        self.assertFalse(elig_short["whatsapp"]["eligible"])
        self.assertIn("Invalid WhatsApp phone number", elig_short["whatsapp"]["reason"])

        # Too long (> 15 digits)
        profile_long = {
            "email": "long@example.com",
            "phone": "+123456789012345678",
            "whatsapp_opt_in": True,
        }
        elig_long = evaluate_channel_eligibility(profile_long)
        self.assertTrue(elig_long["email"]["eligible"])
        self.assertFalse(elig_long["whatsapp"]["eligible"])
        self.assertIn("Invalid WhatsApp phone number", elig_long["whatsapp"]["reason"])

    # --------------------------------------------------------------------------
    # 11. Profile API Serializes WhatsApp Consent Fields
    # --------------------------------------------------------------------------
    def test_profile_api_serializes_whatsapp_consent_fields(self):
        """Profile endpoint exposes safe consent fields."""
        test_email = f"wa_profile_{ObjectId()}@example.com"
        resp = self.client.post("/api/auth/signup", json={
            "email": test_email,
            "password": "Password123!",
            "phone": "+919876543210",
            "whatsapp_opt_in": True,
        })
        self.assertEqual(resp.status_code, 200)
        user_id = resp.get_json()["data"]["user_id"]

        login_resp = self.client.post("/api/auth/login", json={
            "email": test_email,
            "password": "Password123!",
        })
        self.assertEqual(login_resp.status_code, 200)
        token = login_resp.get_json()["data"]["token"]

        get_resp = self.client.get(
            f"/api/profile?user_id={user_id}",
            headers={"Authorization": f"Bearer {token}"}
        )
        self.assertEqual(get_resp.status_code, 200)
        pdata = get_resp.get_json()["data"]
        self.assertTrue(pdata.get("whatsapp_opt_in"))
        self.assertFalse(pdata.get("whatsapp_opt_out"))
        self.assertIsNotNone(pdata.get("whatsapp_opt_in_at"))


if __name__ == "__main__":
    unittest.main()
