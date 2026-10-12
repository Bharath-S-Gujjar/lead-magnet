"""Backend test package initializer.

This file is executed by Python whenever the ``backend.tests`` package is
imported — which happens at the very start of **every** ``python -m unittest``
invocation that targets a module under ``backend/tests/``.

It publishes the test-isolation environment variables *before* any test module
body runs, ensuring that the ``TESTING=1`` guard in ``app.py`` suppresses
``load_dotenv`` regardless of whether the caller is pytest, ``python -m
unittest``, or a direct ``python backend/tests/test_X.py`` invocation.

Design rules:
- Must NOT import ``app`` or any service module — only stdlib and _isolation.
- Must be safe to import multiple times (idempotent).
- Uses importlib with an explicit absolute path so the import works regardless
  of what is on sys.path at the moment this file first executes.
- Fails immediately with ``RuntimeError`` if a remote URI or production
  database name is configured, preventing any test from reaching app code.
"""

import importlib.util
import os
import sys

# ---------------------------------------------------------------------------
# Step 1: Locate _isolation.py by absolute path — independent of sys.path.
# ---------------------------------------------------------------------------
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_ISOLATION_PATH = os.path.join(_THIS_DIR, "_isolation.py")

if not os.path.isfile(_ISOLATION_PATH):
    raise RuntimeError(
        f"[TEST SAFETY] backend/tests/_isolation.py not found at {_ISOLATION_PATH!r}.\n"
        "The test-isolation module is required. Do not delete it."
    )

# Load _isolation via importlib so it works even before sys.path is configured.
_spec = importlib.util.spec_from_file_location("tests._isolation", _ISOLATION_PATH)
_isolation = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_isolation)

# ---------------------------------------------------------------------------
# Step 2: Ensure backend root is on sys.path, then publish env vars.
# ---------------------------------------------------------------------------
_isolation.ensure_backend_on_path()
_isolation.publish_test_environment()
