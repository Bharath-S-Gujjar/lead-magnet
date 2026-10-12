"""Order service handling completed customer orders in MongoDB.

Supports live Myntra string product IDs (e.g. 'myntra_28420390') and snapshots
product prices at checkout time to prevent post-order drift.
"""

from datetime import datetime, timezone
from bson import ObjectId
from cart_service import clear_cart
from product_lookup import resolve_product_doc


def _owner_query(user_id=None, anonymous_id=None):
    if user_id:
        return {"user_id": ObjectId(user_id) if isinstance(user_id, str) else user_id}
    if anonymous_id:
        return {"anonymous_id": str(anonymous_id)}
    raise ValueError("Authenticated user_id is required")


def _validated_cart_items(cart_collection, products_collection, user_id=None, anonymous_id=None, selected_items=None):
    owner_query = _owner_query(user_id, anonymous_id)
    all_cart_items = list(cart_collection.find(owner_query))
    if not all_cart_items:
        raise ValueError("Cannot create order from an empty cart")

    cart_items = all_cart_items
    if selected_items:
        target_ids = set()
        for item in selected_items:
            if isinstance(item, dict):
                pid = item.get("product_id") or item.get("id") or item.get("_id")
                if pid:
                    target_ids.add(str(pid))
            elif item:
                target_ids.add(str(item))

        matching = []
        for c in all_cart_items:
            c_pid = str(c.get("product_id") or "")
            c_id = str(c.get("_id") or "")
            if c_pid in target_ids or c_id in target_ids:
                matching.append(c)
            else:
                try:
                    prod = resolve_product_doc(products_collection, c.get("product_id"))
                    if prod:
                        p_prod_id = str(prod.get("product_id") or "")
                        p_oid = str(prod.get("_id") or "")
                        if p_prod_id in target_ids or p_oid in target_ids:
                            matching.append(c)
                except Exception:
                    pass
        if matching:
            cart_items = matching

    order_items = []
    for cart_item in cart_items:
        raw_pid = cart_item.get("product_id")
        if not raw_pid:
            raise ValueError("Cart contains an invalid product")

        product = resolve_product_doc(products_collection, raw_pid)
        if not product:
            raise ValueError("Cart contains an unavailable product")

        price_val = product.get("price")
        if price_val is None:
            price_val = product.get("current_price")
        if price_val is None or not isinstance(price_val, (int, float)):
            raise ValueError("Cart contains an unavailable product")
        price = price_val

        quantity = cart_item.get("quantity")
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
            raise ValueError("Cart contains an invalid quantity")

        canonical_pid = str(product.get("product_id") or raw_pid or product.get("_id"))
        title = product.get("title") or product.get("name") or "Product"
        primary_img = product.get("primary_image") or product.get("image")
        if not primary_img and isinstance(product.get("images"), list) and product["images"]:
            primary_img = product["images"][0]

        order_items.append({
            "product_id": canonical_pid,
            "name": title,
            "title": title,
            "price": price,
            "quantity": quantity,
            "subtotal": round(price * quantity, 2) if isinstance(price, float) else price * quantity,
            "image": primary_img,
            "primary_image": primary_img,
            "category": product.get("category"),
            "brand": product.get("brand"),
            "url": product.get("url"),
        })

    return owner_query, order_items, cart_items


def create_order(
    orders_collection,
    cart_collection,
    products_collection,
    user_id=None,
    anonymous_id=None,
    customer_email=None,
    customer_name=None,
    shipping_address=None,
    payment_method="Credit Card",
    **kwargs,
):
    """Create an order from current cart items, remove ordered items from the cart, and return the order doc."""
    selected_items = kwargs.get("selected_items") or kwargs.get("items")
    owner_query, order_items, ordered_cart_docs = _validated_cart_items(
        cart_collection, products_collection, user_id, anonymous_id, selected_items=selected_items
    )
    total_amount = sum(item["subtotal"] for item in order_items)
    u_id = ObjectId(user_id) if (user_id and isinstance(user_id, str)) else user_id

    now = datetime.now(timezone.utc)
    order_doc = {
        "user_id": u_id,
        "anonymous_id": str(anonymous_id) if anonymous_id else None,
        "customer_email": customer_email,
        "customer_name": customer_name,
        "items": order_items,
        "total_amount": round(total_amount, 2) if isinstance(total_amount, float) else total_amount,
        "shipping_address": shipping_address or {},
        "payment_method": payment_method,
        "payment_status": "Paid",
        "order_status": "Placed",
        "status": "placed",
        "created_at": now,
        "updated_at": now,
    }

    result = orders_collection.insert_one(order_doc)
    order_doc["_id"] = result.inserted_id

    # Remove only the purchased items from the cart; preserve any unselected items
    ordered_ids = [c["_id"] for c in ordered_cart_docs if "_id" in c]
    if ordered_ids:
        cart_collection.delete_many({"_id": {"$in": ordered_ids}})
    else:
        clear_cart(cart_collection, **owner_query)

    return order_doc


def get_user_orders(orders_collection, user_id=None, customer_email=None):
    """Retrieve order history for a user or email."""
    query = {}
    if user_id:
        u_id = ObjectId(user_id) if isinstance(user_id, str) else user_id
        query["user_id"] = u_id
    elif customer_email:
        query["customer_email"] = customer_email

    orders = list(orders_collection.find(query).sort("created_at", -1))
    return orders


def get_order_by_id(orders_collection, order_id):
    """Retrieve single order details by ObjectId string."""
    o_id = ObjectId(order_id) if isinstance(order_id, str) else order_id
    return orders_collection.find_one({"_id": o_id})
