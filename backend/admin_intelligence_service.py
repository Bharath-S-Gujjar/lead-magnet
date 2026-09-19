"""Admin Intelligence Service layer.

Provides aggregate metrics, customer directory lead views, customer deep dives,
lead distributions, marketing activity, and admin notifications derived from
canonical MongoDB collections (user_profiles, customer_features, customer_lead_state,
marketing_automation_events, marketing_communications, admin_notifications, orders).
"""

import math
from datetime import datetime, timezone
from bson import ObjectId
from customer_feature_service import _to_object_id


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

    return {
        "customer": _sanitize_doc(profile),
        "behavior": _sanitize_doc(features) or {},
        "lead": _sanitize_doc(lead_state) or {},
        "orders": [_sanitize_doc(o) for o in recent_orders],
        "marketing": {
            "automation_events": [_sanitize_doc(e) for e in auto_events],
            "communications": [_sanitize_doc(c) for c in comms]
        }
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
    """Retrieve paginated internal admin notifications.

    Returns:
        dict: Paginated list of admin notification documents.
    """
    notif_col = db["admin_notifications"]

    page = max(1, int(page))
    limit = max(1, min(100, int(limit)))

    query = {}
    if read_status is not None:
        query["read"] = bool(read_status)

    total = notif_col.count_documents(query)
    pages = math.ceil(total / limit) if total > 0 else 0
    skip = (page - 1) * limit

    cursor = notif_col.find(query).sort("created_at", -1).skip(skip).limit(limit)

    items = [_sanitize_doc(n) for n in cursor]

    return {
        "items": items,
        "page": page,
        "limit": limit,
        "total": total,
        "pages": pages
    }
