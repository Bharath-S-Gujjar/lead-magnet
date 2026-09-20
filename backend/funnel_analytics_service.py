"""Funnel analytics service.

Computes e-commerce purchase funnel metrics from real event and session data.
All metrics are dynamically computed from MongoDB collections — no hardcoded values.

Funnel stages:
    Visitors → Product Views → Product Interactions → Cart Adds → Checkout Starts → Purchases
"""


def get_funnel_analytics(db):
    """Compute purchase funnel analytics from real event and session data.

    Args:
        db: PyMongo database object.

    Returns:
        dict: Funnel stages with counts, conversion rates, and drop-off rates.
    """
    if db is None:
        return {"stages": [], "summary": {}}

    sessions_col = db["sessions"]
    events_col = db["events"]
    orders_col = db["orders"]

    # Stage 1: Unique visitors (distinct anonymous_ids from sessions)
    try:
        visitor_ids = sessions_col.distinct("anonymous_id")
        visitors_count = len([v for v in visitor_ids if v])
        if visitors_count == 0:
            # Fallback to session count
            visitors_count = sessions_col.count_documents({})
    except Exception:
        visitors_count = sessions_col.count_documents({})

    # Stage 2: Product Views (unique users who viewed products)
    try:
        product_view_users = events_col.distinct(
            "anonymous_id",
            {"event_type": "product_view"}
        )
        # Also count by user_id for registered users
        product_view_registered = events_col.distinct(
            "user_id",
            {"event_type": "product_view", "user_id": {"$ne": None}}
        )
        product_view_count = len(set(
            [str(v) for v in product_view_users if v] +
            [str(v) for v in product_view_registered if v]
        ))
    except Exception:
        product_view_count = events_col.count_documents({"event_type": "product_view"})

    # Stage 3: Product Interactions (views + clicks + wishlist adds)
    interaction_types = {"product_view", "product_click", "add_to_cart", "wishlist_add"}
    try:
        interaction_users = events_col.distinct(
            "anonymous_id",
            {"event_type": {"$in": list(interaction_types)}}
        )
        interaction_registered = events_col.distinct(
            "user_id",
            {"event_type": {"$in": list(interaction_types)}, "user_id": {"$ne": None}}
        )
        interaction_count = len(set(
            [str(v) for v in interaction_users if v] +
            [str(v) for v in interaction_registered if v]
        ))
    except Exception:
        interaction_count = events_col.count_documents(
            {"event_type": {"$in": list(interaction_types)}}
        )

    # Stage 4: Cart Adds (unique users who added to cart)
    try:
        cart_users = events_col.distinct(
            "anonymous_id",
            {"event_type": "add_to_cart"}
        )
        cart_registered = events_col.distinct(
            "user_id",
            {"event_type": "add_to_cart", "user_id": {"$ne": None}}
        )
        cart_count = len(set(
            [str(v) for v in cart_users if v] +
            [str(v) for v in cart_registered if v]
        ))
    except Exception:
        cart_count = events_col.count_documents({"event_type": "add_to_cart"})

    # Stage 5: Checkout Starts
    try:
        checkout_users = events_col.distinct(
            "anonymous_id",
            {"event_type": "checkout_start"}
        )
        checkout_registered = events_col.distinct(
            "user_id",
            {"event_type": "checkout_start", "user_id": {"$ne": None}}
        )
        checkout_count = len(set(
            [str(v) for v in checkout_users if v] +
            [str(v) for v in checkout_registered if v]
        ))
    except Exception:
        checkout_count = events_col.count_documents({"event_type": "checkout_start"})

    # Stage 6: Purchases (from orders collection for accuracy)
    try:
        purchase_count = len(orders_col.distinct("user_id"))
        if purchase_count == 0:
            # Fallback to order_placed events
            purchase_users = events_col.distinct(
                "user_id",
                {"event_type": {"$in": ["purchase", "order_placed"]}, "user_id": {"$ne": None}}
            )
            purchase_count = len([v for v in purchase_users if v])
    except Exception:
        purchase_count = orders_col.count_documents({})

    # Build funnel stages
    raw_stages = [
        ("Visitors", visitors_count),
        ("Product Views", product_view_count),
        ("Product Interactions", interaction_count),
        ("Cart Adds", cart_count),
        ("Checkout Starts", checkout_count),
        ("Purchases", purchase_count),
    ]

    stages = []
    for i, (name, count) in enumerate(raw_stages):
        prev_count = raw_stages[i - 1][1] if i > 0 else count
        conversion_rate = round((count / prev_count * 100), 2) if prev_count > 0 else 0.0
        drop_off_rate = round(100 - conversion_rate, 2) if i > 0 else 0.0

        stages.append({
            "stage": name,
            "count": count,
            "conversion_rate": conversion_rate if i > 0 else 100.0,
            "drop_off_rate": drop_off_rate,
        })

    # Overall conversion
    overall_conversion = (
        round((purchase_count / visitors_count * 100), 2)
        if visitors_count > 0 else 0.0
    )

    return {
        "stages": stages,
        "summary": {
            "total_visitors": visitors_count,
            "total_purchases": purchase_count,
            "overall_conversion_rate": overall_conversion,
        },
    }
