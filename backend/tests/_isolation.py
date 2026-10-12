"""Shared test-isolation utilities for the backend test suite.

This module is the **single source of truth** for:
- The allowed test MongoDB URI and database name.
- URI and database-name safety validators.
- The env-var publishing function that must run before ``app`` is imported.

It is imported by both:
- ``backend/tests/__init__.py``   → covers ``python -m unittest`` paths.
- ``backend/tests/conftest.py``   → covers all pytest invocation paths.

Do NOT import ``app`` from here.  This module must stay free of application
imports so it can be loaded at the earliest possible point.
"""

from __future__ import annotations

import os
import sys

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Default values — read live from the environment at publish time.
# These module-level constants document the defaults but are NOT used
# inside publish_test_environment(); that function reads os.environ live
# so that mutating TEST_MONGO_URI / TEST_MONGO_DB_NAME *after* module
# import is correctly detected and validated.
_DEFAULT_MONGO_URI: str = "mongodb://127.0.0.1:27017"
_DEFAULT_DATABASE_NAME: str = "leadmagnet_test"

# Expose as module-level names for backward compatibility (conftest imports them).
# These reflect the value at *first import* time only.
TEST_MONGO_URI: str = os.environ.get("TEST_MONGO_URI", _DEFAULT_MONGO_URI)
TEST_DATABASE_NAME: str = os.environ.get("TEST_MONGO_DB_NAME", _DEFAULT_DATABASE_NAME)

_FORBIDDEN_URI_PATTERNS = ("mongodb+srv://", "atlas", ".mongodb.net")
_LOCAL_INDICATORS = ("localhost", "127.", "::1")
_FORBIDDEN_DB_NAMES = frozenset({"leadmagnet", "lead_magnet", "leadmagnetdb", "production"})


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

def assert_safe_test_uri(uri: str) -> None:
    """Raise ``RuntimeError`` if *uri* points at a remote or production database.

    Called at module scope during test discovery so the suite aborts before
    any application code is imported.
    """
    uri_lower = uri.lower()
    for pattern in _FORBIDDEN_URI_PATTERNS:
        if pattern in uri_lower:
            raise RuntimeError(
                f"[TEST SAFETY] Refusing to use URI that looks like a remote/Atlas "
                f"database in the test suite: {uri!r}\n"
                "Set TEST_MONGO_URI to a local MongoDB address "
                "(e.g. mongodb://127.0.0.1:27017) to run database-dependent tests."
            )
    if not any(ind in uri_lower for ind in _LOCAL_INDICATORS):
        raise RuntimeError(
            f"[TEST SAFETY] TEST_MONGO_URI does not appear to be a local "
            f"connection: {uri!r}\n"
            "Only localhost connections are permitted during testing."
        )


def assert_safe_test_db(db_name: str) -> None:
    """Raise ``RuntimeError`` if *db_name* is a known production database name."""
    if db_name.lower() in _FORBIDDEN_DB_NAMES:
        raise RuntimeError(
            f"[TEST SAFETY] Refusing to use database name {db_name!r} for "
            "tests.  Use a name that is clearly scoped to testing, "
            "e.g. 'leadmagnet_test'."
        )
    if "test" not in db_name.lower():
        raise RuntimeError(
            f"[TEST SAFETY] Test database name {db_name!r} does not contain "
            "the word 'test'.  Rename it to something like 'leadmagnet_test' "
            "to make its purpose unambiguous."
        )


def is_safe_to_drop(db) -> bool:
    """Return ``True`` only when *db* is confirmed to be the local test database."""
    if db is None:
        return False
    db_name = db.name if hasattr(db, "name") else str(db)
    # Read the live configured URI so this reflects any override set after import.
    live_uri = os.environ.get("TEST_MONGO_URI", os.environ.get("MONGO_URI", _DEFAULT_MONGO_URI))
    try:
        assert_safe_test_uri(live_uri)
        assert_safe_test_db(db_name)
        return True
    except RuntimeError:
        return False


# ---------------------------------------------------------------------------
# Environment publisher
# ---------------------------------------------------------------------------

def publish_test_environment() -> None:
    """Set all required test environment variables.

    Must be called **before** any import of ``app`` or any service module.
    Calling it multiple times is safe (idempotent).

    Reads ``TEST_MONGO_URI`` and ``TEST_MONGO_DB_NAME`` **live from
    os.environ at call time** so that any override applied after this
    module was first imported is correctly validated.  If the live env
    var is absent, the built-in defaults are used.

    Raises ``RuntimeError`` immediately if the configured URI or database
    name would connect to a remote or production-named database.
    """
    # Read live — do NOT use the module-level constants here.
    uri = os.environ.get("TEST_MONGO_URI", _DEFAULT_MONGO_URI)
    db_name = os.environ.get("TEST_MONGO_DB_NAME", _DEFAULT_DATABASE_NAME)

    # Validate first — fail fast before touching the rest of os.environ.
    assert_safe_test_uri(uri)
    assert_safe_test_db(db_name)

    os.environ["TESTING"] = "1"
    os.environ["LOCAL_ONLY_TESTING"] = "1"
    os.environ["MONGO_URI"] = uri
    os.environ["MONGO_DB_NAME"] = db_name
    os.environ["COMMUNICATION_PROVIDER"] = "dry_run"
    os.environ["ALLOW_REAL_DISPATCH"] = "false"
    os.environ["ENABLE_SCHEDULER"] = "false"
    os.environ["FLASK_ENV"] = "testing"

    # Safe defaults for credentials that app.py reads at import time.
    # Using setdefault so an already-published value is never overwritten.
    os.environ.setdefault("JWT_SECRET", "test-only-insecure-jwt-secret-key-32b")
    os.environ.setdefault("ADMIN_USERNAME", "test_admin")
    os.environ.setdefault("ADMIN_PASSWORD", "test_admin_password")


# ---------------------------------------------------------------------------
# Ensure backend package directory is importable from any invocation path.
# ---------------------------------------------------------------------------

def ensure_backend_on_path() -> None:
    """Add the backend root to ``sys.path`` if it is not already present."""
    backend_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if backend_root not in sys.path:
        sys.path.insert(0, backend_root)
