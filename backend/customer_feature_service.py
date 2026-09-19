"""Customer feature store and behavioral feature aggregation service.

Transforms customer activity across sessions, behavior events, cart, wishlist,
and orders into a canonical customer-level feature representation stored in the
`customer_features` collection.

Rule: ONE REGISTERED CUSTOMER = ONE FEATURE RECORD.
"""

from datetime import datetime, timezone
from bson import ObjectId
from bson.errors import InvalidId


HIGH_INTENT_PAGE_KEYWORDS = ("pricing", "demo", "contact", "checkout")


def _to_object_id(val):
    if isinstance(val, ObjectId):
        return val
    if isinstance(val, str) and ObjectId.is_valid(val):
        return ObjectId(val)
    return None


def _to_utc_datetime(dt):
    if not dt:
        return None
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt)
        except ValueError:
            return None
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    return None


def _session_duration_seconds(session):
    duration = session.get("total_time_seconds")
    if isinstance(duration, (int, float)) and duration >= 0:
        return float(duration)

    started_at = _to_utc_datetime(session.get("started_at"))
    ended_at = _to_utc_datetime(session.get("ended_at") or session.get("last_active_at"))
    if started_at and ended_at and ended_at >= started_at:
        return float((ended_at - started_at).total_seconds())

    return 0.0


def ensure_customer_features_indexes(customer_features_collection):
    """Safely ensure unique index on customer_id in customer_features collection."""
    try:
        existing = {idx["name"] for idx in customer_features_collection.list_indexes()}
        if "customer_id_1" not in existing:
            customer_features_collection.create_index(
                [("customer_id", 1)],
                unique=True,
                name="customer_id_1",
                background=True
            )
    except Exception:
        # Ignore indexing error if caller provides a mock or lightweight collection
        pass


def _extract_product_id(event):
    entity = event.get("entity") or {}
    p_id = entity.get("id") or entity.get("product_id")
    if p_id:
        return str(p_id)
    return None


def aggregate_customer_features(customer_id, db):
    """Compute canonical customer features from persisted Mongo collections.

    Args:
        customer_id: ObjectId or string representing user_profiles._id,
                     or string for anonymous user.
        db: PyMongo Database object or dictionary-like container of collections.

    Returns:
        dict: A feature document for the customer.
    """
    profiles_col = db["user_profiles"]
    sessions_col = db["sessions"]
    events_col = db["events"]
    cart_col = db["cart"]
    wishlist_col = db["wishlist"]
    orders_col = db["orders"]
    products_col = db["products"]

    c_oid = _to_object_id(customer_id)
    profile = None

    if c_oid:
        profile = profiles_col.find_one({"_id": c_oid})
    if not profile and isinstance(customer_id, str):
        profile = profiles_col.find_one({"_id": customer_id}) or profiles_col.find_one({"user_id": customer_id})

    if profile:
        canonical_id = profile["_id"]
        identity_type = "registered"
        profile_email = profile.get("email")
        raw_anons = profile.get("anonymous_ids", [])
        if not isinstance(raw_anons, list):
            raw_anons = []
        anonymous_ids = list(set([str(a) for a in raw_anons if a]))
        if profile.get("visitor_id") and str(profile.get("visitor_id")) not in anonymous_ids:
            anonymous_ids.append(str(profile.get("visitor_id")))
    else:
        canonical_id = c_oid if c_oid else str(customer_id)
        identity_type = "anonymous"
        profile_email = None
        anonymous_ids = [str(customer_id)]

    # 1. Fetch Sessions
    session_query_conditions = []
    if identity_type == "registered":
        session_query_conditions.append({"user_id": canonical_id})
        if isinstance(canonical_id, ObjectId):
            session_query_conditions.append({"user_id": str(canonical_id)})

    if anonymous_ids:
        session_query_conditions.append({"anonymous_id": {"$in": anonymous_ids}})
        session_query_conditions.append({"visitor_id": {"$in": anonymous_ids}})

    session_query = {"$or": session_query_conditions} if session_query_conditions else {"_id": None}
    sessions = list(sessions_col.find(session_query))
    session_ids = [s["_id"] for s in sessions]

    # 2. Fetch Behavior Events
    event_query_conditions = []
    if identity_type == "registered":
        event_query_conditions.append({"user_id": canonical_id})
        if isinstance(canonical_id, ObjectId):
            event_query_conditions.append({"user_id": str(canonical_id)})

    if session_ids:
        event_query_conditions.append({"session_id": {"$in": session_ids}})

    if anonymous_ids:
        event_query_conditions.append({"anonymous_id": {"$in": anonymous_ids}})
        event_query_conditions.append({"visitor_id": {"$in": anonymous_ids}})

    event_query = {"$or": event_query_conditions} if event_query_conditions else {"_id": None}
    events = list(events_col.find(event_query))

    # 3. Fetch Cart Items
    cart_query_conditions = []
    if identity_type == "registered":
        cart_query_conditions.append({"user_id": canonical_id})
        if isinstance(canonical_id, ObjectId):
            cart_query_conditions.append({"user_id": str(canonical_id)})

    if anonymous_ids:
        cart_query_conditions.append({"anonymous_id": {"$in": anonymous_ids}})

    cart_query = {"$or": cart_query_conditions} if cart_query_conditions else {"_id": None}
    cart_items = list(cart_col.find(cart_query))

    # 4. Fetch Wishlist Items
    wishlist_query_conditions = []
    if identity_type == "registered":
        wishlist_query_conditions.append({"user_id": canonical_id})
        if isinstance(canonical_id, ObjectId):
            wishlist_query_conditions.append({"user_id": str(canonical_id)})

    if anonymous_ids:
        wishlist_query_conditions.append({"anonymous_id": {"$in": anonymous_ids}})

    wishlist_query = {"$or": wishlist_query_conditions} if wishlist_query_conditions else {"_id": None}
    wishlist_items = list(wishlist_col.find(wishlist_query))

    # 5. Fetch Orders
    order_query_conditions = []
    if identity_type == "registered":
        order_query_conditions.append({"user_id": canonical_id})
        if isinstance(canonical_id, ObjectId):
            order_query_conditions.append({"user_id": str(canonical_id)})

    if anonymous_ids:
        order_query_conditions.append({"anonymous_id": {"$in": anonymous_ids}})

    if profile_email:
        order_query_conditions.append({"customer_email": profile_email})

    order_query = {"$or": order_query_conditions} if order_query_conditions else {"_id": None}
    orders = list(orders_col.find(order_query))

    # --- AGGREGATION COMPUTATION ---

    # Session Metrics
    sessions_count = len(sessions)
    total_time_spent = sum(_session_duration_seconds(s) for s in sessions)
    average_session_duration = (total_time_spent / sessions_count) if sessions_count > 0 else 0.0

    # Event Metrics
    total_events = len(events)
    page_view_events = [e for e in events if e.get("event_type") == "page_view"]
    page_views_count = len(page_view_events) or sum(s.get("page_views", 0) for s in sessions if isinstance(s.get("page_views"), int))

    product_view_events = [e for e in events if e.get("event_type") == "product_view"]
    products_viewed = len(product_view_events)

    unique_viewed_ids = set()
    for e in product_view_events:
        pid = _extract_product_id(e)
        if pid:
            unique_viewed_ids.add(pid)
    unique_products_viewed = len(unique_viewed_ids)

    product_interaction_types = {"product_view", "product_click", "add_to_cart", "wishlist_add"}
    product_interactions = sum(1 for e in events if e.get("event_type") in product_interaction_types)

    search_count = sum(1 for e in events if e.get("event_type") in ("search", "filter_apply", "sort_apply"))
    form_submit_count = sum(1 for e in events if e.get("event_type") == "form_submit")

    high_intent_page_visits = 0
    for e in page_view_events:
        page = e.get("page")
        if isinstance(page, str) and any(kw in page.lower() for kw in HIGH_INTENT_PAGE_KEYWORDS):
            high_intent_page_visits += 1

    checkout_attempts = sum(1 for e in events if e.get("event_type") == "checkout_start")

    # Cart Aggregation
    cart_item_count = 0
    cart_value = 0.0
    for c_item in cart_items:
        qty = c_item.get("quantity", 1)
        if isinstance(qty, int) and qty > 0:
            cart_item_count += qty
            p_id = c_item.get("product_id")
            if isinstance(p_id, str) and ObjectId.is_valid(p_id):
                p_id = ObjectId(p_id)
            prod = products_col.find_one({"_id": p_id}) if p_id else None
            price = prod.get("price", 0) if prod and isinstance(prod.get("price"), (int, float)) else 0
            cart_value += price * qty

    # Wishlist Aggregation
    wishlist_item_count = len(wishlist_items)

    # Order Aggregation
    orders_count = len(orders)
    total_order_value = sum(float(o.get("total_amount", 0)) for o in orders if isinstance(o.get("total_amount"), (int, float)))
    average_order_value = (total_order_value / orders_count) if orders_count > 0 else 0.0

    # Timestamps & Recency
    all_timestamps = []

    if profile:
        p_created = _to_utc_datetime(profile.get("created_at"))
        p_updated = _to_utc_datetime(profile.get("updated_at"))
        p_active = _to_utc_datetime(profile.get("last_active_at"))
        for t in (p_created, p_updated, p_active):
            if t:
                all_timestamps.append(t)

    for s in sessions:
        s_start = _to_utc_datetime(s.get("started_at"))
        s_end = _to_utc_datetime(s.get("ended_at") or s.get("last_active_at"))
        for t in (s_start, s_end):
            if t:
                all_timestamps.append(t)

    for e in events:
        e_time = _to_utc_datetime(e.get("timestamp"))
        if e_time:
            all_timestamps.append(e_time)

    for o in orders:
        o_time = _to_utc_datetime(o.get("created_at") or o.get("updated_at"))
        if o_time:
            all_timestamps.append(o_time)

    now = datetime.now(timezone.utc)
    first_seen_at = min(all_timestamps) if all_timestamps else now
    last_active_at = max(all_timestamps) if all_timestamps else None

    days_since_last_activity = None
    if last_active_at:
        seconds_diff = (now - last_active_at).total_seconds()
        days_since_last_activity = max(round(seconds_diff / 86400.0, 2), 0.0)

    # Specific Action Recency
    prod_view_times = [_to_utc_datetime(e.get("timestamp")) for e in product_view_events if _to_utc_datetime(e.get("timestamp"))]
    last_product_view_at = max(prod_view_times) if prod_view_times else None

    cart_events = [e for e in events if e.get("event_type") in ("add_to_cart", "remove_from_cart")]
    cart_action_times = [_to_utc_datetime(e.get("timestamp")) for e in cart_events if _to_utc_datetime(e.get("timestamp"))]
    for c_item in cart_items:
        c_time = _to_utc_datetime(c_item.get("updated_at") or c_item.get("added_at"))
        if c_time:
            cart_action_times.append(c_time)
    last_cart_action_at = max(cart_action_times) if cart_action_times else None

    wishlist_events = [e for e in events if e.get("event_type") in ("wishlist_add", "wishlist_remove")]
    wishlist_action_times = [_to_utc_datetime(e.get("timestamp")) for e in wishlist_events if _to_utc_datetime(e.get("timestamp"))]
    for w_item in wishlist_items:
        w_time = _to_utc_datetime(w_item.get("created_at"))
        if w_time:
            wishlist_action_times.append(w_time)
    last_wishlist_action_at = max(wishlist_action_times) if wishlist_action_times else None

    checkout_events = [e for e in events if e.get("event_type") in ("checkout_start", "purchase", "order_placed")]
    checkout_action_times = [_to_utc_datetime(e.get("timestamp")) for e in checkout_events if _to_utc_datetime(e.get("timestamp"))]
    for o in orders:
        o_time = _to_utc_datetime(o.get("created_at"))
        if o_time:
            checkout_action_times.append(o_time)
    last_checkout_action_at = max(checkout_action_times) if checkout_action_times else None

    order_times = [_to_utc_datetime(o.get("created_at")) for o in orders if _to_utc_datetime(o.get("created_at"))]
    last_order_at = max(order_times) if order_times else None

    return {
        "customer_id": canonical_id,
        "identity_type": identity_type,
        "anonymous_ids": anonymous_ids,

        "sessions_count": sessions_count,
        "total_events": total_events,
        "total_time_spent": total_time_spent,
        "average_session_duration": average_session_duration,
        "page_views_count": page_views_count,
        "last_active_at": last_active_at,
        "days_since_last_activity": days_since_last_activity,

        "products_viewed": products_viewed,
        "unique_products_viewed": unique_products_viewed,
        "product_interactions": product_interactions,
        "search_count": search_count,
        "form_submit_count": form_submit_count,
        "high_intent_page_visits": high_intent_page_visits,

        "cart_item_count": cart_item_count,
        "cart_value": cart_value,
        "wishlist_item_count": wishlist_item_count,
        "checkout_attempts": checkout_attempts,

        "orders_count": orders_count,
        "total_order_value": total_order_value,
        "average_order_value": average_order_value,
        "last_order_at": last_order_at,

        "last_product_view_at": last_product_view_at,
        "last_cart_action_at": last_cart_action_at,
        "last_wishlist_action_at": last_wishlist_action_at,
        "last_checkout_action_at": last_checkout_action_at,

        "first_seen_at": first_seen_at,
        "updated_at": now,
    }


def upsert_customer_features(customer_id, db):
    """Aggregate customer features and upsert into customer_features collection."""
    if not customer_id:
        return None

    feature_doc = aggregate_customer_features(customer_id, db)
    features_col = db["customer_features"]

    ensure_customer_features_indexes(features_col)

    canonical_id = feature_doc["customer_id"]
    features_col.update_one(
        {"customer_id": canonical_id},
        {"$set": feature_doc},
        upsert=True
    )
    return feature_doc


def get_customer_features(customer_id, customer_features_collection):
    """Retrieve existing feature record by customer_id."""
    if not customer_id:
        return None

    c_oid = _to_object_id(customer_id)
    query_id = c_oid if c_oid else customer_id

    doc = customer_features_collection.find_one({"customer_id": query_id})
    if not doc and isinstance(customer_id, str):
        doc = customer_features_collection.find_one({"customer_id": customer_id})
    return doc
