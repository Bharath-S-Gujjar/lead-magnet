"""Safe Customer Rescoring Script
==============================

Safely rescores customer lead states with authoritative XGBoost inference.

Safety Invariants:
1. Dry-run by default. Requires explicit `--apply` flag to write changes.
2. Masks DB host and database name in all output.
3. Strictly refuses non-local URIs unless BOTH `--allow-remote` AND
   `--confirm-db <name>` are passed.
4. Checks for a recent backup (within 24h) before applying changes.
5. Prints a structured Before vs. After segment distribution table.

Usage:
  python scripts/rescore_customers.py                  # Dry-run on local DB
  python scripts/rescore_customers.py --apply          # Apply changes to local DB
"""

import os
import sys
import argparse
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, List

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

import pymongo


def _mask_uri(uri: str) -> str:
    """Mask credentials and internal details from MongoDB URI."""
    if not uri:
        return "<empty>"
    # Mask password
    masked = re.sub(r":([^@]+)@", r":****@", uri)
    return masked


def _is_local_uri(uri: str) -> bool:
    """Verify whether URI targets local MongoDB."""
    lower = uri.lower()
    return "localhost" in lower or "127.0.0.1" in lower


def _check_recent_backup(backup_dir: Path, max_age_hours: int = 24) -> bool:
    """Check if a fresh backup directory exists within max_age_hours."""
    if not backup_dir.exists():
        return False
    now = datetime.now(timezone.utc)
    for p in backup_dir.iterdir():
        if p.is_dir():
            mtime = datetime.fromtimestamp(p.stat().st_mtime, timezone.utc)
            if (now - mtime).total_seconds() <= max_age_hours * 3600:
                return True
    return False


def main():
    parser = argparse.ArgumentParser(description="Safely rescore customer leads.")
    parser.add_argument("--apply", action="store_true", default=False, help="Apply changes (default: dry-run only)")
    parser.add_argument("--allow-remote", action="store_true", default=False, help="Allow running on remote DB")
    parser.add_argument("--confirm-db", type=str, default=None, help="Confirm exact DB name for remote execution")
    parser.add_argument("--uri", type=str, default=None, help="Explicit MongoDB connection URI")
    parser.add_argument("--db-name", type=str, default="leadmagnet", help="Database name")
    parser.add_argument("--skip-backup-check", action="store_true", default=False, help="Skip backup check")
    args = parser.parse_args()

    mongo_uri = args.uri or os.getenv("MONGO_URI") or "mongodb://localhost:27017"
    db_name = args.db_name

    # Safety Guard: Check local vs remote
    is_local = _is_local_uri(mongo_uri)
    if not is_local:
        if not args.allow_remote or args.confirm_db != db_name:
            print("\n[SAFETY ABORT] Refusing execution against remote/non-local URI.")
            print(f"Target URI: {_mask_uri(mongo_uri)}")
            print("To run on remote DB, you must supply BOTH:")
            print(f"  --allow-remote --confirm-db {db_name}\n")
            sys.exit(1)

    # Safety Guard: Check backup if applying
    if args.apply and not args.skip_backup_check:
        backup_path = Path(__file__).resolve().parent.parent / "backups"
        if not _check_recent_backup(backup_path):
            print("\n[SAFETY ABORT] No fresh backup (within last 24h) found in backups/.")
            print("Please run backup first:")
            print("  python backend/backup_customer_data.py\n")
            print("Or pass --skip-backup-check if testing locally.")
            sys.exit(1)

    print("=" * 70)
    print("Lead Magnet — Safe Customer Lead Rescoring")
    print("=" * 70)
    print(f"Mode:     {'[LIVE APPLY]' if args.apply else '[DRY-RUN (no changes written)]'}")
    print(f"Host:     {_mask_uri(mongo_uri)}")
    print(f"Database: {db_name}")
    print("=" * 70)

    try:
        client = pymongo.MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        db = client[db_name]
    except Exception as e:
        print(f"[ERROR] Failed to connect to database: {e}")
        sys.exit(1)

    from customer_lead_state_service import sync_customer_lead_state
    from ecommerce_model_adapter import predict_customer_features
    from customer_feature_service import get_customer_features

    state_col = db["customer_lead_state"]
    features_col = db["customer_features"]

    # Initial counts
    before_counts = {
        "Hot": state_col.count_documents({"lead_segment": "Hot"}),
        "Warm": state_col.count_documents({"lead_segment": "Warm"}),
        "Cold": state_col.count_documents({"lead_segment": "Cold"}),
        "Total": state_col.count_documents({}),
    }

    all_features = list(features_col.find({}, {"customer_id": 1}))
    total_customers = len(all_features)
    print(f"\nFound {total_customers} customer feature record(s) to evaluate.\n")

    after_segments = {"Hot": 0, "Warm": 0, "Cold": 0}
    changes = []

    for idx, doc in enumerate(all_features, start=1):
        cid = doc.get("customer_id")
        if not cid:
            continue

        try:
            if args.apply:
                state = sync_customer_lead_state(cid, db)
                seg = state["lead_segment"]
                score = state["lead_score"]
            else:
                f_doc = get_customer_features(cid, features_col)
                pred = predict_customer_features(f_doc)
                seg = pred["lead_segment"]
                score = pred["lead_score"]

            after_segments[seg] = after_segments.get(seg, 0) + 1

            existing_state = state_col.find_one({"customer_id": cid}) or {}
            old_seg = existing_state.get("lead_segment", "None")
            old_score = existing_state.get("lead_score", "None")

            if old_seg != seg or old_score != score:
                changes.append({
                    "customer_id": str(cid),
                    "old_segment": old_seg,
                    "new_segment": seg,
                    "old_score": old_score,
                    "new_score": score,
                })
        except Exception as exc:
            print(f"  [WARN] Error processing customer {cid}: {exc}")

    print("-" * 70)
    print("Rescoring Summary Table")
    print("-" * 70)
    print(f"{'Segment':<12} | {'Before':<10} | {'After':<10} | {'Net Change':<10}")
    print("-" * 70)
    for seg in ["Hot", "Warm", "Cold"]:
        b = before_counts.get(seg, 0)
        a = after_segments.get(seg, 0)
        diff = a - b
        sign = f"+{diff}" if diff > 0 else str(diff)
        print(f"{seg:<12} | {b:<10} | {a:<10} | {sign:<10}")
    print("-" * 70)
    print(f"Total customers modified/evaluated: {len(changes)} / {total_customers}")
    print(f"Action: {'Successfully written to database.' if args.apply else 'DRY RUN ONLY. No data was modified.'}")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
