"""Product affinity and interest analytics service.

Computes product-level affinity signals from event and order data.
This is an ANALYTICS subsystem only — NOT part of the lead probability calculation.
"""

from collections import Counter
from bson import ObjectId

from customer_feature_service import _to_object_id


def compute_product_affinity(customer_id, db):
    """Compute product interest and affinity signals for a customer.

    Args:
        customer_id: ObjectId or string customer identifier.
        db: PyMongo database object.

    Returns:
        dict: Top viewed products, purchased products, category and brand interests.
    """
    if not customer_id or db is None:
        return _empty_affinity()

    events_col = db["events"]
    orders_col = db["orders"]
    products_col = db["products"]

    c_oid = _to_object_id(customer_id)

    # Build user event query
    query_conditions = []
    if c_oid:
        query_conditions.append({"user_id": c_oid})
        query_conditions.append({"user_id": str(c_oid)})
    if isinstance(customer_id, str):
        query_conditions.append({"anonymous_id": customer_id})

    if not query_conditions:
        return _empty_affinity()

    base_query = {"$or": query_conditions}

    # Frequently viewed products
    view_events = list(events_col.find(
        {**base_query, "event_type": {"$in": ["product_view", "product_click"]}},
        {"entity": 1}
    ))

    viewed_product_ids = []
    for e in view_events:
        entity = e.get("entity") or {}
        p_id = entity.get("id") or entity.get("product_id")
        if p_id:
            viewed_product_ids.append(str(p_id))

    view_counts = Counter(viewed_product_ids)
    top_viewed_ids = [pid for pid, _ in view_counts.most_common(10)]

    # Enrich with product details
    top_viewed = _enrich_product_ids(top_viewed_ids, products_col, view_counts)

    # Frequently purchased products
    order_query_conditions = []
    if c_oid:
        order_query_conditions.append({"user_id": c_oid})
        order_query_conditions.append({"user_id": str(c_oid)})
    if isinstance(customer_id, str):
        order_query_conditions.append({"user_id": customer_id})

    orders = list(orders_col.find({"$or": order_query_conditions})) if order_query_conditions else []

    purchased_product_ids = []
    for o in orders:
        items = o.get("items", [])
        if isinstance(items, list):
            for item in items:
                p_id = item.get("product_id")
                if p_id:
                    purchased_product_ids.append(str(p_id))

    purchase_counts = Counter(purchased_product_ids)
    top_purchased_ids = [pid for pid, _ in purchase_counts.most_common(10)]
    top_purchased = _enrich_product_ids(top_purchased_ids, products_col, purchase_counts)

    # Category interest (from views + purchases)
    all_product_ids = set(viewed_product_ids + purchased_product_ids)
    categories, brands = _get_category_brand_distribution(all_product_ids, products_col)

    return {
        "frequently_viewed": top_viewed,
        "frequently_purchased": top_purchased,
        "category_interest": categories,
        "brand_interest": brands,
        "total_products_viewed": len(set(viewed_product_ids)),
        "total_products_purchased": len(set(purchased_product_ids)),
    }


def _empty_affinity():
    return {
        "frequently_viewed": [],
        "frequently_purchased": [],
        "category_interest": [],
        "brand_interest": [],
        "total_products_viewed": 0,
        "total_products_purchased": 0,
    }


def _enrich_product_ids(product_ids, products_col, count_map):
    """Look up product details for a list of product IDs."""
    results = []
    for pid in product_ids:
        product = None
        try:
            if ObjectId.is_valid(pid):
                product = products_col.find_one({"_id": ObjectId(pid)})
        except Exception:
            pass

        if product:
            results.append({
                "product_id": pid,
                "name": product.get("name", "Unknown"),
                "category": product.get("category"),
                "brand": product.get("brand"),
                "price": product.get("price"),
                "count": count_map.get(pid, 0),
            })
        else:
            results.append({
                "product_id": pid,
                "name": "Unknown Product",
                "category": None,
                "brand": None,
                "price": None,
                "count": count_map.get(pid, 0),
            })

    return results


def _get_category_brand_distribution(product_ids, products_col):
    """Get category and brand frequency distribution from product IDs."""
    category_counter = Counter()
    brand_counter = Counter()

    for pid in product_ids:
        try:
            if ObjectId.is_valid(pid):
                product = products_col.find_one(
                    {"_id": ObjectId(pid)},
                    {"category": 1, "brand": 1}
                )
                if product:
                    cat = product.get("category")
                    brand = product.get("brand")
                    if cat:
                        category_counter[cat] += 1
                    if brand:
                        brand_counter[brand] += 1
        except Exception:
            continue

    categories = [
        {"category": cat, "count": count}
        for cat, count in category_counter.most_common(10)
    ]

    brands = [
        {"brand": brand, "count": count}
        for brand, count in brand_counter.most_common(10)
    ]

    return categories, brands
