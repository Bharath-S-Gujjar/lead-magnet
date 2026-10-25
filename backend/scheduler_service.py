"""Lead Magnet Background Scheduler Service.

Coordinates periodic background execution of marketing opportunity scans,
price-drop opportunity dispatches, and catalog synchronization.

Design & Operational Invariants:
    - Thread-safe singleton architecture to prevent multiple active schedulers.
    - Idempotent job registration to eliminate duplicate job executions.
    - Respects Flask reloader guards (WERKZEUG_RUN_MAIN) to avoid double-spawning.
    - Runs in daemon threads; never blocks API startup or request serving.
    - Respects all customer consent (whatsapp_opt_in, whatsapp_opt_out).
    - Strictly observes cooldown periods and idempotency constraints.
    - Sanitizes all log messages to prevent credential, token, or PII leakage.
    - Captures per-job failures safely with detailed non-sensitive diagnostics.
"""

import os
import re
import sys
import time
import uuid
import inspect
import logging
import threading
from datetime import datetime, timezone, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

try:
    from pymongo import ReturnDocument
    from pymongo.errors import DuplicateKeyError
except ImportError:
    ReturnDocument = None
    DuplicateKeyError = Exception

from scoring_constants import HOT, WARM, HOT_PROBABILITY_EQUIV

logger = logging.getLogger("lead_magnet.scheduler")
if not logger.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(logging.Formatter("[%(asctime)s] [SCHEDULER] %(levelname)s: %(message)s"))
    logger.addHandler(_handler)
logger.setLevel(logging.INFO)


def _sanitize_log(msg: str) -> str:
    """Sanitize log text by stripping credentials, tokens, and PII."""
    if not isinstance(msg, str):
        msg = str(msg)
    # Redact Bearer / API tokens
    msg = re.sub(r"(Bearer\s+)[A-Za-z0-9_\-\.]{10,}", r"\1[REDACTED_TOKEN]", msg, flags=re.IGNORECASE)
    # Redact secret key values in key=value or "key": "value" patterns
    msg = re.sub(r"(secret|password|token|key|pwd)\s*[:=]\s*['\"][^'\"]+['\"]", r"\1=[REDACTED]", msg, flags=re.IGNORECASE)
    # Redact email addresses to user_***@domain
    msg = re.sub(r"([a-zA-Z0-9_.+-]+)@([a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)", r"***@\2", msg)
    # Redact full phone numbers (leave only last 4 digits)
    msg = re.sub(r"\+?\d{8,14}(\d{4})", r"***-\1", msg)
    return msg


def ensure_scheduler_indexes(db: Any) -> None:
    """Ensure indexes on scheduler_locks collection for atomic lease handling."""
    if db is None:
        return
    try:
        col = db["scheduler_locks"]
        existing = {idx.get("name") for idx in col.list_indexes()}
        if "expires_at_1" not in existing:
            col.create_index([("expires_at", 1)], name="expires_at_1", background=True)
    except Exception as e:
        logger.debug("Scheduler index notice (may exist): %s", e)


def acquire_job_lease(
    db: Any,
    job_id: str,
    owner_id: str,
    lease_seconds: int = 300,
) -> bool:
    """Atomically acquire or re-acquire a distributed job lease in MongoDB.

    Guarantees:
        - If no lease exists: atomically creates a lease document for (job_id, owner_id).
        - If an active lease exists for another worker: returns False without blocking.
        - If an active lease is owned by the same worker: renews expiration and returns True.
        - If an expired lease exists (e.g. previous crash): claims lease atomically and returns True.
    """
    if db is None:
        return True

    now = datetime.now(timezone.utc)
    expires = now + timedelta(seconds=max(5, int(lease_seconds)))

    try:
        col = db["scheduler_locks"]

        # 1. Update if expired or owned by the same worker
        res = col.find_one_and_update(
            {
                "_id": job_id,
                "$or": [
                    {"expires_at": {"$lte": now}},
                    {"owner_id": owner_id},
                ],
            },
            {
                "$set": {
                    "owner_id": owner_id,
                    "acquired_at": now,
                    "expires_at": expires,
                    "last_heartbeat": now,
                }
            },
            return_document=ReturnDocument.AFTER if ReturnDocument else None,
        )
        if res is not None:
            return True

        # 2. Insert if no document exists yet
        try:
            col.insert_one({
                "_id": job_id,
                "job_id": job_id,
                "owner_id": owner_id,
                "acquired_at": now,
                "expires_at": expires,
                "last_heartbeat": now,
            })
            return True
        except DuplicateKeyError:
            return False
    except Exception as exc:
        logger.warning(_sanitize_log(f"Error acquiring distributed lease for '{job_id}': {exc}"))
        return False


def is_job_lease_valid(db: Any, job_id: str, owner_id: str) -> bool:
    """Check whether the worker's lease is currently active and unexpired."""
    if db is None or not owner_id:
        return True

    try:
        col = db["scheduler_locks"]
        now = datetime.now(timezone.utc)
        doc = col.find_one({"_id": job_id, "owner_id": owner_id, "expires_at": {"$gt": now}})
        return doc is not None
    except Exception as exc:
        logger.warning(_sanitize_log(f"Error checking lease validity for '{job_id}': {exc}"))
        return False


def renew_job_lease(
    db: Any,
    job_id: str,
    owner_id: str,
    extension_seconds: int = 300,
) -> bool:
    """Atomically renew an active job lease.

    Guarantees:
        - Only succeeds if the calling worker still currently owns the lease AND it has not expired yet.
        - Extends expires_at to now + extension_seconds and updates last_heartbeat.
        - Returns False if the lease expired or was claimed by another worker.
        - A stale worker cannot renew or alter another worker's active lease.
    """
    if db is None or not owner_id:
        return True

    now = datetime.now(timezone.utc)
    new_expires = now + timedelta(seconds=max(5, int(extension_seconds)))

    try:
        col = db["scheduler_locks"]
        res = col.find_one_and_update(
            {
                "_id": job_id,
                "owner_id": owner_id,
                "expires_at": {"$gt": now},
            },
            {
                "$set": {
                    "expires_at": new_expires,
                    "last_heartbeat": now,
                }
            },
            return_document=ReturnDocument.AFTER if ReturnDocument else None,
        )
        return res is not None
    except Exception as exc:
        logger.warning(_sanitize_log(f"Error renewing distributed lease for '{job_id}': {exc}"))
        return False


def release_job_lease(db: Any, job_id: str, owner_id: str) -> bool:
    """Safely release the distributed job lease.

    Invariant:
        Only deletes the lease document if owner_id matches.
        If the lease expired and was claimed by another worker, this operation
        will NOT delete or invalidate the other worker's active lease.
    """
    if db is None or not owner_id:
        return True

    try:
        col = db["scheduler_locks"]
        res = col.delete_one({"_id": job_id, "owner_id": owner_id})
        return res.deleted_count > 0
    except Exception as exc:
        logger.warning(_sanitize_log(f"Error releasing distributed lease for '{job_id}': {exc}"))
        return False


class ScheduledJob:
    """Represents a registered background scheduled job with in-process and distributed locking."""

    def __init__(
        self,
        job_id: str,
        name: str,
        interval_seconds: int,
        func: Callable[..., Dict[str, Any]],
        enabled: bool = True,
    ):
        self.job_id = job_id
        self.name = name
        self.interval_seconds = max(5, int(interval_seconds))
        self.func = func
        self.enabled = enabled
        self.last_run: Optional[datetime] = None
        self.last_result: Optional[Dict[str, Any]] = None
        self.last_error: Optional[str] = None
        self.run_count: int = 0
        self.failure_count: int = 0
        self.is_running: bool = False
        self._lock = threading.Lock()

    def is_due(self, now: Optional[datetime] = None) -> bool:
        if not self.enabled:
            return False
        if self.is_running:
            return False
        if self.last_run is None:
            return True
        current = now or datetime.now(timezone.utc)
        elapsed = (current - self.last_run).total_seconds()
        return elapsed >= self.interval_seconds

    def execute(self, *args, **kwargs) -> Dict[str, Any]:
        with self._lock:
            if self.is_running:
                return {"status": "skipped", "reason": "Already running"}
            self.is_running = True

        resolved_db = kwargs.get("db")
        if resolved_db is None and args:
            resolved_db = args[0]

        owner_id = f"{os.getpid()}_{uuid.uuid4().hex}"  # Full 128-bit UUID token — no truncation
        lease_seconds = int(os.getenv("SCHEDULER_LOCK_LEASE_SECONDS", "300"))

        has_lock = False
        if resolved_db is not None:
            has_lock = acquire_job_lease(resolved_db, self.job_id, owner_id, lease_seconds=lease_seconds)
            if not has_lock:
                with self._lock:
                    self.is_running = False
                logger.info(_sanitize_log(f"Job '{self.name}' ({self.job_id}) is locked by another worker; skipping execution."))
                return {"status": "skipped", "reason": "Locked by another worker", "job_id": self.job_id}
        else:
            has_lock = True

        start_time = datetime.now(timezone.utc)
        try:
            logger.info(_sanitize_log(f"Starting job '{self.name}' ({self.job_id}) [worker: {owner_id}]..."))
            call_kwargs = dict(kwargs)
            call_kwargs["owner_id"] = owner_id
            if resolved_db is not None and "db" not in call_kwargs:
                call_kwargs["db"] = resolved_db

            try:
                sig = inspect.signature(self.func)
                has_var_kw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
                if not has_var_kw:
                    call_kwargs = {k: v for k, v in call_kwargs.items() if k in sig.parameters}
            except Exception:
                pass

            result = self.func(*args, **call_kwargs)
            self.last_run = start_time
            self.last_result = result
            self.last_error = None
            self.run_count += 1
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            logger.info(_sanitize_log(f"Completed job '{self.name}' ({self.job_id}) in {duration:.2f}s."))
            return result or {"status": "completed"}
        except Exception as exc:
            self.last_run = start_time
            self.last_error = str(exc)
            self.failure_count += 1
            logger.error(_sanitize_log(f"Error in job '{self.name}' ({self.job_id}): {exc}"))
            return {"status": "failed", "error": str(exc)}
        finally:
            if resolved_db is not None and has_lock:
                release_job_lease(resolved_db, self.job_id, owner_id)
            with self._lock:
                self.is_running = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "name": self.name,
            "interval_seconds": self.interval_seconds,
            "enabled": self.enabled,
            "is_running": self.is_running,
            "run_count": self.run_count,
            "failure_count": self.failure_count,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "last_error": self.last_error,
            "last_result": self.last_result,
        }


class LeadMagnetScheduler:
    """Singleton scheduler manager for background pipeline jobs."""

    _instance = None
    _singleton_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._singleton_lock:
            if cls._instance is None:
                cls._instance = super(LeadMagnetScheduler, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, db: Any = None):
        if getattr(self, "_initialized", False):
            if db is not None:
                self.db = db
            return

        self.db = db
        self.jobs: Dict[str, ScheduledJob] = {}
        self._jobs_lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._is_started = False
        self._initialized = True

    def register_job(
        self,
        job_id: str,
        name: str,
        interval_seconds: int,
        func: Callable[..., Dict[str, Any]],
        enabled: bool = True,
    ) -> ScheduledJob:
        """Register a scheduled job. Replaces if existing with updated parameters without duplication."""
        with self._jobs_lock:
            if job_id in self.jobs:
                job = self.jobs[job_id]
                job.name = name
                job.interval_seconds = max(5, int(interval_seconds))
                job.func = func
                job.enabled = enabled
                logger.info(_sanitize_log(f"Updated registered job '{job_id}' (interval: {interval_seconds}s)"))
                return job

            job = ScheduledJob(
                job_id=job_id,
                name=name,
                interval_seconds=interval_seconds,
                func=func,
                enabled=enabled,
            )
            self.jobs[job_id] = job
            logger.info(_sanitize_log(f"Registered new scheduled job '{job_id}' (interval: {interval_seconds}s)"))
            return job

    def unregister_job(self, job_id: str) -> bool:
        with self._jobs_lock:
            if job_id in self.jobs:
                del self.jobs[job_id]
                return True
            return False

    def get_job(self, job_id: str) -> Optional[ScheduledJob]:
        with self._jobs_lock:
            return self.jobs.get(job_id)

    def is_running(self) -> bool:
        return self._is_started and self._thread is not None and self._thread.is_alive()

    def start(self, db: Any = None, force: bool = False) -> bool:
        """Start background scheduler loop in a daemon thread.

        Guards:
            - If already started, prevents duplicate thread creation.
            - Checks ENABLE_SCHEDULER environment variable (default: true in production, false when disabled).
            - Respects Flask reloader: ignores monitor process if WERKZEUG_RUN_MAIN is not set when debugging.
        """
        with self._singleton_lock:
            if self.is_running():
                logger.info("Scheduler already active; skipping duplicate startup.")
                return False

            if db is not None:
                self.db = db

            enable_env = os.getenv("ENABLE_SCHEDULER", "true").lower()
            if not force and enable_env not in ("true", "1", "yes"):
                logger.info("Scheduler disabled via ENABLE_SCHEDULER=false; background jobs will not start.")
                return False

            # Flask reloader guard: If FLASK_DEBUG is active, avoid starting in parent process
            is_flask_debug = os.getenv("FLASK_DEBUG", "false").lower() in ("true", "1")
            werkzeug_main = os.getenv("WERKZEUG_RUN_MAIN")
            if not force and is_flask_debug and werkzeug_main != "true":
                logger.info("Skipping scheduler startup in Werkzeug reloader monitor process.")
                return False

            self._stop_event.clear()
            self._thread = threading.Thread(target=self._loop, name="LeadMagnetSchedulerThread", daemon=True)
            self._thread.start()
            self._is_started = True
            logger.info(_sanitize_log(f"Lead Magnet Background Scheduler STARTED with {len(self.jobs)} registered jobs."))
            return True

    def stop(self, timeout: float = 5.0) -> bool:
        """Gracefully stop background scheduler."""
        with self._singleton_lock:
            if not self._is_started or self._thread is None:
                return False

            logger.info("Stopping Lead Magnet Background Scheduler...")
            self._stop_event.set()
            if self._thread.is_alive():
                self._thread.join(timeout=timeout)
            self._is_started = False
            self._thread = None
            logger.info("Lead Magnet Background Scheduler stopped.")
            return True

    def _loop(self):
        """Internal daemon worker loop."""
        while not self._stop_event.is_set():
            now = datetime.now(timezone.utc)
            due_jobs: List[ScheduledJob] = []

            with self._jobs_lock:
                for job in self.jobs.values():
                    if job.is_due(now):
                        due_jobs.append(job)

            for job in due_jobs:
                if self._stop_event.is_set():
                    break
                try:
                    # Execute job with db reference
                    job.execute(db=self.db)
                except Exception as exc:
                    logger.error(_sanitize_log(f"Unhandled error in scheduled job '{job.job_id}': {exc}"))

            # Sleep in short increments to allow rapid, graceful shutdown
            for _ in range(10):
                if self._stop_event.is_set():
                    break
                time.sleep(0.5)

    def trigger_job(self, job_id: str, db: Any = None) -> Dict[str, Any]:
        """Manually trigger a job immediately (e.g. for testing or admin manual dispatch)."""
        job = self.get_job(job_id)
        if not job:
            return {"status": "not_found", "error": f"Job '{job_id}' is not registered"}
        resolved_db = db if db is not None else self.db
        return job.execute(db=resolved_db)

    def get_status(self) -> Dict[str, Any]:
        """Return diagnostic status of the scheduler."""
        with self._jobs_lock:
            jobs_summary = {jid: j.to_dict() for jid, j in self.jobs.items()}

        return {
            "is_running": self.is_running(),
            "job_count": len(jobs_summary),
            "jobs": jobs_summary,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


# ==============================================================================
# Pipeline Jobs Implementation
# ==============================================================================

def run_opportunity_pipeline_job(
    db: Any = None,
    provider: Any = None,
    max_customers: int = 50,
    owner_id: Optional[str] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Execute opportunity detection & dispatch pipeline across eligible hot customers.

    Flow:
        1. Identifies eligible hot and active customers (lead_probability >= 0.70 or active interest).
        2. Evaluates detected opportunities for each customer.
        3. Enforces lease validity check (stops if lease expired or claimed by another worker).
        4. Respects 24-hour opportunity cooldown, promotional opt-out suppression, and idempotency.
        5. Selects single primary channel per opportunity.
        6. Dispatches communications deterministically via configured or provided provider.
    """
    if db is None:
        try:
            import app as app_module
            db = getattr(app_module, "db", None)
        except Exception:
            pass

    if db is None:
        return {"status": "skipped", "reason": "Database unavailable"}

    from opportunity_engine import process_customer_opportunities

    # 1. Discover customer candidates: Hot lead states or customers with cart/wishlist
    candidate_ids = set()

    try:
        # Check customer_lead_state for Hot leads (lead_probability >= HOT_PROBABILITY_EQUIV)
        state_col = db["customer_lead_state"]
        hot_docs = list(state_col.find(
            {"$or": [{"lead_probability": {"$gte": HOT_PROBABILITY_EQUIV}}, {"lead_state": "Hot"}]},
            {"customer_id": 1}
        ).limit(max_customers))
        for d in hot_docs:
            cid = d.get("customer_id")
            if cid:
                candidate_ids.add(str(cid))

        # Check cart & wishlist for customers with active intent
        cart_col = db["cart"]
        cart_cids = cart_col.distinct("user_id", {"items.0": {"$exists": True}})
        for cid in cart_cids:
            if cid and len(candidate_ids) < max_customers:
                candidate_ids.add(str(cid))

        wishlist_col = db["wishlist"]
        wish_cids = wishlist_col.distinct("user_id", {"items.0": {"$exists": True}})
        for cid in wish_cids:
            if cid and len(candidate_ids) < max_customers:
                candidate_ids.add(str(cid))
    except Exception as exc:
        logger.warning(_sanitize_log(f"Error querying opportunity candidates: {exc}"))

    total_scanned = len(candidate_ids)
    total_communicated = 0
    total_skipped = 0
    details = []

    lease_seconds = int(os.getenv("SCHEDULER_LOCK_LEASE_SECONDS", "300"))
    lease_guard = None
    if owner_id and db is not None:
        lease_guard = lambda: renew_job_lease(db, "opportunity_pipeline", owner_id, extension_seconds=lease_seconds)

    for cid in candidate_ids:
        # Check and renew lease immediately before evaluating each customer batch
        if owner_id and not renew_job_lease(db, "opportunity_pipeline", owner_id, extension_seconds=lease_seconds):
            logger.warning(_sanitize_log("Lease for opportunity_pipeline expired or acquired by another worker. Halting execution."))
            break

        try:
            res = process_customer_opportunities(
                customer_id=cid,
                db=db,
                provider=provider,
                lease_checker=lease_guard,
            )
            comm_list = res.get("communicated", [])
            skip_list = res.get("skipped", [])
            total_communicated += len(comm_list)
            total_skipped += len(skip_list)
            details.append({
                "customer_id": str(cid),
                "detected": res.get("detected_count", 0),
                "communicated": len(comm_list),
                "skipped": len(skip_list),
            })
        except Exception as c_exc:
            total_skipped += 1
            logger.warning(_sanitize_log(f"Error evaluating opportunities for customer {cid}: {c_exc}"))

    return {
        "status": "completed",
        "customers_evaluated": total_scanned,
        "communicated_count": total_communicated,
        "skipped_count": total_skipped,
        "summary": details,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def run_price_drop_pipeline_job(
    db: Any = None,
    provider: Any = None,
    max_drops: int = 50,
    owner_id: Optional[str] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Execute price drop dispatch pipeline and optional catalog refresh check.

    Flow:
        1. Queries pending detected product_price_drop opportunities.
        2. Enforces lease validity and atomic renewal check before each dispatch.
        3. Dispatches each opportunity deterministically via dispatch_price_drop_opportunity.
        4. Enforces 24-hour opportunity cooldown, customer consent, and idempotency.
        5. Checks catalog refresh status; triggers refresh if scheduled/due.
    """
    if db is None:
        try:
            import app as app_module
            db = getattr(app_module, "db", None)
        except Exception:
            pass

    if db is None:
        return {"status": "skipped", "reason": "Database unavailable"}

    from price_drop_opportunity_service import dispatch_price_drop_opportunity

    opp_col = db["marketing_opportunities"]
    pending_opps = list(opp_col.find({
        "opportunity_type": "product_price_drop",
        "opportunity_state": "detected",
    }).limit(max_drops))

    dispatched = 0
    skipped = 0
    results = []

    lease_seconds = int(os.getenv("SCHEDULER_LOCK_LEASE_SECONDS", "300"))
    lease_guard = None
    if owner_id and db is not None:
        lease_guard = lambda: renew_job_lease(db, "price_drop_pipeline", owner_id, extension_seconds=lease_seconds)

    for opp in pending_opps:
        # Check and renew lease immediately before dispatching each price drop
        if owner_id and not renew_job_lease(db, "price_drop_pipeline", owner_id, extension_seconds=lease_seconds):
            logger.warning(_sanitize_log("Lease for price_drop_pipeline expired or acquired by another worker. Halting execution."))
            break

        try:
            res = dispatch_price_drop_opportunity(
                opportunity_or_key=opp,
                db=db,
                provider=provider,
                enforce_cooldown=True,
                lease_checker=lease_guard,
            )
            if res.get("success"):
                dispatched += 1
            else:
                skipped += 1
            results.append({
                "opportunity_key": opp.get("opportunity_key"),
                "status": res.get("status"),
                "error": res.get("error"),
            })
        except Exception as d_exc:
            skipped += 1
            logger.warning(_sanitize_log(f"Error dispatching price drop opportunity: {d_exc}"))

    # Catalog refresh check: only permitted when the worker still owns the lease
    catalog_refresh_status = "not_due"
    if owner_id and not is_job_lease_valid(db, "price_drop_pipeline", owner_id):
        logger.warning(_sanitize_log(
            "Lease for price_drop_pipeline was lost before catalog refresh. Skipping catalog refresh."
        ))
        catalog_refresh_status = "skipped_lease_lost"
    else:
        try:
            from myntra_catalog_refresh_service import is_refresh_due, run_catalog_refresh
            due, reason, _ = is_refresh_due(db=db)
            if due:
                logger.info(_sanitize_log(f"Catalog refresh due ({reason}). Executing scheduled refresh..."))
                refresh_rep = run_catalog_refresh(db=db, force=False)
                catalog_refresh_status = refresh_rep.get("status", "completed")
        except Exception as cat_exc:
            catalog_refresh_status = f"error: {type(cat_exc).__name__}"

    return {
        "status": "completed",
        "pending_evaluated": len(pending_opps),
        "dispatched_count": dispatched,
        "skipped_count": skipped,
        "catalog_refresh_status": catalog_refresh_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def run_customer_recency_rescore_job(
    db: Any = None,
    max_customers: int = 100,
    owner_id: Optional[str] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Rescore customers active in the last 45 days so recency decay applies automatically.

    Lease-locked to ensure single-worker execution across distributed nodes.
    Idempotent: Re-scoring with unchanged activity produces identical results.
    """
    if db is None:
        try:
            import app as app_module
            db = getattr(app_module, "db", None)
        except Exception:
            pass

    if db is None:
        return {"status": "skipped", "reason": "Database unavailable"}

    from customer_lead_state_service import sync_customer_lead_state

    lease_seconds = int(os.getenv("SCHEDULER_LOCK_LEASE_SECONDS", "300"))
    if owner_id and not renew_job_lease(db, "customer_recency_rescore", owner_id, extension_seconds=lease_seconds):
        logger.warning(_sanitize_log("Lease for customer_recency_rescore expired or acquired by another worker. Halting."))
        return {"status": "skipped_lease_lost"}

    features_col = db["customer_features"]
    active_docs = list(features_col.find(
        {"days_since_last_activity": {"$lte": 45.0}},
        {"customer_id": 1}
    ).limit(max_customers))

    rescored_count = 0
    errors_count = 0

    for doc in active_docs:
        cid = doc.get("customer_id")
        if not cid:
            continue

        if owner_id and not renew_job_lease(db, "customer_recency_rescore", owner_id, extension_seconds=lease_seconds):
            logger.warning(_sanitize_log("Lease lost during customer_recency_rescore. Stopping batch."))
            break

        try:
            sync_customer_lead_state(cid, db)
            rescored_count += 1
        except Exception as exc:
            errors_count += 1
            logger.warning(_sanitize_log(f"Error rescoring customer {cid}: {exc}"))

    return {
        "status": "completed",
        "customers_rescored": rescored_count,
        "errors_count": errors_count,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ==============================================================================
# Global Instance Helper & Registration
# ==============================================================================

_global_scheduler: Optional[LeadMagnetScheduler] = None


def get_scheduler(db: Any = None) -> LeadMagnetScheduler:
    """Retrieve or initialize the global LeadMagnetScheduler instance."""
    global _global_scheduler
    if _global_scheduler is None:
        _global_scheduler = LeadMagnetScheduler(db=db)

        # Register default core pipeline jobs
        opp_interval = int(os.getenv("OPPORTUNITY_PIPELINE_INTERVAL_SECONDS", "3600"))  # default 1 hour
        drop_interval = int(os.getenv("PRICE_DROP_PIPELINE_INTERVAL_SECONDS", "1800"))   # default 30 mins
        rescore_interval = int(os.getenv("CUSTOMER_RESCORE_INTERVAL_SECONDS", "86400")) # default 24 hours

        _global_scheduler.register_job(
            job_id="opportunity_pipeline",
            name="Hot Lead Opportunity Scan Pipeline",
            interval_seconds=opp_interval,
            func=run_opportunity_pipeline_job,
            enabled=True,
        )

        _global_scheduler.register_job(
            job_id="price_drop_pipeline",
            name="Product Price Drop Dispatch Pipeline",
            interval_seconds=drop_interval,
            func=run_price_drop_pipeline_job,
            enabled=True,
        )

        _global_scheduler.register_job(
            job_id="customer_recency_rescore",
            name="Customer Recency Decay Rescore Job",
            interval_seconds=rescore_interval,
            func=run_customer_recency_rescore_job,
            enabled=True,
        )

    if db is not None:
        _global_scheduler.db = db

    return _global_scheduler


def run_scheduler_daemon(db: Any = None, poll_interval: float = 1.0) -> None:
    """Run the scheduler in the foreground as a standalone dedicated daemon process.

    Gracefully handles SIGINT (Ctrl+C) and SIGTERM signals for clean shutdown.
    """
    import signal

    scheduler = get_scheduler(db)
    shutdown_requested = threading.Event()

    def _signal_handler(signum, frame):
        sig_name = signal.Signals(signum).name if hasattr(signal, "Signals") else str(signum)
        logger.info(f"Received shutdown signal {sig_name}. Stopping scheduler daemon...")
        shutdown_requested.set()

    signal.signal(signal.SIGINT, _signal_handler)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _signal_handler)

    logger.info("Starting Lead Magnet dedicated scheduler process in foreground...")
    scheduler.start(db, force=True)

    try:
        while not shutdown_requested.is_set():
            shutdown_requested.wait(poll_interval)
    finally:
        scheduler.stop(timeout=5.0)
        logger.info("Lead Magnet dedicated scheduler process stopped cleanly.")


if __name__ == "__main__":
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    try:
        import app as app_module
        app_db = getattr(app_module, "db", None)
    except Exception as e:
        logger.warning(f"Could not import app db: {e}")
        app_db = None

    run_scheduler_daemon(db=app_db)
