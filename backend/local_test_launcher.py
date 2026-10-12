"""Lead Magnet Local Test Launcher & Staging Environment Helper (Task 21.5).

Provides a dedicated, strictly isolated local-only execution path for manual
and automated workflow testing. Resolves the ambiguity between the standard
runtime's Atlas configuration and the isolated local test environment.

Safety Guarantees & Invariants:
    1. NEVER connects to MongoDB Atlas or any remote database host.
    2. NEVER mutates, overwrites, or alters backend/.env or .env.example.
    3. Fails closed immediately if remote URIs, production database names,
       live communication providers, or real dispatch flags are detected.
    4. Guarantees:
       - TESTING=1 and LOCAL_ONLY_TESTING=1
       - MONGO_URI restricted to loopback (mongodb://127.0.0.1:27017)
       - MONGO_DB_NAME=leadmagnet_test
       - COMMUNICATION_PROVIDER=dry_run
       - ALLOW_REAL_DISPATCH=false
       - ENABLE_SCHEDULER=false
    5. Clean CLI interface for testing application journeys in safe dry-run mode.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any, Dict, Optional, Tuple

# Constants for strict local test isolation
LOCAL_MONGO_URI: str = "mongodb://127.0.0.1:27017"
LOCAL_DATABASE_NAME: str = "leadmagnet_test"
FORBIDDEN_URI_PATTERNS: Tuple[str, ...] = ("mongodb+srv://", ".mongodb.net", "atlas")
FORBIDDEN_DATABASE_NAMES: Tuple[str, ...] = ("leadmagnet", "production", "lead_magnet", "leadmagnetdb")
ALLOWED_LOOPBACK_HOSTS: Tuple[str, ...] = ("127.0.0.1", "localhost", "::1")


def configure_local_test_environment(extra_env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Publish guaranteed local-only environment variables in os.environ without altering .env on disk.

    Returns:
        Dict[str, str]: Copy of the published local environment settings.
    """
    local_env = {
        "TESTING": "1",
        "LOCAL_ONLY_TESTING": "1",
        "MONGO_URI": LOCAL_MONGO_URI,
        "MONGO_DB_NAME": LOCAL_DATABASE_NAME,
        "COMMUNICATION_PROVIDER": "dry_run",
        "ALLOW_REAL_DISPATCH": "false",
        "ENABLE_SCHEDULER": "false",
        "FLASK_ENV": "testing",
    }

    if extra_env:
        local_env.update(extra_env)

    # Validate before applying to prevent unsafe override
    assert_local_only_safety(local_env)

    # Apply to os.environ
    for k, v in local_env.items():
        os.environ[k] = v

    return dict(local_env)


def assert_local_only_safety(env: Optional[Dict[str, str]] = None) -> None:
    """Fail closed if any unsafe, remote, production, or live dispatch settings are present.

    Raises:
        RuntimeError: If any safety invariant is violated.
    """
    target = env if env is not None else os.environ

    # 1. Guard requirement
    testing_flag = target.get("TESTING", "").strip()
    local_flag = target.get("LOCAL_ONLY_TESTING", "").strip()
    if testing_flag != "1" and local_flag != "1":
        raise RuntimeError(
            "[LOCAL ISOLATION REJECTED] Local-only testing guard is missing. "
            "Must set TESTING=1 or LOCAL_ONLY_TESTING=1 to prevent loading production .env."
        )

    # 2. URI safety check
    uri = target.get("MONGO_URI", "").strip().lower()
    if not uri:
        raise RuntimeError("[LOCAL ISOLATION REJECTED] MONGO_URI must not be empty.")

    for pattern in FORBIDDEN_URI_PATTERNS:
        if pattern in uri:
            raise RuntimeError(
                f"[LOCAL ISOLATION REJECTED] Forbidden remote/Atlas pattern {pattern!r} "
                f"detected in MONGO_URI. Only local loopback connections are permitted."
            )

    if not any(lh in uri for lh in ALLOWED_LOOPBACK_HOSTS):
        raise RuntimeError(
            f"[LOCAL ISOLATION REJECTED] MONGO_URI does not target a loopback host "
            f"({ALLOWED_LOOPBACK_HOSTS}). Got: {uri!r}."
        )

    # 3. Database name safety check
    db_name = target.get("MONGO_DB_NAME", "").strip().lower()
    if not db_name:
        raise RuntimeError("[LOCAL ISOLATION REJECTED] MONGO_DB_NAME must not be empty.")

    if db_name in FORBIDDEN_DATABASE_NAMES:
        raise RuntimeError(
            f"[LOCAL ISOLATION REJECTED] Database name {db_name!r} is a forbidden production "
            f"name. Must use an isolated test database, e.g. 'leadmagnet_test'."
        )

    if "test" not in db_name:
        raise RuntimeError(
            f"[LOCAL ISOLATION REJECTED] Database name {db_name!r} does not contain 'test'. "
            "Local test launcher requires a database clearly named with 'test'."
        )

    # 4. Provider safety check
    prov = target.get("COMMUNICATION_PROVIDER", "").strip().lower()
    if prov and prov != "dry_run":
        raise RuntimeError(
            f"[LOCAL ISOLATION REJECTED] Live communication provider {prov!r} is forbidden "
            f"in local-only testing. Must be 'dry_run'."
        )

    # 5. Real dispatch switch check
    allow_real = target.get("ALLOW_REAL_DISPATCH", "").strip().lower()
    if allow_real in ("true", "1", "yes"):
        raise RuntimeError(
            "[LOCAL ISOLATION REJECTED] ALLOW_REAL_DISPATCH cannot be 'true' in local-only "
            "test launcher. Live dispatches are strictly disabled."
        )

    # 6. Scheduler switch check
    sched = target.get("ENABLE_SCHEDULER", "").strip().lower()
    if sched in ("true", "1", "yes"):
        raise RuntimeError(
            "[LOCAL ISOLATION REJECTED] ENABLE_SCHEDULER cannot be 'true' in local-only "
            "test launcher. Background scheduler must remain disabled."
        )


def verify_database_connection(uri: str = LOCAL_MONGO_URI, db_name: str = LOCAL_DATABASE_NAME) -> Tuple[Any, Any]:
    """Connect to the verified local MongoDB instance and confirm loopback isolation.

    Returns:
        Tuple[MongoClient, Database]: Connected client and database instances.
    """
    # Fail closed on exact arguments and safety switches BEFORE importing or creating client
    validation_env = {
        "TESTING": os.environ.get("TESTING", "1"),
        "LOCAL_ONLY_TESTING": os.environ.get("LOCAL_ONLY_TESTING", "1"),
        "MONGO_URI": uri,
        "MONGO_DB_NAME": db_name,
        "COMMUNICATION_PROVIDER": os.environ.get("COMMUNICATION_PROVIDER", "dry_run"),
        "ALLOW_REAL_DISPATCH": os.environ.get("ALLOW_REAL_DISPATCH", "false"),
        "ENABLE_SCHEDULER": os.environ.get("ENABLE_SCHEDULER", "false"),
    }
    assert_local_only_safety(validation_env)

    from pymongo import MongoClient

    client = MongoClient(uri, serverSelectionTimeoutMS=2000)
    client.admin.command("ping")

    # Confirm node addresses are strictly loopback
    nodes = getattr(client, "nodes", set())
    address = getattr(client, "address", None)
    hosts = [address[0]] if address else [n[0] for n in nodes]
    ports = [address[1]] if address else [n[1] for n in nodes]

    for h in hosts:
        if h not in ALLOWED_LOOPBACK_HOSTS:
            raise RuntimeError(f"[LOCAL ISOLATION REJECTED] Connected host {h!r} is not in loopback hosts.")
        if any(pat in h.lower() for pat in FORBIDDEN_URI_PATTERNS):
            raise RuntimeError(f"[LOCAL ISOLATION REJECTED] Remote host pattern detected in connected host: {h!r}.")

    for p in ports:
        if p != 27017:
            raise RuntimeError(f"[LOCAL ISOLATION REJECTED] Unexpected port {p} (expected 27017).")

    db = client[db_name]
    if db.name != db_name:
        raise RuntimeError(f"[LOCAL ISOLATION REJECTED] Connected to unexpected database {db.name!r} (expected {db_name!r}).")

    return client, db


def run_local_test_journey(customer_identifier: str, opportunity_identifier: Optional[str] = None) -> Tuple[bool, Dict[str, Any]]:
    """Execute run_application_whatsapp_journey within guaranteed local test isolation and dry-run provider.

    Args:
        customer_identifier: Email, user_id, or username of the test customer.
        opportunity_identifier: Optional specific opportunity key or ID.

    Returns:
        Tuple[bool, Dict[str, Any]]: Success status and result dictionary.
    """
    configure_local_test_environment()
    _, local_db = verify_database_connection()

    from communication_provider import DryRunCommunicationProvider
    from verify_real_delivery import run_application_whatsapp_journey

    provider = DryRunCommunicationProvider()
    return run_application_whatsapp_journey(
        customer_identifier=customer_identifier,
        opportunity_identifier=opportunity_identifier,
        confirm_real=True,  # Authorizes test harness execution; provider is dry-run
        provider=provider,
        db=local_db,
    )


def print_isolation_status() -> None:
    """Print the verified local-only configuration status without exposing secrets."""
    print("=" * 70)
    print("LEAD MAGNET: LOCAL TEST LAUNCHER ISOLATION STATUS")
    print("=" * 70)
    try:
        configure_local_test_environment()
        client, db = verify_database_connection()
        addr = client.address
        print(f"  Isolation Guard:          ACTIVE (TESTING=1, LOCAL_ONLY_TESTING=1)")
        print(f"  Target Database Host:     {addr[0]}:{addr[1]} (Loopback Verified)")
        print(f"  Target Database Name:     {db.name} (Isolated Test DB)")
        print(f"  Remote Atlas Status:      ZERO REMOTE NODES (Atlas Completely Disconnected)")
        print(f"  Communication Provider:   {os.environ.get('COMMUNICATION_PROVIDER')} (Dry-Run Enforced)")
        print(f"  Real Dispatch Switch:     {os.environ.get('ALLOW_REAL_DISPATCH')} (Blocked)")
        print(f"  Scheduler State:          {os.environ.get('ENABLE_SCHEDULER')} (Disabled)")
        print("-" * 70)
        print("VERDICT: LOCAL TEST ENVIRONMENT FULLY ISOLATED & SAFE")
        print("=" * 70)
    except Exception as e:
        print(f"ISOLATION CHECK FAILED: {e}")
        print("=" * 70)
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Lead Magnet Local Test Launcher (Task 21.5)")
    parser.add_argument("--check-isolation", action="store_true", help="Audit local test isolation guarantees")
    parser.add_argument("--test-journey", type=str, help="Customer ID/email to run dry-run marketing journey against local DB")
    parser.add_argument("--opportunity-id", type=str, help="Optional exact opportunity ID/key for journey test")
    parser.add_argument("--serve", action="store_true", help="Launch backend server in verified isolated test mode")
    parser.add_argument("--port", type=int, default=5000, help="Port to run server on (default: 5000)")
    args = parser.parse_args()

    if args.check_isolation:
        print_isolation_status()
    elif args.test_journey:
        configure_local_test_environment()
        print(f"Executing local dry-run journey for: {args.test_journey}")
        success, res = run_local_test_journey(args.test_journey, opportunity_identifier=args.opportunity_id)
        print(f"Journey Result: Success={success}, Details={res}")
    elif args.serve:
        configure_local_test_environment()
        client, db = verify_database_connection()
        print(f"[ISOLATED SERVER] Connected to verified local DB: {db.name} @ {client.address}")
        print(f"[ISOLATED SERVER] Starting server on port {args.port}...")
        from app import app, socketio, initialize_database
        initialize_database()
        socketio.run(app, debug=False, port=args.port, allow_unsafe_werkzeug=True)
    else:
        print_isolation_status()
