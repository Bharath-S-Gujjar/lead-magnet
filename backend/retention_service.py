"""Retention and inactivity intelligence service.

Provides behavioral recency and engagement trend signals.
All signals are EXPLICITLY LABELED AS HEURISTIC — no separate ML churn model is claimed.

Signals:
    days_since_last_activity, activity_trend, engagement_trend,
    returning_customer, inactivity_risk (heuristic)
"""

from datetime import datetime, timezone, timedelta
from bson import ObjectId

from customer_feature_service import _to_object_id, _to_utc_datetime


# Inactivity risk thresholds (in days) — heuristic
INACTIVITY_THRESHOLDS = {
    "low": 7,
    "medium": 14,
    "high": 30,
}


def compute_retention_signals(customer_id, db):
    """Compute retention and engagement heuristic signals for a customer.

    Args:
        customer_id: ObjectId or string customer identifier.
        db: PyMongo database object.

    Returns:
        dict: Retention signals including activity trends and inactivity risk.
    """
    if not customer_id or db is None:
        return _empty_signals()

    features_col = db["customer_features"]
    events_col = db["events"]
    sessions_col = db["sessions"]

    c_oid = _to_object_id(customer_id)

    # Get feature doc for days_since_last_activity
    feature_doc = None
    if c_oid:
        feature_doc = features_col.find_one({"customer_id": c_oid})
    if not feature_doc and isinstance(customer_id, str):
        feature_doc = features_col.find_one({"customer_id": customer_id})

    days_since = None
    if feature_doc:
        days_since = feature_doc.get("days_since_last_activity")

    if days_since is None:
        days_since = _compute_days_since(customer_id, db)

    # Inactivity risk (heuristic)
    inactivity_risk = "none"
    if days_since is not None:
        if days_since >= INACTIVITY_THRESHOLDS["high"]:
            inactivity_risk = "high"
        elif days_since >= INACTIVITY_THRESHOLDS["medium"]:
            inactivity_risk = "medium"
        elif days_since >= INACTIVITY_THRESHOLDS["low"]:
            inactivity_risk = "low"

    risk_level_map = {
        "none": "Low",
        "low": "Low",
        "medium": "Medium",
        "high": "High",
    }
    churn_risk_level = risk_level_map.get(inactivity_risk, "Low")

    # Activity trend: compare recent 7 days vs prior 7 days
    activity_trend, engagement_trend = _compute_trends(customer_id, events_col)

    # Returning customer: has >1 session with >24h gap
    returning_customer = _is_returning_customer(customer_id, sessions_col)

    return {
        "days_since_last_activity": round(days_since, 2) if days_since is not None else None,
        "activity_trend": activity_trend,
        "engagement_trend": engagement_trend,
        "returning_customer": returning_customer,
        "inactivity_risk": inactivity_risk,
        "churn_risk_level": churn_risk_level,
        "inactivity_risk_method": "heuristic_threshold",
        "inactivity_thresholds": INACTIVITY_THRESHOLDS,
    }


def _empty_signals():
    return {
        "days_since_last_activity": None,
        "activity_trend": "unknown",
        "engagement_trend": "unknown",
        "returning_customer": False,
        "inactivity_risk": "unknown",
        "churn_risk_level": "Low",
        "inactivity_risk_method": "heuristic_threshold",
        "inactivity_thresholds": INACTIVITY_THRESHOLDS,
    }


def _compute_days_since(customer_id, db):
    """Compute days since last activity from events/sessions."""
    c_oid = _to_object_id(customer_id)
    events_col = db["events"]
    sessions_col = db["sessions"]

    now = datetime.now(timezone.utc)

    # Check latest event
    query_conditions = []
    if c_oid:
        query_conditions.append({"user_id": c_oid})
        query_conditions.append({"user_id": str(c_oid)})
    if isinstance(customer_id, str):
        query_conditions.append({"anonymous_id": customer_id})

    if not query_conditions:
        return None

    latest_event = events_col.find_one(
        {"$or": query_conditions},
        sort=[("timestamp", -1)]
    )
    latest_session = sessions_col.find_one(
        {"$or": query_conditions},
        sort=[("last_active_at", -1)]
    )

    timestamps = []
    if latest_event:
        t = _to_utc_datetime(latest_event.get("timestamp"))
        if t:
            timestamps.append(t)
    if latest_session:
        t = _to_utc_datetime(latest_session.get("last_active_at"))
        if t:
            timestamps.append(t)

    if timestamps:
        last_active = max(timestamps)
        return max(0, (now - last_active).total_seconds() / 86400.0)

    return None


def _compute_trends(customer_id, events_col):
    """Compare recent 7d event count vs prior 7d to determine trends."""
    c_oid = _to_object_id(customer_id)
    now = datetime.now(timezone.utc)
    seven_days_ago = now - timedelta(days=7)
    fourteen_days_ago = now - timedelta(days=14)

    query_conditions = []
    if c_oid:
        query_conditions.append({"user_id": c_oid})
        query_conditions.append({"user_id": str(c_oid)})
    if isinstance(customer_id, str):
        query_conditions.append({"anonymous_id": customer_id})

    if not query_conditions:
        return "unknown", "unknown"

    base_query = {"$or": query_conditions}

    try:
        # Recent 7 days
        recent_query = {**base_query, "timestamp": {"$gte": seven_days_ago}}
        recent_count = events_col.count_documents(recent_query)

        # Prior 7 days (7-14 days ago)
        prior_query = {
            **base_query,
            "timestamp": {"$gte": fourteen_days_ago, "$lt": seven_days_ago}
        }
        prior_count = events_col.count_documents(prior_query)
    except Exception:
        return "unknown", "unknown"

    # Activity trend
    if recent_count > prior_count * 1.2:
        activity_trend = "increasing"
    elif recent_count < prior_count * 0.8:
        activity_trend = "declining"
    else:
        activity_trend = "stable"

    # Engagement trend (same logic, different label semantics)
    engagement_trend = activity_trend

    return activity_trend, engagement_trend


def _is_returning_customer(customer_id, sessions_col):
    """Check if customer has multiple sessions with >24h gap."""
    c_oid = _to_object_id(customer_id)

    query_conditions = []
    if c_oid:
        query_conditions.append({"user_id": c_oid})
        query_conditions.append({"user_id": str(c_oid)})
    if isinstance(customer_id, str):
        query_conditions.append({"anonymous_id": customer_id})

    if not query_conditions:
        return False

    try:
        sessions = list(
            sessions_col.find(
                {"$or": query_conditions},
                {"started_at": 1}
            ).sort("started_at", 1).limit(10)
        )
    except Exception:
        return False

    if len(sessions) < 2:
        return False

    for i in range(1, len(sessions)):
        prev_start = _to_utc_datetime(sessions[i - 1].get("started_at"))
        curr_start = _to_utc_datetime(sessions[i].get("started_at"))
        if prev_start and curr_start:
            gap = (curr_start - prev_start).total_seconds()
            if gap > 86400:  # 24 hours
                return True

    return False


def get_retention_overview(db):
    """Get aggregate retention signals for admin dashboard.

    Returns:
        dict: Distribution of inactivity risk levels across customers with features.
    """
    if db is None:
        return {"risk_distribution": {}, "total_customers": 0}

    features_col = db["customer_features"]

    try:
        all_features = list(features_col.find(
            {"days_since_last_activity": {"$exists": True}},
            {"days_since_last_activity": 1}
        ))
    except Exception:
        return {"risk_distribution": {}, "total_customers": 0}

    risk_counts = {"none": 0, "low": 0, "medium": 0, "high": 0}

    for f in all_features:
        days = f.get("days_since_last_activity")
        if days is None:
            continue
        try:
            days = float(days)
        except (ValueError, TypeError):
            continue

        if days >= INACTIVITY_THRESHOLDS["high"]:
            risk_counts["high"] += 1
        elif days >= INACTIVITY_THRESHOLDS["medium"]:
            risk_counts["medium"] += 1
        elif days >= INACTIVITY_THRESHOLDS["low"]:
            risk_counts["low"] += 1
        else:
            risk_counts["none"] += 1

    return {
        "risk_distribution": risk_counts,
        "total_customers": len(all_features),
        "thresholds": INACTIVITY_THRESHOLDS,
        "method": "heuristic_threshold",
    }
