"""RFM (Recency, Frequency, Monetary) intelligence service.

Computes RFM scores from order history and assigns customer segments.
This is a SEPARATE intelligence dimension from the ML lead score.

Clear naming convention:
    rfm_recency, rfm_frequency, rfm_monetary, rfm_segment
    (distinct from lead_score, lead_probability, lead_segment)
"""

from datetime import datetime, timezone
from bson import ObjectId

from customer_feature_service import _to_object_id


# RFM segment labels based on quintile combinations
RFM_SEGMENT_MAP = {
    (5, 5, 5): "Champions",
    (5, 5, 4): "Champions",
    (5, 4, 5): "Champions",
    (5, 4, 4): "Loyal Customers",
    (4, 5, 5): "Loyal Customers",
    (4, 5, 4): "Loyal Customers",
    (4, 4, 5): "Loyal Customers",
    (4, 4, 4): "Loyal Customers",
    (5, 3, 3): "Potential Loyalists",
    (4, 3, 3): "Potential Loyalists",
    (5, 3, 4): "Potential Loyalists",
    (5, 3, 5): "Potential Loyalists",
    (5, 2, 1): "New Customers",
    (5, 2, 2): "New Customers",
    (5, 1, 1): "New Customers",
    (5, 1, 2): "New Customers",
    (4, 2, 1): "Promising",
    (4, 2, 2): "Promising",
    (4, 1, 1): "Promising",
    (3, 3, 3): "Need Attention",
    (3, 3, 4): "Need Attention",
    (3, 4, 4): "Need Attention",
    (3, 4, 3): "Need Attention",
    (2, 3, 3): "About To Sleep",
    (2, 2, 3): "About To Sleep",
    (2, 3, 2): "About To Sleep",
    (2, 2, 2): "About To Sleep",
    (3, 1, 1): "About To Sleep",
    (2, 1, 1): "At Risk",
    (2, 1, 2): "At Risk",
    (1, 3, 3): "At Risk",
    (1, 3, 4): "At Risk",
    (1, 4, 4): "At Risk",
    (1, 2, 1): "Hibernating",
    (1, 2, 2): "Hibernating",
    (1, 1, 1): "Lost",
    (1, 1, 2): "Lost",
}


def _score_quintile(value, thresholds):
    """Assign a 1-5 score based on quintile thresholds."""
    if not thresholds or len(thresholds) < 4:
        return 3  # Default mid-range
    if value <= thresholds[0]:
        return 1
    elif value <= thresholds[1]:
        return 2
    elif value <= thresholds[2]:
        return 3
    elif value <= thresholds[3]:
        return 4
    else:
        return 5


def assign_rfm_segment(r_score, f_score, m_score):
    """Map RFM quintile scores to a named segment.

    Args:
        r_score (int): Recency quintile (1-5, 5 = most recent).
        f_score (int): Frequency quintile (1-5, 5 = most frequent).
        m_score (int): Monetary quintile (1-5, 5 = highest value).

    Returns:
        str: Named RFM segment.
    """
    key = (r_score, f_score, m_score)
    if key in RFM_SEGMENT_MAP:
        return RFM_SEGMENT_MAP[key]

    # Fallback heuristic for unmapped combinations
    avg = (r_score + f_score + m_score) / 3.0
    if avg >= 4.0:
        return "Loyal Customers"
    elif avg >= 3.0:
        return "Potential Loyalists"
    elif avg >= 2.0:
        return "Need Attention"
    else:
        return "At Risk"


def compute_rfm(customer_id, db):
    """Compute RFM scores for a single customer from order history.

    Args:
        customer_id: ObjectId or string customer identifier.
        db: PyMongo database object.

    Returns:
        dict: RFM metrics and segment assignment.
    """
    if not customer_id or db is None:
        return {
            "rfm_recency_days": None,
            "rfm_frequency": 0,
            "rfm_monetary": 0.0,
            "rfm_r_score": 1,
            "rfm_f_score": 1,
            "rfm_m_score": 1,
            "rfm_segment": "No Orders",
        }

    orders_col = db["orders"]
    c_oid = _to_object_id(customer_id)

    # Build query for customer orders
    query_conditions = []
    if c_oid:
        query_conditions.append({"user_id": c_oid})
        query_conditions.append({"user_id": str(c_oid)})
    if isinstance(customer_id, str):
        query_conditions.append({"user_id": customer_id})

    if not query_conditions:
        query_conditions.append({"_id": None})

    orders = list(orders_col.find({"$or": query_conditions}))

    if not orders:
        return {
            "rfm_recency_days": None,
            "rfm_frequency": 0,
            "rfm_monetary": 0.0,
            "rfm_r_score": 1,
            "rfm_f_score": 1,
            "rfm_m_score": 1,
            "rfm_segment": "No Orders",
        }

    now = datetime.now(timezone.utc)

    # Recency: days since last order
    order_dates = []
    for o in orders:
        created = o.get("created_at")
        if isinstance(created, datetime):
            order_dates.append(created)
        elif isinstance(created, str):
            try:
                order_dates.append(datetime.fromisoformat(created))
            except (ValueError, TypeError):
                pass

    if order_dates:
        last_order = max(order_dates)
        if last_order.tzinfo is None:
            last_order = last_order.replace(tzinfo=timezone.utc)
        recency_days = max(0, (now - last_order).days)
    else:
        recency_days = 999

    # Frequency: order count
    frequency = len(orders)

    # Monetary: total order value
    monetary = sum(
        float(o.get("total_amount", 0))
        for o in orders
        if isinstance(o.get("total_amount"), (int, float))
    )

    # Compute all customers' RFM for quintile thresholds
    all_customers = _get_all_customer_rfm_raw(db)

    r_thresholds = _compute_quintile_thresholds([c["recency"] for c in all_customers])
    f_thresholds = _compute_quintile_thresholds([c["frequency"] for c in all_customers])
    m_thresholds = _compute_quintile_thresholds([c["monetary"] for c in all_customers])

    # Recency is inverted: lower days = better = higher score
    r_score = 6 - _score_quintile(recency_days, r_thresholds) if r_thresholds else 5
    r_score = max(1, min(5, r_score))
    f_score = _score_quintile(frequency, f_thresholds)
    m_score = _score_quintile(monetary, m_thresholds)

    segment = assign_rfm_segment(r_score, f_score, m_score)

    return {
        "rfm_recency_days": recency_days,
        "rfm_frequency": frequency,
        "rfm_monetary": round(monetary, 2),
        "rfm_r_score": r_score,
        "rfm_f_score": f_score,
        "rfm_m_score": m_score,
        "rfm_segment": segment,
    }


def _compute_quintile_thresholds(values):
    """Compute quintile boundary values for a list of numbers."""
    if not values:
        return []
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    if n < 5:
        return sorted_vals
    return [
        sorted_vals[int(n * 0.20)],
        sorted_vals[int(n * 0.40)],
        sorted_vals[int(n * 0.60)],
        sorted_vals[int(n * 0.80)],
    ]


def _get_all_customer_rfm_raw(db):
    """Get raw RFM values for all customers with orders (for quintile computation)."""
    orders_col = db["orders"]
    pipeline = [
        {
            "$group": {
                "_id": "$user_id",
                "last_order": {"$max": "$created_at"},
                "frequency": {"$sum": 1},
                "monetary": {"$sum": {"$toDouble": {"$ifNull": ["$total_amount", 0]}}},
            }
        }
    ]
    try:
        results = list(orders_col.aggregate(pipeline))
    except Exception:
        return []

    now = datetime.now(timezone.utc)
    customers = []
    for r in results:
        last = r.get("last_order")
        if isinstance(last, datetime):
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            recency = max(0, (now - last).days)
        elif isinstance(last, str):
            try:
                dt = datetime.fromisoformat(last)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                recency = max(0, (now - dt).days)
            except (ValueError, TypeError):
                recency = 999
        else:
            recency = 999

        customers.append({
            "recency": recency,
            "frequency": r.get("frequency", 0),
            "monetary": r.get("monetary", 0.0),
        })

    return customers


def get_rfm_distribution(db):
    """Get aggregate RFM segment distribution for admin analytics.

    Returns:
        dict: Segment counts and overall RFM statistics.
    """
    if db is None:
        return {"segments": {}, "total_customers_with_orders": 0}

    all_rfm = _get_all_customer_rfm_raw(db)
    if not all_rfm:
        return {"segments": {}, "total_customers_with_orders": 0}

    r_thresholds = _compute_quintile_thresholds([c["recency"] for c in all_rfm])
    f_thresholds = _compute_quintile_thresholds([c["frequency"] for c in all_rfm])
    m_thresholds = _compute_quintile_thresholds([c["monetary"] for c in all_rfm])

    segment_counts = {}
    for c in all_rfm:
        r_score = 6 - _score_quintile(c["recency"], r_thresholds) if r_thresholds else 3
        r_score = max(1, min(5, r_score))
        f_score = _score_quintile(c["frequency"], f_thresholds)
        m_score = _score_quintile(c["monetary"], m_thresholds)
        seg = assign_rfm_segment(r_score, f_score, m_score)
        segment_counts[seg] = segment_counts.get(seg, 0) + 1

    return {
        "segments": segment_counts,
        "total_customers_with_orders": len(all_rfm),
    }
