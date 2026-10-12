"""Regression and hardening tests for WhatsApp Configuration and Safe Delivery (Task 14.3).

Verifies:
1. Missing credentials block WhatsApp dispatch gracefully with clear error.
2. Dry-run mode makes zero network calls and generates safe message IDs.
3. Phone numbers are normalized and validated in E.164 format.
4. Promotional WhatsApp messages require explicit consent (whatsapp_promotional_consent).
5. Inbound STOP opt-out strictly overrides consent.
6. Smart channel selector selects single primary channel with graceful fallback.
7. Repeated dispatch attempts do not duplicate messages (idempotency key protection).
8. Provider errors redact access tokens and never leak secrets.
9. Webhook signature verification validates HMAC-SHA256 and rejects invalid signatures.
10. Controlled delivery execution safeguard blocks unconfirmed dispatches.
"""

import os
import unittest
from unittest.mock import patch, MagicMock
from bson import ObjectId

from communication_provider import (
    DryRunCommunicationProvider,
    WhatsAppBusinessProvider,
    normalize_whatsapp_phone,
)
from channel_selector_service import select_communication_channel
from whatsapp_webhook_service import verify_webhook_signature, verify_webhook_challenge
from marketing_automation_service import dispatch_communication
from verify_real_delivery import (
    check_configuration,
    run_controlled_whatsapp_test,
    run_application_whatsapp_journey,
    validate_phone_utility,
)


class TestWhatsAppConfigurationHardening(unittest.TestCase):
    """Test suite for WhatsApp configuration hardening and safe delivery controls."""

    def test_01_missing_credentials_block_dispatch_gracefully(self):
        """Missing Meta credentials return a clear structured error without raising exceptions."""
        with patch.dict(os.environ, {"WHATSAPP_API_TOKEN": "", "WHATSAPP_PHONE_NUMBER_ID": ""}):
            provider = WhatsAppBusinessProvider()
            res = provider.send_whatsapp("+919876543210", "Hello test")
            self.assertFalse(res["success"])
            self.assertEqual(res["provider"], "whatsapp_business")
            self.assertIn("WhatsApp Business credentials not configured", res["error"])
            self.assertIn("WHATSAPP_API_TOKEN", res["error"])
            self.assertIn("WHATSAPP_PHONE_NUMBER_ID", res["error"])

    def test_02_dry_run_provider_makes_zero_network_calls(self):
        """Dry-run provider generates mock ID and makes zero network calls."""
        provider = DryRunCommunicationProvider()
        res = provider.send_whatsapp("+919876543210", "Dry run test")
        self.assertTrue(res["success"])
        self.assertEqual(res["provider"], "dry_run")
        self.assertEqual(res["channel"], "whatsapp")
        self.assertTrue(res["provider_message_id"].startswith("dry-run-whatsapp-"))

    def test_03_phone_number_e164_normalization_rules(self):
        """Phone numbers must include country code; 10-digit national numbers are rejected."""
        # Valid international numbers with '+'
        valid_in, err = normalize_whatsapp_phone("+91 98765-43210")
        self.assertIsNone(err)
        self.assertEqual(valid_in, "919876543210")

        valid_us, err = normalize_whatsapp_phone("+1 (555) 123-4567")
        self.assertIsNone(err)
        self.assertEqual(valid_us, "15551234567")

        # Invalid: 10-digit number without country code
        invalid_no_cc, err = normalize_whatsapp_phone("9876543210")
        self.assertIsNone(invalid_no_cc)
        self.assertIn("lacks international country code", err)

        # Invalid: Empty or non-digits
        empty, err = normalize_whatsapp_phone("")
        self.assertIsNone(empty)
        self.assertIn("Invalid or empty phone number", err)

    def test_04_promotional_whatsapp_requires_explicit_consent(self):
        """Promotional campaigns strictly reject WhatsApp if consent is false or missing."""
        profile_no_consent = {
            "email": "cust@example.com",
            "phone": "+919876543210",
            "whatsapp_opt_in": False,
            "whatsapp_promotional_consent": False,
            "preferred_channel": "whatsapp",
        }
        res = select_communication_channel(
            user_profile=profile_no_consent,
            campaign_type="cart_abandonment",
            policy={"preference_policy": "whatsapp_first"},
        )
        # Should fallback to email because WhatsApp lacks promotional consent
        self.assertEqual(res["channel"], "email")
        self.assertEqual(res["selected_channel"], "email")
        self.assertFalse(res["eligibility"]["whatsapp"]["eligible"])

    def test_05_stop_opt_out_overrides_consent(self):
        """Customer who opted out (whatsapp_opt_out=True) cannot be selected for WhatsApp."""
        profile_opted_out = {
            "email": "cust@example.com",
            "phone": "+919876543210",
            "whatsapp_opt_in": True,
            "whatsapp_promotional_consent": True,
            "whatsapp_opt_out": True,
            "preferred_channel": "whatsapp",
        }
        res = select_communication_channel(
            user_profile=profile_opted_out,
            campaign_type="cart_abandonment",
            policy={"preference_policy": "whatsapp_first"},
        )
        self.assertEqual(res["channel"], "email")
        self.assertEqual(res["selected_channel"], "email")
        self.assertFalse(res["eligibility"]["whatsapp"]["eligible"])

    def test_06_idempotency_prevents_duplicate_sends(self):
        """Repeated dispatch with same idempotency key returns existing record without resending."""
        mock_comm_col = MagicMock()
        existing_doc = {
            "_id": ObjectId(),
            "idempotency_key": "cart_abandon:cust_123:email",
            "status": "sent",
            "channel": "email",
            "recipient": "cust@example.com",
        }
        mock_comm_col.find_one.return_value = existing_doc
        mock_db = {"marketing_communications": mock_comm_col}

        provider = MagicMock()
        res = dispatch_communication(
            mock_db,
            "cust_123",
            "cart_abandonment",
            "email",
            "cust@example.com",
            subject="Test",
            body="Body",
            idempotency_key="cart_abandon:cust_123:email",
            provider=provider,
        )

        self.assertEqual(res["status"], "sent")
        provider.send_email.assert_not_called()

    @patch("communication_provider._requests_lib.post")
    def test_07_provider_error_redacts_tokens(self, mock_post):
        """Meta API error response redacts sensitive access token."""
        secret_token = "EAABw_SUPER_SECRET_TOKEN_999888"
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.content = b'{"error":{"message":"Failed"}}'
        mock_response.json.return_value = {
            "error": {"code": 190, "message": f"Invalid OAuth token: {secret_token}"}
        }
        mock_post.return_value = mock_response

        with patch.dict(os.environ, {
            "WHATSAPP_API_TOKEN": secret_token,
            "WHATSAPP_PHONE_NUMBER_ID": "12345678",
        }):
            provider = WhatsAppBusinessProvider()
            res = provider.send_whatsapp("+919876543210", "Test message")
            self.assertFalse(res["success"])
            self.assertNotIn(secret_token, res["error"])
            self.assertIn("[REDACTED]", res["error"])

    def test_08_webhook_signature_validation(self):
        """HMAC-SHA256 signature verification accepts valid signature and rejects invalid/tampered bodies."""
        import hmac, hashlib
        app_secret = "test_meta_app_secret_abc123"
        raw_body = b'{"entry": [{"id": "123", "changes": []}]}'

        valid_sig = "sha256=" + hmac.new(app_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
        self.assertTrue(verify_webhook_signature(raw_body, valid_sig, app_secret))

        # Tampered body fails
        tampered_body = b'{"entry": [{"id": "999", "changes": []}]}'
        self.assertFalse(verify_webhook_signature(tampered_body, valid_sig, app_secret))

        # Wrong secret fails
        self.assertFalse(verify_webhook_signature(raw_body, valid_sig, "wrong_secret"))

    def test_09_verify_real_delivery_safeguard_blocks_unconfirmed_dispatch(self):
        """verify_real_delivery.py safely blocks live dispatch if confirm_real flag is missing."""
        with patch.dict(os.environ, {"ALLOW_REAL_DISPATCH": "false"}):
            # Without confirm_real=True, must return False without attempting send
            with patch("communication_provider.WhatsAppBusinessProvider.send_whatsapp") as mock_send:
                res = run_controlled_whatsapp_test("+919876543210", confirm_real=False)
                self.assertFalse(res)
                mock_send.assert_not_called()

    def test_10_validate_phone_utility_runs_safely(self):
        """validate_phone_utility reports validity without making external calls."""
        self.assertTrue(validate_phone_utility("+919876543210"))
        self.assertFalse(validate_phone_utility("9876543210"))

    def test_11_customer_with_promotional_consent_and_e164_selected_for_whatsapp(self):
        """Customer with explicit promotional consent and valid E.164 phone is selected for WhatsApp."""
        profile = {
            "email": "tester@example.com",
            "phone": "+917022441738",
            "whatsapp_opt_in": True,
            "whatsapp_promotional_consent": True,
            "whatsapp_opt_out": False,
        }
        res = select_communication_channel(
            user_profile=profile,
            campaign_type="cart_abandonment",
            policy={"preference_policy": "whatsapp_first"},
        )
        self.assertEqual(res["channel"], "whatsapp")
        self.assertEqual(res["selected_channel"], "whatsapp")
        self.assertTrue(res["eligible"])
        self.assertEqual(res["recipient"], "+917022441738")
        self.assertTrue(res["fallback_available"])
        self.assertEqual(res["fallback_channel"], "email")

    def test_12_customer_with_promotional_consent_only_flag_selected_for_whatsapp(self):
        """Customer with only whatsapp_promotional_consent=True (without whatsapp_opt_in) is selected."""
        profile = {
            "email": "tester@example.com",
            "phone": "+917022441738",
            "whatsapp_promotional_consent": True,
            "whatsapp_opt_out": False,
        }
        res = select_communication_channel(
            user_profile=profile,
            campaign_type="cart_abandonment",
            policy={"preference_policy": "whatsapp_first"},
        )
        self.assertEqual(res["channel"], "whatsapp")
        self.assertTrue(res["eligible"])

    def test_13_customer_without_consent_falls_back_to_email(self):
        """Customer without promotional consent is not sent WhatsApp; falls back to email."""
        profile = {
            "email": "tester@example.com",
            "phone": "+917022441738",
            "whatsapp_opt_in": False,
            "whatsapp_promotional_consent": False,
            "whatsapp_opt_out": False,
        }
        res = select_communication_channel(
            user_profile=profile,
            campaign_type="cart_abandonment",
            policy={"preference_policy": "whatsapp_first"},
        )
        self.assertEqual(res["channel"], "email")
        self.assertEqual(res["selected_channel"], "email")
        self.assertTrue(res["fallback_applied"])
        self.assertFalse(res["eligibility"]["whatsapp"]["eligible"])

    def test_14_customer_with_invalid_phone_falls_back_to_email(self):
        """Customer with non-E.164 phone (missing country code) is rejected for WhatsApp and falls back to email."""
        profile = {
            "email": "tester@example.com",
            "phone": "7022441738",  # 10 digits without country code
            "whatsapp_opt_in": True,
            "whatsapp_promotional_consent": True,
            "whatsapp_opt_out": False,
        }
        res = select_communication_channel(
            user_profile=profile,
            campaign_type="cart_abandonment",
            policy={"preference_policy": "whatsapp_first"},
        )
        self.assertEqual(res["channel"], "email")
        self.assertFalse(res["eligibility"]["whatsapp"]["eligible"])
        self.assertIn("lacks international country code", res["eligibility"]["whatsapp"]["reason"])

    def test_15_one_primary_channel_rule_strictly_enforced(self):
        """Only one primary channel is selected per opportunity, never simultaneous email and WhatsApp."""
        profile = {
            "email": "tester@example.com",
            "phone": "+917022441738",
            "whatsapp_opt_in": True,
            "whatsapp_promotional_consent": True,
            "whatsapp_opt_out": False,
        }
        res = select_communication_channel(
            user_profile=profile,
            campaign_type="product_price_drop",
            policy={"preference_policy": "whatsapp_first"},
        )
        # Primary channel is singular
        self.assertIn(res["channel"], ["whatsapp", "email"])
        self.assertIsInstance(res["channel"], str)
        self.assertNotEqual(res["channel"], "multi_channel")

    def test_16_customer_profile_service_syncs_both_consent_flags(self):
        """update_customer_whatsapp_consent synchronizes whatsapp_opt_in and whatsapp_promotional_consent."""
        from customer_profile_service import update_customer_whatsapp_consent
        mock_col = MagicMock()
        mock_col.find_one.return_value = {
            "user_id": "cust_task15",
            "whatsapp_opt_in": True,
            "whatsapp_promotional_consent": True,
            "whatsapp_opt_out": False,
        }

        # Test Opt-in
        res = update_customer_whatsapp_consent(mock_col, "cust_task15", opt_in=True)
        set_args = mock_col.update_one.call_args[0][1]["$set"]
        self.assertTrue(set_args["whatsapp_opt_in"])
        self.assertTrue(set_args["whatsapp_promotional_consent"])
        self.assertFalse(set_args["whatsapp_opt_out"])

        # Test Opt-out
        res = update_customer_whatsapp_consent(mock_col, "cust_task15", opt_out=True)
        set_args = mock_col.update_one.call_args[0][1]["$set"]
        self.assertFalse(set_args["whatsapp_opt_in"])
        self.assertFalse(set_args["whatsapp_promotional_consent"])
        self.assertTrue(set_args["whatsapp_opt_out"])

    def test_17_communication_provider_defaults_to_dry_run_safely(self):
        """With default test environment, provider defaults to dry_run and makes no network calls."""
        from communication_provider import get_communication_provider
        provider = get_communication_provider("dry_run")
        self.assertIsInstance(provider, DryRunCommunicationProvider)
        res = provider.send_whatsapp("+917022441738", "Test dry run message")
        self.assertTrue(res["success"])
        self.assertEqual(res["provider"], "dry_run")

    def test_18_workflow_delivery_safeguard_blocks_unconfirmed_dispatch(self):
        """run_application_whatsapp_journey blocks execution if confirm_real is False."""
        with patch.dict(os.environ, {"ALLOW_REAL_DISPATCH": "false"}):
            success, res = run_application_whatsapp_journey("nonexistent_cust", confirm_real=False)
            self.assertFalse(success)
            self.assertIn("confirmation required", res["error"])

    def test_19_workflow_delivery_safeguard_blocks_customer_without_consent(self):
        """run_application_whatsapp_journey blocks customers without promotional WhatsApp consent."""
        mock_profiles = MagicMock()
        mock_profiles.find_one.return_value = {
            "_id": ObjectId(),
            "email": "test_noconsent@example.com",
            "phone": "+919999988888",
            "whatsapp_opt_in": False,
            "whatsapp_promotional_consent": False,
            "whatsapp_opt_out": False,
        }
        mock_db = {"user_profiles": mock_profiles}
        with patch.dict(os.environ, {"ALLOW_REAL_DISPATCH": "true"}):
            success, res = run_application_whatsapp_journey("test_noconsent@example.com", confirm_real=True, db=mock_db)
            self.assertFalse(success)
            self.assertIn("not granted WhatsApp promotional consent", res["error"])

    def test_20_workflow_delivery_safeguard_blocks_opted_out_customer(self):
        """run_application_whatsapp_journey blocks customers with whatsapp_opt_out=True."""
        mock_profiles = MagicMock()
        mock_profiles.find_one.return_value = {
            "_id": ObjectId(),
            "email": "test_optout@example.com",
            "phone": "+919999988888",
            "whatsapp_opt_in": True,
            "whatsapp_promotional_consent": True,
            "whatsapp_opt_out": True,
        }
        mock_db = {"user_profiles": mock_profiles}
        with patch.dict(os.environ, {"ALLOW_REAL_DISPATCH": "true"}):
            success, res = run_application_whatsapp_journey("test_optout@example.com", confirm_real=True, db=mock_db)
            self.assertFalse(success)
            self.assertIn("opted out", res["error"])

    def test_21_workflow_delivery_runs_safely_with_mock_provider_when_confirmed(self):
        """run_application_whatsapp_journey executes the full pipeline when confirmed with provider."""
        cust_id = ObjectId()
        mock_profiles = MagicMock()
        mock_profiles.find_one.return_value = {
            "_id": cust_id,
            "email": "test_eligible@example.com",
            "phone": "+919999988888",
            "whatsapp_opt_in": True,
            "whatsapp_promotional_consent": True,
            "whatsapp_opt_out": False,
        }
        mock_provider = MagicMock(spec=DryRunCommunicationProvider)
        mock_comm_record = {
            "customer_id": cust_id,
            "channel": "whatsapp",
            "status": "sent",
            "provider": "dry_run",
            "provider_message_id": "dry-run-test-id",
        }
        mock_comm = MagicMock()
        mock_comm.find_one.return_value = mock_comm_record
        mock_db = {
            "user_profiles": mock_profiles,
            "marketing_communications": mock_comm,
        }

        with patch("opportunity_engine.process_customer_opportunities") as mock_opp_proc:
            mock_opp_proc.return_value = {
                "detected_count": 1,
                "communicated": [{"opportunity_key": "cart_disc:123", "channel": "whatsapp"}],
                "skipped": [],
            }
            with patch.dict(os.environ, {"ALLOW_REAL_DISPATCH": "true"}):
                success, res = run_application_whatsapp_journey(
                    str(cust_id),
                    confirm_real=True,
                    provider=mock_provider,
                    db=mock_db,
                )
                self.assertTrue(success)
                self.assertEqual(res["record"]["status"], "sent")
                self.assertEqual(res["record"]["channel"], "whatsapp")
                self.assertTrue(res["api_accepted"])
                self.assertFalse(res["delivery_confirmed"])
                self.assertIn("API Acceptance", res["delivery_status_note"])
                mock_opp_proc.assert_called_once()

    def test_22_ambiguous_customer_identifier_blocks_dispatch(self):
        """run_application_whatsapp_journey refuses dispatch if customer identifier matches multiple profiles."""
        mock_profiles = MagicMock()
        mock_profiles.find.return_value.limit.return_value = [
            {"_id": ObjectId(), "email": "duplicate@example.com"},
            {"_id": ObjectId(), "email": "duplicate@example.com"},
        ]
        mock_db = {"user_profiles": mock_profiles}
        with patch.dict(os.environ, {"ALLOW_REAL_DISPATCH": "true"}):
            success, res = run_application_whatsapp_journey(
                "duplicate@example.com",
                confirm_real=True,
                db=mock_db,
            )
            self.assertFalse(success)
            self.assertIn("ambiguous", res["error"].lower())

    def test_23_ambiguous_opportunities_without_selector_blocks_dispatch(self):
        """run_application_whatsapp_journey refuses dispatch if multiple opportunities exist without --opportunity-id."""
        cust_id = ObjectId()
        mock_profiles = MagicMock()
        mock_profiles.find_one.return_value = {
            "_id": cust_id,
            "email": "test@example.com",
            "phone": "+919999988888",
            "whatsapp_opt_in": True,
            "whatsapp_promotional_consent": True,
            "whatsapp_opt_out": False,
        }
        mock_opps_col = MagicMock()
        mock_opps_col.find.return_value = [
            {"_id": ObjectId(), "opportunity_key": "opp:1:cart"},
            {"_id": ObjectId(), "opportunity_key": "opp:2:wishlist"},
        ]
        mock_comm_col = MagicMock()
        mock_comm_col.find_one.return_value = None

        mock_db = {
            "user_profiles": mock_profiles,
            "marketing_opportunities": mock_opps_col,
            "marketing_communications": mock_comm_col,
        }
        with patch.dict(os.environ, {"ALLOW_REAL_DISPATCH": "true"}):
            success, res = run_application_whatsapp_journey(
                str(cust_id),
                confirm_real=True,
                db=mock_db,
            )
            self.assertFalse(success)
            self.assertIn("multiple eligible opportunities", res["error"].lower())
            self.assertEqual(len(res["eligible_opportunities"]), 2)

    def test_24_exact_opportunity_id_allows_dispatch_among_multiples(self):
        """Specifying exact opportunity ID allows dispatching single intended opportunity among multiples."""
        cust_id = ObjectId()
        opp1_id = ObjectId()
        opp2_id = ObjectId()
        mock_profiles = MagicMock()
        mock_profiles.find_one.return_value = {
            "_id": cust_id,
            "email": "test@example.com",
            "phone": "+919999988888",
            "whatsapp_opt_in": True,
            "whatsapp_promotional_consent": True,
            "whatsapp_opt_out": False,
        }
        mock_opps_col = MagicMock()
        mock_opps_col.find.return_value = [
            {"_id": opp1_id, "opportunity_key": "opp:1:cart"},
            {"_id": opp2_id, "opportunity_key": "opp:2:wishlist"},
        ]
        mock_comm_col = MagicMock()
        def _mock_comm_find(query):
            if "status" in query and query.get("status") == "sent":
                # Pre-dispatch check: not sent yet
                return None
            return {
                "customer_id": cust_id,
                "channel": "whatsapp",
                "status": "sent",
                "provider": "dry_run",
                "provider_message_id": "test-wamid-123",
            }
        mock_comm_col.find_one.side_effect = _mock_comm_find
        mock_db = {
            "user_profiles": mock_profiles,
            "marketing_opportunities": mock_opps_col,
            "marketing_communications": mock_comm_col,
        }
        mock_provider = MagicMock(spec=DryRunCommunicationProvider)

        with patch("opportunity_engine.process_customer_opportunities") as mock_opp_proc:
            mock_opp_proc.return_value = {
                "detected_count": 1,
                "communicated": [{"opportunity_key": "opp:2:wishlist", "channel": "whatsapp"}],
                "skipped": [],
            }
            with patch.dict(os.environ, {"ALLOW_REAL_DISPATCH": "true"}):
                success, res = run_application_whatsapp_journey(
                    str(cust_id),
                    opportunity_identifier="opp:2:wishlist",
                    confirm_real=True,
                    provider=mock_provider,
                    db=mock_db,
                )
                self.assertTrue(success)
                self.assertEqual(mock_opp_proc.call_args[1]["target_opportunity_key"], "opp:2:wishlist")
                self.assertTrue(res["api_accepted"])
                self.assertFalse(res["delivery_confirmed"])

    def test_25_zero_eligible_opportunities_blocks_dispatch(self):
        """run_application_whatsapp_journey refuses dispatch if customer has zero eligible opportunities."""
        cust_id = ObjectId()
        mock_profiles = MagicMock()
        mock_profiles.find_one.return_value = {
            "_id": cust_id,
            "email": "test@example.com",
            "phone": "+919999988888",
            "whatsapp_opt_in": True,
            "whatsapp_promotional_consent": True,
            "whatsapp_opt_out": False,
        }
        mock_opps_col = MagicMock()
        mock_opps_col.find.return_value = []
        mock_comm_col = MagicMock()

        mock_db = {
            "user_profiles": mock_profiles,
            "marketing_opportunities": mock_opps_col,
            "marketing_communications": mock_comm_col,
        }
        with patch.dict(os.environ, {"ALLOW_REAL_DISPATCH": "true"}):
            success, res = run_application_whatsapp_journey(
                str(cust_id),
                confirm_real=True,
                db=mock_db,
            )
            self.assertFalse(success)
            self.assertIn("zero eligible opportunities", res["error"].lower())

    def test_26_repeated_invocation_blocked_by_idempotency_guard(self):
        """Second invocation of run_application_whatsapp_journey is blocked because opportunity is already communicated."""
        cust_id = ObjectId()
        opp_key = "opp:repeat:key"
        mock_profiles = MagicMock()
        mock_profiles.find_one.return_value = {
            "_id": cust_id,
            "email": "test@example.com",
            "phone": "+919999988888",
            "whatsapp_opt_in": True,
            "whatsapp_promotional_consent": True,
            "whatsapp_opt_out": False,
        }
        mock_opps_col = MagicMock()
        mock_opps_col.find.return_value = [{"_id": ObjectId(), "opportunity_key": opp_key}]
        mock_comm_col = MagicMock()
        # Simulated existing sent record in marketing_communications
        mock_comm_col.find_one.return_value = {
            "customer_id": cust_id,
            "status": "sent",
            "channel": "whatsapp",
            "idempotency_key": f"{opp_key}:whatsapp",
        }
        mock_db = {
            "user_profiles": mock_profiles,
            "marketing_opportunities": mock_opps_col,
            "marketing_communications": mock_comm_col,
        }
        with patch.dict(os.environ, {"ALLOW_REAL_DISPATCH": "true"}):
            success, res = run_application_whatsapp_journey(
                str(cust_id),
                confirm_real=True,
                db=mock_db,
            )
            self.assertFalse(success)
            self.assertIn("zero eligible opportunities", res["error"].lower())


if __name__ == "__main__":
    unittest.main()
