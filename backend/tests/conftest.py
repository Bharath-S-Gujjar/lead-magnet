"""Isolated MongoDB configuration for the backend pytest suite.

All environment variables are set in ``_isolation.py`` via ``__init__.py``
which runs before any test module import.  This conftest.py imports those
already-validated values, imports ``app``, and provides the autouse fixture.

Safety guarantees
-----------------
* TESTING=1 is set before app is imported → load_dotenv is suppressed.
* Atlas / remote URIs are rejected immediately on first import.
* Production database names are rejected immediately on first import.
* Every test starts and ends with an empty, explicitly named test database.
* Destructive operations are blocked unless both URI and DB name are validated.
* Both pytest and python -m unittest receive the same safety configuration via
  __init__.py (runs on package import) and this conftest.py (runs via pytest).
"""

import importlib.util
import os
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# 1. Load _isolation.py by absolute path — works regardless of sys.path state.
#    __init__.py already ran when the tests package was first imported, but
#    conftest.py may also be invoked directly by pytest before __init__ in some
#    edge cases.  Using importlib guarantees we always find the module.
# ---------------------------------------------------------------------------
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_ISOLATION_PATH = os.path.join(_THIS_DIR, "_isolation.py")

_spec = importlib.util.spec_from_file_location("tests._isolation", _ISOLATION_PATH)
_iso_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_iso_mod)

assert_safe_test_uri = _iso_mod.assert_safe_test_uri
assert_safe_test_db = _iso_mod.assert_safe_test_db
is_safe_to_drop = _iso_mod.is_safe_to_drop
publish_test_environment = _iso_mod.publish_test_environment
TEST_MONGO_URI = _iso_mod.TEST_MONGO_URI
TEST_DATABASE_NAME = _iso_mod.TEST_DATABASE_NAME

# Belt-and-suspenders: ensure env vars are published even if __init__ didn't run.
publish_test_environment()

# Keep old names as aliases so any test that imports from conftest still works.
_assert_safe_test_uri = assert_safe_test_uri
_assert_safe_test_db = assert_safe_test_db
_is_safe_to_drop = is_safe_to_drop

# Ensure backend root is on sys.path before importing app.
_BACKEND = str(Path(__file__).resolve().parents[1])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)


# ---------------------------------------------------------------------------
# 2. Import app now — TESTING=1 guarantees load_dotenv is skipped.
# ---------------------------------------------------------------------------
import app as app_module  # noqa: E402

# ---------------------------------------------------------------------------
# 3. Rebind all collection references to the test database (belt-and-suspenders
#    in case bind_collections ran before MONGO_DB_NAME was set).
# ---------------------------------------------------------------------------
app_module.app.config["TESTING"] = True
app_module.app.testing = True

_mongo_available = getattr(app_module, "MONGO_AVAILABLE", False)
if not _mongo_available:
    try:
        import mongomock
        _mock_client = mongomock.MongoClient()
        app_module.mongo_client = _mock_client
        app_module.MONGO_AVAILABLE = True
        _test_db = _mock_client[TEST_DATABASE_NAME]
    except Exception:
        _test_db = None
else:
    try:
        _test_db = app_module.mongo_client[TEST_DATABASE_NAME]
    except Exception:
        _test_db = None

if _test_db is not None:
    app_module.db = _test_db
    app_module.profiles_collection = _test_db["user_profiles"]
    app_module.legacy_users_collection = _test_db["users"]
    app_module.products_collection = _test_db["myntra_products"]
    app_module.sessions_collection = _test_db["sessions"]
    app_module.events_collection = _test_db["events"]
    app_module.leads_collection = _test_db["leads"]
    app_module.orders_collection = _test_db["orders"]
    app_module.cart_collection = _test_db["cart"]
    app_module.wishlist_collection = _test_db["wishlist"]
    app_module.campaigns_collection = _test_db["campaigns"]
    app_module.campaign_logs_collection = _test_db["campaign_logs"]
    app_module.customer_features_collection = _test_db["customer_features"]
    app_module.customer_lead_state_collection = _test_db["customer_lead_state"]
    app_module.marketing_automation_events_collection = _test_db[
        "marketing_automation_events"
    ]
    app_module.marketing_communications_collection = _test_db[
        "marketing_communications"
    ]
    app_module.admin_notifications_collection = _test_db["admin_notifications"]
    app_module.lead_score_history_collection = _test_db["lead_score_history"]


# ---------------------------------------------------------------------------
# 4. Autouse fixture — runs around every test in the pytest session.
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolated_test_database():
    """Start and finish every test with an empty, explicitly named test DB.

    - Refuses to drop any database not validated as a safe local test DB.
    - Skips database-dependent tests gracefully when local MongoDB is offline.
    - Verifies app_module.db.name matches the expected test database name.
    """
    db = getattr(app_module, "db", None)
    mongo_available = getattr(app_module, "MONGO_AVAILABLE", False)

    if not mongo_available:
        yield  # mock-only tests still run
        return

    # Hard guard: reject any non-test database.
    if db is not None and not is_safe_to_drop(db):
        raise RuntimeError(
            "[TEST SAFETY] Refusing to run tests: app_module.db is not the "
            f"isolated test database.  db.name={db.name!r}, "
            f"expected {TEST_DATABASE_NAME!r}."
        )

    if db is not None and db.name != TEST_DATABASE_NAME:
        raise RuntimeError(
            f"[TEST SAFETY] app_module.db.name={db.name!r} does not match "
            f"expected test database name {TEST_DATABASE_NAME!r}."
        )

    if db is not None:
        try:
            app_module.mongo_client.drop_database(TEST_DATABASE_NAME)
        except Exception as exc:
            pytest.skip(f"Could not reset test database: {exc}")

    try:
        yield
    finally:
        if db is not None:
            try:
                app_module.mongo_client.drop_database(TEST_DATABASE_NAME)
            except Exception:
                pass
