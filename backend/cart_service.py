"""Cart service handling persistent shopping cart operations in MongoDB.

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
    """Build condition matching stored cart product_id in various valid formats."""
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

    # Deduplicate while preserving non-hashables safely
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


def get_user_cart(cart_collection, products_collection, user_id=None, anonymous_id=None):
    """Fetch cart items with populated Myntra product details."""
    query = _build_query(user_id, anonymous_id)
    cart_items = list(cart_collection.find(query))

    result = []
    for item in cart_items:
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

            mrp_val = product.get("mrp") or product.get("price_before_discount")
            disc_val = product.get("discount_percent") or product.get("discount", 0)

            added_at = item.get("added_at")
            if isinstance(added_at, datetime):
                added_at = added_at.isoformat()

            result.append({
                "cart_item_id": str(item["_id"]),
                "product_id": resolved_pid,
                "name": name,
                "title": name,
                "price": price_val,
                "mrp": mrp_val,
                "discount_percent": disc_val,
                "discount": disc_val,
                "image": primary_img,
                "primary_image": primary_img,
                "category": product.get("category"),
                "brand": product.get("brand"),
                "url": product.get("url"),
                "quantity": item.get("quantity", 1),
                "added_at": added_at,
            })

    return result


def add_to_cart(cart_collection, products_collection, product_id, quantity=1, user_id=None, anonymous_id=None):
    """Add a product to cart or increment quantity if already present.

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
    existing = cart_collection.find_one(item_query)

    now = datetime.now(timezone.utc)
    if existing:
        new_qty = existing.get("quantity", 0) + quantity
        cart_collection.update_one(
            {"_id": existing["_id"]},
            {"$set": {"quantity": new_qty, "updated_at": now}}
        )
    else:
        doc = {
            **query,
            "product_id": canonical_pid,
            "quantity": quantity,
            "added_at": now,
            "updated_at": now
        }
        cart_collection.insert_one(doc)

    return get_user_cart(cart_collection, products_collection, user_id, anonymous_id)


def update_cart_quantity(cart_collection, products_collection, product_id, quantity, user_id=None, anonymous_id=None):
    """Update item quantity or remove if quantity <= 0."""
    query = _build_query(user_id, anonymous_id)
    product = resolve_product_doc(products_collection, product_id)
    canonical_pid = product.get("product_id") if product else None
    item_query = {**query, **_product_match_cond(product_id, canonical_pid)}

    if quantity <= 0:
        cart_collection.delete_one(item_query)
    else:
        cart_collection.update_one(
            item_query,
            {"$set": {"quantity": quantity, "updated_at": datetime.now(timezone.utc)}}
        )

    return get_user_cart(cart_collection, products_collection, user_id, anonymous_id)


def remove_from_cart(cart_collection, products_collection, product_id, user_id=None, anonymous_id=None):
    """Remove a product from cart."""
    query = _build_query(user_id, anonymous_id)
    product = resolve_product_doc(products_collection, product_id)
    canonical_pid = product.get("product_id") if product else None
    item_query = {**query, **_product_match_cond(product_id, canonical_pid)}

    cart_collection.delete_one(item_query)
    return get_user_cart(cart_collection, products_collection, user_id, anonymous_id)


def clear_cart(cart_collection, user_id=None, anonymous_id=None):
    """Remove all items from user cart."""
    query = _build_query(user_id, anonymous_id)
    cart_collection.delete_many(query)


def merge_anonymous_cart(cart_collection, anonymous_id, user_id):
    """Merge anonymous cart items into user cart upon login/signup."""
    if not anonymous_id or not user_id:
        return 0

    u_id = ObjectId(user_id) if isinstance(user_id, str) else user_id
    anon_items = list(cart_collection.find({"anonymous_id": str(anonymous_id)}))

    merged_count = 0
    for item in anon_items:
        p_id = item["product_id"]
        cond = _product_match_cond(p_id)
        existing = cart_collection.find_one({"user_id": u_id, **cond})
        if existing:
            cart_collection.update_one(
                {"_id": existing["_id"]},
                {"$set": {"quantity": existing["quantity"] + item.get("quantity", 1)}}
            )
            cart_collection.delete_one({"_id": item["_id"]})
        else:
            cart_collection.update_one(
                {"_id": item["_id"]},
                {"$set": {"user_id": u_id}, "$unset": {"anonymous_id": ""}}
            )
        merged_count += 1

    return merged_count
