"""Unit and API tests for WhatsApp Consent Management API (Task 4).

Covers all 12 requirement areas:
1. Unauthenticated requests are rejected (missing token, invalid token, expired token).
2. Explicit opt-in is persisted correctly with timestamp and source.
3. Explicit opt-out disables opt-in and persists opt-out with timestamp and source.
4. Opt-in after a previous opt-out clears the opt-out flag only after an explicit opt-in request.
5. Missing fields are rejected.
6. Non-boolean values such as strings, numbers, and null are rejected.
7. Contradictory consent values are rejected.
8. A user cannot change another user's consent (user ID spoofing in body or query rejected).
9. Existing profiles missing consent fields remain promotional-WhatsApp-ineligible.
10. Eligibility still blocks WhatsApp when opt-out is true.
11. The endpoint never sends a communication or invokes an external provider.
12. Existing authentication and profile tests continue to pass.
"""

import datetime
import os
import sys
import unittest
from unittest.mock import patch, MagicMock
from bson import ObjectId
import jwt

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module
from app import app
from customer_profile_service import update_customer_whatsapp_consent
from marketing_automation_service import evaluate_channel_eligibility


class TestWhatsAppConsentAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = app.test_client()
        cls.jwt_secret = app_module.JWT_SECRET
        cls.profiles = app_module.profiles_collection

    def setUp(self):
        # Create primary test customer
        self.user_oid = ObjectId()
        self.user_id = str(self.user_oid)
        self.user_email = f"wa_consent_{self.user_id}@example.com"
        self.phone = "+919876543210"

        self.profiles.insert_one({
            "_id": self.user_oid,
            "email": self.user_email,
            "phone": self.phone,
            "role": "user",
            "full_name": "Consent Test User",
            "password": b"$2b$12$testpasswordhashstringvalue",
            "whatsapp_opt_in": False,
            "whatsapp_opt_out": False,
            "created_at": datetime.datetime.utcnow(),
        })

        # Create secondary victim customer
        self.victim_oid = ObjectId()
        self.victim_id = str(self.victim_oid)
        self.victim_email = f"wa_victim_{self.victim_id}@example.com"

        self.profiles.insert_one({
            "_id": self.victim_oid,
            "email": self.victim_email,
            "phone": "+919123456789",
            "role": "user",
            "full_name": "Victim User",
            "password": b"$2b$12$testvictimpasswordhash",
            "whatsapp_opt_in": False,
            "whatsapp_opt_out": False,
            "created_at": datetime.datetime.utcnow(),
        })

        self.token = self._generate_token(user_id=self.user_id, email=self.user_email)

    def tearDown(self):
        self.profiles.delete_many({
            "_id": {"$in": [self.user_oid, self.victim_oid]}
        })

    def _generate_token(self, user_id, email, exp_minutes=60, include_exp=True):
        payload = {
            "sub": str(user_id),
            "email": email,
            "role": "user",
        }
        if include_exp:
            exp_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=exp_minutes)
            payload["exp"] = exp_time
        return jwt.encode(payload, self.jwt_secret, algorithm="HS256")

    # --------------------------------------------------------------------------
    # 1. Unauthenticated requests are rejected
    # --------------------------------------------------------------------------
    def test_01_unauthenticated_requests_rejected(self):
        """Requests without a valid token are rejected with 401."""
        url = "/api/profile/whatsapp-consent"

        # Missing token
        res_no_auth = self.client.patch(url, json={"whatsapp_opt_in": True})
        self.assertEqual(res_no_auth.status_code, 401)
        self.assertFalse(res_no_auth.get_json()["success"])

        # Invalid token scheme / malformed token
        res_bad_tok = self.client.patch(
            url,
            headers={"Authorization": "Bearer totally-invalid-jwt-token"},
            json={"whatsapp_opt_in": True},
        )
        self.assertEqual(res_bad_tok.status_code, 401)
        self.assertFalse(res_bad_tok.get_json()["success"])

        # Expired token
        expired_token = self._generate_token(self.user_id, self.user_email, exp_minutes=-10)
        res_exp = self.client.patch(
            url,
            headers={"Authorization": f"Bearer {expired_token}"},
            json={"whatsapp_opt_in": True},
        )
        self.assertEqual(res_exp.status_code, 401)
        self.assertFalse(res_exp.get_json()["success"])

        # Missing exp claim
        no_exp_tok = self._generate_token(self.user_id, self.user_email, include_exp=False)
        res_no_exp = self.client.patch(
            url,
            headers={"Authorization": f"Bearer {no_exp_tok}"},
            json={"whatsapp_opt_in": True},
        )
        self.assertEqual(res_no_exp.status_code, 401)

    # --------------------------------------------------------------------------
    # 2. Explicit opt-in is persisted correctly
    # --------------------------------------------------------------------------
    def test_02_explicit_opt_in_persisted_correctly(self):
        """Explicit opt-in updates profile and persists timestamps and source."""
        url = "/api/profile/whatsapp-consent"
        res = self.client.patch(
            url,
            headers={"Authorization": f"Bearer {self.token}"},
            json={"whatsapp_opt_in": True, "source": "user_settings"},
        )
        self.assertEqual(res.status_code, 200)
        body = res.get_json()
        self.assertTrue(body["success"])
        data = body["data"]

        # Check returned data
        self.assertTrue(data["whatsapp_opt_in"])
        self.assertFalse(data["whatsapp_opt_out"])
        self.assertIsNotNone(data["whatsapp_opt_in_at"])
        self.assertEqual(data["whatsapp_opt_in_source"], "user_settings")
        # Ensure password is not exposed
        self.assertNotIn("password", data)
        self.assertNotIn("password_hash", data)

        # Verify DB directly
        doc = self.profiles.find_one({"_id": self.user_oid})
        self.assertTrue(doc["whatsapp_opt_in"])
        self.assertFalse(doc["whatsapp_opt_out"])
        self.assertIsNotNone(doc["whatsapp_opt_in_at"])
        self.assertEqual(doc["whatsapp_opt_in_source"], "user_settings")

    # --------------------------------------------------------------------------
    # 3. Explicit opt-out disables opt-in and persists opt-out
    # --------------------------------------------------------------------------
    def test_03_explicit_opt_out_disables_opt_in_and_persists_opt_out(self):
        """Explicit opt-out sets whatsapp_opt_out=True and disables whatsapp_opt_in."""
        # Pre-seed user as opted in
        self.profiles.update_one(
            {"_id": self.user_oid},
            {"$set": {"whatsapp_opt_in": True, "whatsapp_opt_out": False, "whatsapp_opt_in_at": "2026-10-01T00:00:00"}},
        )

        url = "/api/profile/whatsapp-consent"
        res = self.client.patch(
            url,
            headers={"Authorization": f"Bearer {self.token}"},
            json={"whatsapp_opt_out": True, "source": "settings_toggle"},
        )
        self.assertEqual(res.status_code, 200)
        body = res.get_json()
        self.assertTrue(body["success"])
        data = body["data"]

        self.assertFalse(data["whatsapp_opt_in"])
        self.assertTrue(data["whatsapp_opt_out"])
        self.assertIsNotNone(data["whatsapp_opt_out_at"])
        self.assertEqual(data["whatsapp_opt_out_source"], "settings_toggle")

        # Verify DB directly
        doc = self.profiles.find_one({"_id": self.user_oid})
        self.assertFalse(doc["whatsapp_opt_in"])
        self.assertTrue(doc["whatsapp_opt_out"])
        self.assertIsNotNone(doc["whatsapp_opt_out_at"])
        self.assertEqual(doc["whatsapp_opt_out_source"], "settings_toggle")

    # --------------------------------------------------------------------------
    # 4. Opt-in after prior opt-out clears opt-out only after explicit opt-in
    # --------------------------------------------------------------------------
    def test_04_opt_in_after_opt_out_clears_opt_out_only_after_explicit_opt_in(self):
        """Clearing opt-out only occurs after explicit opt-in request, not implicitly."""
        # Seed as opted out
        self.profiles.update_one(
            {"_id": self.user_oid},
            {"$set": {"whatsapp_opt_in": False, "whatsapp_opt_out": True, "whatsapp_opt_out_at": "2026-10-01T00:00:00"}},
        )

        url = "/api/profile/whatsapp-consent"

        # Sending whatsapp_opt_out: False clears the opt-out flag, but does NOT opt into promotional
        res_clear_optout = self.client.patch(
            url,
            headers={"Authorization": f"Bearer {self.token}"},
            json={"whatsapp_opt_out": False},
        )
        self.assertEqual(res_clear_optout.status_code, 200)
        doc = self.profiles.find_one({"_id": self.user_oid})
        self.assertFalse(doc["whatsapp_opt_out"])
        self.assertFalse(doc["whatsapp_opt_in"])  # Promotional remains disabled!

        # Re-seed as opted out
        self.profiles.update_one(
            {"_id": self.user_oid},
            {"$set": {"whatsapp_opt_in": False, "whatsapp_opt_out": True}},
        )

        # Explicit opt-in request clears the opt-out flag AND enables opt-in
        res_optin = self.client.patch(
            url,
            headers={"Authorization": f"Bearer {self.token}"},
            json={"whatsapp_opt_in": True},
        )
        self.assertEqual(res_optin.status_code, 200)
        doc_after = self.profiles.find_one({"_id": self.user_oid})
        self.assertTrue(doc_after["whatsapp_opt_in"])
        self.assertFalse(doc_after["whatsapp_opt_out"])

    # --------------------------------------------------------------------------
    # 5. Missing fields are rejected
    # --------------------------------------------------------------------------
    def test_05_missing_fields_rejected(self):
        """Requests with empty bodies or without consent fields are rejected with 400."""
        url = "/api/profile/whatsapp-consent"

        # Empty dict
        res_empty = self.client.patch(url, headers={"Authorization": f"Bearer {self.token}"}, json={})
        self.assertEqual(res_empty.status_code, 400)
        self.assertFalse(res_empty.get_json()["success"])

        # Dict with only unrelated fields
        res_unrelated = self.client.patch(
            url,
            headers={"Authorization": f"Bearer {self.token}"},
            json={"other_key": "some_value"},
        )
        self.assertEqual(res_unrelated.status_code, 400)
        self.assertFalse(res_unrelated.get_json()["success"])

    # --------------------------------------------------------------------------
    # 6. Non-boolean values such as strings, numbers, and null are rejected
    # --------------------------------------------------------------------------
    def test_06_non_boolean_values_rejected(self):
        """Values that are strings, numbers, floats, null, or arrays are rejected with 400."""
        url = "/api/profile/whatsapp-consent"
        invalid_values = [
            "true", "false", "1", "0", 1, 0, 1.0, None, [True], {"enabled": True}
        ]

        for bad_val in invalid_values:
            # Test in whatsapp_opt_in
            res_in = self.client.patch(
                url,
                headers={"Authorization": f"Bearer {self.token}"},
                json={"whatsapp_opt_in": bad_val},
            )
            self.assertEqual(res_in.status_code, 400, f"Expected 400 for whatsapp_opt_in={bad_val}")
            self.assertFalse(res_in.get_json()["success"])

            # Test in whatsapp_opt_out
            res_out = self.client.patch(
                url,
                headers={"Authorization": f"Bearer {self.token}"},
                json={"whatsapp_opt_out": bad_val},
            )
            self.assertEqual(res_out.status_code, 400, f"Expected 400 for whatsapp_opt_out={bad_val}")
            self.assertFalse(res_out.get_json()["success"])

    # --------------------------------------------------------------------------
    # 7. Contradictory consent values are rejected
    # --------------------------------------------------------------------------
    def test_07_contradictory_consent_values_rejected(self):
        """Contradictory values (both True, or both False) are rejected with 400."""
        url = "/api/profile/whatsapp-consent"

        # Both True
        res_both_true = self.client.patch(
            url,
            headers={"Authorization": f"Bearer {self.token}"},
            json={"whatsapp_opt_in": True, "whatsapp_opt_out": True},
        )
        self.assertEqual(res_both_true.status_code, 400)
        self.assertFalse(res_both_true.get_json()["success"])
        self.assertIn("cannot both be True", res_both_true.get_json()["message"])

        # Both False
        res_both_false = self.client.patch(
            url,
            headers={"Authorization": f"Bearer {self.token}"},
            json={"whatsapp_opt_in": False, "whatsapp_opt_out": False},
        )
        self.assertEqual(res_both_false.status_code, 400)
        self.assertFalse(res_both_false.get_json()["success"])
        self.assertIn("cannot both be False", res_both_false.get_json()["message"])

        # Non-contradictory combinations succeed
        res_valid_1 = self.client.patch(
            url,
            headers={"Authorization": f"Bearer {self.token}"},
            json={"whatsapp_opt_in": True, "whatsapp_opt_out": False},
        )
        self.assertEqual(res_valid_1.status_code, 200)

        res_valid_2 = self.client.patch(
            url,
            headers={"Authorization": f"Bearer {self.token}"},
            json={"whatsapp_opt_in": False, "whatsapp_opt_out": True},
        )
        self.assertEqual(res_valid_2.status_code, 200)

    # --------------------------------------------------------------------------
    # 8. A user cannot change another user's consent
    # --------------------------------------------------------------------------
    def test_08_user_cannot_change_another_user_consent(self):
        """User A cannot modify User B's consent via body or query user_id spoofing."""
        url = "/api/profile/whatsapp-consent"

        # Victim currently has opt_in=False, opt_out=False
        victim_before = self.profiles.find_one({"_id": self.victim_oid})
        self.assertFalse(victim_before["whatsapp_opt_in"])
        self.assertFalse(victim_before["whatsapp_opt_out"])

        # User A supplies victim_id in request body
        res_body_spoof = self.client.patch(
            url,
            headers={"Authorization": f"Bearer {self.token}"},
            json={"user_id": self.victim_id, "whatsapp_opt_in": True},
        )
        self.assertEqual(res_body_spoof.status_code, 403)
        self.assertFalse(res_body_spoof.get_json()["success"])

        # User A supplies victim_id in query parameter
        res_query_spoof = self.client.patch(
            f"{url}?user_id={self.victim_id}",
            headers={"Authorization": f"Bearer {self.token}"},
            json={"whatsapp_opt_in": True},
        )
        self.assertEqual(res_query_spoof.status_code, 403)
        self.assertFalse(res_query_spoof.get_json()["success"])

        # Verify Victim's consent was NOT touched
        victim_after = self.profiles.find_one({"_id": self.victim_oid})
        self.assertFalse(victim_after["whatsapp_opt_in"])
        self.assertFalse(victim_after["whatsapp_opt_out"])

        # Verify User A's legitimate request only changes User A's profile
        res_legit = self.client.patch(
            url,
            headers={"Authorization": f"Bearer {self.token}"},
            json={"whatsapp_opt_in": True},
        )
        self.assertEqual(res_legit.status_code, 200)
        user_a_doc = self.profiles.find_one({"_id": self.user_oid})
        self.assertTrue(user_a_doc["whatsapp_opt_in"])

    # --------------------------------------------------------------------------
    # 9. Existing profiles missing consent fields remain promotional-ineligible
    # --------------------------------------------------------------------------
    def test_09_existing_profiles_missing_consent_fields_remain_promotional_ineligible(self):
        """Legacy documents with no consent fields remain ineligible for promotional WhatsApp."""
        legacy_oid = ObjectId()
        self.profiles.insert_one({
            "_id": legacy_oid,
            "email": "legacy_consent_test@example.com",
            "phone": "+919876543210",
            "full_name": "Legacy Customer",
        })

        try:
            legacy_doc = self.profiles.find_one({"_id": legacy_oid})
            self.assertNotIn("whatsapp_opt_in", legacy_doc)
            self.assertNotIn("whatsapp_opt_out", legacy_doc)

            # Promotional evaluation
            for promo_type in ["lead_qualified", "cart_abandoned", "product_price_drop"]:
                elig = evaluate_channel_eligibility(legacy_doc, campaign_type=promo_type)
                self.assertTrue(elig["email"]["eligible"])
                self.assertFalse(elig["whatsapp"]["eligible"])
                self.assertIn("not opted in", elig["whatsapp"]["reason"])
        finally:
            self.profiles.delete_one({"_id": legacy_oid})

    # --------------------------------------------------------------------------
    # 10. Eligibility still blocks WhatsApp when opt-out is true
    # --------------------------------------------------------------------------
    def test_10_eligibility_blocks_whatsapp_when_opt_out_is_true(self):
        """Opt-out strictly blocks WhatsApp for both promotional and transactional flows."""
        # Opt-out via the API
        url = "/api/profile/whatsapp-consent"
        res = self.client.patch(
            url,
            headers={"Authorization": f"Bearer {self.token}"},
            json={"whatsapp_opt_out": True},
        )
        self.assertEqual(res.status_code, 200)

        updated_profile = self.profiles.find_one({"_id": self.user_oid})
        self.assertTrue(updated_profile["whatsapp_opt_out"])

        # Check promotional
        promo_elig = evaluate_channel_eligibility(updated_profile, campaign_type="cart_abandoned")
        self.assertFalse(promo_elig["whatsapp"]["eligible"])
        self.assertIn("opted out", promo_elig["whatsapp"]["reason"])
        self.assertTrue(promo_elig["email"]["eligible"])

        # Check transactional
        tx_elig = evaluate_channel_eligibility(updated_profile, campaign_type="registration")
        self.assertFalse(tx_elig["whatsapp"]["eligible"])
        self.assertIn("opted out", tx_elig["whatsapp"]["reason"])
        self.assertTrue(tx_elig["email"]["eligible"])

    # --------------------------------------------------------------------------
    # 11. The endpoint never sends communications or invokes external providers
    # --------------------------------------------------------------------------
    @patch("communication_provider.CommunicationProvider.send_whatsapp")
    @patch("communication_provider.CommunicationProvider.send_email")
    def test_11_endpoint_never_sends_communications_or_invokes_external_providers(
        self, mock_send_email, mock_send_wa
    ):
        """Calling the consent endpoint never triggers any email or WhatsApp message."""
        url = "/api/profile/whatsapp-consent"

        res_optin = self.client.patch(
            url,
            headers={"Authorization": f"Bearer {self.token}"},
            json={"whatsapp_opt_in": True},
        )
        self.assertEqual(res_optin.status_code, 200)

        res_optout = self.client.patch(
            url,
            headers={"Authorization": f"Bearer {self.token}"},
            json={"whatsapp_opt_out": True},
        )
        self.assertEqual(res_optout.status_code, 200)

        # Assert no communication calls were made
        mock_send_email.assert_not_called()
        mock_send_wa.assert_not_called()

    # --------------------------------------------------------------------------
    # 12. GET consent & phone normalization integration
    # --------------------------------------------------------------------------
    def test_12_get_consent_and_phone_normalization(self):
        """Endpoint supports GET for consent inspection and normalizes optional phone."""
        url = "/api/profile/whatsapp-consent"

        # Update consent with formatted phone
        res_patch = self.client.patch(
            url,
            headers={"Authorization": f"Bearer {self.token}"},
            json={"whatsapp_opt_in": True, "phone": "+91 98765-43210"},
        )
        self.assertEqual(res_patch.status_code, 200)
        data_patch = res_patch.get_json()["data"]
        self.assertEqual(data_patch["phone"], "919876543210")

        # GET request returns current profile consent
        res_get = self.client.get(
            url,
            headers={"Authorization": f"Bearer {self.token}"},
        )
        self.assertEqual(res_get.status_code, 200)
        data_get = res_get.get_json()["data"]
        self.assertTrue(data_get["whatsapp_opt_in"])
        self.assertFalse(data_get["whatsapp_opt_out"])
        self.assertEqual(data_get["phone"], "919876543210")
        self.assertNotIn("password", data_get)

        # Invalid phone is rejected
        res_bad_phone = self.client.patch(
            url,
            headers={"Authorization": f"Bearer {self.token}"},
            json={"whatsapp_opt_in": True, "phone": "invalid-phone"},
        )
        self.assertEqual(res_bad_phone.status_code, 400)
        self.assertIn("Invalid WhatsApp phone number", res_bad_phone.get_json()["message"])


if __name__ == "__main__":
    unittest.main()
