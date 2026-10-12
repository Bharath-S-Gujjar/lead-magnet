"""Production Scheduler Safety & Multi-Process Lease Tests (Task 7).

Verifies:
1. Scheduler disabled in web-worker mode (ENABLE_SCHEDULER=false).
2. Scheduler starts correctly in dedicated-scheduler mode (ENABLE_SCHEDULER=true or force=True).
3. Repeated initialization does not register duplicate jobs.
4. The same job cannot overlap with itself within a process.
5. Concurrent workers cannot both acquire the same active distributed lease.
6. Expired leases can be recovered after a simulated worker crash.
7. Lock release does not release another worker's lease.
8. Exceptions do not permanently disable subsequent scheduled executions.
9. Pipeline jobs halt safely if lease expires mid-run.
10. Manual admin trigger respects distributed locking and prevents overlapping runs.
"""

import os
import sys
import time
import unittest
import threading
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

# Ensure backend root is on sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

import app as app_module
from scheduler_service import (
    LeadMagnetScheduler,
    ScheduledJob,
    get_scheduler,
    acquire_job_lease,
    renew_job_lease,
    is_job_lease_valid,
    release_job_lease,
    ensure_scheduler_indexes,
    run_opportunity_pipeline_job,
    run_price_drop_pipeline_job,
)


class TestSchedulerProductionSafety(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = getattr(app_module, "db", None)
        if cls.db is not None:
            ensure_scheduler_indexes(cls.db)
            cls.locks_col = cls.db["scheduler_locks"]

    def setUp(self):
        if self.db is not None:
            self.locks_col.delete_many({})
        # Ensure fresh scheduler instance
        import scheduler_service
        scheduler_service._global_scheduler = None

    def tearDown(self):
        if self.db is not None:
            self.locks_col.delete_many({})
        import scheduler_service
        if scheduler_service._global_scheduler is not None:
            scheduler_service._global_scheduler.stop(timeout=1.0)
            scheduler_service._global_scheduler = None

    # 1. Scheduler disabled in web-worker mode
    def test_01_scheduler_disabled_in_web_worker_mode(self):
        """When ENABLE_SCHEDULER=false, scheduler refuses to start in web workers."""
        with patch.dict(os.environ, {"ENABLE_SCHEDULER": "false"}):
            scheduler = LeadMagnetScheduler(db=self.db)
            started = scheduler.start(db=self.db, force=False)
            self.assertFalse(started)
            self.assertFalse(scheduler.is_running())

    # 2. Scheduler starts correctly in dedicated-scheduler mode
    def test_02_scheduler_starts_correctly_in_dedicated_scheduler_mode(self):
        """Dedicated scheduler process starts cleanly and stops gracefully."""
        with patch.dict(os.environ, {"ENABLE_SCHEDULER": "true"}):
            scheduler = LeadMagnetScheduler(db=self.db)
            started = scheduler.start(db=self.db, force=True)
            self.assertTrue(started)
            self.assertTrue(scheduler.is_running())
            stopped = scheduler.stop(timeout=2.0)
            self.assertTrue(stopped)
            self.assertFalse(scheduler.is_running())

    # 3. Repeated initialization does not register duplicate jobs
    def test_03_repeated_initialization_does_not_register_duplicate_jobs(self):
        """Calling get_scheduler and register_job repeatedly updates in place without duplication."""
        scheduler = LeadMagnetScheduler(db=self.db)

        test_id = "safety_duplicate_test"
        dummy_fn = lambda db=None: {"status": "ok"}

        job1 = scheduler.register_job(test_id, "Job v1", 60, dummy_fn)
        self.assertEqual(len([j for j in scheduler.jobs if j == test_id]), 1)
        self.assertEqual(job1.interval_seconds, 60)

        job2 = scheduler.register_job(test_id, "Job v2", 120, dummy_fn)
        self.assertEqual(len([j for j in scheduler.jobs if j == test_id]), 1)
        self.assertEqual(job2.interval_seconds, 120)
        self.assertEqual(scheduler.jobs[test_id].name, "Job v2")

        scheduler.unregister_job(test_id)

    # 4. The same job cannot overlap with itself within a process
    def test_04_job_cannot_overlap_with_itself_within_process(self):
        """If a job is currently executing, a second invocation within process is safely skipped."""
        gate = threading.Event()
        started_event = threading.Event()

        def slow_job(db=None, **kwargs):
            started_event.set()
            gate.wait(timeout=3.0)
            return {"status": "slow_done"}

        job = ScheduledJob("slow_overlap_job", "Slow Job", 60, slow_job)

        bg_thread = threading.Thread(target=job.execute, kwargs={"db": self.db})
        bg_thread.start()

        started_event.wait(timeout=2.0)

        # Attempt overlapping execution
        res = job.execute(db=self.db)
        self.assertEqual(res["status"], "skipped")
        self.assertIn("Already running", res["reason"])

        # Unblock and join
        gate.set()
        bg_thread.join(timeout=5.0)
        self.assertFalse(job.is_running)

    # 5. Concurrent workers cannot both acquire the same active lease
    def test_05_concurrent_workers_cannot_both_acquire_active_lease(self):
        """If Worker A holds an active lease, Worker B cannot acquire it."""
        if self.db is None:
            self.skipTest("MongoDB not available")

        job_id = "test_lease_mutual_exclusion"
        worker_a = "worker_proc_A_1234"
        worker_b = "worker_proc_B_5678"

        acquired_a = acquire_job_lease(self.db, job_id, worker_a, lease_seconds=60)
        self.assertTrue(acquired_a)

        # Worker B attempts to acquire the same lease
        acquired_b = acquire_job_lease(self.db, job_id, worker_b, lease_seconds=60)
        self.assertFalse(acquired_b)

        # Confirm lease is valid for Worker A, not B
        self.assertTrue(is_job_lease_valid(self.db, job_id, worker_a))
        self.assertFalse(is_job_lease_valid(self.db, job_id, worker_b))

        release_job_lease(self.db, job_id, worker_a)

    # 6. Expired leases can be recovered after a simulated crash
    def test_06_expired_leases_recovered_after_simulated_crash(self):
        """When a worker crashes and lease expires, another worker recovers and claims the lease."""
        if self.db is None:
            self.skipTest("MongoDB not available")

        job_id = "test_lease_crash_recovery"
        worker_dead = "worker_crashed_9999"
        worker_alive = "worker_new_1111"

        acquire_job_lease(self.db, job_id, worker_dead, lease_seconds=60)

        # Simulate crash: backdate expiration to 10 seconds ago
        past_time = datetime.now(timezone.utc) - timedelta(seconds=10)
        self.locks_col.update_one({"_id": job_id}, {"$set": {"expires_at": past_time}})

        self.assertFalse(is_job_lease_valid(self.db, job_id, worker_dead))

        # Worker Alive claims expired lease
        claimed = acquire_job_lease(self.db, job_id, worker_alive, lease_seconds=60)
        self.assertTrue(claimed)
        self.assertTrue(is_job_lease_valid(self.db, job_id, worker_alive))

        release_job_lease(self.db, job_id, worker_alive)

    # 7. Lock release does not release another worker's lease
    def test_07_lock_release_does_not_release_another_workers_lease(self):
        """A stale release from an old worker does not delete or invalidate a new worker's lease."""
        if self.db is None:
            self.skipTest("MongoDB not available")

        job_id = "test_stale_release_protection"
        worker_old = "worker_stale_0001"
        worker_new = "worker_current_0002"

        # Worker Old acquires lease, which expires
        acquire_job_lease(self.db, job_id, worker_old, lease_seconds=60)
        past_time = datetime.now(timezone.utc) - timedelta(seconds=10)
        self.locks_col.update_one({"_id": job_id}, {"$set": {"expires_at": past_time}})

        # Worker New acquires lease
        acquire_job_lease(self.db, job_id, worker_new, lease_seconds=60)

        # Worker Old belatedly calls release
        released_old = release_job_lease(self.db, job_id, worker_old)
        self.assertFalse(released_old)

        # Worker New's lease must still be active and intact!
        self.assertTrue(is_job_lease_valid(self.db, job_id, worker_new))

        # Worker New releases cleanly
        released_new = release_job_lease(self.db, job_id, worker_new)
        self.assertTrue(released_new)

    # 8. Exceptions do not permanently disable subsequent scheduled executions
    def test_08_exceptions_do_not_permanently_disable_subsequent_executions(self):
        """When a job function throws an error, lock is released and future runs still execute."""
        should_fail = {"fail": True}

        def flaky_job(db=None, **kwargs):
            if should_fail["fail"]:
                raise RuntimeError("Transient pipeline database error")
            return {"status": "recovered_ok"}

        job = ScheduledJob("flaky_test_job", "Flaky Job", 60, flaky_job)

        # First run fails
        res1 = job.execute(db=self.db)
        self.assertEqual(res1["status"], "failed")
        self.assertIn("Transient pipeline", res1["error"])
        self.assertEqual(job.failure_count, 1)

        # Lock must be released
        if self.db is not None:
            lock_doc = self.locks_col.find_one({"_id": "flaky_test_job"})
            self.assertIsNone(lock_doc)

        # Subsequent run succeeds
        should_fail["fail"] = False
        res2 = job.execute(db=self.db)
        self.assertEqual(res2["status"], "recovered_ok")
        self.assertEqual(job.run_count, 1)

    # 9. Pipeline halts if lease expires mid-run
    def test_09_pipeline_halts_if_lease_lost_during_execution(self):
        """Pipeline job halts further customer processing if its lease is lost or expired mid-run."""
        if self.db is None:
            self.skipTest("MongoDB not available")

        # Fake lease for worker
        fake_owner = "worker_expired_mid_flight"
        # Since no lease is acquired in DB for fake_owner, is_job_lease_valid returns False
        res = run_opportunity_pipeline_job(db=self.db, owner_id=fake_owner, max_customers=10)
        self.assertEqual(res["status"], "completed")
        # Since lease was invalid immediately, 0 customers were evaluated
        self.assertEqual(len(res["summary"]), 0)

    # 10. Manual admin trigger respects distributed lock
    def test_10_manual_admin_trigger_respects_distributed_lock(self):
        """Manual admin trigger skips if another worker currently holds the distributed lease."""
        if self.db is None:
            self.skipTest("MongoDB not available")

        scheduler = LeadMagnetScheduler(db=self.db)
        test_job_id = "admin_safety_trigger_job"

        executed = {"count": 0}

        def dummy_job(db=None, **kwargs):
            executed["count"] += 1
            return {"status": "admin_ok"}

        scheduler.register_job(test_job_id, "Admin Test Job", 60, dummy_job)

        # Worker locks the job
        other_worker = "other_active_worker_7777"
        acquire_job_lease(self.db, test_job_id, other_worker, lease_seconds=60)

        # Admin attempts to trigger job
        res = scheduler.trigger_job(test_job_id, db=self.db)
        self.assertEqual(res["status"], "skipped")
        self.assertEqual(res["reason"], "Locked by another worker")
        self.assertEqual(executed["count"], 0)

        # Release lock and try again
        release_job_lease(self.db, test_job_id, other_worker)
        res_ok = scheduler.trigger_job(test_job_id, db=self.db)
        self.assertEqual(res_ok["status"], "admin_ok")
        self.assertEqual(executed["count"], 1)

        scheduler.unregister_job(test_job_id)

    # 11. Lease renewal extends expiration and updates heartbeat
    def test_11_lease_renewal_extends_expiration(self):
        """Active worker can atomically renew its lease and extend expiration."""
        if self.db is None:
            self.skipTest("MongoDB not available")

        job_id = "test_lease_renewal_job"
        worker_id = "worker_active_renew_1"

        acquire_job_lease(self.db, job_id, worker_id, lease_seconds=10)
        doc1 = self.locks_col.find_one({"_id": job_id})
        orig_expires = doc1["expires_at"]

        time.sleep(0.05)
        renewed = renew_job_lease(self.db, job_id, worker_id, extension_seconds=60)
        self.assertTrue(renewed)

        doc2 = self.locks_col.find_one({"_id": job_id})
        self.assertGreater(doc2["expires_at"], orig_expires)
        self.assertEqual(doc2["owner_id"], worker_id)

        release_job_lease(self.db, job_id, worker_id)

    # 12. Stale worker cannot renew stolen or expired lease
    def test_12_stale_worker_cannot_renew_stolen_or_expired_lease(self):
        """A worker whose lease expired and was claimed by another worker cannot renew or alter it."""
        if self.db is None:
            self.skipTest("MongoDB not available")

        job_id = "test_lease_stale_renew_job"
        worker_stale = "worker_stale_lost_lease"
        worker_new = "worker_new_current_owner"

        # Worker stale acquires, but lease expires
        acquire_job_lease(self.db, job_id, worker_stale, lease_seconds=10)
        past_time = datetime.now(timezone.utc) - timedelta(seconds=5)
        self.locks_col.update_one({"_id": job_id}, {"$set": {"expires_at": past_time}})

        # Worker new claims the lease
        acquire_job_lease(self.db, job_id, worker_new, lease_seconds=120)

        # Worker stale attempts to renew the lease
        stale_renewed = renew_job_lease(self.db, job_id, worker_stale, extension_seconds=300)
        self.assertFalse(stale_renewed)

        # Confirm worker new's lease is untouched
        doc = self.locks_col.find_one({"_id": job_id})
        self.assertEqual(doc["owner_id"], worker_new)

        release_job_lease(self.db, job_id, worker_new)

    # 13. Simulated lease expiration during running batch and ownership transfer
    def test_13_simulated_lease_expiration_mid_batch_stops_dispatch(self):
        """Simulate lease expiration during batch processing; stale worker immediately halts and cannot dispatch further messages."""
        if self.db is None:
            self.skipTest("MongoDB not available")

        from opportunity_engine import process_customer_opportunities
        from communication_provider import DryRunCommunicationProvider

        mock_provider = DryRunCommunicationProvider()

        # Seed test customer with hot lead state and cart item
        test_user_id = f"stale_batch_user_{int(time.time())}"
        self.db["user_profiles"].insert_one({
            "user_id": test_user_id,
            "email": f"{test_user_id}@example.com",
            "phone": "+919876543210",
            "whatsapp_opt_in": True,
            "whatsapp_opt_out": False,
        })
        self.db["customer_lead_state"].insert_one({
            "customer_id": test_user_id,
            "lead_probability": 0.85,
            "lead_state": "Hot",
        })
        prod_id = f"prod_stale_{int(time.time() * 1000)}"
        self.db["cart"].insert_one({
            "user_id": test_user_id,
            "items": [{"product_id": prod_id, "price": 1000}],
        })
        self.db["products"].insert_one({
            "product_id": prod_id,
            "name": "Test Shirt",
            "price": 800,
            "original_price": 1000,
            "category": "Clothing",
        })

        worker_stale = "worker_stale_mid_batch"
        worker_new = "worker_new_claimed_lease"
        job_id = "opportunity_pipeline"

        acquire_job_lease(self.db, job_id, worker_stale, lease_seconds=10)

        # Simulate lease expiration and transfer to Worker New before dispatch occurs
        past_time = datetime.now(timezone.utc) - timedelta(seconds=10)
        self.locks_col.update_one({"_id": job_id}, {"$set": {"expires_at": past_time}})
        acquire_job_lease(self.db, job_id, worker_new, lease_seconds=120)

        # When Worker Stale executes process_customer_opportunities with lease guard:
        lease_guard = lambda: renew_job_lease(self.db, job_id, worker_stale)
        res = process_customer_opportunities(
            customer_id=test_user_id,
            db=self.db,
            provider=mock_provider,
            lease_checker=lease_guard,
        )

        # Worker Stale was halted because lease was transferred
        self.assertEqual(len(res.get("communicated", [])), 0)
        skipped_reasons = [s.get("reason") for s in res.get("skipped", [])]
        self.assertTrue(any("lease" in str(r).lower() for r in skipped_reasons))
        sent_comms = list(self.db["marketing_communications"].find({"customer_id": test_user_id, "status": "sent"}))
        self.assertEqual(len(sent_comms), 0)

        # Cleanup
        release_job_lease(self.db, job_id, worker_new)
        self.db["user_profiles"].delete_one({"user_id": test_user_id})
        self.db["customer_lead_state"].delete_one({"customer_id": test_user_id})
        self.db["cart"].delete_one({"user_id": test_user_id})
        self.db["products"].delete_one({"product_id": prod_id})
        self.db["products"].delete_one({"product_id": "prod_stale_1"})

    # 14. Multiprocess concurrency test using independent OS processes
    def test_14_multiprocess_concurrent_workers_race(self):
        """Two independent OS processes race to acquire the same MongoDB lease; exactly one succeeds."""
        if self.db is None:
            self.skipTest("MongoDB not available")

        import subprocess

        job_id = "test_multiprocess_race_job"
        self.locks_col.delete_one({"_id": job_id})

        # The subprocess inherits TESTING=1, MONGO_URI, and MONGO_DB_NAME
        # from the parent's environment.  Never hard-code a URI or DB name.
        script = f'''import sys, os
sys.path.insert(0, r"{backend_dir}")

_uri = os.environ.get("MONGO_URI", "")
_db_name = os.environ.get("MONGO_DB_NAME", "")

# Safety check: refuse to connect to Atlas or a non-test DB.
if "mongodb+srv://" in _uri or ".mongodb.net" in _uri:
    print("RESULT:REFUSED_ATLAS"); sys.exit(1)
if not any(h in _uri.lower() for h in ("localhost", "127.", "::1")):
    print("RESULT:REFUSED_NONLOCAL"); sys.exit(1)
if "test" not in _db_name.lower():
    print("RESULT:REFUSED_PRODDB"); sys.exit(1)

from pymongo import MongoClient
from scheduler_service import acquire_job_lease

client = MongoClient(_uri, serverSelectionTimeoutMS=2000)
db = client[_db_name]
owner = f"proc_{{os.getpid()}}"
success = acquire_job_lease(db, "{job_id}", owner, lease_seconds=30)
print(f"RESULT:{{success}}")
'''
        # Explicitly pass the validated test environment to each subprocess.
        env = os.environ.copy()
        p1 = subprocess.Popen(
            [sys.executable, "-c", script],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, env=env,
        )
        p2 = subprocess.Popen(
            [sys.executable, "-c", script],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, env=env,
        )

        out1, err1 = p1.communicate(timeout=10)
        out2, err2 = p2.communicate(timeout=10)

        # Abort if either subprocess refused due to an unsafe configuration.
        for out in (out1, out2):
            for refused in ("RESULT:REFUSED_ATLAS", "RESULT:REFUSED_NONLOCAL", "RESULT:REFUSED_PRODDB"):
                if refused in out:
                    self.fail(
                        f"Subprocess refused unsafe DB config: {refused}\n"
                        f"MONGO_URI={os.environ.get('MONGO_URI')!r}"
                    )

        res1 = "RESULT:True" in out1
        res2 = "RESULT:True" in out2

        # Exactly one process acquired the lease
        self.assertTrue(res1 != res2, f"Expected exactly one process to win race, got p1={res1}, p2={res2}")

        self.locks_col.delete_one({"_id": job_id})


if __name__ == "__main__":
    unittest.main()
