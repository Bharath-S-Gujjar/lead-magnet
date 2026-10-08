"""Wishlist service handling persistent wishlist operations in MongoDB.

Supports live Myntra string product IDs (e.g. 'myntra_28420390') as well as
legacy ObjectId values where required by existing tests.
"""

from datetime import datetime, timezone
from typing import Any, Optional
from bson import ObjectId

from product_lookup import resolve_product_doc


def _build_query(user_id=None, anonymous_id=None):
    if user_id:
        return {"user_id": ObjectId(user_id) if isinstance(user_id, str) else user_id}
    if anonymous_id:
        return {"anonymous_id": str(anonymous_id)}
    raise ValueError("Either user_id or anonymous_id must be provided")


def _product_match_cond(product_id: Any, canonical_pid: Optional[str] = None):
    """Build condition matching stored wishlist product_id in various valid formats."""
    pids = []
    if product_id is not None:
        pids.append(product_id)
        if isinstance(product_id, str):
            if ObjectId.is_valid(product_id):
                pids.append(ObjectId(product_id))
        elif isinstance(product_id, ObjectId):
            pids.append(str(product_id))

    if canonical_pid:
        pids.append(canonical_pid)
        if ObjectId.is_valid(canonical_pid):
            pids.append(ObjectId(canonical_pid))

    unique_pids = []
    seen = set()
    for p in pids:
        key = (type(p), str(p))
        if key not in seen:
            seen.add(key)
            unique_pids.append(p)

    if len(unique_pids) == 1:
        return {"product_id": unique_pids[0]}
    return {"product_id": {"$in": unique_pids}}


def get_user_wishlist(wishlist_collection, products_collection, user_id=None, anonymous_id=None):
    """Fetch wishlist items with populated Myntra product details."""
    query = _build_query(user_id, anonymous_id)
    wishlist_items = list(wishlist_collection.find(query))

    result = []
    for item in wishlist_items:
        p_id = item.get("product_id")
        product = resolve_product_doc(products_collection, p_id) if p_id else None
        if product:
            resolved_pid = str(product.get("product_id") or p_id or product.get("_id"))
            name = product.get("title") or product.get("name") or "Product"
            primary_img = product.get("primary_image") or product.get("image")
            if not primary_img and isinstance(product.get("images"), list) and product["images"]:
                primary_img = product["images"][0]

            price_val = product.get("price")
            if price_val is None:
                price_val = product.get("current_price", 0)

            disc_val = product.get("discount_percent") or product.get("discount", 0)

            created_at = item.get("created_at")
            if isinstance(created_at, datetime):
                created_at = created_at.isoformat()

            result.append({
                "wishlist_item_id": str(item["_id"]),
                "product_id": resolved_pid,
                "name": name,
                "title": name,
                "price": price_val,
                "mrp": product.get("mrp") or product.get("price_before_discount"),
                "discount": disc_val,
                "discount_percent": disc_val,
                "image": primary_img,
                "primary_image": primary_img,
                "category": product.get("category"),
                "brand": product.get("brand"),
                "url": product.get("url"),
                "added_at": created_at,
            })

    return result


def add_to_wishlist(wishlist_collection, products_collection, product_id, user_id=None, anonymous_id=None):
    """Add a product to wishlist if not already present.

    Preserves exact Myntra product_id (e.g. 'myntra_28420390').
    """
    query = _build_query(user_id, anonymous_id)
    product = resolve_product_doc(products_collection, product_id)
    if not product:
        raise ValueError("Product not found")

    if isinstance(product_id, str) and (product_id.startswith("myntra_") or product.get("product_id")):
        canonical_pid = product.get("product_id") or product_id
    elif isinstance(product_id, ObjectId):
        canonical_pid = product_id
    elif isinstance(product_id, str) and ObjectId.is_valid(product_id):
        canonical_pid = ObjectId(product_id)
    else:
        canonical_pid = product.get("product_id") or product_id

    item_query = {**query, **_product_match_cond(product_id, canonical_pid)}
    existing = wishlist_collection.find_one(item_query)

    if not existing:
        doc = {
            **query,
            "product_id": canonical_pid,
            "created_at": datetime.now(timezone.utc)
        }
        wishlist_collection.insert_one(doc)

    return get_user_wishlist(wishlist_collection, products_collection, user_id, anonymous_id)


def remove_from_wishlist(wishlist_collection, products_collection, product_id, user_id=None, anonymous_id=None):
    """Remove a product from wishlist."""
    query = _build_query(user_id, anonymous_id)
    product = resolve_product_doc(products_collection, product_id)
    canonical_pid = product.get("product_id") if product else None
    item_query = {**query, **_product_match_cond(product_id, canonical_pid)}

    wishlist_collection.delete_one(item_query)
    return get_user_wishlist(wishlist_collection, products_collection, user_id, anonymous_id)


def clear_wishlist(wishlist_collection, user_id=None, anonymous_id=None):
    """Remove all wishlist items for one owner."""
    query = _build_query(user_id, anonymous_id)
    wishlist_collection.delete_many(query)


def merge_anonymous_wishlist(wishlist_collection, anonymous_id, user_id):
    """Merge anonymous wishlist items into user wishlist upon login/signup."""
    if not anonymous_id or not user_id:
        return 0

    u_id = ObjectId(user_id) if isinstance(user_id, str) else user_id
    anon_items = list(wishlist_collection.find({"anonymous_id": str(anonymous_id)}))

    merged_count = 0
    for item in anon_items:
        p_id = item["product_id"]
        cond = _product_match_cond(p_id)
        existing = wishlist_collection.find_one({"user_id": u_id, **cond})
        if existing:
            wishlist_collection.delete_one({"_id": item["_id"]})
        else:
            wishlist_collection.update_one(
                {"_id": item["_id"]},
                {"$set": {"user_id": u_id}, "$unset": {"anonymous_id": ""}}
            )
        merged_count += 1

    return merged_count
