"""Lead-to-revenue attribution service.

Tracks whether qualified leads later purchase and computes attribution metrics.

Attribution logic:
    If a customer was qualified (in customer_lead_state with qualification_status='qualified')
    BEFORE their order created_at timestamp, that order's revenue is attributed to lead
    qualification.

DOCUMENTED LIMITATION:
    This is correlation-based attribution, not causal. A qualified lead who purchases
    may have purchased regardless of qualification. True causal attribution requires
    A/B testing or incrementality analysis which is beyond current data capabilities.
"""

from datetime import datetime, timezone
from bson import ObjectId

from customer_feature_service import _to_object_id, _to_utc_datetime


def compute_lead_revenue_attribution(db):
    """Compute lead-to-revenue attribution metrics.

    Args:
        db: PyMongo database object.

    Returns:
        dict: Attribution metrics including conversion rate and attributed revenue.
    """
    if db is None:
        return _empty_attribution()

    lead_state_col = db["customer_lead_state"]
    orders_col = db["orders"]

    # Get all customers who were ever qualified
    qualified_leads = list(lead_state_col.find({
        "$or": [
            {"qualification_status": "qualified"},
            {"first_qualified_at": {"$ne": None}},
        ]
    }))

    if not qualified_leads:
        return _empty_attribution()

    total_qualified = len(qualified_leads)
    qualified_with_purchase = 0
    attributed_revenue = 0.0
    attributed_orders = 0

    for lead in qualified_leads:
        c_id = lead.get("customer_id")
        first_qualified_at = lead.get("first_qualified_at")

        # Find orders for this customer
        c_oid = _to_object_id(c_id)
        order_query_conditions = []
        if c_oid:
            order_query_conditions.append({"user_id": c_oid})
            order_query_conditions.append({"user_id": str(c_oid)})
        if isinstance(c_id, str):
            order_query_conditions.append({"user_id": c_id})

        if not order_query_conditions:
            continue

        customer_orders = list(orders_col.find({"$or": order_query_conditions}))

        if not customer_orders:
            continue

        customer_has_purchase = False
        qualified_dt = _to_utc_datetime(first_qualified_at) if first_qualified_at else None

        for order in customer_orders:
            order_created = _to_utc_datetime(order.get("created_at"))
            amount = order.get("total_amount")

            if isinstance(amount, (int, float)):
                order_revenue = float(amount)
            else:
                order_revenue = 0.0

            customer_has_purchase = True

            # Attribution: order happened after qualification
            if qualified_dt and order_created:
                if order_created >= qualified_dt:
                    attributed_revenue += order_revenue
                    attributed_orders += 1
            else:
                # If we can't determine timing, count conservatively
                # (don't attribute without evidence)
                pass

        if customer_has_purchase:
            qualified_with_purchase += 1

    conversion_rate = (
        round((qualified_with_purchase / total_qualified * 100), 2)
        if total_qualified > 0 else 0.0
    )

    return {
        "total_qualified_leads": total_qualified,
        "qualified_with_purchase": qualified_with_purchase,
        "qualified_to_purchase_conversion_rate": conversion_rate,
        "attributed_revenue": round(attributed_revenue, 2),
        "attributed_orders": attributed_orders,
        "attribution_method": "temporal_correlation",
        "attribution_disclaimer": (
            "Revenue is attributed when a customer was qualified before their order. "
            "This is correlation-based, not causal. True attribution requires "
            "controlled experiments."
        ),
    }


def _empty_attribution():
    return {
        "total_qualified_leads": 0,
        "qualified_with_purchase": 0,
        "qualified_to_purchase_conversion_rate": 0.0,
        "attributed_revenue": 0.0,
        "attributed_orders": 0,
        "attribution_method": "temporal_correlation",
        "attribution_disclaimer": (
            "Revenue is attributed when a customer was qualified before their order. "
            "This is correlation-based, not causal."
        ),
    }
