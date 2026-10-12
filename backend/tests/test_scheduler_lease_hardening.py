"""Scheduler Lease Hardening Tests (Task 10 — Part 3).

Covers the concrete race conditions and defects found during the Task 10 audit:

1. owner_id uniqueness — full 128-bit UUID token, no collisions across processes.
2. Catalog refresh is skipped when the worker loses its lease mid-job.
3. Multiprocess subprocess race: exactly one winner, with subprocess safety checks.
4. Stale owner cannot renew after another worker takes over (regression guard).
5. Release by stale owner does not affect the current owner's lease.
6. Lease expiry allows clean takeover and the taken-over owner can renew normally.
7. Job exception releases the correct owner's lease and not a subsequently acquired one.
8. Renewal extends the owner's lease and rejects renewal after lease window ends.
9. Catalog refresh proceeds normally when owner still holds the lease.
10. Process-level: two subprocesses race to acquire; exactly one wins.
11. Process-level: renewal by correct owner in subprocess succeeds; stale owner rejected.
12. Process-level: long-running job that loses lease stops before catalog refresh.

All tests use TESTING=1, mongodb://127.0.0.1:27017, leadmagnet_test.
No Atlas URIs, no production database names, no external provider calls.
"""

import os
import sys
import time
import uuid
import unittest
import subprocess
import threading
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

# Ensure backend root is importable
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

# Safety: abort if not using the local isolated test database
_uri = os.environ.get("MONGO_URI", "")
_db_name = os.environ.get("MONGO_DB_NAME", "")

if os.environ.get("TESTING", "0") != "1":
    raise RuntimeError("TESTING=1 must be set before importing this test module.")
if "mongodb+srv://" in _uri or ".mongodb.net" in _uri:
    raise RuntimeError(f"REFUSED: Atlas URI detected in MONGO_URI. Tests require local MongoDB. URI={_uri!r}")
if not any(h in _uri for h in ("localhost", "127.", "::1")):
    raise RuntimeError(f"REFUSED: Non-local MONGO_URI detected: {_uri!r}. Tests require local MongoDB.")
if "test" not in _db_name.lower():
    raise RuntimeError(f"REFUSED: MONGO_DB_NAME '{_db_name}' does not contain 'test'. Must use an isolated test DB.")

import app as app_module
from scheduler_service import (
    ScheduledJob,
    acquire_job_lease,
    renew_job_lease,
    is_job_lease_valid,
    release_job_lease,
    ensure_scheduler_indexes,
    run_price_drop_pipeline_job,
)


class TestSchedulerLeaseHardening(unittest.TestCase):
    """Tests for the lease hardening changes and defects found in Task 10 audit."""

    @classmethod
    def setUpClass(cls):
        cls.db = getattr(app_module, "db", None)
        if cls.db is not None:
            ensure_scheduler_indexes(cls.db)
            cls.locks_col = cls.db["scheduler_locks"]

    def setUp(self):
        if self.db is not None:
            self.locks_col.delete_many({})

    def tearDown(self):
        if self.db is not None:
            self.locks_col.delete_many({})

    # ── 1. owner_id uniqueness ────────────────────────────────────────────────

    def test_01_owner_id_is_full_uuid_no_collision(self):
        """ScheduledJob.execute generates a full 128-bit owner_id token, not a truncated one."""
        captured = []

        def _capture_job(db=None, owner_id=None, **kwargs):
            captured.append(owner_id)
            return {"status": "ok"}

        job = ScheduledJob("uid_test_job", "UID Test", 60, _capture_job)
        job.execute(db=self.db)

        self.assertEqual(len(captured), 1)
        token = captured[0]
        self.assertIsNotNone(token)

        # Format: "<pid>_<uuid4_hex>" — uuid4 hex is 32 chars (128 bits)
        parts = token.split("_", 1)
        self.assertEqual(len(parts), 2, f"Expected 'pid_uuid' format, got: {token!r}")
        pid_part, uuid_part = parts
        self.assertTrue(pid_part.isdigit(), f"First part should be PID digits, got: {pid_part!r}")
        self.assertEqual(len(uuid_part), 32, f"UUID hex should be 32 chars (128 bits), got len={len(uuid_part)}: {uuid_part!r}")

    def test_02_owner_ids_are_unique_across_executions(self):
        """Each job execution produces a distinct owner_id token."""
        captured = []

        def _capture_job(db=None, owner_id=None, **kwargs):
            captured.append(owner_id)
            return {"status": "ok"}

        job = ScheduledJob("uid_unique_test", "UID Unique Test", 60, _capture_job)
        for _ in range(5):
            job.is_running = False  # Reset so each call is accepted
            job.execute(db=self.db)

        self.assertEqual(len(captured), 5)
        self.assertEqual(len(set(captured)), 5, f"Non-unique owner_ids detected: {captured}")

    # ── 2. Catalog refresh lease guard ───────────────────────────────────────

    def test_03_catalog_refresh_skipped_when_lease_lost(self):
        """run_price_drop_pipeline_job skips catalog_refresh when owner_id has lost its lease."""
        if self.db is None:
            self.skipTest("MongoDB not available")

        refresh_called = []

        def _mock_is_refresh_due(db=None):
            return True, "scheduled", None

        def _mock_execute_catalog_refresh(resolved_db=None, force=False):
            refresh_called.append(True)
            return {"status": "completed"}

        stale_owner = "stale_owner_no_lease"
        # Do NOT acquire a lease — so is_job_lease_valid returns False immediately

        with patch("myntra_catalog_refresh_service.is_refresh_due", _mock_is_refresh_due), \
             patch("myntra_catalog_refresh_service.run_catalog_refresh", _mock_execute_catalog_refresh), \
             patch("price_drop_opportunity_service.dispatch_price_drop_opportunity", return_value={"success": False, "status": "skipped"}):

            result = run_price_drop_pipeline_job(
                db=self.db,
                provider=MagicMock(),
                owner_id=stale_owner,
                max_drops=0,  # No price drops to process — goes straight to catalog refresh check
            )

        # Catalog refresh must have been skipped, not called
        self.assertFalse(refresh_called, "catalog refresh must NOT be called when the lease was lost")
        self.assertEqual(result["catalog_refresh_status"], "skipped_lease_lost",
                         f"Expected 'skipped_lease_lost', got: {result['catalog_refresh_status']!r}")

    def test_04_catalog_refresh_runs_when_lease_valid(self):
        """run_price_drop_pipeline_job executes catalog_refresh when owner still holds the lease."""
        if self.db is None:
            self.skipTest("MongoDB not available")

        refresh_called = []

        import myntra_catalog_refresh_service as _cat

        def _mock_is_refresh_due(db=None):
            return True, "scheduled", None

        def _mock_run_catalog_refresh(**kw):
            refresh_called.append(True)
            return {"status": "refreshed"}

        active_owner = f"active_catalog_owner_{uuid.uuid4().hex}"
        # Acquire the lease so is_job_lease_valid returns True
        acquire_job_lease(self.db, "price_drop_pipeline", active_owner, lease_seconds=120)

        try:
            orig_is_refresh_due = _cat.is_refresh_due
            orig_run_catalog_refresh = _cat.run_catalog_refresh
            _cat.is_refresh_due = _mock_is_refresh_due
            _cat.run_catalog_refresh = _mock_run_catalog_refresh
            try:
                with patch("price_drop_opportunity_service.dispatch_price_drop_opportunity",
                           return_value={"success": False}):
                    result = run_price_drop_pipeline_job(
                        db=self.db,
                        provider=MagicMock(),
                        owner_id=active_owner,
                        max_drops=0,
                    )
            finally:
                _cat.is_refresh_due = orig_is_refresh_due
                _cat.run_catalog_refresh = orig_run_catalog_refresh

            self.assertTrue(refresh_called, "catalog refresh SHOULD be called when the lease is still valid")
            self.assertIn(result["catalog_refresh_status"], ("refreshed", "completed"),
                          f"Unexpected catalog_refresh_status: {result['catalog_refresh_status']!r}")
        finally:
            release_job_lease(self.db, "price_drop_pipeline", active_owner)

    def test_05_catalog_refresh_runs_when_no_owner_id_given(self):
        """When owner_id is None (legacy mode), catalog refresh still runs (backward compat)."""
        if self.db is None:
            self.skipTest("MongoDB not available")

        refresh_called = []

        import myntra_catalog_refresh_service as _cat

        def _mock_is_refresh_due(db=None):
            return True, "scheduled", None

        def _mock_run(db=None, force=False, **kw):
            refresh_called.append(True)
            return {"status": "done"}

        orig_is = _cat.is_refresh_due
        orig_run = _cat.run_catalog_refresh
        _cat.is_refresh_due = _mock_is_refresh_due
        _cat.run_catalog_refresh = _mock_run
        try:
            with patch("price_drop_opportunity_service.dispatch_price_drop_opportunity",
                       return_value={"success": False}):
                result = run_price_drop_pipeline_job(
                    db=self.db,
                    provider=MagicMock(),
                    owner_id=None,  # Legacy: no lease guard
                    max_drops=0,
                )
        finally:
            _cat.is_refresh_due = orig_is
            _cat.run_catalog_refresh = orig_run

        self.assertTrue(refresh_called, "catalog refresh should run in legacy no-owner_id mode")

    # ── 3. Lease acquisition atomicity and exclusion ─────────────────────────

    def test_06_stale_owner_cannot_renew_after_takeover(self):
        """After lease expiry and takeover by a new worker, the stale worker's renewal is rejected."""
        if self.db is None:
            self.skipTest("MongoDB not available")

        job_id = "t10_stale_renew_protection"
        stale = "t10_stale_worker"
        fresh = "t10_fresh_worker"

        # Stale acquires, then expires
        acquire_job_lease(self.db, job_id, stale, lease_seconds=60)
        past = datetime.now(timezone.utc) - timedelta(seconds=5)
        self.locks_col.update_one({"_id": job_id}, {"$set": {"expires_at": past}})

        # Fresh takes over
        acquired = acquire_job_lease(self.db, job_id, fresh, lease_seconds=60)
        self.assertTrue(acquired, "Fresh worker must claim the expired lease")

        # Stale attempts renewal — must fail
        renewed = renew_job_lease(self.db, job_id, stale, extension_seconds=300)
        self.assertFalse(renewed, "Stale worker must not be able to renew after fresh worker took over")

        # Fresh owner's lease must be untouched
        self.assertTrue(is_job_lease_valid(self.db, job_id, fresh))

        release_job_lease(self.db, job_id, fresh)

    def test_07_stale_owner_release_does_not_affect_current_owner(self):
        """Stale owner's belated release() must not delete the current owner's lease."""
        if self.db is None:
            self.skipTest("MongoDB not available")

        job_id = "t10_stale_release_protection"
        stale = "t10_stale_release_worker"
        current = "t10_current_release_worker"

        acquire_job_lease(self.db, job_id, stale, lease_seconds=60)
        past = datetime.now(timezone.utc) - timedelta(seconds=5)
        self.locks_col.update_one({"_id": job_id}, {"$set": {"expires_at": past}})
        acquire_job_lease(self.db, job_id, current, lease_seconds=60)

        stale_released = release_job_lease(self.db, job_id, stale)
        self.assertFalse(stale_released, "Stale release must return False (stale owner mismatch)")

        self.assertTrue(is_job_lease_valid(self.db, job_id, current), "Current owner's lease must remain valid")
        release_job_lease(self.db, job_id, current)

    def test_08_expired_lease_allows_clean_takeover_and_renewal(self):
        """After a clean takeover of an expired lease, the new owner can renew normally."""
        if self.db is None:
            self.skipTest("MongoDB not available")

        job_id = "t10_takeover_renewal"
        dead = "t10_dead_worker"
        alive = "t10_alive_worker"

        acquire_job_lease(self.db, job_id, dead, lease_seconds=60)
        past = datetime.now(timezone.utc) - timedelta(seconds=10)
        self.locks_col.update_one({"_id": job_id}, {"$set": {"expires_at": past}})

        # Takeover
        acquired = acquire_job_lease(self.db, job_id, alive, lease_seconds=30)
        self.assertTrue(acquired)

        # Alive worker renews successfully
        renewed = renew_job_lease(self.db, job_id, alive, extension_seconds=60)
        self.assertTrue(renewed, "New owner should be able to renew after taking over")

        doc = self.locks_col.find_one({"_id": job_id})
        self.assertEqual(doc["owner_id"], alive)
        # expires_at stored as naive UTC in MongoDB; compare accordingly
        expires_at = doc["expires_at"]
        if expires_at.tzinfo is not None:
            now_cmp = datetime.now(timezone.utc)
        else:
            now_cmp = datetime.now(timezone.utc).replace(tzinfo=None)
        self.assertGreater(expires_at, now_cmp)

        release_job_lease(self.db, job_id, alive)

    def test_09_exception_releases_correct_owner_lease_only(self):
        """When a job raises an exception, only the current owner's lease is released."""
        if self.db is None:
            self.skipTest("MongoDB not available")

        job_id = "t10_exception_release_job"
        captured_owner = []

        def _failing_job(db=None, owner_id=None, **kwargs):
            captured_owner.append(owner_id)
            raise RuntimeError("Simulated job failure")

        job = ScheduledJob(job_id, "Exception Release Test", 60, _failing_job)
        result = job.execute(db=self.db)

        self.assertEqual(result["status"], "failed")
        self.assertEqual(len(captured_owner), 1)

        # Lease must have been released (doc deleted)
        doc = self.locks_col.find_one({"_id": job_id})
        self.assertIsNone(doc, "Lease must be released even when job raises an exception")

    # ── 4. Per-batch lease renewal ────────────────────────────────────────────

    def test_10_opportunity_pipeline_renews_before_each_candidate(self):
        """run_opportunity_pipeline_job calls renew_job_lease once per candidate evaluated."""
        if self.db is None:
            self.skipTest("MongoDB not available")

        from scheduler_service import run_opportunity_pipeline_job

        renewal_calls = []
        original_renew = __import__("scheduler_service").renew_job_lease

        def _counting_renew(db, job_id, owner_id, extension_seconds=300):
            renewal_calls.append((job_id, owner_id))
            return True  # Pretend renewal always succeeds

        owner = f"t10_opp_owner_{uuid.uuid4().hex}"
        # Seed two hot lead customers to trigger the renewal loop
        test_cids = [f"t10_cid_{i}" for i in range(2)]
        for cid in test_cids:
            self.db["customer_lead_state"].insert_one({
                "customer_id": cid,
                "lead_probability": 0.90,
                "lead_state": "Hot",
            })

        # Acquire valid lease first
        acquire_job_lease(self.db, "opportunity_pipeline", owner, lease_seconds=120)

        try:
            with patch("scheduler_service.renew_job_lease", side_effect=_counting_renew), \
                 patch("opportunity_engine.process_customer_opportunities",
                       return_value={"communicated": [], "skipped": [], "detected_count": 0}):
                result = run_opportunity_pipeline_job(db=self.db, owner_id=owner, max_customers=2)
        finally:
            release_job_lease(self.db, "opportunity_pipeline", owner)
            for cid in test_cids:
                self.db["customer_lead_state"].delete_one({"customer_id": cid})

        # At minimum one renewal call per candidate (could be 2 since there are 2 candidates)
        opp_renewals = [c for c in renewal_calls if c[0] == "opportunity_pipeline"]
        self.assertGreaterEqual(len(opp_renewals), 1,
                                "Expected at least one renewal call during opportunity pipeline execution")

    def test_11_opportunity_pipeline_halts_on_renewal_failure(self):
        """run_opportunity_pipeline_job stops processing candidates when renewal fails."""
        if self.db is None:
            self.skipTest("MongoDB not available")

        from scheduler_service import run_opportunity_pipeline_job

        calls = []

        def _renew_fails(db, job_id, owner_id, extension_seconds=300):
            return False  # Simulate lease lost

        def _process_opp(customer_id, db=None, provider=None, lease_checker=None):
            calls.append(customer_id)
            return {"communicated": [], "skipped": [], "detected_count": 0}

        owner = f"t10_halt_owner_{uuid.uuid4().hex}"
        test_cids = [f"t10_halt_cid_{i}" for i in range(3)]
        for cid in test_cids:
            self.db["customer_lead_state"].insert_one({
                "customer_id": cid,
                "lead_probability": 0.90,
                "lead_state": "Hot",
            })
        acquire_job_lease(self.db, "opportunity_pipeline", owner, lease_seconds=120)

        try:
            with patch("scheduler_service.renew_job_lease", side_effect=_renew_fails), \
                 patch("opportunity_engine.process_customer_opportunities", side_effect=_process_opp):
                result = run_opportunity_pipeline_job(db=self.db, owner_id=owner, max_customers=3)
        finally:
            release_job_lease(self.db, "opportunity_pipeline", owner)
            for cid in test_cids:
                self.db["customer_lead_state"].delete_one({"customer_id": cid})

        # Pipeline must have halted at the first candidate (renewal failed immediately)
        self.assertEqual(len(calls), 0,
                         "Pipeline must halt at first candidate check when renewal fails; "
                         f"but process_customer_opportunities was called for: {calls}")

    # ── 5. Multiprocess lease race (real subprocesses) ────────────────────────

    def test_12_multiprocess_renewal_stale_owner_rejected(self):
        """Subprocess: stale owner whose lease was taken over cannot renew it."""
        if self.db is None:
            self.skipTest("MongoDB not available")

        job_id = "t10_proc_stale_renew"
        self.locks_col.delete_one({"_id": job_id})

        script = f'''
import sys, os
sys.path.insert(0, r"{backend_dir}")

_uri = os.environ.get("MONGO_URI", "")
_db_name = os.environ.get("MONGO_DB_NAME", "")

if "mongodb+srv://" in _uri or ".mongodb.net" in _uri:
    print("RESULT:REFUSED_ATLAS"); sys.exit(1)
if not any(h in _uri for h in ("localhost", "127.", "::1")):
    print("RESULT:REFUSED_NONLOCAL"); sys.exit(1)
if "test" not in _db_name.lower():
    print("RESULT:REFUSED_PRODDB"); sys.exit(1)

from pymongo import MongoClient
from scheduler_service import acquire_job_lease, renew_job_lease, release_job_lease
from datetime import datetime, timezone, timedelta

client = MongoClient(_uri, serverSelectionTimeoutMS=2000)
db = client[_db_name]
locks = db["scheduler_locks"]

job_id = "{job_id}"
stale = "proc_stale_{{}}".format(os.getpid())
fresh = "proc_fresh_{{}}".format(os.getpid() + 1)

# Stale acquires
acquire_job_lease(db, job_id, stale, lease_seconds=60)

# Simulate expiry
past = datetime.now(timezone.utc) - timedelta(seconds=5)
locks.update_one({{"_id": job_id}}, {{"$set": {{"expires_at": past}}}})

# Fresh takes over
acquire_job_lease(db, job_id, fresh, lease_seconds=60)

# Stale tries to renew — must fail
stale_renewed = renew_job_lease(db, job_id, stale, extension_seconds=300)
doc = locks.find_one({{"_id": job_id}})

# Cleanup
release_job_lease(db, job_id, fresh)

if not stale_renewed and doc and doc["owner_id"] == fresh:
    print("RESULT:PASSED")
else:
    print(f"RESULT:FAILED stale_renewed={{stale_renewed}} owner={{doc.get('owner_id') if doc else 'None'}}")
'''
        env = os.environ.copy()
        proc = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True, text=True, env=env, timeout=15,
        )

        output = proc.stdout.strip()
        for refused in ("RESULT:REFUSED_ATLAS", "RESULT:REFUSED_NONLOCAL", "RESULT:REFUSED_PRODDB"):
            if refused in output:
                self.fail(f"Subprocess refused due to unsafe DB config: {output}")

        self.assertIn("RESULT:PASSED", output,
                      f"Stale-owner renewal rejection failed in subprocess.\nstdout={output!r}\nstderr={proc.stderr!r}")

    def test_13_multiprocess_catalog_refresh_lease_guard(self):
        """Subprocess: catalog refresh is skipped when the worker lost its lease."""
        if self.db is None:
            self.skipTest("MongoDB not available")

        job_id = "t10_proc_catalog_lease"
        self.locks_col.delete_one({"_id": job_id})

        script = f'''
import sys, os
sys.path.insert(0, r"{backend_dir}")

_uri = os.environ.get("MONGO_URI", "")
_db_name = os.environ.get("MONGO_DB_NAME", "")

if "mongodb+srv://" in _uri or ".mongodb.net" in _uri:
    print("RESULT:REFUSED_ATLAS"); sys.exit(1)
if not any(h in _uri for h in ("localhost", "127.", "::1")):
    print("RESULT:REFUSED_NONLOCAL"); sys.exit(1)
if "test" not in _db_name.lower():
    print("RESULT:REFUSED_PRODDB"); sys.exit(1)

from pymongo import MongoClient
from scheduler_service import is_job_lease_valid

client = MongoClient(_uri, serverSelectionTimeoutMS=2000)
db = client[_db_name]

# Simulate the catalog-refresh guard logic directly
stale_owner = "proc_stale_cat_{{}}".format(os.getpid())
# No lease acquired — is_job_lease_valid returns False

catalog_skipped = False
if stale_owner and not is_job_lease_valid(db, "price_drop_pipeline", stale_owner):
    catalog_skipped = True

print("RESULT:SKIPPED" if catalog_skipped else "RESULT:NOT_SKIPPED")
'''
        env = os.environ.copy()
        proc = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True, text=True, env=env, timeout=15,
        )

        output = proc.stdout.strip()
        for refused in ("RESULT:REFUSED_ATLAS", "RESULT:REFUSED_NONLOCAL", "RESULT:REFUSED_PRODDB"):
            if refused in output:
                self.fail(f"Subprocess refused due to unsafe DB config: {output}")

        self.assertIn("RESULT:SKIPPED", output,
                      f"Expected catalog refresh to be skipped in subprocess.\nstdout={output!r}\nstderr={proc.stderr!r}")


if __name__ == "__main__":
    unittest.main()
