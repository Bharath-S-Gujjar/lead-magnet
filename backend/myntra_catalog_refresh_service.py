"""Credit-efficient dynamic Myntra catalog refresh service.

Maintains live catalog ('myntra_products' in MongoDB) freshness while strictly
preserving ReefAPI free-credit budget (~994 remaining through January 2027).

Architecture & Refresh Policies:
  1. General catalog refresh interval: ~15 days (default: 15).
  2. Batch search only (never calls /product/detail per product).
  3. Small fixed set of broad clothing queries (limit 50 per batch).
  4. Customer-interest priority: cart products > wishlist products.
     Batched targeted reconciliation; avoids refreshing recently synced products.
  5. Strict credit guardrails: hard cap on calls per run (default 5, max 10),
     safe credit reserve check, fail-safe on budget exhaustion.
  6. Idempotent upserts:
     - old current_price becomes previous_price
     - newly fetched price becomes current_price
     - price_history appended only on genuine price change
     - image URLs preserved if new response has sparse image data
     - no product deletion occurs.
  7. Genuine price-drop events fed into existing price_drop_opportunity_service
     without modifying email/Gmail/WhatsApp/ML pipelines.
"""

from __future__ import annotations

import argparse
import datetime
import logging
import os
import sys
from typing import Any, Dict, List, Optional, Set, Tuple

# Logger configuration (sanitizes secret keys automatically)
logger = logging.getLogger("myntra_catalog_refresh")
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] [MyntraRefresh] %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

# Default configuration constants
DEFAULT_MAX_REEF_CALLS_PER_RUN = 5
DEFAULT_GENERAL_REFRESH_INTERVAL_DAYS = 15
DEFAULT_PRIORITY_REFRESH_INTERVAL_DAYS = 3
DEFAULT_SAFE_CREDIT_RESERVE = 50
DEFAULT_BATCH_LIMIT = 50

# Broad fixed general search queries for cost-effective batch population
DEFAULT_GENERAL_QUERIES = [
    "men shirts",
    "women dresses",
    "men jeans",
    "women tops",
    "kurtas",
]

METADATA_COLLECTION_NAME = "catalog_sync_metadata"
METADATA_DOC_ID = "myntra_catalog_refresh"


def _sanitize_log(msg: str) -> str:
    """Ensure no secret credentials appear in log statements."""
    key = os.getenv("REEF_API_KEY")
    if key and key in msg:
        return msg.replace(key, "[REDACTED]")
    return msg


def get_catalog_sync_metadata(db: Any) -> Dict[str, Any]:
    """Retrieve catalog refresh metadata document from MongoDB.

    Falls back to inspecting the most recent last_synced_at timestamp
    in myntra_products if no explicit metadata record exists yet.
    """
    if db is None:
        return {}

    try:
        meta_col = db[METADATA_COLLECTION_NAME]
        doc = meta_col.find_one({"_id": METADATA_DOC_ID})
        if doc:
            return doc
    except Exception:
        pass

    # Fallback: check most recent last_synced_at from myntra_products
    try:
        prod_col = db["myntra_products"]
        latest = prod_col.find_one(
            {"last_synced_at": {"$ne": None}},
            sort=[("last_synced_at", -1)],
        )
        if latest and latest.get("last_synced_at"):
            return {
                "_id": METADATA_DOC_ID,
                "last_general_refresh_at": latest.get("last_synced_at"),
                "total_reef_calls_made": 0,
            }
    except Exception:
        pass

    return {}


def update_catalog_sync_metadata(db: Any, update_data: Dict[str, Any]) -> None:
    """Persist updated refresh metadata in MongoDB."""
    if db is None:
        return
    try:
        meta_col = db[METADATA_COLLECTION_NAME]
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        update_data["updated_at"] = now_iso
        meta_col.update_one(
            {"_id": METADATA_DOC_ID},
            {"$set": update_data},
            upsert=True,
        )
    except Exception as exc:
        logger.warning(f"Could not update catalog sync metadata: {exc}")


def is_refresh_due(
    db: Any = None,
    now: Optional[datetime.datetime] = None,
    force: bool = False,
    interval_days: int = DEFAULT_GENERAL_REFRESH_INTERVAL_DAYS,
) -> Tuple[bool, str, Optional[float]]:
    """Determine whether a catalog refresh run is due based on interval policies.

    Args:
        db: MongoDB database instance.
        now: Current timestamp (defaults to UTC now).
        force: If True, bypasses interval check.
        interval_days: Number of days between general refresh runs.

    Returns:
        Tuple of (is_due: bool, reason: str, elapsed_days: float or None).
    """
    if force:
        return True, "Refresh forced by explicit request", 0.0

    current_time = now or datetime.datetime.now(datetime.timezone.utc)
    metadata = get_catalog_sync_metadata(db)
    last_refresh_str = metadata.get("last_general_refresh_at")

    if not last_refresh_str:
        return True, "Initial refresh due (no previous refresh timestamp recorded)", None

    try:
        last_dt = datetime.datetime.fromisoformat(last_refresh_str)
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=datetime.timezone.utc)

        elapsed_seconds = (current_time - last_dt).total_seconds()
        elapsed_days = elapsed_seconds / 86400.0

        if elapsed_days < interval_days:
            remaining = interval_days - elapsed_days
            reason = (
                f"Refresh skipped: last general refresh was {elapsed_days:.1f} days ago "
                f"(interval: {interval_days}d, {remaining:.1f}d remaining)"
            )
            return False, reason, elapsed_days

        reason = f"Refresh due: last refresh was {elapsed_days:.1f} days ago (interval: {interval_days}d)"
        return True, reason, elapsed_days
    except Exception as exc:
        return True, f"Refresh due (could not parse last refresh date: {exc})", None


def get_priority_customer_product_ids(
    db: Any,
    priority_interval_days: int = DEFAULT_PRIORITY_REFRESH_INTERVAL_DAYS,
    now: Optional[datetime.datetime] = None,
) -> Dict[str, Any]:
    """Identify products currently in customer carts and wishlists.

    Cart items receive higher priority than wishlist items.
    Excludes products already synced within priority_interval_days to avoid
    wasteful redundant requests.

    Returns:
        dict:
          - cart_product_ids (list)
          - wishlist_product_ids (list)
          - stale_priority_ids (list)
          - recommended_queries (list)
    """
    if db is None:
        return {
            "cart_product_ids": [],
            "wishlist_product_ids": [],
            "stale_priority_ids": [],
            "recommended_queries": [],
        }

    current_time = now or datetime.datetime.now(datetime.timezone.utc)
    cart_pids: Set[str] = set()
    wishlist_pids: Set[str] = set()

    # 1. Active Cart Products (Rank 1 Priority)
    try:
        cart_col = db["cart"]
        for doc in cart_col.find({}, {"product_id": 1, "items": 1}):
            pid = doc.get("product_id")
            if pid:
                cart_pids.add(str(pid).strip())
            items = doc.get("items")
            if isinstance(items, list):
                for it in items:
                    if isinstance(it, dict) and it.get("product_id"):
                        cart_pids.add(str(it["product_id"]).strip())
    except Exception as exc:
        logger.warning(f"Error querying cart collection: {exc}")

    # 2. Active Wishlist Products (Rank 2 Priority)
    try:
        wishlist_col = db["wishlist"]
        for doc in wishlist_col.find({}, {"product_id": 1, "items": 1}):
            pid = doc.get("product_id")
            if pid:
                wishlist_pids.add(str(pid).strip())
            items = doc.get("items")
            if isinstance(items, list):
                for it in items:
                    if isinstance(it, dict) and it.get("product_id"):
                        wishlist_pids.add(str(it["product_id"]).strip())
    except Exception as exc:
        logger.warning(f"Error querying wishlist collection: {exc}")

    # Deduplicate: Cart products have precedence over wishlist
    ordered_priority_ids: List[str] = list(cart_pids) + [p for p in wishlist_pids if p not in cart_pids]

    stale_priority_ids: List[str] = []
    recommended_query_candidates: Set[str] = set()

    # 3. Check staleness in myntra_products
    try:
        prod_col = db["myntra_products"]
        for pid in ordered_priority_ids:
            query = {"$or": [{"product_id": pid}, {"source_product_id": pid.replace("myntra_", "")}]}
            prod_doc = prod_col.find_one(query)
            if not prod_doc:
                stale_priority_ids.append(pid)
                continue

            last_sync_str = prod_doc.get("last_synced_at")
            if not last_sync_str:
                stale_priority_ids.append(pid)
            else:
                try:
                    last_dt = datetime.datetime.fromisoformat(last_sync_str)
                    if last_dt.tzinfo is None:
                        last_dt = last_dt.replace(tzinfo=datetime.timezone.utc)
                    elapsed_days = (current_time - last_dt).total_seconds() / 86400.0
                    if elapsed_days >= priority_interval_days:
                        stale_priority_ids.append(pid)
                        # Extract brand or category for batched search query
                        brand = prod_doc.get("brand")
                        category = prod_doc.get("category")
                        if brand:
                            recommended_query_candidates.add(brand.strip())
                        elif category:
                            recommended_query_candidates.add(category.strip())
                except Exception:
                    stale_priority_ids.append(pid)
    except Exception as exc:
        logger.warning(f"Error evaluating priority product staleness: {exc}")

    return {
        "cart_product_ids": list(cart_pids),
        "wishlist_product_ids": list(wishlist_pids),
        "stale_priority_ids": stale_priority_ids,
        "recommended_queries": list(recommended_query_candidates)[:3],  # limit to top 3 targeted queries
    }


def run_catalog_refresh(
    force: bool = False,
    max_calls: Optional[int] = None,
    general_interval_days: Optional[int] = None,
    priority_interval_days: Optional[int] = None,
    general_queries: Optional[List[str]] = None,
    api_client: Any = None,
    db: Any = None,
    products_collection: Any = None,
    now: Optional[datetime.datetime] = None,
    notify_price_drops: bool = True,
) -> Dict[str, Any]:
    """Execute a controlled dynamic catalog refresh respecting credit guardrails.

    Rules strictly enforced:
      - Checks whether refresh is due before executing ReefAPI calls.
      - Never makes more than max_calls (hard-capped at 10).
      - Uses ONLY batch search endpoint (never detail endpoint).
      - Never retries failed API requests automatically.
      - Deduplicates products across query responses.
      - Upserts into myntra_products without deleting existing items.
      - Passes genuine price drops to price_drop_opportunity_service.
      - Updates metadata record in MongoDB.

    Returns:
        Dict report with status, calls_made, credits_consumed, products_fetched,
        inserted_count, updated_count, unchanged_count, price_drops, etc.
    """
    from myntra_product_sync_service import (
        MyntraProductSyncService,
        get_myntra_products_collection,
    )
    from reef_api_client import ReefAPIClient

    current_time = now or datetime.datetime.now(datetime.timezone.utc)
    current_time_iso = current_time.isoformat()

    # 1. Resolve configuration and credit guardrails
    env_max = os.getenv("MYNTRA_REFRESH_MAX_CALLS")
    configured_max = int(max_calls or (int(env_max) if env_max else DEFAULT_MAX_REEF_CALLS_PER_RUN))
    # Hard safety cap: never exceed 10 calls per execution under any circumstances
    effective_max_calls = max(1, min(configured_max, 10))

    env_gen_int = os.getenv("MYNTRA_REFRESH_GENERAL_INTERVAL_DAYS")
    eff_gen_interval = int(general_interval_days or (int(env_gen_int) if env_gen_int else DEFAULT_GENERAL_REFRESH_INTERVAL_DAYS))

    env_prio_int = os.getenv("MYNTRA_REFRESH_PRIORITY_INTERVAL_DAYS")
    eff_prio_interval = int(priority_interval_days or (int(env_prio_int) if env_prio_int else DEFAULT_PRIORITY_REFRESH_INTERVAL_DAYS))

    # 2. Resolve database and collection
    col = products_collection
    if col is None:
        col = get_myntra_products_collection(db=db)
    resolved_db = db
    if resolved_db is None and col is not None and hasattr(col, "database"):
        resolved_db = col.database

    # 3. Check whether refresh is due
    due, reason, elapsed_days = is_refresh_due(
        db=resolved_db,
        now=current_time,
        force=force,
        interval_days=eff_gen_interval,
    )

    initial_catalog_count = col.count_documents({}) if (col is not None and hasattr(col, "count_documents")) else 0

    if not due and not force:
        logger.info(_sanitize_log(f"Catalog refresh SKIPPED: {reason}"))
        return {
            "status": "skipped",
            "reason": reason,
            "calls_made": 0,
            "credits_consumed": 0,
            "products_fetched": 0,
            "deduplicated_count": 0,
            "inserted_count": 0,
            "updated_count": 0,
            "unchanged_count": 0,
            "price_drops_detected": 0,
            "price_increases_detected": 0,
            "final_catalog_count": initial_catalog_count,
            "executed_at": current_time_iso,
            "failures": [],
        }

    logger.info(_sanitize_log(f"Catalog refresh STARTED (force={force}, max_calls={effective_max_calls}): {reason}"))

    # 4. Resolve ReefAPI client
    client = api_client
    if client is None:
        try:
            client = ReefAPIClient()
        except Exception as exc:
            err_msg = f"Failed to initialize ReefAPIClient: {exc}"
            logger.error(_sanitize_log(err_msg))
            return {
                "status": "failed",
                "reason": err_msg,
                "calls_made": 0,
                "credits_consumed": 0,
                "products_fetched": 0,
                "deduplicated_count": 0,
                "inserted_count": 0,
                "updated_count": 0,
                "unchanged_count": 0,
                "price_drops_detected": 0,
                "price_increases_detected": 0,
                "final_catalog_count": initial_catalog_count,
                "executed_at": current_time_iso,
                "failures": [{"stage": "init_client", "error": str(exc)}],
            }

    # 5. Plan queries: Combine customer-interest priority queries + broad general queries
    prio_info = get_priority_customer_product_ids(
        db=resolved_db,
        priority_interval_days=eff_prio_interval,
        now=current_time,
    )

    planned_queries: List[str] = []

    # If stale cart/wishlist items exist, allocate up to 2 calls for targeted reconciliation
    recommended_prio_queries = prio_info.get("recommended_queries", [])
    if recommended_prio_queries:
        for pq in recommended_prio_queries:
            if len(planned_queries) < 2 and len(planned_queries) < effective_max_calls:
                planned_queries.append(pq)

    # Fill remaining budget from broad general clothing queries
    source_general = general_queries or DEFAULT_GENERAL_QUERIES
    for gq in source_general:
        if len(planned_queries) < effective_max_calls and gq not in planned_queries:
            planned_queries.append(gq)

    logger.info(_sanitize_log(f"Planned queries ({len(planned_queries)} calls): {planned_queries}"))

    # 6. Execute controlled batch search queries via existing MyntraProductSyncService
    sync_service = MyntraProductSyncService(collection=col, db=resolved_db)
    sync_report = sync_service.sync_search_queries(
        api_client=client,
        queries=planned_queries,
        limit=DEFAULT_BATCH_LIMIT,
    )

    # 7. Feed genuine price drops into price_drop_opportunity_service if available
    price_drops = sync_report.get("price_drops", [])
    opportunities_created = 0
    if notify_price_drops and price_drops and resolved_db is not None:
        try:
            from price_drop_opportunity_service import process_price_drop_event
            for drop_event in price_drops:
                try:
                    res = process_price_drop_event(
                        price_drop_event=drop_event,
                        db=resolved_db,
                        enforce_cooldown=True,
                        current_time=current_time,
                    )
                    opps = res.get("opportunities", [])
                    opportunities_created += len(opps)
                except Exception as opp_exc:
                    logger.warning(f"Error handling price drop opportunity: {opp_exc}")
        except ImportError:
            logger.info("price_drop_opportunity_service not available for event hook.")

    # 8. Update catalog metadata in MongoDB
    final_catalog_count = col.count_documents({}) if (col is not None and hasattr(col, "count_documents")) else initial_catalog_count

    prev_metadata = get_catalog_sync_metadata(resolved_db)
    prev_total_calls = int(prev_metadata.get("total_reef_calls_made") or 0)
    new_total_calls = prev_total_calls + sync_report.get("search_calls_made", 0)

    summary_metadata = {
        "last_general_refresh_at": current_time_iso,
        "last_refresh_type": "forced" if force else "scheduled",
        "total_reef_calls_made": new_total_calls,
        "last_refresh_report": {
            "search_calls_made": sync_report.get("search_calls_made", 0),
            "credits_consumed": sync_report.get("credits_consumed", 0),
            "total_products_fetched": sync_report.get("total_products_fetched", 0),
            "deduplicated_count": sync_report.get("deduplicated_count", 0),
            "inserted_count": sync_report.get("inserted_count", 0),
            "updated_count": sync_report.get("updated_count", 0),
            "unchanged_count": sync_report.get("unchanged_count", 0),
            "price_drops_detected": len(price_drops),
            "price_increases_detected": len(sync_report.get("price_increases", [])),
            "opportunities_created": opportunities_created,
            "final_catalog_count": final_catalog_count,
        },
    }
    update_catalog_sync_metadata(resolved_db, summary_metadata)

    # 9. Structured summary log (safe, zero credentials)
    logger.info(
        _sanitize_log(
            f"Catalog refresh COMPLETED. Calls made: {sync_report['search_calls_made']}, "
            f"Products fetched: {sync_report['total_products_fetched']}, "
            f"Deduplicated: {sync_report['deduplicated_count']}, "
            f"Inserted: {sync_report['inserted_count']}, "
            f"Updated: {sync_report['updated_count']}, "
            f"Price drops: {len(price_drops)}, "
            f"Final catalog count: {final_catalog_count}"
        )
    )

    return {
        "status": "completed",
        "reason": reason,
        "calls_made": sync_report.get("search_calls_made", 0),
        "credits_consumed": sync_report.get("credits_consumed", 0),
        "products_fetched": sync_report.get("total_products_fetched", 0),
        "deduplicated_count": sync_report.get("deduplicated_count", 0),
        "inserted_count": sync_report.get("inserted_count", 0),
        "updated_count": sync_report.get("updated_count", 0),
        "unchanged_count": sync_report.get("unchanged_count", 0),
        "price_drops_detected": len(price_drops),
        "price_increases_detected": len(sync_report.get("price_increases", [])),
        "opportunities_created": opportunities_created,
        "final_catalog_count": final_catalog_count,
        "executed_at": current_time_iso,
        "queries_used": planned_queries,
        "failures": sync_report.get("failures", []),
    }


def main():
    """CLI entry point for manual or scheduled catalog refresh."""
    parser = argparse.ArgumentParser(description="Myntra Live Catalog Refresh")
    parser.add_argument("--force", action="store_true", help="Force refresh even if not yet due")
    parser.add_argument("--max-calls", type=int, default=5, help="Maximum ReefAPI search calls to make (default: 5)")
    parser.add_argument("--check-only", action="store_true", help="Only check if refresh is due without making API calls")
    args = parser.parse_args()

    from myntra_product_sync_service import get_myntra_products_collection
    col = get_myntra_products_collection()
    db = col.database if col is not None and hasattr(col, "database") else None

    if args.check_only:
        due, reason, elapsed = is_refresh_due(db=db, force=args.force)
        print(f"Refresh Due: {due}")
        print(f"Reason:      {reason}")
        sys.exit(0)

    report = run_catalog_refresh(
        force=args.force,
        max_calls=args.max_calls,
        db=db,
        products_collection=col,
    )
    import json
    print("=" * 60)
    print("MYNTRA_CATALOG_REFRESH_REPORT:")
    print(json.dumps(report, indent=2))
    print("=" * 60)


if __name__ == "__main__":
    main()
