"""Safe test-runner entry point for the backend test suite.

Usage
-----
Run ALL tests (isolation safeguards applied automatically)::

    python run_tests.py

Run a specific test module::

    python run_tests.py backend/tests/test_cart_wishlist_persistence.py

Run only the isolation-verification tests first::

    python run_tests.py backend/tests/test_db_isolation.py

Why this file exists
--------------------
``python -m unittest`` and ``python -m pytest`` launched directly do **not**
guarantee that ``backend/tests/conftest.py`` is executed before the first test
module is imported.  This script sets the required environment variables
*before* importing any test code so that the ``TESTING=1`` guard in ``app.py``
suppresses ``.env`` loading in every invocation path.

Constraints
-----------
* Never commits, pushes, or deploys.
* Never connects to the Atlas database.
* Delegates all test execution to pytest.
"""

import os
import sys

# ---------------------------------------------------------------------------
# 1. Set environment variables BEFORE any test module or ``app`` is imported.
# ---------------------------------------------------------------------------
TEST_MONGO_URI = os.environ.get("TEST_MONGO_URI", "mongodb://127.0.0.1:27017")
TEST_DATABASE_NAME = os.environ.get("TEST_MONGO_DB_NAME", "leadmagnet_test")

os.environ["TESTING"] = "1"
os.environ["MONGO_URI"] = TEST_MONGO_URI
os.environ["MONGO_DB_NAME"] = TEST_DATABASE_NAME
os.environ.setdefault("JWT_SECRET", "test-only-insecure-jwt-secret")
os.environ.setdefault("ADMIN_USERNAME", "test_admin")
os.environ.setdefault("ADMIN_PASSWORD", "test_admin_password")
os.environ.setdefault("COMMUNICATION_PROVIDER", "dry_run")
os.environ.setdefault("ENABLE_SCHEDULER", "false")
os.environ.setdefault("FLASK_ENV", "testing")

# ---------------------------------------------------------------------------
# 2. Validate the target database is safe before running anything.
# ---------------------------------------------------------------------------
_FORBIDDEN_URI_PATTERNS = ("mongodb+srv://", "atlas", ".mongodb.net")
_local_indicators = ("localhost", "127.", "::1")

for _pat in _FORBIDDEN_URI_PATTERNS:
    if _pat in TEST_MONGO_URI.lower():
        print(
            f"[FATAL] TEST_MONGO_URI looks like a remote/Atlas connection: "
            f"{TEST_MONGO_URI!r}\n"
            "Set TEST_MONGO_URI to a local MongoDB address before running tests.",
            file=sys.stderr,
        )
        sys.exit(1)

if not any(ind in TEST_MONGO_URI.lower() for ind in _local_indicators):
    print(
        f"[FATAL] TEST_MONGO_URI does not appear to be a local connection: "
        f"{TEST_MONGO_URI!r}",
        file=sys.stderr,
    )
    sys.exit(1)

if "test" not in TEST_DATABASE_NAME.lower():
    print(
        f"[FATAL] TEST_MONGO_DB_NAME {TEST_DATABASE_NAME!r} does not contain "
        "'test'.  Use a name like 'leadmagnet_test'.",
        file=sys.stderr,
    )
    sys.exit(1)

# ---------------------------------------------------------------------------
# 3. Delegate to pytest.
# ---------------------------------------------------------------------------
import pytest  # noqa: E402

# Default to the tests directory; allow callers to pass specific paths/flags.
extra_args = sys.argv[1:] if len(sys.argv) > 1 else ["backend/tests"]
sys.exit(pytest.main(["-ra", "--tb=short"] + extra_args))
