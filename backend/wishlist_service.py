"""Wishlist service handling persistent wishlist operations in MongoDB."""

from datetime import datetime, timezone
from bson import ObjectId


def _build_query(user_id=None, anonymous_id=None):
    if user_id:
        return {"user_id": ObjectId(user_id) if isinstance(user_id, str) else user_id}
    if anonymous_id:
        return {"anonymous_id": str(anonymous_id)}
    raise ValueError("Either user_id or anonymous_id must be provided")


def get_user_wishlist(wishlist_collection, products_collection, user_id=None, anonymous_id=None):
    """Fetch wishlist items with populated product details."""
    query = _build_query(user_id, anonymous_id)
    wishlist_items = list(wishlist_collection.find(query))

    result = []
    for item in wishlist_items:
        p_id = item.get("product_id")
        if isinstance(p_id, str):
            p_id = ObjectId(p_id)
        product = products_collection.find_one({"_id": p_id}) if p_id else None
        if product:
            result.append({
                "wishlist_item_id": str(item["_id"]),
                "product_id": str(product["_id"]),
                "name": product.get("name"),
                "price": product.get("price", 0),
                "image": product.get("image") or (product.get("images", [None])[0] if isinstance(product.get("images"), list) else None),
                "category": product.get("category"),
                "brand": product.get("brand"),
                "added_at": item.get("created_at").isoformat() if isinstance(item.get("created_at"), datetime) else item.get("created_at"),
            })

    return result


def add_to_wishlist(wishlist_collection, products_collection, product_id, user_id=None, anonymous_id=None):
    """Add a product to wishlist if not already present."""
    query = _build_query(user_id, anonymous_id)
    p_id = ObjectId(product_id) if isinstance(product_id, str) else product_id

    product = products_collection.find_one({"_id": p_id})
    if not product:
        raise ValueError("Product not found")

    item_query = {**query, "product_id": p_id}
    existing = wishlist_collection.find_one(item_query)

    if not existing:
        doc = {
            **query,
            "product_id": p_id,
            "created_at": datetime.now(timezone.utc)
        }
        wishlist_collection.insert_one(doc)

    return get_user_wishlist(wishlist_collection, products_collection, user_id, anonymous_id)


def remove_from_wishlist(wishlist_collection, products_collection, product_id, user_id=None, anonymous_id=None):
    """Remove a product from wishlist."""
    query = _build_query(user_id, anonymous_id)
    p_id = ObjectId(product_id) if isinstance(product_id, str) else product_id
    wishlist_collection.delete_one({**query, "product_id": p_id})
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
        existing = wishlist_collection.find_one({"user_id": u_id, "product_id": p_id})
        if existing:
            wishlist_collection.delete_one({"_id": item["_id"]})
        else:
            wishlist_collection.update_one(
                {"_id": item["_id"]},
                {"$set": {"user_id": u_id}, "$unset": {"anonymous_id": ""}}
            )
        merged_count += 1

    return merged_count
