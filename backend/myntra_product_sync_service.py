"""Myntra Product Synchronization Service for Lead Magnet.

Synchronizes live Myntra products from ReefAPI into MongoDB ('myntra_products' collection),
tracking previous and current prices, price drop/increase transitions, and price history
while strictly preserving product images and maintaining credit safety.
"""

from __future__ import annotations

import datetime
import os
from typing import Any, Dict, List, Optional, Tuple, Union

from reef_api_client import normalize_myntra_product

COLLECTION_NAME = "myntra_products"


def ensure_myntra_product_indexes(collection: Any) -> None:
    """Ensure indexes on myntra_products collection safely and idempotently.

    Indexes:
      - product_id (unique)
      - source_product_id
      - category
      - brand
      - current_price
      - last_synced_at
    """
    if collection is None:
        return

    try:
        existing = set()
        if hasattr(collection, "list_indexes"):
            for idx in collection.list_indexes():
                if isinstance(idx, dict) and "name" in idx:
                    existing.add(idx["name"])

        indexes_to_create = [
            ("product_id_1", [("product_id", 1)], {"unique": True}),
            ("source_product_id_1", [("source_product_id", 1)], {}),
            ("category_1", [("category", 1)], {}),
            ("brand_1", [("brand", 1)], {}),
            ("current_price_1", [("current_price", 1)], {}),
            ("last_synced_at_-1", [("last_synced_at", -1)], {}),
        ]

        for name, keys, kwargs in indexes_to_create:
            if name not in existing and hasattr(collection, "create_index"):
                try:
                    collection.create_index(keys, name=name, background=True, **kwargs)
                except Exception:
                    pass
    except Exception:
        pass


def get_myntra_products_collection(collection: Any = None, db: Any = None) -> Any:
    """Resolve MongoDB collection for live Myntra products.

    Reuses existing project connection / config approach.
    """
    if collection is not None:
        return collection

    if db is not None:
        return db[COLLECTION_NAME]

    # Attempt to resolve from app module globals if already initialized
    try:
        import app as app_module
        if hasattr(app_module, "db") and app_module.db is not None:
            return app_module.db[COLLECTION_NAME]
    except Exception:
        pass

    # Direct pymongo client fallback (fast, does not load heavy ML modules)
    try:
        uri = os.getenv("MONGO_URI") or os.getenv("MONGODB_URI")
        if uri:
            import certifi
            import pymongo
            client = pymongo.MongoClient(
                uri,
                tls=True,
                tlsCAFile=certifi.where(),
                serverSelectionTimeoutMS=5000,
            )
            client.admin.command("ping")
            db_name = os.getenv("MONGO_DB_NAME", "leadmagnet")
            return client[db_name][COLLECTION_NAME]
    except Exception:
        pass

    # Direct client creation fallback
    try:
        from app import create_mongo_client
        client, _ = create_mongo_client()
        db_name = os.getenv("MONGO_DB_NAME", "leadmagnet")
        return client[db_name][COLLECTION_NAME]
    except Exception:
        return None


def sync_single_product(
    product_data: Dict[str, Any],
    collection: Any = None,
) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]], bool]:
    """Synchronize a single Myntra product into MongoDB.

    Args:
        product_data: Either a normalized product dict or a raw ReefAPI product dict.
        collection: The MongoDB collection to sync into.

    Returns:
        Tuple of:
          - synchronized_document (dict)
          - price_change_event (dict or None)
          - is_new_insertion (bool)
    """
    if collection is None:
        collection = get_myntra_products_collection()
    if collection is None:
        raise RuntimeError("MongoDB collection 'myntra_products' could not be resolved.")

    # 1. Normalize if not already normalized
    if product_data.get("source") == "myntra" and "source_product_id" in product_data:
        norm = dict(product_data)
    else:
        norm = normalize_myntra_product(product_data)

    product_id = norm.get("product_id") or ""
    if not product_id:
        raise ValueError("Cannot sync a product without a product_id.")

    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    fetched_price = norm.get("price")

    # 2. Look up existing document
    existing = collection.find_one({"product_id": product_id})
    is_new = existing is None

    price_change_event: Optional[Dict[str, Any]] = None

    if is_new:
        # First sync:
        # previous_price = null
        # current_price = fetched price
        # Do NOT treat first insertion as a price drop or increase
        first_seen_at = now_iso
        last_synced_at = now_iso
        previous_price = None
        current_price = fetched_price
        price_history: List[Dict[str, Any]] = []
    else:
        # Later sync:
        # previous_price = existing current_price
        # current_price = newly fetched price
        first_seen_at = existing.get("first_seen_at", now_iso)
        last_synced_at = now_iso
        existing_current_price = existing.get("current_price")
        price_history = list(existing.get("price_history", []))

        if fetched_price is not None and existing_current_price is not None:
            if fetched_price != existing_current_price:
                # Genuine price change detected!
                previous_price = existing_current_price
                current_price = fetched_price

                change_type = "drop" if fetched_price < existing_current_price else "increase"
                history_entry = {
                    "product_id": product_id,
                    "old_price": existing_current_price,
                    "new_price": fetched_price,
                    "detected_at": now_iso,
                }
                price_history.append(history_entry)

                price_change_event = {
                    "product_id": product_id,
                    "title": norm.get("title") or existing.get("title", ""),
                    "old_price": existing_current_price,
                    "new_price": fetched_price,
                    "difference": round(fetched_price - existing_current_price, 2),
                    "change_type": change_type,
                    "detected_at": now_iso,
                    "primary_image": norm.get("primary_image") or existing.get("primary_image"),
                    "url": norm.get("url") or existing.get("url"),
                }
            else:
                # Unchanged price:
                # previous_price was existing current_price
                # current_price is newly fetched price
                # Do NOT create history when price has not changed
                previous_price = existing_current_price
                current_price = fetched_price
        elif fetched_price is not None:
            previous_price = existing.get("previous_price")
            current_price = fetched_price
        else:
            previous_price = existing.get("previous_price")
            current_price = existing_current_price

    # 3. Preserve images safely: never discard images
    primary_image = norm.get("primary_image")
    images = norm.get("images") or []
    if not primary_image and existing:
        primary_image = existing.get("primary_image")
    if not images and existing:
        images = existing.get("images") or []

    # 4. Construct complete synchronized document
    synced_doc = {
        "product_id": product_id,
        "source_product_id": norm.get("source_product_id") or "",
        "source": "myntra",
        "title": norm.get("title") or "",
        "brand": norm.get("brand") or "",
        "category": norm.get("category") or "",
        "gender": norm.get("gender") or "",
        "url": norm.get("url") or "",
        "primary_image": primary_image,
        "images": images,
        "price": current_price,
        "mrp": norm.get("mrp"),
        "price_before_discount": norm.get("price_before_discount"),
        "discount_amount": norm.get("discount_amount"),
        "discount_percent": norm.get("discount_percent"),
        "currency": norm.get("currency") or "INR",
        "rating": norm.get("rating"),
        "stock": norm.get("stock"),
        "availability_status": norm.get("availability_status") or "in_stock",
        "first_seen_at": first_seen_at,
        "last_synced_at": last_synced_at,
        "previous_price": previous_price,
        "current_price": current_price,
        "price_history": price_history,
    }

    # 5. Persist to MongoDB with upsert
    collection.update_one(
        {"product_id": product_id},
        {"$set": synced_doc},
        upsert=True,
    )

    return synced_doc, price_change_event, is_new


def sync_myntra_products(
    products: List[Dict[str, Any]],
    collection: Any = None,
) -> Dict[str, Any]:
    """Synchronize a list of Myntra products returned from ReefAPI.

    This function does NOT call ReefAPI. It accepts a pre-fetched list
    to preserve credits and prevent automated loops.

    Returns:
        Summary report dict containing:
          - total_processed
          - inserted_count
          - updated_count
          - price_drops
          - price_increases
          - unchanged_count
          - products
    """
    if collection is None:
        collection = get_myntra_products_collection()

    ensure_myntra_product_indexes(collection)

    inserted_count = 0
    updated_count = 0
    unchanged_count = 0
    price_drops: List[Dict[str, Any]] = []
    price_increases: List[Dict[str, Any]] = []
    synced_products: List[Dict[str, Any]] = []

    for item in products:
        synced_doc, price_event, is_new = sync_single_product(item, collection=collection)
        synced_products.append(synced_doc)

        if is_new:
            inserted_count += 1
        else:
            updated_count += 1

        if price_event:
            if price_event["change_type"] == "drop":
                price_drops.append(price_event)
            else:
                price_increases.append(price_event)
        elif not is_new:
            unchanged_count += 1

    return {
        "total_processed": len(products),
        "inserted_count": inserted_count,
        "updated_count": updated_count,
        "unchanged_count": unchanged_count,
        "price_drops": price_drops,
        "price_increases": price_increases,
        "products": synced_products,
    }


class MyntraProductSyncService:
    """Service wrapper for Myntra catalog persistence and queries."""

    def __init__(self, collection: Any = None, db: Any = None) -> None:
        self.collection = get_myntra_products_collection(collection=collection, db=db)
        if self.collection is not None:
            ensure_myntra_product_indexes(self.collection)

    def ensure_indexes(self) -> None:
        ensure_myntra_product_indexes(self.collection)

    def sync_products(self, products: List[Dict[str, Any]]) -> Dict[str, Any]:
        return sync_myntra_products(products, collection=self.collection)

    def sync_product(self, product: Dict[str, Any]) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]], bool]:
        return sync_single_product(product, collection=self.collection)

    def get_product(self, product_id: str) -> Optional[Dict[str, Any]]:
        if not self.collection or not product_id:
            return None
        return self.collection.find_one({"product_id": str(product_id).strip()})

    def get_price_history(self, product_id: str) -> List[Dict[str, Any]]:
        doc = self.get_product(product_id)
        if not doc:
            return []
        return doc.get("price_history", [])

    def list_products(
        self,
        query: Optional[Dict[str, Any]] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        if not self.collection:
            return []
        q = query or {}
        cursor = self.collection.find(q)
        if limit and hasattr(cursor, "limit"):
            cursor = cursor.limit(limit)
        return list(cursor)

    def sync_search_queries(
        self,
        api_client: Any,
        queries: List[str],
        limit: int = 50,
    ) -> Dict[str, Any]:
        """Execute controlled search queries via ReefAPIClient, deduplicate, and upsert.

        Rules strictly observed:
          - Performs ONLY search requests (never calls detail endpoint).
          - Does NOT retry failed requests automatically.
          - Deduplicates products across all query responses by canonical product ID.
          - Preserves all available normalized fields.
          - Does not delete existing documents.

        Args:
            api_client: An initialized ReefAPIClient instance.
            queries: List of search queries.
            limit: Limit per search request (e.g. 50).

        Returns:
            Dict containing execution summary and sync counts.
        """
        search_calls_made = 0
        all_raw_products: List[Dict[str, Any]] = []
        failures: List[Dict[str, Any]] = []

        for q in queries:
            search_calls_made += 1
            try:
                resp = api_client.search_products(query=q, limit=limit)
                prods = resp.get("products", [])
                all_raw_products.extend(prods)
            except Exception as exc:
                failures.append({"query": q, "error": str(exc)})

        # Deduplicate by canonical Myntra product ID
        deduped_map: Dict[str, Dict[str, Any]] = {}
        for item in all_raw_products:
            canonical_id = item.get("product_id")
            if not canonical_id:
                raw_id = item.get("source_product_id") or item.get("id") or item.get("style_id") or ""
                canonical_id = f"myntra_{raw_id}" if raw_id else ""
            if canonical_id and canonical_id not in deduped_map:
                deduped_map[canonical_id] = item

        deduped_list = list(deduped_map.values())
        sync_result = self.sync_products(deduped_list)

        return {
            "search_calls_made": search_calls_made,
            "credits_consumed": search_calls_made,
            "total_products_fetched": len(all_raw_products),
            "deduplicated_count": len(deduped_list),
            "inserted_count": sync_result.get("inserted_count", 0),
            "updated_count": sync_result.get("updated_count", 0),
            "unchanged_count": sync_result.get("unchanged_count", 0),
            "price_drops": sync_result.get("price_drops", []),
            "price_increases": sync_result.get("price_increases", []),
            "failures": failures,
        }

