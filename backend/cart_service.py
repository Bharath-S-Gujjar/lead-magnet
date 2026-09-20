"""Cart service handling persistent shopping cart operations in MongoDB."""

from datetime import datetime, timezone
from bson import ObjectId


def _build_query(user_id=None, anonymous_id=None):
    if user_id:
        return {"user_id": ObjectId(user_id) if isinstance(user_id, str) else user_id}
    if anonymous_id:
        return {"anonymous_id": str(anonymous_id)}
    raise ValueError("Either user_id or anonymous_id must be provided")


def get_user_cart(cart_collection, products_collection, user_id=None, anonymous_id=None):
    """Fetch cart items with populated product details."""
    query = _build_query(user_id, anonymous_id)
    cart_items = list(cart_collection.find(query))

    result = []
    for item in cart_items:
        p_id = item.get("product_id")
        if isinstance(p_id, str):
            p_id = ObjectId(p_id)
        product = products_collection.find_one({"_id": p_id}) if p_id else None
        if product:
            result.append({
                "cart_item_id": str(item["_id"]),
                "product_id": str(product["_id"]),
                "name": product.get("name"),
                "price": product.get("price", 0),
                "image": product.get("image") or (product.get("images", [None])[0] if isinstance(product.get("images"), list) else None),
                "category": product.get("category"),
                "brand": product.get("brand"),
                "quantity": item.get("quantity", 1),
                "added_at": item.get("added_at").isoformat() if isinstance(item.get("added_at"), datetime) else item.get("added_at"),
            })

    return result


def add_to_cart(cart_collection, products_collection, product_id, quantity=1, user_id=None, anonymous_id=None):
    """Add a product to cart or increment quantity if already present."""
    query = _build_query(user_id, anonymous_id)
    p_id = ObjectId(product_id) if isinstance(product_id, str) else product_id

    product = products_collection.find_one({"_id": p_id})
    if not product:
        raise ValueError("Product not found")

    item_query = {**query, "product_id": p_id}
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
            "product_id": p_id,
            "quantity": quantity,
            "added_at": now,
            "updated_at": now
        }
        cart_collection.insert_one(doc)

    return get_user_cart(cart_collection, products_collection, user_id, anonymous_id)


def update_cart_quantity(cart_collection, products_collection, product_id, quantity, user_id=None, anonymous_id=None):
    """Update item quantity or remove if quantity <= 0."""
    query = _build_query(user_id, anonymous_id)
    p_id = ObjectId(product_id) if isinstance(product_id, str) else product_id

    if quantity <= 0:
        cart_collection.delete_one({**query, "product_id": p_id})
    else:
        cart_collection.update_one(
            {**query, "product_id": p_id},
            {"$set": {"quantity": quantity, "updated_at": datetime.now(timezone.utc)}}
        )

    return get_user_cart(cart_collection, products_collection, user_id, anonymous_id)


def remove_from_cart(cart_collection, products_collection, product_id, user_id=None, anonymous_id=None):
    """Remove a product from cart."""
    query = _build_query(user_id, anonymous_id)
    p_id = ObjectId(product_id) if isinstance(product_id, str) else product_id
    cart_collection.delete_one({**query, "product_id": p_id})
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
        existing = cart_collection.find_one({"user_id": u_id, "product_id": p_id})
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
