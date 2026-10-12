"""Focused unit tests for Smart Channel Selection Service.

Tests:
1. WhatsApp selected when eligible and preferred by policy.
2. Gmail selected when WhatsApp consent is missing.
3. Gmail selected when customer has opted out of WhatsApp.
4. Gmail selected when WhatsApp number is invalid.
5. Promotional WhatsApp never selected without explicit opt-in.
6. Transactional messages follow transactional eligibility rules.
7. No eligible channel returns a clear no-channel result.
8. Repeated selection with identical inputs is deterministic.
9. Email-preferred policy selects Gmail when both channels are eligible.
10. Pre-computed eligibility dict respected with safety guards.
"""

import os
import sys
import unittest
from bson import ObjectId

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from channel_selector_service import (
    select_communication_channel,
    POLICY_WHATSAPP_FIRST,
    POLICY_EMAIL_FIRST,
    CHANNEL_EMAIL,
    CHANNEL_WHATSAPP,
)


class TestChannelSelectorService(unittest.TestCase):
    """Test suite verifying isolated smart channel selection logic."""

    # --------------------------------------------------------------------------
    # 1. WhatsApp selected when eligible and preferred by policy
    # --------------------------------------------------------------------------
    def test_whatsapp_selected_when_eligible_and_preferred_by_policy(self):
        """Customer with opt-in, valid phone, and valid email receives WhatsApp when preferred."""
        profile = {
            "email": "eligible@example.com",
            "phone": "+919876543210",
            "whatsapp_opt_in": True,
            "whatsapp_opt_out": False,
        }
        result = select_communication_channel(
            user_profile=profile,
            campaign_type="cart_abandoned",
            preference_policy=POLICY_WHATSAPP_FIRST,
        )

        self.assertTrue(result["eligible"])
        self.assertEqual(result["channel"], CHANNEL_WHATSAPP)
        self.assertEqual(result["selected_channel"], CHANNEL_WHATSAPP)
        self.assertEqual(result["recipient"], "+919876543210")
        self.assertTrue(result["fallback_available"])
        self.assertEqual(result["fallback_channel"], CHANNEL_EMAIL)
        self.assertIn("WhatsApp selected as primary channel", result["reason"])

    # --------------------------------------------------------------------------
    # 2. Gmail selected when WhatsApp consent is missing
    # --------------------------------------------------------------------------
    def test_gmail_selected_when_whatsapp_consent_is_missing(self):
        """Customer without recorded WhatsApp opt-in falls back to Gmail for promotional messages."""
        profile = {
            "email": "noconsent@example.com",
            "phone": "+919876543210",
            # whatsapp_opt_in omitted / missing
        }
        result = select_communication_channel(
            user_profile=profile,
            campaign_type="lead_qualified",
            preference_policy=POLICY_WHATSAPP_FIRST,
        )

        self.assertTrue(result["eligible"])
        self.assertEqual(result["channel"], CHANNEL_EMAIL)
        self.assertEqual(result["recipient"], "noconsent@example.com")
        self.assertFalse(result["fallback_available"])
        self.assertIsNone(result["fallback_channel"])
        self.assertIn("WhatsApp is ineligible", result["reason"])
        self.assertIn("not opted in", result["reason"].lower())

    # --------------------------------------------------------------------------
    # 3. Gmail selected when the customer has opted out of WhatsApp
    # --------------------------------------------------------------------------
    def test_gmail_selected_when_customer_has_opted_out_of_whatsapp(self):
        """Customer with opt-out falls back to Gmail, even if whatsapp_opt_in was True."""
        profile = {
            "email": "optedout@example.com",
            "phone": "+919876543210",
            "whatsapp_opt_in": True,
            "whatsapp_opt_out": True,
        }
        result = select_communication_channel(
            user_profile=profile,
            campaign_type="cart_abandoned",
            preference_policy=POLICY_WHATSAPP_FIRST,
        )

        self.assertTrue(result["eligible"])
        self.assertEqual(result["channel"], CHANNEL_EMAIL)
        self.assertEqual(result["recipient"], "optedout@example.com")
        self.assertFalse(result["fallback_available"])
        self.assertIn("opted out", result["reason"].lower())

    # --------------------------------------------------------------------------
    # 4. Gmail selected when the WhatsApp number is invalid
    # --------------------------------------------------------------------------
    def test_gmail_selected_when_whatsapp_number_is_invalid(self):
        """Invalid or unusable phone numbers result in Gmail selection."""
        invalid_numbers = [
            None,
            "",
            "    ",
            "not-a-number",
            "9876543210",        # National number without country code
            "+1234",              # < 8 digits
            "+1234567890123456",  # > 15 digits
        ]
        for bad_phone in invalid_numbers:
            profile = {
                "email": "valid_email@example.com",
                "phone": bad_phone,
                "whatsapp_opt_in": True,
                "whatsapp_opt_out": False,
            }
            result = select_communication_channel(
                user_profile=profile,
                campaign_type="cart_abandoned",
                preference_policy=POLICY_WHATSAPP_FIRST,
            )

            self.assertTrue(result["eligible"], f"Email should be eligible for phone: {bad_phone}")
            self.assertEqual(result["channel"], CHANNEL_EMAIL)
            self.assertEqual(result["recipient"], "valid_email@example.com")
            self.assertFalse(result["fallback_available"])

    # --------------------------------------------------------------------------
    # 5. Promotional WhatsApp never selected without explicit opt-in
    # --------------------------------------------------------------------------
    def test_promotional_whatsapp_never_selected_without_explicit_opt_in(self):
        """All promotional campaigns refuse WhatsApp without explicit opt_in=True."""
        promotional_campaigns = [
            "lead_qualified",
            "lead_qualification",
            "cart_abandoned",
            "wishlist_reminder",
            "opportunity",
            "product_price_drop",
        ]
        profile_no_opt_in = {
            "email": "promo@example.com",
            "phone": "+919876543210",
            "whatsapp_opt_in": False,
            "whatsapp_opt_out": False,
        }

        for camp in promotional_campaigns:
            result = select_communication_channel(
                user_profile=profile_no_opt_in,
                campaign_type=camp,
                preference_policy=POLICY_WHATSAPP_FIRST,
            )
            self.assertNotEqual(result["channel"], CHANNEL_WHATSAPP, f"WhatsApp selected for {camp} without consent!")
            self.assertEqual(result["channel"], CHANNEL_EMAIL)

        # When email is also unavailable, channel must be None
        profile_no_email_no_optin = {
            "email": "",
            "phone": "+919876543210",
            "whatsapp_opt_in": False,
        }
        res_none = select_communication_channel(
            user_profile=profile_no_email_no_optin,
            campaign_type="lead_qualified",
        )
        self.assertFalse(res_none["eligible"])
        self.assertIsNone(res_none["channel"])

    # --------------------------------------------------------------------------
    # 6. Transactional messages follow transactional eligibility rules
    # --------------------------------------------------------------------------
    def test_transactional_messages_follow_transactional_eligibility_rules(self):
        """Transactional messages allow WhatsApp with valid phone without requiring promotional opt-in."""
        profile = {
            "email": "buyer@example.com",
            "phone": "+919876543210",
            "whatsapp_opt_in": False,
            "whatsapp_opt_out": False,
        }

        # 6a. Registration with WhatsApp-first policy selects WhatsApp
        res_reg = select_communication_channel(
            user_profile=profile,
            campaign_type="registration",
            preference_policy=POLICY_WHATSAPP_FIRST,
        )
        self.assertTrue(res_reg["eligible"])
        self.assertEqual(res_reg["channel"], CHANNEL_WHATSAPP)
        self.assertEqual(res_reg["classification"], "transactional")

        # 6b. Order confirmation with Email-first policy selects Email
        res_order = select_communication_channel(
            user_profile=profile,
            campaign_type="order_confirmation",
            preference_policy=POLICY_EMAIL_FIRST,
        )
        self.assertTrue(res_order["eligible"])
        self.assertEqual(res_order["channel"], CHANNEL_EMAIL)
        self.assertEqual(res_order["classification"], "transactional")
        self.assertTrue(res_order["fallback_available"])
        self.assertEqual(res_order["fallback_channel"], CHANNEL_WHATSAPP)

        # 6c. Transactional message blocked from WhatsApp if customer opted out
        profile_opted_out = dict(profile, whatsapp_opt_out=True)
        res_blocked = select_communication_channel(
            user_profile=profile_opted_out,
            campaign_type="registration",
            preference_policy=POLICY_WHATSAPP_FIRST,
        )
        self.assertTrue(res_blocked["eligible"])
        self.assertEqual(res_blocked["channel"], CHANNEL_EMAIL)
        self.assertFalse(res_blocked["fallback_available"])

    # --------------------------------------------------------------------------
    # 7. No eligible channel returns clear no-channel result
    # --------------------------------------------------------------------------
    def test_no_eligible_channel_returns_clear_no_channel_result(self):
        """When neither channel is eligible, returns channel=None with descriptive reason."""
        profile_empty = {
            "email": "",
            "phone": "",
            "whatsapp_opt_in": True,
        }
        result = select_communication_channel(user_profile=profile_empty)

        self.assertFalse(result["eligible"])
        self.assertIsNone(result["channel"])
        self.assertIsNone(result["selected_channel"])
        self.assertIsNone(result["recipient"])
        self.assertFalse(result["fallback_available"])
        self.assertIsNone(result["fallback_channel"])
        self.assertIn("No eligible channel available", result["reason"])

    # --------------------------------------------------------------------------
    # 8. Repeated selection with identical inputs is deterministic
    # --------------------------------------------------------------------------
    def test_repeated_selection_with_identical_inputs_is_deterministic(self):
        """Repeated invocations across 50 iterations yield identical decisions."""
        profile = {
            "email": "deterministic@example.com",
            "phone": "+919876543210",
            "whatsapp_opt_in": True,
            "whatsapp_opt_out": False,
        }

        first_res = select_communication_channel(
            user_profile=profile,
            campaign_type="cart_abandoned",
            preference_policy=POLICY_WHATSAPP_FIRST,
        )

        for _ in range(50):
            res = select_communication_channel(
                user_profile=profile,
                campaign_type="cart_abandoned",
                preference_policy=POLICY_WHATSAPP_FIRST,
            )
            self.assertEqual(res["channel"], first_res["channel"])
            self.assertEqual(res["recipient"], first_res["recipient"])
            self.assertEqual(res["eligible"], first_res["eligible"])
            self.assertEqual(res["reason"], first_res["reason"])
            self.assertEqual(res["classification"], first_res["classification"])
            self.assertEqual(res["fallback_available"], first_res["fallback_available"])

    # --------------------------------------------------------------------------
    # 9. Email-preferred policy selects Gmail when both eligible
    # --------------------------------------------------------------------------
    def test_email_preferred_policy_selects_gmail(self):
        """When policy prefers email, Gmail is selected even if WhatsApp is fully eligible."""
        profile = {
            "email": "prefer_email@example.com",
            "phone": "+919876543210",
            "whatsapp_opt_in": True,
            "whatsapp_opt_out": False,
        }
        result = select_communication_channel(
            user_profile=profile,
            campaign_type="lead_qualified",
            preference_policy=POLICY_EMAIL_FIRST,
        )

        self.assertTrue(result["eligible"])
        self.assertEqual(result["channel"], CHANNEL_EMAIL)
        self.assertEqual(result["recipient"], "prefer_email@example.com")
        self.assertTrue(result["fallback_available"])
        self.assertEqual(result["fallback_channel"], CHANNEL_WHATSAPP)

    # --------------------------------------------------------------------------
    # 10. Pre-computed eligibility dict respected with safety guards
    # --------------------------------------------------------------------------
    def test_precomputed_eligibility_respected_with_safety_guards(self):
        """Passing precomputed eligibility works, and opt-out invariant still overrides."""
        precomputed = {
            "email": {"eligible": True, "recipient": "pre@example.com", "reason": "eligible"},
            "whatsapp": {"eligible": True, "recipient": "+919876543210", "reason": "eligible"},
        }

        # 10a. Normal case
        res1 = select_communication_channel(
            user_profile={"whatsapp_opt_in": True},
            eligibility=precomputed,
            preference_policy=POLICY_WHATSAPP_FIRST,
        )
        self.assertEqual(res1["channel"], CHANNEL_WHATSAPP)

        # 10b. Safety guard: Customer opted out in profile overrides precomputed WhatsApp eligibility
        res2 = select_communication_channel(
            user_profile={"whatsapp_opt_in": True, "whatsapp_opt_out": True},
            eligibility=precomputed,
            preference_policy=POLICY_WHATSAPP_FIRST,
        )
        self.assertEqual(res2["channel"], CHANNEL_EMAIL)


if __name__ == "__main__":
    unittest.main()
