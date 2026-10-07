"""Order service handling completed customer orders in MongoDB."""

from datetime import datetime, timezone
from bson import ObjectId
from cart_service import clear_cart


def _owner_query(user_id=None, anonymous_id=None):
    if user_id:
        return {"user_id": ObjectId(user_id) if isinstance(user_id, str) else user_id}
    if anonymous_id:
        return {"anonymous_id": str(anonymous_id)}
    raise ValueError("Authenticated user_id is required")


def _validated_cart_items(cart_collection, products_collection, user_id=None, anonymous_id=None, item_ids=None):
    owner_query = _owner_query(user_id, anonymous_id)
    query = dict(owner_query)
    if item_ids:
        parsed_ids = []
        for iid in item_ids:
            if isinstance(iid, dict):
                iid = iid.get("product_id") or iid.get("id") or iid.get("_id")
            if isinstance(iid, str) and ObjectId.is_valid(iid):
                parsed_ids.append(ObjectId(iid))
            elif isinstance(iid, ObjectId):
                parsed_ids.append(iid)
        if parsed_ids:
            query["product_id"] = {"$in": parsed_ids}

    cart_items = list(cart_collection.find(query))
    if not cart_items:
        raise ValueError("Cannot create order from an empty cart")

    order_items = []
    for cart_item in cart_items:
        product_id = cart_item.get("product_id")
        if isinstance(product_id, str):
            if not ObjectId.is_valid(product_id):
                raise ValueError("Cart contains an invalid product")
            product_id = ObjectId(product_id)
        if not isinstance(product_id, ObjectId):
            raise ValueError("Cart contains an invalid product")

        product = products_collection.find_one({"_id": product_id})
        if not product or not isinstance(product.get("price"), (int, float)):
            raise ValueError("Cart contains an unavailable product")

        quantity = cart_item.get("quantity")
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
            raise ValueError("Cart contains an invalid quantity")

        price = product["price"]
        order_items.append({
            "product_id": str(product_id),
            "name": product.get("name"),
            "price": price,
            "quantity": quantity,
            "subtotal": price * quantity,
            "image": product.get("image") or (product.get("images", [None])[0] if isinstance(product.get("images"), list) else None),
            "category": product.get("category"),
            "brand": product.get("brand"),
        })

    return owner_query, order_items


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
    items=None,
    product_ids=None,
):
    """Create an order from current cart items, remove purchased items from the cart, and return the order doc."""
    target_ids = product_ids or items
    owner_query, order_items = _validated_cart_items(
        cart_collection, products_collection, user_id, anonymous_id, item_ids=target_ids
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
        "total_amount": total_amount,
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

    # Remove only purchased cart items from active cart state
    purchased_product_ids = [
        ObjectId(item["product_id"]) if isinstance(item["product_id"], str) and ObjectId.is_valid(item["product_id"]) else item["product_id"]
        for item in order_items
        if item.get("product_id")
    ]
    if purchased_product_ids:
        cart_collection.delete_many({**owner_query, "product_id": {"$in": purchased_product_ids}})
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
