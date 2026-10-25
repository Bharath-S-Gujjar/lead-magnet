"""Canonical Lead State Compatibility Adapter.

Converts canonical single-document customer lead state representations
(`customer_lead_state`) into backward-compatible response envelopes expected by
legacy admin lead directories, single-lead detail endpoints, and dashboard aggregations.

Ensures:
1. Single source of truth: customer_lead_state is authoritative for score, segment, and status.
2. Legacy field compatibility: _id, customer_id, visitor_id, score, segment, next_action, prediction_time, status.
3. Deduplication: Guarantees one entry per customer even if multiple identities or legacy aliases exist.
4. Safe defaults: Missing or malformed fields fall back cleanly without inventing data.
"""

from datetime import datetime, timezone
from bson import ObjectId

from action_recommendations import get_next_action
from customer_feature_service import _to_object_id
from scoring_constants import HOT_PROBABILITY_EQUIV

LEAD_STATUSES = {"New", "Contacted", "Qualified", "Converted", "Lost"}
VALID_SEGMENTS = {"Hot", "Warm", "Cold"}


def resolve_effective_segment(lead_doc):
    """Determine authoritative segment for a lead document with strict precedence.

    Rules:
    1. If `lead_segment` is present in the document:
       - If it contains a valid segment (Hot, Warm, Cold - case-insensitive), that is authoritative.
       - If it is None, empty, or invalid, it is authoritative as invalid (cannot fall back to legacy segment).
    2. Only if `lead_segment` is genuinely MISSING from the document (legacy record):
       - Fall back to legacy `segment` if it is a valid segment (Hot, Warm, Cold - case-insensitive).
    3. Otherwise: returns None.

    Args:
        lead_doc: Dict representing customer lead document.

    Returns:
        str or None: Canonical segment string ("Hot", "Warm", "Cold"), or None if unassigned/invalid.
    """
    if not isinstance(lead_doc, dict):
        return None

    if "lead_segment" in lead_doc:
        val = lead_doc.get("lead_segment")
        if val is not None and isinstance(val, str):
            cleaned = val.strip().capitalize()
            if cleaned in VALID_SEGMENTS:
                return cleaned
        return None

    # Genuine legacy record (lead_segment key missing)
    legacy_val = lead_doc.get("segment")
    if legacy_val is not None and isinstance(legacy_val, str):
        cleaned = legacy_val.strip().capitalize()
        if cleaned in VALID_SEGMENTS:
            return cleaned

    return None


def adapt_canonical_lead(lead_doc, profile_doc=None, session_doc=None):
    """Convert a canonical customer_lead_state record into a legacy-compatible lead envelope.

    Args:
        lead_doc: Dict representing customer_lead_state document.
        profile_doc: Optional dict representing customer user_profiles document.
        session_doc: Optional dict representing customer's latest session.

    Returns:
        dict: Standardized lead dict containing both legacy and canonical keys.
    """
    if not lead_doc or not isinstance(lead_doc, dict):
        return None

    # Customer identifiers
    raw_id = lead_doc.get("_id")
    c_id = lead_doc.get("customer_id")
    c_id_str = str(c_id) if c_id is not None else ""
    lead_id_str = str(raw_id) if raw_id is not None else c_id_str

    # Probability & scores
    raw_prob = lead_doc.get("lead_probability")
    if raw_prob is None:
        raw_prob = lead_doc.get("score", 0.0)
    try:
        lead_prob = float(raw_prob)
    except (ValueError, TypeError):
        lead_prob = 0.0

    raw_score = lead_doc.get("lead_score")
    if raw_score is None:
        raw_score = round(lead_prob * 100)
    try:
        lead_score = int(raw_score)
    except (ValueError, TypeError):
        lead_score = 0

    # Segmentation & qualification
    effective_segment = resolve_effective_segment(lead_doc)
    segment = effective_segment if effective_segment else "Cold"
    qual_status = str(
        lead_doc.get("qualification_status")
        or ("qualified" if lead_prob >= HOT_PROBABILITY_EQUIV else "not_qualified")
    )
    next_action = lead_doc.get("next_action") or get_next_action(segment)

    # Workflow status (manual override or derived from qualification)
    status = lead_doc.get("status") or ("Qualified" if qual_status == "qualified" else "New")

    # Timestamp
    prediction_time = (
        lead_doc.get("last_scored_at")
        or lead_doc.get("prediction_time")
        or lead_doc.get("updated_at")
        or lead_doc.get("created_at")
        or datetime.now(timezone.utc).isoformat()
    )
    if isinstance(prediction_time, datetime):
        prediction_time = prediction_time.isoformat()

    model_version = str(lead_doc.get("model_version") or "v2.0_ecommerce_xgb")

    adapted = {
        "_id": lead_id_str,
        "customer_id": c_id_str,
        "visitor_id": str(lead_doc.get("visitor_id") or c_id_str),
        "score": round(lead_prob, 2),
        "lead_score": lead_score,
        "lead_probability": lead_prob,
        "segment": segment,
        "lead_segment": segment,
        "qualification_status": qual_status,
        "status": status,
        "next_action": next_action,
        "prediction_time": prediction_time,
        "model_version": model_version,
    }

    # Session identifier preservation
    if "session_id" in lead_doc and lead_doc["session_id"] is not None:
        adapted["session_id"] = str(lead_doc["session_id"])
    elif session_doc and "_id" in session_doc:
        adapted["session_id"] = str(session_doc["_id"])

    # User identifier preservation
    if "user_id" in lead_doc and lead_doc["user_id"] is not None:
        adapted["user_id"] = str(lead_doc["user_id"])
    elif profile_doc and "_id" in profile_doc:
        adapted["user_id"] = str(profile_doc["_id"])
    elif isinstance(c_id, ObjectId):
        adapted["user_id"] = str(c_id)

    # Customer details if joined with user_profiles
    if profile_doc and isinstance(profile_doc, dict):
        if profile_doc.get("email"):
            adapted["email"] = profile_doc["email"]
        if profile_doc.get("full_name"):
            adapted["full_name"] = profile_doc["full_name"]
        if profile_doc.get("phone"):
            adapted["phone"] = profile_doc["phone"]
    elif lead_doc.get("email"):
        adapted["email"] = lead_doc["email"]

    return adapted


def get_canonical_leads_adapted(
    collection,
    profiles_collection=None,
    query=None,
    sort_field="last_scored_at",
    sort_dir=-1
):
    """Query canonical leads and return deduplicated, adapted records.

    Args:
        collection: customer_lead_state PyMongo collection or mock.
        profiles_collection: Optional user_profiles collection for customer details.
        query: Optional MongoDB query filter.
        sort_field: Field to sort by (default: 'last_scored_at').
        sort_dir: Sort direction (-1 for desc, 1 for asc).

    Returns:
        list[dict]: List of legacy-compatible adapted lead dicts.
    """
    if collection is None:
        return []

    # Safe sort execution
    try:
        cursor = collection.find(query or {}).sort(sort_field, sort_dir)
    except Exception:
        try:
            cursor = collection.find(query or {}).sort("last_scored_at", -1)
        except Exception:
            cursor = collection.find(query or {})

    seen_customers = set()
    adapted_leads = []

    for doc in cursor:
        cust_id = doc.get("customer_id")
        cust_key = str(cust_id) if cust_id is not None else str(doc.get("visitor_id") or doc.get("_id"))

        if cust_key in seen_customers:
            continue
        seen_customers.add(cust_key)

        # Lookup profile if available
        profile = None
        if profiles_collection is not None and cust_id is not None:
            c_oid = _to_object_id(cust_id)
            if c_oid:
                profile = profiles_collection.find_one({"_id": c_oid})
            if not profile:
                profile = profiles_collection.find_one({
                    "$or": [{"_id": cust_id}, {"user_id": cust_id}]
                })

        adapted = adapt_canonical_lead(doc, profile_doc=profile)
        if adapted:
            adapted_leads.append(adapted)

    return adapted_leads


def get_canonical_lead_by_id(collection, lead_id, profiles_collection=None):
    """Retrieve a single lead by its ObjectId or customer_id.

    Args:
        collection: customer_lead_state PyMongo collection.
        lead_id: ObjectId or string representation of lead or customer ID.
        profiles_collection: Optional user_profiles collection for profile details.

    Returns:
        dict or None: Adapted lead dict, or None if not found.
    """
    if collection is None or not lead_id:
        return None

    c_oid = _to_object_id(lead_id)
    doc = None
    if c_oid:
        doc = collection.find_one({
            "$or": [{"_id": c_oid}, {"customer_id": c_oid}, {"customer_id": str(lead_id)}]
        })
    if not doc:
        doc = collection.find_one({
            "$or": [{"_id": lead_id}, {"customer_id": str(lead_id)}]
        })

    if not doc:
        return None

    cust_id = doc.get("customer_id")
    profile = None
    if profiles_collection is not None and cust_id is not None:
        p_oid = _to_object_id(cust_id)
        if p_oid:
            profile = profiles_collection.find_one({"_id": p_oid})
        if not profile:
            profile = profiles_collection.find_one({
                "$or": [{"_id": cust_id}, {"user_id": cust_id}]
            })

    return adapt_canonical_lead(doc, profile_doc=profile)


def update_canonical_lead_status(collection, lead_id, status):
    """Update workflow status of a canonical lead.

    Args:
        collection: customer_lead_state PyMongo collection.
        lead_id: ObjectId or string lead/customer identifier.
        status: New status string (must be in LEAD_STATUSES).

    Returns:
        bool: True if matched and updated, False otherwise.
    """
    if collection is None or not lead_id or not status:
        return False

    if status not in LEAD_STATUSES:
        raise ValueError(f"Invalid lead status: {status}")

    c_oid = _to_object_id(lead_id)
    query = {"_id": c_oid} if c_oid else {"_id": lead_id}

    update_fields = {
        "status": status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    res = collection.update_one(query, {"$set": update_fields})
    if getattr(res, "matched_count", 0) > 0:
        return True

    # Fallback search by customer_id if _id did not match
    if c_oid:
        res = collection.update_one(
            {"$or": [{"customer_id": c_oid}, {"customer_id": str(lead_id)}]},
            {"$set": update_fields}
        )
    else:
        res = collection.update_one(
            {"customer_id": str(lead_id)},
            {"$set": update_fields}
        )

    return getattr(res, "matched_count", 0) > 0


def aggregate_canonical_dashboard(collection):
    """Aggregate lead counts and statistics from customer_lead_state.

    Ensures:
    - Precedence: lead_segment is authoritative; fallback to segment only when lead_segment is missing.
    - Consistency: Each record contributes to at most one of Hot, Warm, or Cold.
    - Conflicting, null, or invalid canonical values do not promote records to Hot.
    - average_score reflects canonical lead_probability.

    Args:
        collection: customer_lead_state PyMongo collection.

    Returns:
        dict: Dict containing total_leads, hot_leads, warm_leads, cold_leads, average_score.
    """
    if collection is None:
        return {
            "total_leads": 0,
            "hot_leads": 0,
            "warm_leads": 0,
            "cold_leads": 0,
            "average_score": 0.0,
        }

    summary_pipeline = [
        {
            "$project": {
                "lead_probability": 1,
                "score": 1,
                "effective_segment": {
                    "$cond": [
                        {"$in": ["$lead_segment", ["Hot", "hot", "Warm", "warm", "Cold", "cold"]]},
                        "$lead_segment",
                        {
                            "$cond": [
                                {"$eq": [{"$type": "$lead_segment"}, "missing"]},
                                {
                                    "$cond": [
                                        {"$in": ["$segment", ["Hot", "hot", "Warm", "warm", "Cold", "cold"]]},
                                        "$segment",
                                        None
                                    ]
                                },
                                None
                            ]
                        }
                    ]
                }
            }
        },
        {
            "$group": {
                "_id": None,
                "total_leads": {"$sum": 1},
                "hot_leads": {
                    "$sum": {
                        "$cond": [
                            {"$in": ["$effective_segment", ["Hot", "hot"]]},
                            1,
                            0
                        ]
                    }
                },
                "warm_leads": {
                    "$sum": {
                        "$cond": [
                            {"$in": ["$effective_segment", ["Warm", "warm"]]},
                            1,
                            0
                        ]
                    }
                },
                "cold_leads": {
                    "$sum": {
                        "$cond": [
                            {"$in": ["$effective_segment", ["Cold", "cold"]]},
                            1,
                            0
                        ]
                    }
                },
                "average_score": {
                    "$avg": {
                        "$ifNull": ["$lead_probability", "$score"]
                    }
                },
            }
        }
    ]

    try:
        results = list(collection.aggregate(summary_pipeline))
        summary = results[0] if results else {}
    except Exception:
        try:
            # Python fallback if aggregate is unsupported by in-memory test mocks
            docs = list(collection.find({}))
            total = len(docs)
            hot = sum(1 for d in docs if resolve_effective_segment(d) == "Hot")
            warm = sum(1 for d in docs if resolve_effective_segment(d) == "Warm")
            cold = sum(1 for d in docs if resolve_effective_segment(d) == "Cold")
            scores = [
                float(d["lead_probability"] if d.get("lead_probability") is not None else d.get("score", 0.0))
                for d in docs
                if d.get("lead_probability") is not None or d.get("score") is not None
            ]
            avg_score = sum(scores) / len(scores) if scores else 0.0
            summary = {
                "total_leads": total,
                "hot_leads": hot,
                "warm_leads": warm,
                "cold_leads": cold,
                "average_score": avg_score
            }
        except Exception:
            summary = {}

    return {
        "total_leads": int(summary.get("total_leads", 0)),
        "hot_leads": int(summary.get("hot_leads", 0)),
        "warm_leads": int(summary.get("warm_leads", 0)),
        "cold_leads": int(summary.get("cold_leads", 0)),
        "average_score": float(summary.get("average_score") or 0.0),
    }
