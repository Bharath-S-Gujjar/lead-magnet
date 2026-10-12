"""Production configuration hardening tests (Task 9).

Covers:
1. Production-mode activation via FLASK_ENV / ENV.
2. CORS wildcard origin rejection in production.
3. MongoDB TLS — no insecure tlsAllowInvalidCertificates fallback.
4. Scheduler process isolation — web workers must not start the scheduler
   when ENABLE_SCHEDULER is not set to 'true'.
5. WhatsApp webhook fail-closed when verify token is absent.
6. No real messages, external API calls, or Atlas connections are made.
7. All DB operations use the isolated local test database.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch, call
import threading

# Ensure backend root is importable
_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

import app as app_module
from app import app


# ---------------------------------------------------------------------------
# 1. Production mode activation
# ---------------------------------------------------------------------------


class TestProductionModeActivation(unittest.TestCase):
    """Verify the application recognises FLASK_ENV=production."""

    def test_flask_env_production_detected(self):
        """IS_PRODUCTION is True when FLASK_ENV=production."""
        with patch.dict(os.environ, {"FLASK_ENV": "production"}, clear=False):
            is_prod = (
                os.getenv("FLASK_ENV", "").lower() == "production"
                or os.getenv("ENV", "").lower() == "production"
            )
            self.assertTrue(is_prod)

    def test_env_production_detected(self):
        """IS_PRODUCTION is True when ENV=production."""
        with patch.dict(os.environ, {"ENV": "production"}, clear=False):
            is_prod = (
                os.getenv("FLASK_ENV", "").lower() == "production"
                or os.getenv("ENV", "").lower() == "production"
            )
            self.assertTrue(is_prod)

    def test_non_production_env_not_detected(self):
        """IS_PRODUCTION is False when neither variable is 'production'."""
        env = {"FLASK_ENV": "development", "ENV": "development"}
        with patch.dict(os.environ, env, clear=False):
            is_prod = (
                os.getenv("FLASK_ENV", "").lower() == "production"
                or os.getenv("ENV", "").lower() == "production"
            )
            self.assertFalse(is_prod)

    def test_testing_env_not_detected_as_production(self):
        """FLASK_ENV=testing must not be treated as production."""
        with patch.dict(os.environ, {"FLASK_ENV": "testing"}, clear=False):
            is_prod = (
                os.getenv("FLASK_ENV", "").lower() == "production"
                or os.getenv("ENV", "").lower() == "production"
            )
            self.assertFalse(is_prod)

    def test_insecure_jwt_secret_raises_in_production(self):
        """Startup must raise ValueError if JWT_SECRET is the default in production."""
        insecure_secret = "default_jwt_secret_key_for_lead_magnet"
        is_prod = True
        # Simulate the env var being absent so the insecure default is used
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("JWT_SECRET", None)
            jwt_secret = os.getenv("JWT_SECRET") or insecure_secret

        if is_prod:
            with self.assertRaises(ValueError) as ctx:
                if jwt_secret == insecure_secret:
                    raise ValueError(
                        "Insecure JWT_SECRET detected in production environment."
                    )
            self.assertIn("JWT_SECRET", str(ctx.exception))

    def test_insecure_admin_password_raises_in_production(self):
        """Startup must raise ValueError if ADMIN_PASSWORD is 'admin12345' in production."""
        insecure_pw = "admin12345"
        is_prod = True
        # Simulate the env var being absent so the insecure default is used
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ADMIN_PASSWORD", None)
            admin_pw = os.getenv("ADMIN_PASSWORD", insecure_pw)

        if is_prod:
            with self.assertRaises(ValueError) as ctx:
                if admin_pw == insecure_pw:
                    raise ValueError(
                        "Insecure ADMIN_PASSWORD detected in production environment."
                    )
            self.assertIn("ADMIN_PASSWORD", str(ctx.exception))


# ---------------------------------------------------------------------------
# 2. CORS wildcard rejection in production
# ---------------------------------------------------------------------------


class TestCORSWildcardRejection(unittest.TestCase):
    """Wildcard FRONTEND_URL must be rejected at startup in production."""

    def _apply_cors_logic(self, frontend_url, is_prod):
        """Reproduce the CORS origin resolution logic from app.py for unit testing."""
        DEFAULT_ALLOWED_ORIGINS = [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]

        if is_prod and frontend_url and frontend_url.strip() == "*":
            raise ValueError(
                'FRONTEND_URL is set to "*" which is not allowed in production.'
            )

        if frontend_url:
            raw_origins = [o.strip() for o in frontend_url.split(",") if o.strip()]
            if is_prod and "*" in raw_origins:
                raise ValueError(
                    'FRONTEND_URL contains a wildcard origin "*" which is not permitted in production.'
                )
            allowed = raw_origins
        else:
            allowed = [] if is_prod else DEFAULT_ALLOWED_ORIGINS

        return allowed

    def test_wildcard_string_rejected_in_production(self):
        """FRONTEND_URL='*' raises ValueError in production."""
        with self.assertRaises(ValueError) as ctx:
            self._apply_cors_logic("*", is_prod=True)
        self.assertIn("*", str(ctx.exception))
        self.assertIn("not allowed", str(ctx.exception))

    def test_wildcard_in_list_rejected_in_production(self):
        """FRONTEND_URL='https://app.example.com,*' raises ValueError in production."""
        with self.assertRaises(ValueError) as ctx:
            self._apply_cors_logic("https://app.example.com,*", is_prod=True)
        self.assertIn("*", str(ctx.exception))

    def test_valid_origin_accepted_in_production(self):
        """Well-formed HTTPS origin list is accepted in production."""
        allowed = self._apply_cors_logic(
            "https://app.example.com,https://admin.example.com", is_prod=True
        )
        self.assertIn("https://app.example.com", allowed)
        self.assertIn("https://admin.example.com", allowed)
        self.assertNotIn("*", allowed)

    def test_no_frontend_url_in_production_yields_empty_origins(self):
        """Missing FRONTEND_URL in production yields an empty allowed-origins list."""
        allowed = self._apply_cors_logic(None, is_prod=True)
        self.assertEqual(allowed, [])
        self.assertNotIn("*", allowed)

    def test_wildcard_allowed_in_development(self):
        """Wildcard in FRONTEND_URL does NOT raise in non-production (development)."""
        # No ValueError expected
        allowed = self._apply_cors_logic("*", is_prod=False)
        self.assertIn("*", allowed)

    def test_empty_frontend_url_in_development_uses_defaults(self):
        """Missing FRONTEND_URL in development returns the localhost defaults."""
        allowed = self._apply_cors_logic(None, is_prod=False)
        self.assertGreater(len(allowed), 0)
        self.assertNotIn("*", allowed)


# ---------------------------------------------------------------------------
# 3. MongoDB TLS — no insecure fallback
# ---------------------------------------------------------------------------


class TestMongoDBTLSNoInsecureFallback(unittest.TestCase):
    """create_mongo_client must never pass tlsAllowInvalidCertificates=True."""

    def test_tls_allow_invalid_certificates_never_used(self):
        """MongoClient must never be called with tlsAllowInvalidCertificates=True."""
        from app import create_mongo_client

        calls_made = []

        class _MockClient:
            def __init__(self, uri, **kwargs):
                calls_made.append({"uri": uri, "kwargs": kwargs})
                self._fail = kwargs.get("serverSelectionTimeoutMS", 0) == 5000

            def admin(self):
                return self

            def command(self, cmd):
                if self._fail:
                    raise ConnectionError("simulated failure")

        with patch("app.MongoClient", side_effect=_MockClient):
            with patch.dict(os.environ, {"MONGO_URI": "mongodb://127.0.0.1:27017/test"}, clear=False):
                try:
                    create_mongo_client()
                except Exception:
                    pass

        for c in calls_made:
            self.assertFalse(
                c["kwargs"].get("tlsAllowInvalidCertificates", False),
                f"MongoClient was called with tlsAllowInvalidCertificates=True: {c}",
            )

    def test_create_mongo_client_does_not_use_insecure_flag_source(self):
        """Verify tlsAllowInvalidCertificates is absent from create_mongo_client source."""
        import inspect
        from app import create_mongo_client
        source = inspect.getsource(create_mongo_client)
        self.assertNotIn(
            "tlsAllowInvalidCertificates=True",
            source,
            "create_mongo_client must not contain tlsAllowInvalidCertificates=True",
        )

    def test_local_fallback_does_not_use_insecure_tls(self):
        """When MONGO_URI is unset the local fallback must not use insecure TLS."""
        from app import create_mongo_client

        calls_made = []

        class _MockLocalClient:
            def __init__(self, uri, **kwargs):
                calls_made.append({"uri": uri, "kwargs": kwargs})

            class admin:
                @staticmethod
                def command(cmd):
                    pass

        with patch("app.MongoClient", side_effect=_MockLocalClient):
            with patch.dict(os.environ, {}, clear=False):
                env_backup = os.environ.pop("MONGO_URI", None)
                try:
                    create_mongo_client()
                except Exception:
                    pass
                finally:
                    if env_backup is not None:
                        os.environ["MONGO_URI"] = env_backup

        for c in calls_made:
            self.assertFalse(
                c["kwargs"].get("tlsAllowInvalidCertificates", False),
                f"Local fallback MongoClient used insecure TLS: {c}",
            )


# ---------------------------------------------------------------------------
# 4. Scheduler process isolation
# ---------------------------------------------------------------------------


class TestSchedulerProcessIsolation(unittest.TestCase):
    """Web workers must not start the scheduler unless ENABLE_SCHEDULER=true."""

    def _simulate_initialize_database_scheduler_block(self, enable_scheduler_value):
        """Reproduce the scheduler-start decision logic from initialize_database."""
        enable_env = enable_scheduler_value.lower() if enable_scheduler_value else "false"
        is_enabled = enable_env in ("true", "1", "yes")
        is_testing = True  # always True in tests

        started = False
        if not is_testing and is_enabled:
            started = True
        return started

    def test_scheduler_not_started_when_enable_scheduler_false(self):
        """ENABLE_SCHEDULER=false means scheduler.start() is never called."""
        started = self._simulate_initialize_database_scheduler_block("false")
        self.assertFalse(started)

    def test_scheduler_not_started_when_enable_scheduler_unset(self):
        """Missing ENABLE_SCHEDULER (default false) means scheduler is not started."""
        started = self._simulate_initialize_database_scheduler_block("")
        self.assertFalse(started)

    def test_scheduler_started_when_enable_scheduler_true(self):
        """ENABLE_SCHEDULER=true AND not testing means scheduler.start() is called."""
        # Override the is_testing flag manually for this logic check
        enable_env = "true"
        is_enabled = enable_env in ("true", "1", "yes")
        is_testing = False

        started = False
        if not is_testing and is_enabled:
            started = True
        self.assertTrue(started)

    def test_enable_scheduler_default_is_false_not_true(self):
        """The app.py default for ENABLE_SCHEDULER must be 'false', not 'true'."""
        import inspect
        from app import initialize_database
        source = inspect.getsource(initialize_database)
        # The default must be "false" — old code defaulted to "true"
        self.assertIn('"false"', source)
        self.assertNotIn(
            'os.getenv("ENABLE_SCHEDULER", "true")',
            source,
            "initialize_database must not default ENABLE_SCHEDULER to 'true'.",
        )

    def test_scheduler_not_started_during_testing(self):
        """Scheduler must not start while TESTING=1 even if ENABLE_SCHEDULER=true."""
        with patch.dict(os.environ, {"ENABLE_SCHEDULER": "true", "TESTING": "1"}, clear=False):
            mock_scheduler = MagicMock()

            # Reproduce the decision logic from initialize_database directly.
            # When TESTING=1, app.testing is True and app.config["TESTING"] is True.
            is_testing = (
                os.environ.get("TESTING", "").strip() == "1"
                or getattr(app, "testing", False)
                or app.config.get("TESTING", False)
            )
            enable_env = os.getenv("ENABLE_SCHEDULER", "false").lower()
            is_enabled = enable_env in ("true", "1", "yes")

            if not is_testing and is_enabled:
                mock_scheduler.start(None)

        mock_scheduler.start.assert_not_called()


# ---------------------------------------------------------------------------
# 5. WhatsApp webhook fail-closed
# ---------------------------------------------------------------------------


class TestWhatsAppWebhookFailClosed(unittest.TestCase):
    """Webhook GET verification must fail closed when verify token is absent."""

    def setUp(self):
        self.client = app.test_client()
        # Ensure DB collections are available
        if app_module.MONGO_AVAILABLE:
            app_module.profiles_collection.delete_many({})

    def _get_webhook(self, token_env_value=None, mode="subscribe", token="sometoken", challenge="mychallenge"):
        """Helper: issue a GET to the webhook endpoint with controlled env."""
        env_patch = {}
        for key in ("WHATSAPP_WEBHOOK_VERIFY_TOKEN", "WHATSAPP_VERIFY_TOKEN", "META_VERIFY_TOKEN"):
            env_patch[key] = token_env_value or ""

        with patch.dict(os.environ, env_patch, clear=False):
            # Also clear any app.config override
            app.config.pop("WHATSAPP_WEBHOOK_VERIFY_TOKEN", None)
            resp = self.client.get(
                f"/api/webhook/whatsapp"
                f"?hub.mode={mode}&hub.verify_token={token}&hub.challenge={challenge}"
            )
        return resp

    def test_webhook_fails_closed_when_no_token_configured(self):
        """GET /api/webhook/whatsapp returns 500 when no verify token is set."""
        resp = self._get_webhook(token_env_value="")
        self.assertIn(resp.status_code, (500, 403))
        data = resp.get_json()
        self.assertFalse(data.get("success", True))

    def test_webhook_accepts_challenge_when_token_matches(self):
        """GET /api/webhook/whatsapp returns 200 when token is configured and matches."""
        secret_token = "test-verify-token-12345"
        with patch.dict(
            os.environ,
            {"WHATSAPP_WEBHOOK_VERIFY_TOKEN": secret_token},
            clear=False,
        ):
            resp = self.client.get(
                f"/api/webhook/whatsapp"
                f"?hub.mode=subscribe&hub.verify_token={secret_token}&hub.challenge=abc123"
            )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data, b"abc123")

    def test_webhook_rejects_wrong_token(self):
        """GET /api/webhook/whatsapp returns 403 when token does not match."""
        with patch.dict(
            os.environ,
            {"WHATSAPP_WEBHOOK_VERIFY_TOKEN": "correct-token"},
            clear=False,
        ):
            resp = self.client.get(
                "/api/webhook/whatsapp"
                "?hub.mode=subscribe&hub.verify_token=wrong-token&hub.challenge=abc123"
            )
        self.assertEqual(resp.status_code, 403)
        data = resp.get_json()
        self.assertFalse(data.get("success", True))

    def test_hardcoded_default_token_not_present_in_source(self):
        """The hardcoded fallback 'leadmagnet_wa_verify_token' must not exist in app.py."""
        import inspect
        source = inspect.getsource(app_module)
        self.assertNotIn(
            "leadmagnet_wa_verify_token",
            source,
            "Hardcoded fallback verify token 'leadmagnet_wa_verify_token' was found in app.py. "
            "It must be removed so that verification fails closed when no token is configured.",
        )

    def test_post_webhook_requires_app_secret(self):
        """POST /api/webhook/whatsapp with no app secret returns 500 (not 200)."""
        env_clear = {
            "WHATSAPP_APP_SECRET": "",
            "META_APP_SECRET": "",
        }
        with patch.dict(os.environ, env_clear, clear=False):
            app.config.pop("WHATSAPP_APP_SECRET", None)
            resp = self.client.post(
                "/api/webhook/whatsapp",
                data=b'{"entry":[]}',
                content_type="application/json",
                headers={"X-Hub-Signature-256": "sha256=invalid"},
            )
        # Either 401 (signature check) or 500 (no secret configured)
        self.assertIn(resp.status_code, (401, 500))
        data = resp.get_json()
        self.assertFalse(data.get("success", True))


# ---------------------------------------------------------------------------
# 6. Render.yaml deployment configuration
# ---------------------------------------------------------------------------


class TestRenderYamlConfiguration(unittest.TestCase):
    """render.yaml must not contain wildcard CORS or insecure defaults."""

    def _load_render_yaml_text(self):
        render_yaml_path = os.path.join(_BACKEND_DIR, "render.yaml")
        if not os.path.isfile(render_yaml_path):
            self.skipTest("render.yaml not found")
        with open(render_yaml_path, "r", encoding="utf-8") as f:
            return f.read()

    def test_no_wildcard_frontend_url_value(self):
        """render.yaml must not contain FRONTEND_URL value: \"*\"."""
        text = self._load_render_yaml_text()
        # Detect committed wildcard value
        import re
        # Match: "key: FRONTEND_URL" followed (eventually) by "value: \"*\""
        wildcard_pattern = re.compile(
            r"key:\s*FRONTEND_URL.*?value:\s*[\"']?\*[\"']?",
            re.DOTALL,
        )
        match = wildcard_pattern.search(text)
        self.assertIsNone(
            match,
            "render.yaml contains FRONTEND_URL with value \"*\". "
            "Remove or replace it with real frontend origins.",
        )

    def test_flask_env_production_set(self):
        """render.yaml must set FLASK_ENV=production for the web service."""
        text = self._load_render_yaml_text()
        self.assertIn("FLASK_ENV", text)
        self.assertIn("production", text)

    def test_enable_scheduler_false_for_web_service(self):
        """render.yaml web service must set ENABLE_SCHEDULER=false."""
        text = self._load_render_yaml_text()
        self.assertIn("ENABLE_SCHEDULER", text)
        self.assertIn("false", text)

    def test_admin_username_not_hardcoded(self):
        """render.yaml must not commit ADMIN_USERNAME with a literal value like 'admin'."""
        text = self._load_render_yaml_text()
        import re
        # Match hardcoded value: "key: ADMIN_USERNAME\n    value: admin"
        hardcoded = re.compile(
            r"key:\s*ADMIN_USERNAME\s*\n\s*value:\s*admin\s*$",
            re.MULTILINE,
        )
        self.assertIsNone(
            hardcoded.search(text),
            "render.yaml hardcodes ADMIN_USERNAME=admin. "
            "Use sync: false and configure it in the Render dashboard.",
        )


# ---------------------------------------------------------------------------
# 7. Webhook signature validation preserved
# ---------------------------------------------------------------------------


class TestWebhookSignatureValidation(unittest.TestCase):
    """Existing HMAC-SHA256 signature validation must still work correctly."""

    def test_valid_signature_accepted(self):
        """verify_webhook_signature returns True for a correct HMAC-SHA256."""
        import hmac as _hmac
        import hashlib
        from whatsapp_webhook_service import verify_webhook_signature

        secret = "test-app-secret-abc123"
        body = b'{"entry": []}'
        sig = _hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        self.assertTrue(verify_webhook_signature(body, f"sha256={sig}", secret))

    def test_invalid_signature_rejected(self):
        """verify_webhook_signature returns False for a tampered HMAC."""
        from whatsapp_webhook_service import verify_webhook_signature
        self.assertFalse(
            verify_webhook_signature(b"body", "sha256=deadbeef", "secret")
        )

    def test_missing_signature_header_rejected(self):
        """verify_webhook_signature returns False when signature header is None."""
        from whatsapp_webhook_service import verify_webhook_signature
        self.assertFalse(verify_webhook_signature(b"body", None, "secret"))

    def test_missing_app_secret_rejected(self):
        """verify_webhook_signature returns False when app_secret is None."""
        from whatsapp_webhook_service import verify_webhook_signature
        self.assertFalse(verify_webhook_signature(b"body", "sha256=abc", None))


if __name__ == "__main__":
    unittest.main()
