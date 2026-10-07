"""Admin Intelligence Service layer.

Provides aggregate metrics, customer directory lead views, customer deep dives,
lead distributions, marketing activity, and admin notifications derived from
canonical MongoDB collections (user_profiles, customer_features, customer_lead_state,
marketing_automation_events, marketing_communications, admin_notifications, orders,
events, sessions, wishlist).

Key design rule: behavior_summary and behavior_distribution MUST be derived from the
same canonical events/sessions/wishlist data as the journey timeline. Never read from
the potentially-stale customer_features collection for display counts.
"""

import math
from collections import Counter
from datetime import datetime, timezone
from bson import ObjectId
from customer_feature_service import _to_object_id
from score_history_service import get_score_history
from model_explainability_service import explain_lead_score
from rfm_service import compute_rfm
from product_affinity_service import compute_product_affinity
from retention_service import compute_retention_signals


SENSITIVE_PROFILE_FIELDS = {
    "password", "password_hash", "hashed_password", "jwt", "token", "secret", "credentials"
}


def _sanitize_doc(doc):
    if not doc or not isinstance(doc, dict):
        return doc
    clean = {}
    for k, v in doc.items():
        if k in SENSITIVE_PROFILE_FIELDS:
            continue
        if isinstance(v, ObjectId):
            clean[k] = str(v)
        elif isinstance(v, datetime):
            clean[k] = v.isoformat()
        elif isinstance(v, bytes):
            continue
        elif isinstance(v, dict):
            clean[k] = _sanitize_doc(v)
        elif isinstance(v, list):
            clean[k] = [_sanitize_doc(item) if isinstance(item, dict) else (str(item) if isinstance(item, ObjectId) else item) for item in v]
        else:
            clean[k] = v
    return clean


def get_intelligence_overview(db):
    """Aggregate real-time metrics across canonical collections.

    Returns:
        dict: Overview metrics including customer counts, lead counts, and marketing dispatches.
    """
    profiles_col = db["user_profiles"]
    lead_state_col = db["customer_lead_state"]
    events_col = db["marketing_automation_events"]
    comms_col = db["marketing_communications"]

    now = datetime.now(timezone.utc)
    today_prefix = now.strftime("%Y-%m-%d")

    # Customer counts
    total_customers = profiles_col.count_documents({"role": {"$ne": "admin"}})
    if total_customers == 0:
        # Fallback if roles are not populated
        total_customers = profiles_col.count_documents({})

    # Active today: last_active_at matches today's date prefix or within last 24 hours
    active_today = profiles_col.count_documents({
        "last_active_at": {"$regex": f"^{today_prefix}"}
    })

    # New customers created today
    new_today_count = profiles_col.count_documents({
        "created_at": {"$regex": f"^{today_prefix}"}
    })
    # If no documents have string created_at with today's date, check if any profile has created_at field
    has_created_at = profiles_col.count_documents({"created_at": {"$exists": True}}) > 0
    new_today = new_today_count if has_created_at else None

    # Lead state counts
    total_qualified = lead_state_col.count_documents({"qualification_status": "qualified"})
    hot_leads = lead_state_col.count_documents({"qualification_status": "qualified", "lead_segment": "Hot"})
    warm_leads = lead_state_col.count_documents({"qualification_status": "qualified", "lead_segment": "Warm"})
    cold_leads = lead_state_col.count_documents({"qualification_status": "qualified", "lead_segment": "Cold"})

    newly_qualified_today = lead_state_col.count_documents({
        "qualification_status": "qualified",
        "$or": [
            {"is_newly_qualified": True},
            {"first_qualified_at": {"$regex": f"^{today_prefix}"}}
        ]
    })

    # Marketing communications counts
    automation_events_count = events_col.count_documents({})
    comms_sent = comms_col.count_documents({"status": "sent"})
    comms_failed = comms_col.count_documents({"status": "failed"})
    comms_skipped = comms_col.count_documents({"status": "skipped"})

    return {
        "customers": {
            "total": total_customers,
            "active_today": active_today,
            "new_today": new_today
        },
        "leads": {
            "total_qualified": total_qualified,
            "hot": hot_leads,
            "warm": warm_leads,
            "cold": cold_leads,
            "newly_qualified_today": newly_qualified_today
        },
        "marketing": {
            "automation_events": automation_events_count,
            "communications_sent": comms_sent,
            "communications_failed": comms_failed,
            "communications_skipped": comms_skipped
        },
        "updated_at": now.isoformat()
    }


def get_qualified_leads_list(db, qualification_status="qualified", segment="all", sort_by="lead_score", sort_order="desc", page=1, limit=25):
    """Retrieve paginated, customer-level lead directory.

    Returns:
        dict: Paginated lead items with customer details and communication status.
    """
    lead_state_col = db["customer_lead_state"]
    profiles_col = db["user_profiles"]
    comms_col = db["marketing_communications"]

    page = max(1, int(page))
    limit = max(1, min(100, int(limit)))

    query = {}
    if qualification_status and qualification_status != "all":
        query["qualification_status"] = qualification_status

    if segment and segment != "all":
        query["lead_segment"] = segment

    # Sorting
    valid_sort_fields = {"lead_score", "lead_probability", "last_scored_at", "first_qualified_at", "created_at"}
    field = sort_by if sort_by in valid_sort_fields else "lead_score"
    direction = -1 if str(sort_order).lower() == "desc" else 1

    total = lead_state_col.count_documents(query)
    pages = math.ceil(total / limit) if total > 0 else 0
    skip = (page - 1) * limit

    lead_cursor = lead_state_col.find(query).sort(field, direction).skip(skip).limit(limit)

    items = []
    for lead in lead_cursor:
        c_id = lead.get("customer_id")
        c_oid = _to_object_id(c_id)

        profile = None
        if c_oid:
            profile = profiles_col.find_one({"_id": c_oid})
        if not profile and isinstance(c_id, (str, ObjectId)):
            profile = profiles_col.find_one({"_id": c_id})

        name = "Anonymous Customer"
        email = None
        if profile:
            name = profile.get("full_name") or profile.get("username") or name
            email = profile.get("email")

        # Last communication attempt for this customer
        comm_query = {"customer_id": c_oid} if c_oid else {"customer_id": c_id}
        last_comm = comms_col.find_one(comm_query, sort=[("created_at", -1)])

        comm_status = None
        if last_comm:
            comm_status = {
                "last_channel": last_comm.get("channel"),
                "last_status": last_comm.get("status"),
                "last_sent_at": last_comm.get("sent_at") or last_comm.get("created_at")
            }

        items.append({
            "customer_id": str(c_id),
            "name": name,
            "email": email,
            "lead_score": lead.get("lead_score"),
            "lead_probability": lead.get("lead_probability"),
            "lead_segment": lead.get("lead_segment"),
            "qualification_status": lead.get("qualification_status"),
            "first_qualified_at": lead.get("first_qualified_at"),
            "last_scored_at": lead.get("last_scored_at"),
            "communication_status": comm_status
        })

    return {
        "items": items,
        "page": page,
        "limit": limit,
        "total": total,
        "pages": pages
    }


# ---------------------------------------------------------------------------
# Canonical behavior summary — SINGLE SOURCE OF TRUTH for all counts
# ---------------------------------------------------------------------------

def _build_customer_id_conditions(customer_id):
    """Return a list of identity conditions usable in a MongoDB $or query."""
    c_oid = _to_object_id(customer_id)
    conds = []
    if c_oid:
        conds.append({"user_id": c_oid})
        conds.append({"user_id": str(c_oid)})
    if isinstance(customer_id, str):
        conds.append({"user_id": customer_id})
        conds.append({"anonymous_id": customer_id})
    return conds


def _compute_behavior_summary(customer_id, db, events_list=None, sessions_list=None):
    """Compute canonical behavior summary from live events + sessions + wishlist.

    This function is the SINGLE source of truth for all behavioral counts.
    It must agree with _build_journey_timeline which reads from the same events
    collection. The stale customer_features collection is NOT used for display counts.

    Args:
        customer_id: ObjectId or string
        db: PyMongo database
        events_list: pre-fetched events list (optional, avoids re-querying)
        sessions_list: pre-fetched sessions list (optional)

    Returns:
        dict with behavior_summary and behavior_distribution
    """
    c_oid = _to_object_id(customer_id)
    id_conds = _build_customer_id_conditions(customer_id)
    if not id_conds:
        return {"behavior_summary": {}, "behavior_distribution": {}}

    # Resolve ALL anonymous_ids from the user's profile so pre-login sessions
    # are included in the session count (customer_feature_service also does this).
    all_anon_ids = []
    if c_oid:
        profile_doc = db["user_profiles"].find_one({"_id": c_oid}, {"anonymous_ids": 1, "visitor_id": 1})
        if profile_doc:
            raw_anons = profile_doc.get("anonymous_ids") or []
            all_anon_ids = [str(a) for a in raw_anons if a]
            vid = profile_doc.get("visitor_id")
            if vid and str(vid) not in all_anon_ids:
                all_anon_ids.append(str(vid))

    # Build full set of session query conditions
    session_id_conds = list(id_conds)
    for aid in all_anon_ids:
        session_id_conds.append({"anonymous_id": aid})
        session_id_conds.append({"visitor_id": aid})

    # Fetch sessions if not provided
    if sessions_list is None:
        seen_sess_ids = set()
        raw_sessions = list(db["sessions"].find({"$or": session_id_conds}))
        sessions_list = []
        for s in raw_sessions:
            if s["_id"] not in seen_sess_ids:
                seen_sess_ids.add(s["_id"])
                sessions_list.append(s)

    session_ids = [s["_id"] for s in sessions_list]

    # Fetch events if not provided — include session-linked events + anon events
    if events_list is None:
        event_id_conds = list(id_conds)  # copy
        # Include events linked to any of the anon IDs
        for aid in all_anon_ids:
            event_id_conds.append({"anonymous_id": aid})
            event_id_conds.append({"visitor_id": aid})
        if session_ids:
            event_id_conds.append({"session_id": {"$in": session_ids}})
        # De-duplicate events by _id
        seen_event_ids = set()
        events_list = []
        for e in db["events"].find({"$or": event_id_conds}):
            if e["_id"] not in seen_event_ids:
                seen_event_ids.add(e["_id"])
                events_list.append(e)

    # Count event types
    type_counter = Counter(e.get("event_type") for e in events_list if e.get("event_type"))

    page_views_count = type_counter.get("page_view", 0)
    product_views_count = type_counter.get("product_view", 0) + type_counter.get("product_click", 0)
    cart_adds_count = type_counter.get("add_to_cart", 0)
    wishlist_adds_count = type_counter.get("wishlist_add", 0)
    checkout_starts_count = type_counter.get("checkout_start", 0)
    searches_count = type_counter.get("search", 0) + type_counter.get("filter_apply", 0)

    # Real orders from orders collection (ground truth for orders_count)
    order_id_conds = []
    if c_oid:
        order_id_conds.append({"user_id": c_oid})
        order_id_conds.append({"user_id": str(c_oid)})
    if isinstance(customer_id, str):
        order_id_conds.append({"user_id": customer_id})
    orders_count = db["orders"].count_documents({"$or": order_id_conds}) if order_id_conds else 0

    # Wishlist items (current, from wishlist collection)
    wl_id_conds = []
    if c_oid:
        wl_id_conds.append({"user_id": c_oid})
        wl_id_conds.append({"user_id": str(c_oid)})
    wishlist_current_count = db["wishlist"].count_documents({"$or": wl_id_conds}) if wl_id_conds else 0

    # Cart items (current, from cart collection)
    cart_id_conds = []
    if c_oid:
        cart_id_conds.append({"user_id": c_oid})
        cart_id_conds.append({"user_id": str(c_oid)})
    if isinstance(customer_id, str):
        cart_id_conds.append({"user_id": customer_id})
    cart_docs = list(db["cart"].find({"$or": cart_id_conds})) if cart_id_conds else []
    cart_current_count = len(cart_docs)
    cart_total_quantity = sum(int(doc.get("quantity", 1)) for doc in cart_docs)

    total_events = len(events_list)
    sessions_count = len(sessions_list)

    behavior_summary = {
        "sessions_count": sessions_count,
        "page_views_count": page_views_count,
        "product_views_count": product_views_count,
        "cart_adds_count": cart_adds_count,
        "cart_current_count": cart_current_count,
        "cart_total_quantity": cart_total_quantity,
        "wishlist_adds_count": wishlist_adds_count,
        "wishlist_current_count": wishlist_current_count,
        "checkout_starts_count": checkout_starts_count,
        "searches_count": searches_count,
        "orders_count": orders_count,
        "total_events": total_events,
    }

    # Distribution for bar chart — same data, different shape.
    # Consolidate synonyms so the chart doesn't double-count:
    #   order_placed + order -> order  (both mean an order event)
    #   product_view + product_click -> product_view
    SYNONYM_MAP = {
        "order_placed": "order",
        "product_click": "product_view",
        "add_to_wishlist": "wishlist_add",
        "wishlist_remove": "wishlist_remove",
        "remove_from_cart": "cart_remove",
        "filter_apply": "search",
    }
    merged_dist: dict = {}
    for k, v in type_counter.items():
        if v <= 0:
            continue
        canonical_key = SYNONYM_MAP.get(k, k)
        merged_dist[canonical_key] = merged_dist.get(canonical_key, 0) + v
    # Ensure orders are in distribution from orders collection (ground truth)
    if orders_count > 0:
        merged_dist["order"] = orders_count

    return {
        "behavior_summary": behavior_summary,
        "behavior_distribution": merged_dist,
    }


# ---------------------------------------------------------------------------
# Cart resolution with product lookup
# ---------------------------------------------------------------------------

def _resolve_cart(customer_id, db):
    """Resolve the customer's current cart with real product details.

    Strategy:
    1. Try the `cart` collection (persistent cart).
    2. If empty, reconstruct a best-effort cart from add_to_cart events minus
       remove_from_cart events, looking up products for each product_id.

    Returns:
        list[dict]: Cart items with resolved product details.
    """
    c_oid = _to_object_id(customer_id)
    products_col = db["products"]

    def _lookup_product(product_id_raw):
        """Look up product by _id (ObjectId or string) or product_id field."""
        if not product_id_raw:
            return None
        p_oid = None
        try:
            p_oid = ObjectId(str(product_id_raw)) if not isinstance(product_id_raw, ObjectId) else product_id_raw
        except Exception:
            pass
        prod = None
        if p_oid:
            prod = products_col.find_one({"_id": p_oid})
        if not prod:
            prod = products_col.find_one({"product_id": str(product_id_raw)})
        return prod

    def _fmt_item(product_id_raw, qty, prod, event_entity=None):
        """Format a cart item, using event entity as fallback for null-price products.
        
        If no legitimate price exists in catalog or event, price and subtotal are None
        (unknown / unavailable), never fabricated as 0.
        """
        entity = event_entity or {}
        price = None
        if prod:
            raw_price = prod.get("price") if prod.get("price") is not None else prod.get("price_inr")
            if raw_price is None and entity.get("price") is not None:
                raw_price = entity.get("price")
            try:
                if raw_price is not None and float(raw_price) > 0:
                    price = float(raw_price)
            except (ValueError, TypeError):
                price = None

            subtotal = round(price * qty, 2) if price is not None else None

            return {
                "product_id": str(product_id_raw),
                "name": prod.get("name") or entity.get("name") or "Product unavailable",
                "brand": prod.get("brand") or "",
                "category": prod.get("category") or "",
                "gender": prod.get("gender") or "",
                "price": price,
                "quantity": qty,
                "subtotal": subtotal,
                "image": prod.get("image") or (prod.get("images", [None])[0] if isinstance(prod.get("images"), list) else None),
            }
        else:
            # Product not in catalog at all
            fallback_name = entity.get("name") or "Product unavailable"
            raw_price = entity.get("price")
            try:
                if raw_price is not None and float(raw_price) > 0:
                    price = float(raw_price)
            except (ValueError, TypeError):
                price = None

            subtotal = round(price * qty, 2) if price is not None else None

            return {
                "product_id": str(product_id_raw),
                "name": fallback_name,
                "brand": entity.get("brand") or "",
                "category": entity.get("category") or "",
                "gender": "",
                "price": price,
                "quantity": qty,
                "subtotal": subtotal,
                "image": None,
            }

    # --- Strategy 1: cart collection ---
    cart_col = db["cart"]
    id_conds = []
    if c_oid:
        id_conds.append({"user_id": c_oid})
        id_conds.append({"user_id": str(c_oid)})
    if isinstance(customer_id, str):
        id_conds.append({"user_id": customer_id})
    cart_docs = list(cart_col.find({"$or": id_conds})) if id_conds else []

    result = []
    for doc in cart_docs:
        p_id = doc.get("product_id")
        qty = int(doc.get("quantity", 1))
        prod = _lookup_product(p_id)
        result.append(_fmt_item(p_id, qty, prod))
    return result


def _resolve_wishlist(customer_id, db):
    """Resolve the customer's current wishlist with real product details.

    Reads strictly from the canonical `wishlist` collection.

    Returns:
        list[dict]: Active wishlist items with resolved product details.
    """
    c_oid = _to_object_id(customer_id)
    products_col = db["products"]
    wishlist_col = db["wishlist"]

    id_conds = []
    if c_oid:
        id_conds.append({"user_id": c_oid})
        id_conds.append({"user_id": str(c_oid)})
    if isinstance(customer_id, str):
        id_conds.append({"user_id": customer_id})
    wishlist_docs = list(wishlist_col.find({"$or": id_conds})) if id_conds else []

    result = []
    for doc in wishlist_docs:
        p_id = doc.get("product_id")
        p_oid = None
        try:
            p_oid = ObjectId(str(p_id)) if not isinstance(p_id, ObjectId) else p_id
        except Exception:
            pass
        prod = None
        if p_oid:
            prod = products_col.find_one({"_id": p_oid})
        if not prod:
            prod = products_col.find_one({"product_id": str(p_id)})

        price = None
        if prod:
            raw_price = prod.get("price") if prod.get("price") is not None else prod.get("price_inr")
            try:
                if raw_price is not None and float(raw_price) > 0:
                    price = float(raw_price)
            except (ValueError, TypeError):
                price = None

        added_at = doc.get("created_at")
        result.append({
            "wishlist_item_id": str(doc.get("_id", "")),
            "product_id": str(p_id),
            "name": prod.get("name") if prod else "Product unavailable",
            "brand": prod.get("brand") or "" if prod else "",
            "category": prod.get("category") or "" if prod else "",
            "gender": prod.get("gender") or "" if prod else "",
            "price": price,
            "image": prod.get("image") or (prod.get("images", [None])[0] if isinstance(prod.get("images"), list) else None) if prod else None,
            "added_at": added_at.isoformat() if isinstance(added_at, datetime) else added_at,
        })
    return result


# ---------------------------------------------------------------------------
# Customer intelligence detail
# ---------------------------------------------------------------------------

def get_customer_intelligence_detail(db, customer_id):
    """Retrieve full unified intelligence view for a single customer.

    Returns:
        dict or None: Sanitized customer profile, behavioral features, lead state, orders, and marketing dispatches.
    """
    if not customer_id:
        return None

    c_oid = _to_object_id(customer_id)
    query_id = c_oid if c_oid else customer_id

    profiles_col = db["user_profiles"]
    features_col = db["customer_features"]
    lead_state_col = db["customer_lead_state"]
    orders_col = db["orders"]
    events_col = db["marketing_automation_events"]
    comms_col = db["marketing_communications"]

    profile = profiles_col.find_one({"_id": query_id})
    if not profile and isinstance(customer_id, str):
        profile = profiles_col.find_one({"_id": customer_id}) or profiles_col.find_one({"user_id": customer_id})

    if not profile:
        return None

    actual_c_id = profile["_id"]

    features = features_col.find_one({"customer_id": actual_c_id}) or features_col.find_one({"customer_id": str(actual_c_id)})
    lead_state = lead_state_col.find_one({"customer_id": actual_c_id}) or lead_state_col.find_one({"customer_id": str(actual_c_id)})

    # Recent orders
    orders_query = {"$or": [{"user_id": actual_c_id}, {"user_id": str(actual_c_id)}]}
    if profile.get("email"):
        orders_query["$or"].append({"customer_email": profile["email"]})
    recent_orders = list(orders_col.find(orders_query).sort("created_at", -1).limit(10))

    # Recent marketing automation events & communications
    auto_events = list(events_col.find({"$or": [{"customer_id": actual_c_id}, {"customer_id": str(actual_c_id)}]}).sort("created_at", -1).limit(10))
    comms = list(comms_col.find({"$or": [{"customer_id": actual_c_id}, {"customer_id": str(actual_c_id)}]}).sort("created_at", -1).limit(10))

    # --- Customer 360 Expansion ---

    # Score history
    score_history = []
    try:
        score_history = get_score_history(actual_c_id, db, limit=30)
    except Exception:
        pass

    # RFM intelligence
    rfm = {}
    try:
        rfm = compute_rfm(actual_c_id, db)
    except Exception:
        pass

    # Product affinity
    product_affinity = {}
    try:
        product_affinity = compute_product_affinity(actual_c_id, db)
    except Exception:
        pass

    # Lead explanation
    lead_explanation = {}
    try:
        if features:
            lead_explanation = explain_lead_score(features)
    except Exception:
        pass

    # Retention signals
    retention = {}
    try:
        retention = compute_retention_signals(actual_c_id, db)
    except Exception:
        pass

    # Customer journey timeline and behavior summary MUST use same events data
    journey_timeline = _build_journey_timeline(actual_c_id, db)

    # Canonical behavior summary (SINGLE SOURCE OF TRUTH)
    behavior_data = {}
    try:
        behavior_data = _compute_behavior_summary(actual_c_id, db)
    except Exception:
        pass

    # Cart — resolved strictly from cart collection
    cart = []
    try:
        cart = _resolve_cart(actual_c_id, db)
    except Exception:
        pass

    # Wishlist — resolved strictly from wishlist collection
    wishlist = []
    try:
        wishlist = _resolve_wishlist(actual_c_id, db)
    except Exception:
        pass

    return {
        "customer": _sanitize_doc(profile),
        "behavior": _sanitize_doc(features) or {},
        "behavior_summary": behavior_data.get("behavior_summary", {}),
        "behavior_distribution": behavior_data.get("behavior_distribution", {}),
        "lead": _sanitize_doc(lead_state) or {},
        "orders": [_sanitize_doc(o) for o in recent_orders],
        "cart": cart,
        "wishlist": wishlist,
        "marketing": {
            "automation_events": [_sanitize_doc(e) for e in auto_events],
            "communications": [_sanitize_doc(c) for c in comms]
        },
        "score_history": score_history,
        "rfm": rfm,
        "product_affinity": product_affinity,
        "lead_explanation": lead_explanation,
        "retention": retention,
        "journey_timeline": journey_timeline,
    }


def get_lead_distribution(db):
    """Retrieve customer-level lead distribution by segment and qualification status.

    Returns:
        dict: Total count, segment breakdown (hot/warm/cold), and qualification breakdown.
    """
    lead_state_col = db["customer_lead_state"]

    total = lead_state_col.count_documents({})

    hot_count = lead_state_col.count_documents({"lead_segment": "Hot"})
    warm_count = lead_state_col.count_documents({"lead_segment": "Warm"})
    cold_count = lead_state_col.count_documents({"lead_segment": "Cold"})

    qualified_count = lead_state_col.count_documents({"qualification_status": "qualified"})
    not_qualified_count = lead_state_col.count_documents({"qualification_status": "not_qualified"})

    return {
        "total": total,
        "segments": {
            "hot": hot_count,
            "warm": warm_count,
            "cold": cold_count
        },
        "qualification": {
            "qualified": qualified_count,
            "not_qualified": not_qualified_count
        }
    }


def get_recent_leads(db, page=1, limit=10):
    """Retrieve customers who recently transitioned to qualified lead status.

    Returns:
        dict: Paginated list of recent qualified leads.
    """
    lead_state_col = db["customer_lead_state"]
    profiles_col = db["user_profiles"]

    page = max(1, int(page))
    limit = max(1, min(100, int(limit)))

    query = {
        "qualification_status": "qualified",
        "$or": [
            {"qualification_transition": "not_qualified_to_qualified"},
            {"is_newly_qualified": True},
            {"first_qualified_at": {"$ne": None}}
        ]
    }

    total = lead_state_col.count_documents(query)
    pages = math.ceil(total / limit) if total > 0 else 0
    skip = (page - 1) * limit

    cursor = lead_state_col.find(query).sort("first_qualified_at", -1).skip(skip).limit(limit)

    items = []
    for lead in cursor:
        c_id = lead.get("customer_id")
        c_oid = _to_object_id(c_id)

        profile = profiles_col.find_one({"_id": c_oid}) if c_oid else None
        if not profile and isinstance(c_id, (str, ObjectId)):
            profile = profiles_col.find_one({"_id": c_id})

        name = "Anonymous Customer"
        email = None
        if profile:
            name = profile.get("full_name") or profile.get("username") or name
            email = profile.get("email")

        items.append({
            "customer_id": str(c_id),
            "name": name,
            "email": email,
            "lead_score": lead.get("lead_score"),
            "lead_probability": lead.get("lead_probability"),
            "lead_segment": lead.get("lead_segment"),
            "qualified_at": lead.get("first_qualified_at") or lead.get("updated_at")
        })

    return {
        "items": items,
        "page": page,
        "limit": limit,
        "total": total,
        "pages": pages
    }


def get_marketing_activity(db, page=1, limit=25):
    """Retrieve recent marketing dispatches and automation events.

    Returns:
        dict: Paginated list of marketing activity records.
    """
    comms_col = db["marketing_communications"]
    profiles_col = db["user_profiles"]

    page = max(1, int(page))
    limit = max(1, min(100, int(limit)))

    total = comms_col.count_documents({})
    pages = math.ceil(total / limit) if total > 0 else 0
    skip = (page - 1) * limit

    cursor = comms_col.find({}).sort("created_at", -1).skip(skip).limit(limit)

    items = []
    for comm in cursor:
        c_id = comm.get("customer_id")
        c_oid = _to_object_id(c_id)

        profile = profiles_col.find_one({"_id": c_oid}) if c_oid else None
        if not profile and isinstance(c_id, (str, ObjectId)):
            profile = profiles_col.find_one({"_id": c_id})

        items.append({
            "customer_id": str(c_id),
            "customer_name": profile.get("full_name") if profile else None,
            "recipient": comm.get("recipient"),
            "event_type": "lead_qualified",
            "channel": comm.get("channel"),
            "status": comm.get("status"),
            "provider": comm.get("provider"),
            "created_at": comm.get("created_at"),
            "sent_at": comm.get("sent_at")
        })

    return {
        "items": items,
        "page": page,
        "limit": limit,
        "total": total,
        "pages": pages
    }


def get_admin_notifications_list(db, read_status=None, page=1, limit=25):
    """Retrieve paginated internal admin notifications from canonical admin_notifications collection.

    If admin_notifications is empty, returns empty list with unread_count 0.
    Does NOT manufacture fake or synthetic notifications.

    Returns:
        dict: Paginated list of real admin notification documents.
    """
    notif_col = db["admin_notifications"]

    page = max(1, int(page))
    limit = max(1, min(100, int(limit)))

    unread_count = notif_col.count_documents({"read": False})

    query = {}
    if read_status is not None:
        query["read"] = bool(read_status)

    total = notif_col.count_documents(query)
    pages = math.ceil(total / limit) if total > 0 else 0
    skip = (page - 1) * limit
    cursor = notif_col.find(query).sort("created_at", -1).skip(skip).limit(limit)
    items = [_sanitize_doc(n) for n in cursor]
    for it in items:
        if "_id" in it and "id" not in it:
            it["id"] = it["_id"]
        if "message" in it and "body" not in it:
            it["body"] = it["message"]
        if "body" in it and "message" not in it:
            it["message"] = it["body"]

    return {"items": items, "page": page, "limit": limit, "total": total, "pages": pages, "unread_count": unread_count}


def create_admin_notification(db, notif_type, message, title=None, customer_id=None, metadata=None, socketio=None):
    """Create a new admin notification, persist to admin_notifications, and emit Socket.IO.

    Args:
        db: PyMongo database object.
        notif_type (str): Notification type ('lead_qualified', 'order_placed', 'new_customer', etc.).
        message (str): Notification description text.
        title (str, optional): Short title for the notification.
        customer_id (str or ObjectId, optional): Related customer ID.
        metadata (dict, optional): Additional contextual metadata.
        socketio (SocketIO, optional): Flask-SocketIO instance for real-time delivery.

    Returns:
        dict: Sanitized notification document.
    """
    notif_col = db["admin_notifications"]

    DEFAULT_TITLES = {
        "lead_qualified": "New Hot Lead",
        "order_placed": "New Order Placed",
        "new_customer": "New Customer",
        "cart_abandoned": "Cart Abandoned",
        "churn_risk": "High Churn Risk",
    }
    notif_title = title or DEFAULT_TITLES.get(notif_type, "Admin Notification")

    now = datetime.now(timezone.utc)
    c_id_str = str(customer_id) if customer_id else None

    doc = {
        "type": notif_type,
        "title": notif_title,
        "message": message,
        "customer_id": c_id_str,
        "metadata": metadata or {},
        "read": False,
        "created_at": now,
    }

    res = notif_col.insert_one(doc)
    doc["_id"] = res.inserted_id

    sanitized = _sanitize_doc(doc)
    if "_id" in sanitized and "id" not in sanitized:
        sanitized["id"] = sanitized["_id"]

    unread_count = notif_col.count_documents({"read": False})
    sanitized["unread_count"] = unread_count

    if socketio:
        try:
            socketio.emit("admin_notification", sanitized)
        except Exception:
            pass

    return sanitized


def mark_notification_read(db, notification_id):
    """Mark a single notification as read by id.

    Args:
        db: PyMongo database object.
        notification_id: string or ObjectId.

    Returns:
        dict: Result with updated notification, unread_count, and success flag.
    """
    notif_col = db["admin_notifications"]
    n_oid = _to_object_id(notification_id)
    now = datetime.now(timezone.utc)

    id_queries = [{"_id": notification_id}, {"id": str(notification_id)}]
    if n_oid:
        id_queries.append({"_id": n_oid})

    updated = notif_col.find_one_and_update(
        {"$or": id_queries},
        {"$set": {"read": True, "read_at": now}},
        return_document=True,
    )

    unread_count = notif_col.count_documents({"read": False})

    if updated:
        sanitized = _sanitize_doc(updated)
        if "_id" in sanitized and "id" not in sanitized:
            sanitized["id"] = sanitized["_id"]
        if "message" in sanitized and "body" not in sanitized:
            sanitized["body"] = sanitized["message"]
        if "body" in sanitized and "message" not in sanitized:
            sanitized["message"] = sanitized["body"]
        return {"notification": sanitized, "unread_count": unread_count, "success": True}

    return {"notification": {"id": str(notification_id), "read": True}, "unread_count": unread_count, "success": True}


def mark_all_notifications_read(db):
    """Mark all unread admin notifications as read idempotently.

    Args:
        db: PyMongo database object.

    Returns:
        dict: modified_count, unread_count (0), and success boolean.
    """
    notif_col = db["admin_notifications"]
    now = datetime.now(timezone.utc)

    result = notif_col.update_many(
        {"read": False},
        {"$set": {"read": True, "read_at": now}}
    )

    return {
        "success": True,
        "modified_count": result.modified_count,
        "unread_count": 0,
    }


def _build_journey_timeline(customer_id, db, limit=30):
    """Build a chronological customer journey timeline from events, orders, and marketing comms.

    Returns:
        list[dict]: Timeline entries sorted by timestamp, most recent first.
    """
    timeline = []

    c_oid = _to_object_id(customer_id)
    id_conditions = []
    if c_oid:
        id_conditions.append({"user_id": c_oid})
        id_conditions.append({"user_id": str(c_oid)})
    if isinstance(customer_id, str):
        id_conditions.append({"anonymous_id": customer_id})

    if not id_conditions:
        return []

    base_query = {"$or": id_conditions}

    known_order_ids = set()
    known_order_timestamps = set()

    # 1. Orders from orders collection (canonical order records)
    try:
        order_query = {"$or": []}
        if c_oid:
            order_query["$or"].append({"user_id": c_oid})
            order_query["$or"].append({"user_id": str(c_oid)})
        if isinstance(customer_id, str):
            order_query["$or"].append({"user_id": customer_id})

        if order_query["$or"]:
            orders = list(db["orders"].find(order_query).sort("created_at", -1).limit(10))
            for o in orders:
                oid_str = str(o.get("_id", ""))
                known_order_ids.add(oid_str)
                ts = o.get("created_at")
                ts_str = ts.isoformat() if isinstance(ts, datetime) else (str(ts) if ts else None)
                if ts_str:
                    known_order_timestamps.add(ts_str)
                    known_order_timestamps.add(ts_str[:19])
                timeline.append({
                    "type": "order",
                    "order_id": oid_str,
                    "total_amount": o.get("total_amount"),
                    "timestamp": ts_str,
                })
    except Exception:
        pass

    # 2. Behavior events — deduplicate order_placed / order events that represent real orders
    try:
        events = list(db["events"].find(base_query).sort("timestamp", -1).limit(limit))
        for e in events:
            evt_type = e.get("event_type")
            ts = e.get("timestamp")
            ts_str = ts.isoformat() if isinstance(ts, datetime) else (str(ts) if ts else None)

            if evt_type in ("order_placed", "order", "purchase"):
                entity = e.get("entity") or {}
                meta = e.get("metadata") or {}
                e_order_id = str(entity.get("id") or meta.get("order_id") or "")

                # If this order is already recorded via orders collection, skip duplicate
                is_duplicate = False
                if e_order_id and e_order_id in known_order_ids:
                    is_duplicate = True
                elif ts_str and (ts_str in known_order_timestamps or ts_str[:19] in known_order_timestamps):
                    is_duplicate = True

                if is_duplicate:
                    continue

                # If no orders doc was found, include as canonical order entry
                canonical_oid = e_order_id or str(e.get("_id", ""))
                known_order_ids.add(canonical_oid)
                if ts_str:
                    known_order_timestamps.add(ts_str)
                    known_order_timestamps.add(ts_str[:19])
                timeline.append({
                    "type": "order",
                    "order_id": canonical_oid,
                    "total_amount": meta.get("total_amount"),
                    "timestamp": ts_str,
                })
            else:
                timeline.append({
                    "type": "event",
                    "event_type": evt_type,
                    "page": e.get("page"),
                    "timestamp": ts_str,
                })
    except Exception:
        pass

    # Marketing comms
    try:
        comm_query = {"$or": []}
        if c_oid:
            comm_query["$or"].append({"customer_id": c_oid})
            comm_query["$or"].append({"customer_id": str(c_oid)})
        if isinstance(customer_id, str):
            comm_query["$or"].append({"customer_id": customer_id})

        if comm_query["$or"]:
            comms = list(db["marketing_communications"].find(comm_query).sort("created_at", -1).limit(10))
            for c in comms:
                ts = c.get("sent_at") or c.get("created_at")
                timeline.append({
                    "type": "marketing",
                    "channel": c.get("channel"),
                    "status": c.get("status"),
                    "timestamp": ts if isinstance(ts, str) else str(ts) if ts else None,
                })
    except Exception:
        pass

    # Sort by timestamp descending
    def _sort_key(entry):
        ts = entry.get("timestamp", "")
        return ts if isinstance(ts, str) else ""

    timeline.sort(key=_sort_key, reverse=True)

    return timeline[:limit]
