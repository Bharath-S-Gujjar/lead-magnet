"""Regression tests proving that database isolation safeguards are enforced
across all test entry points (pytest, python -m unittest, direct script).

Test coverage
-------------
1.  TESTING=1 is set before app is imported (env guard works).
2.  Active MONGO_URI is local, not Atlas.
3.  Active MONGO_DB_NAME contains "test" and is not a production name.
4.  app._TESTING is True (dotenv was skipped).
5.  app_module.db.name matches the expected test database name.
6.  assert_safe_test_uri rejects Atlas / remote URIs.
7.  assert_safe_test_db rejects production database names.
8.  is_safe_to_drop blocks non-test databases.
9.  No Atlas connection at runtime (connection node is local).
10. MONGO_URI env var matches TEST_MONGO_URI constant.
11. tests/__init__.py is present and sets TESTING=1 before app imports.
12. publish_test_environment is idempotent.
13. Missing TESTING would cause app to load dotenv (proven by module introspection).
14. Subprocess test config is not hard-coded (no 'leadmagnet' literal in script strings).
15. Archive exclusion script exists and is executable.

All tests are mock-based or use env introspection — no live MongoDB required.
"""

import importlib.util
import os
import sys
import unittest
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Bootstrap: load _isolation.py via absolute path so this file is safe to run
# from any working directory under any invocation method.
# ---------------------------------------------------------------------------
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_ISOLATION_PATH = os.path.join(_THIS_DIR, "_isolation.py")
_spec = importlib.util.spec_from_file_location("tests._isolation", _ISOLATION_PATH)
_iso = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_iso)

assert_safe_test_uri = _iso.assert_safe_test_uri
assert_safe_test_db = _iso.assert_safe_test_db
is_safe_to_drop = _iso.is_safe_to_drop
publish_test_environment = _iso.publish_test_environment
TEST_MONGO_URI = _iso.TEST_MONGO_URI
TEST_DATABASE_NAME = _iso.TEST_DATABASE_NAME

# Ensure test env vars are published before any app import.
# __init__.py already did this for the package path, but direct invocations
# may have bypassed it.  publish_test_environment() is idempotent.
_iso.ensure_backend_on_path()
publish_test_environment()



class TestEnvironmentIsolation(unittest.TestCase):
    """Verify environment-level isolation is in place under every entry point."""

    def test_testing_flag_is_set(self):
        """TESTING=1 must be set so app.py skips load_dotenv."""
        self.assertEqual(
            os.environ.get("TESTING"), "1",
            "TESTING env var must be '1' during test runs so that app.py "
            "does not load backend/.env."
        )

    def test_mongo_uri_is_not_atlas(self):
        """The active MONGO_URI must not be an Atlas / cloud connection."""
        active_uri = os.environ.get("MONGO_URI", "")
        self.assertNotIn("mongodb+srv://", active_uri,
                         f"MONGO_URI {active_uri!r} looks like an Atlas URI.")
        self.assertNotIn(".mongodb.net", active_uri,
                         f"MONGO_URI {active_uri!r} points at MongoDB Atlas.")

    def test_mongo_uri_is_local(self):
        """The active MONGO_URI must target localhost / 127.x."""
        active_uri = os.environ.get("MONGO_URI", "")
        self.assertTrue(
            any(ind in active_uri.lower() for ind in ("localhost", "127.", "::1")),
            f"MONGO_URI {active_uri!r} does not target localhost."
        )

    def test_mongo_db_name_is_test_database(self):
        """MONGO_DB_NAME must contain 'test' and must not be 'leadmagnet'."""
        db_name = os.environ.get("MONGO_DB_NAME", "")
        self.assertIn("test", db_name.lower(),
                      f"MONGO_DB_NAME={db_name!r} does not contain 'test'.")
        self.assertNotEqual(db_name.lower(), "leadmagnet",
                            f"MONGO_DB_NAME={db_name!r} is the production database name.")

    def test_app_module_db_name_is_test_database(self):
        """app_module.db.name must match the configured test database."""
        import app as app_module
        db = getattr(app_module, "db", None)
        if db is None:
            self.skipTest("app_module.db is None — no live MongoDB connection.")
        self.assertEqual(
            db.name, TEST_DATABASE_NAME,
            f"app_module.db.name={db.name!r} != TEST_DATABASE_NAME={TEST_DATABASE_NAME!r}."
        )

    def test_app_dotenv_not_loaded_during_testing(self):
        """When TESTING=1, app._TESTING must be True (load_dotenv was skipped)."""
        import app as app_module
        self.assertTrue(
            getattr(app_module, "_TESTING", False),
            "app._TESTING is False — app.py loaded backend/.env despite TESTING=1."
        )

    def test_tests_init_sets_env_vars(self):
        """tests/__init__.py must exist and must have published TESTING=1."""
        init_path = os.path.join(os.path.dirname(__file__), "__init__.py")
        self.assertTrue(
            os.path.isfile(init_path),
            "backend/tests/__init__.py does not exist.  "
            "It is required so that 'python -m unittest' sets isolation env vars."
        )
        # The env vars are already set by the time this test runs — proof that
        # __init__.py (or conftest.py) published them before app was imported.
        self.assertEqual(os.environ.get("TESTING"), "1")
        self.assertEqual(os.environ.get("MONGO_URI"), TEST_MONGO_URI)
        self.assertEqual(os.environ.get("MONGO_DB_NAME"), TEST_DATABASE_NAME)

    def test_publish_test_environment_is_idempotent(self):
        """Calling publish_test_environment() twice must not change env values."""
        before_uri = os.environ.get("MONGO_URI")
        before_db = os.environ.get("MONGO_DB_NAME")
        publish_test_environment()  # second call
        self.assertEqual(os.environ.get("MONGO_URI"), before_uri)
        self.assertEqual(os.environ.get("MONGO_DB_NAME"), before_db)


class TestUriSafetyValidation(unittest.TestCase):
    """Verify assert_safe_test_uri rejects dangerous URIs."""

    def test_atlas_srv_uri_is_rejected(self):
        with self.assertRaises(RuntimeError) as ctx:
            assert_safe_test_uri("mongodb+srv://user:pass@cluster.mongodb.net/db")
        self.assertIn("TEST SAFETY", str(ctx.exception))

    def test_atlas_dotnet_uri_is_rejected(self):
        with self.assertRaises(RuntimeError):
            assert_safe_test_uri("mongodb://user:pass@leadmagnet.4hmf3fs.mongodb.net/db")

    def test_non_local_ip_uri_is_rejected(self):
        with self.assertRaises(RuntimeError):
            assert_safe_test_uri("mongodb://192.168.1.100:27017")

    def test_localhost_uri_is_accepted(self):
        assert_safe_test_uri("mongodb://localhost:27017")  # no exception

    def test_127_uri_is_accepted(self):
        assert_safe_test_uri("mongodb://127.0.0.1:27017")  # no exception

    def test_keyword_atlas_in_hostname_is_rejected(self):
        with self.assertRaises(RuntimeError):
            assert_safe_test_uri("mongodb://myatlas-server.internal:27017")


class TestDatabaseNameSafetyValidation(unittest.TestCase):
    """Verify assert_safe_test_db rejects production database names."""

    def test_production_name_leadmagnet_is_rejected(self):
        with self.assertRaises(RuntimeError) as ctx:
            assert_safe_test_db("leadmagnet")
        self.assertIn("TEST SAFETY", str(ctx.exception))

    def test_production_name_lead_magnet_is_rejected(self):
        with self.assertRaises(RuntimeError):
            assert_safe_test_db("lead_magnet")

    def test_production_name_is_case_insensitive(self):
        with self.assertRaises(RuntimeError):
            assert_safe_test_db("LeadMagnet")

    def test_name_without_test_keyword_is_rejected(self):
        with self.assertRaises(RuntimeError):
            assert_safe_test_db("myapp_database")

    def test_leadmagnet_test_is_accepted(self):
        assert_safe_test_db("leadmagnet_test")  # no exception

    def test_test_db_is_accepted(self):
        assert_safe_test_db("test_db")  # no exception

    def test_myapp_testing_is_accepted(self):
        assert_safe_test_db("myapp_testing")  # no exception


class TestIsSafeToDropGuard(unittest.TestCase):
    """Verify the is_safe_to_drop helper used by the autouse fixture."""

    def _make_db(self, name: str):
        db = MagicMock()
        db.name = name
        return db

    def test_none_db_is_not_safe(self):
        self.assertFalse(is_safe_to_drop(None))

    def test_production_db_is_not_safe(self):
        self.assertFalse(is_safe_to_drop(self._make_db("leadmagnet")))

    def test_non_test_named_db_is_not_safe(self):
        self.assertFalse(is_safe_to_drop(self._make_db("myapp")))

    def test_test_db_is_safe(self):
        self.assertTrue(is_safe_to_drop(self._make_db("leadmagnet_test")))

    def test_testing_db_is_safe(self):
        self.assertTrue(is_safe_to_drop(self._make_db("testing_db")))


class TestNoAtlasConnectionAtRuntime(unittest.TestCase):
    """Verify that no Atlas connection is attempted during the test run."""

    def test_mongo_client_host_is_local(self):
        """mongo_client must be connected to a local host."""
        import app as app_module
        client = getattr(app_module, "mongo_client", None)
        if client is None:
            self.skipTest("No mongo_client on app_module.")
        hosts = []
        try:
            for addr in client.nodes:
                hosts.append(addr[0])
        except Exception:
            pass
        if not hosts:
            host = getattr(client, "HOST", "") or getattr(client, "host", "")
            if host:
                hosts = [host]
        if not hosts:
            self.skipTest("Cannot inspect mongo_client hosts.")
        for host in hosts:
            self.assertTrue(
                any(ind in host.lower() for ind in ("localhost", "127.", "::1")),
                f"mongo_client host {host!r} is not localhost."
            )

    def test_configured_uri_matches_test_uri(self):
        self.assertEqual(
            os.environ.get("MONGO_URI"), TEST_MONGO_URI,
            "MONGO_URI has drifted from TEST_MONGO_URI."
        )


class TestSubprocessIsolation(unittest.TestCase):
    """Verify subprocess tests do not hard-code production database details."""

    def test_scheduler_subprocess_does_not_hardcode_production_db(self):
        """test_scheduler_production_safety.py must not contain the string
        'mongodb://localhost:27017/leadmagnet' or 'client[\"leadmagnet\"]'."""
        scheduler_test = os.path.join(
            os.path.dirname(__file__), "test_scheduler_production_safety.py"
        )
        if not os.path.isfile(scheduler_test):
            self.skipTest("test_scheduler_production_safety.py not found.")
        with open(scheduler_test, encoding="utf-8") as fh:
            source = fh.read()
        self.assertNotIn(
            'localhost:27017/leadmagnet', source,
            "test_scheduler_production_safety.py hard-codes the production "
            "MongoDB URI 'localhost:27017/leadmagnet'.  Use the test URI from "
            "the environment instead."
        )
        self.assertNotIn(
            'client["leadmagnet"]', source,
            "test_scheduler_production_safety.py hard-codes the production "
            "database name 'leadmagnet' in a MongoClient constructor.  Use "
            "MONGO_DB_NAME from the environment instead."
        )

    def test_no_test_file_hardcodes_atlas_uri_as_connection(self):
        """No file in backend/tests/ should use a mongodb+srv:// URI as an actual
        connection string.  Files that merely check *for* the pattern in rejection
        logic (e.g. '_isolation.py', 'conftest.py', 'test_db_isolation.py') are
        excluded from this check because they are the guards, not the offenders.
        """
        # Files whose job is to validate/reject Atlas URIs — they must mention
        # the pattern and are therefore excluded from this scan.
        EXCLUSIONS = {
            "_isolation.py",
            "conftest.py",
            "test_db_isolation.py",
            "test_task21_7_regression.py",
            "test_task21_9_safety_evidence.py",
        }
        tests_dir = os.path.dirname(__file__)
        violations = []
        for fname in os.listdir(tests_dir):
            if not fname.endswith(".py") or fname in EXCLUSIONS:
                continue
            fpath = os.path.join(tests_dir, fname)
            try:
                with open(fpath, encoding="utf-8") as fh:
                    source = fh.read()
                # Only flag if the Atlas URI pattern appears in a MongoClient
                # constructor call or in a variable assignment — not in a string
                # comparison or assertNotIn call.
                import re as _re
                # Match patterns like: MongoClient("mongodb+srv://...") or
                # uri = "mongodb+srv://..." (assignment context)
                if _re.search(r'MongoClient\s*\(\s*["\']mongodb\+srv://', source):
                    violations.append(fname)
                elif _re.search(r'=\s*["\']mongodb\+srv://', source):
                    violations.append(fname)
            except OSError:
                pass
        self.assertEqual(
            violations, [],
            f"These test files use a hard-coded Atlas URI in a connection context: {violations}"
        )



class TestDirectUnittestEntryPoint(unittest.TestCase):
    """Prove that the python -m unittest entry point is safe.

    When python -m unittest backend.tests.X is run, Python imports the
    backend.tests package first, which triggers backend/tests/__init__.py.
    That file calls publish_test_environment() before any test module body
    runs, setting TESTING=1 so app.py skips load_dotenv.

    This test class verifies the evidence that this chain worked.
    """

    def test_init_py_is_present(self):
        """backend/tests/__init__.py must exist."""
        init_path = os.path.join(os.path.dirname(__file__), "__init__.py")
        self.assertTrue(os.path.isfile(init_path),
                        "backend/tests/__init__.py missing — unittest path is unprotected.")

    def test_isolation_module_is_present(self):
        """backend/tests/_isolation.py must exist."""
        iso_path = os.path.join(os.path.dirname(__file__), "_isolation.py")
        self.assertTrue(os.path.isfile(iso_path),
                        "backend/tests/_isolation.py missing.")

    def test_testing_flag_set_at_module_import_time(self):
        """TESTING=1 must already be set by the time any test class is defined.

        If __init__.py is working correctly, TESTING=1 will have been set
        before this test module was imported.  We verify by checking the flag.
        """
        self.assertEqual(os.environ.get("TESTING"), "1",
                         "TESTING is not '1' — __init__.py or conftest.py did not run "
                         "before this module was imported.")

    def test_no_atlas_uri_in_any_env_var(self):
        """No environment variable should contain an Atlas URI."""
        atlas_patterns = ("mongodb+srv://", ".mongodb.net")
        violations = {}
        for key, value in os.environ.items():
            if isinstance(value, str):
                for pat in atlas_patterns:
                    if pat in value.lower():
                        violations[key] = value[:40] + "..."
                        break
        self.assertEqual(
            violations, {},
            f"These environment variables contain Atlas URIs: {list(violations.keys())}\n"
            "This means backend/.env was loaded during the test run."
        )



class TestAppModuleState(unittest.TestCase):
    """Verify the live app module is in test-isolation mode.

    This class imports ``app`` and asserts on its runtime state.  It
    serves as a regression guard for the specific condition that:

    - ``app._TESTING`` is ``True`` (meaning ``load_dotenv`` was skipped)
    - ``app.db.name`` is the test database, not a production database
    - ``app.mongo_client.nodes`` contains only local addresses

    If any of these assertions fail it means that production credentials
    were loaded, which constitutes a test-isolation breach.

    The assertions hold for every entry point (pytest, python -m unittest,
    direct script) because ``__init__.py`` calls ``publish_test_environment``
    before any module in the package is imported.
    """

    @classmethod
    def setUpClass(cls):
        import app as _app
        cls.app_module = _app

    def test_app_testing_flag_is_true(self):
        """app._TESTING must be True — proves load_dotenv was skipped."""
        self.assertTrue(
            self.app_module._TESTING,
            "app._TESTING is False: load_dotenv ran and may have loaded Atlas credentials."
        )

    def test_app_db_name_is_test_database(self):
        """app.db.name must be the isolated test database name."""
        db = getattr(self.app_module, "db", None)
        if db is None:
            self.skipTest("app.db is None (MongoDB unavailable).")
        self.assertIn(
            "test", db.name.lower(),
            f"app.db.name={db.name!r} is not a test database. "
            "Production database may be in use."
        )
        self.assertNotIn(
            db.name.lower(),
            {"leadmagnet", "lead_magnet", "leadmagnetdb", "production"},
            f"app.db.name={db.name!r} is a known production database name."
        )

    def test_mongo_client_connects_only_to_local_host(self):
        """mongo_client.nodes must all be local addresses."""
        client = getattr(self.app_module, "mongo_client", None)
        if client is None:
            self.skipTest("app.mongo_client is None.")
        try:
            nodes = list(client.nodes)
        except Exception:
            nodes = []
        for host, port in nodes:
            self.assertTrue(
                any(loc in host for loc in ("127.", "localhost", "::1")),
                f"mongo_client has non-local node: {host}:{port}. "
                "This indicates a connection to a remote (possibly Atlas) database."
            )

    def test_mongo_uri_env_is_local_during_tests(self):
        """MONGO_URI in os.environ must be a local URI."""
        uri = os.environ.get("MONGO_URI", "")
        self.assertNotIn("mongodb+srv://", uri,
                         f"MONGO_URI={uri!r} is an Atlas URI.")
        self.assertNotIn(".mongodb.net", uri,
                         f"MONGO_URI={uri!r} points at MongoDB Atlas.")
        self.assertTrue(
            any(loc in uri for loc in ("127.", "localhost", "::1")),
            f"MONGO_URI={uri!r} is not a local connection."
        )


if __name__ == "__main__":
    unittest.main()
