"""Customer lead state management and qualification transition service.

Calculates, stores, and synchronizes single-document customer lead state representations
in the `customer_lead_state` collection.

Rule: ONE CANONICAL REGISTERED CUSTOMER = ONE LEAD STATE DOCUMENT.
"""

from datetime import datetime, timezone
from bson import ObjectId

from customer_feature_service import get_customer_features, _to_object_id
from ecommerce_model_adapter import predict_customer_features
from scoring_constants import HOT, WARM


# Qualification: customer is in Hot segment (score >= 70) with active cart and recent checkout.
# Not a probability test -- see scoring_constants.HOT for the integer threshold.
QUALIFICATION_PROBABILITY_THRESHOLD = HOT / 100.0  # legacy alias; prefer segment check


_ENSURED_LEAD_STATE_INDEXES = set()


def ensure_customer_lead_state_indexes(customer_lead_state_collection):
    """Safely ensure unique index on customer_id in customer_lead_state collection."""
    if customer_lead_state_collection is None:
        return
    col_id = id(customer_lead_state_collection)
    if col_id in _ENSURED_LEAD_STATE_INDEXES:
        return
    try:
        existing = {idx["name"] for idx in customer_lead_state_collection.list_indexes()}
        if "customer_id_1" not in existing:
            customer_lead_state_collection.create_index(
                [("customer_id", 1)],
                unique=True,
                name="customer_id_1",
                background=True
            )
        _ENSURED_LEAD_STATE_INDEXES.add(col_id)
    except Exception:
        # Ignore indexing errors when testing with mock collections
        pass


def get_customer_lead_state(customer_id, db_or_collection):
    """Retrieve current lead state document for a customer_id.

    Args:
        customer_id: ObjectId or string representing customer ID.
        db_or_collection: PyMongo database object or customer_lead_state collection.

    Returns:
        dict or None: Customer lead state document if present.
    """
    if not customer_id:
        return None

    if hasattr(db_or_collection, "name") and getattr(db_or_collection, "name", None) == "customer_lead_state":
        state_col = db_or_collection
    elif hasattr(db_or_collection, "__getitem__") and hasattr(db_or_collection, "list_collection_names"):
        state_col = db_or_collection["customer_lead_state"]
    elif hasattr(db_or_collection, "customer_lead_state"):
        state_col = db_or_collection.customer_lead_state
    else:
        state_col = db_or_collection

    c_oid = _to_object_id(customer_id)
    query_id = c_oid if c_oid else customer_id

    doc = state_col.find_one({"customer_id": query_id})
    if not doc and isinstance(customer_id, str):
        doc = state_col.find_one({"customer_id": customer_id})
    return doc


def sync_customer_lead_state(customer_id, db):
    """Synchronize customer lead state from feature store and ML inference.

    Args:
        customer_id: ObjectId or string customer identifier.
        db: PyMongo database object.

    Returns:
        dict: Updated lead state document.

    Raises:
        ValueError: If customer_features document is missing or invalid.
    """
    if not customer_id:
        raise ValueError("customer_id is required for lead state synchronization")

    features_col = db["customer_features"]
    state_col = db["customer_lead_state"]

    ensure_customer_lead_state_indexes(state_col)

    feature_doc = get_customer_features(customer_id, features_col)
    if not feature_doc:
        raise ValueError(f"No customer feature record found for customer_id: {customer_id}")

    # Run ML inference
    prediction = predict_customer_features(feature_doc)

    canonical_id = feature_doc.get("customer_id", customer_id)
    c_oid = _to_object_id(canonical_id)
    query_id = c_oid if c_oid else canonical_id

    prob = float(prediction["lead_probability"])
    score = int(prediction["lead_score"])
    segment = str(prediction["lead_segment"])
    model_version = str(prediction["model_version"])

    is_converted = prediction.get("is_converted", False)
    orders_count = int(feature_doc.get("orders_count") or 0)

    # Lifecycle status — independent of lead qualification pipeline.
    # prospect         : no orders placed yet (unconverted lead)
    # converted        : exactly 1 order (first-time buyer; retention target)
    # repeat_customer  : 2+ orders (loyal buyer)
    if orders_count >= 2:
        lifecycle_status = "repeat_customer"
    elif orders_count == 1:
        lifecycle_status = "converted"
    else:
        lifecycle_status = "prospect"

    cart_item_count = int(feature_doc.get("cart_item_count") or 0)

    # Check whether checkout was started within 24 hours:
    checkout_within_24h = bool(
        feature_doc.get("checkout_started_within_24h")
        or prediction.get("active_checkout_override")
    )
    if not checkout_within_24h:
        last_checkout_ts = feature_doc.get("last_checkout_start_at") or feature_doc.get("last_checkout_action_at")
        if last_checkout_ts:
            try:
                now_dt = datetime.now(timezone.utc)
                if isinstance(last_checkout_ts, str):
                    last_checkout_dt = datetime.fromisoformat(last_checkout_ts.replace("Z", "+00:00"))
                else:
                    last_checkout_dt = last_checkout_ts
                if last_checkout_dt.tzinfo is None:
                    last_checkout_dt = last_checkout_dt.replace(tzinfo=timezone.utc)
                if (now_dt - last_checkout_dt).total_seconds() <= 86400:
                    checkout_within_24h = True
            except Exception:
                pass
        if not checkout_within_24h and int(feature_doc.get("checkout_attempts") or 0) > 0:
            days_since = float(feature_doc.get("days_since_last_activity") or 0.0)
            if days_since <= 1.0:
                checkout_within_24h = True

    # Dynamic Qualification criteria:
    # A customer shows strong active buying intent when:
    # 1. Score is at least 70 (score >= 70).
    # 2. Cart contains at least one item (cart_item_count >= 1).
    # 3. Checkout was started within the last 24 hours (checkout_started_within_24h == True).
    # (Unconverted prospect restriction 'orders_count == 0' removed: customers with past orders can qualify if actively shopping)
    is_score_hot = bool(score >= HOT)
    has_cart_items = bool(cart_item_count >= 1)
    has_active_checkout_24h = bool(checkout_within_24h and int(feature_doc.get("checkout_attempts") or 0) > 0)

    is_qualified = bool(is_score_hot and has_cart_items and has_active_checkout_24h)
    qual_status = "qualified" if is_qualified else "not_qualified"
    now_iso = datetime.now(timezone.utc).isoformat()

    existing = state_col.find_one({"customer_id": query_id})
    if not existing and isinstance(canonical_id, str):
        existing = state_col.find_one({"customer_id": canonical_id})

    if existing:
        prev_prob = existing.get("lead_probability")
        prev_score = existing.get("lead_score")
        prev_segment = existing.get("lead_segment")
        prev_qual_status = existing.get("qualification_status")

        first_qual_at = existing.get("first_qualified_at")
        if not first_qual_at and qual_status == "qualified":
            first_qual_at = now_iso

        last_qual_at = existing.get("last_qualified_at")
        if qual_status == "qualified":
            last_qual_at = now_iso

        created_at = existing.get("created_at") or now_iso
    else:
        prev_prob = None
        prev_score = None
        prev_segment = None
        prev_qual_status = None

        first_qual_at = now_iso if qual_status == "qualified" else None
        last_qual_at = now_iso if qual_status == "qualified" else None
        created_at = now_iso

    # Transition evaluations
    if prev_qual_status is None:
        transition = f"none_to_{qual_status}"
    else:
        transition = f"{prev_qual_status}_to_{qual_status}"

    is_newly_qualified = (prev_qual_status != "qualified" and qual_status == "qualified")
    segment_changed = (prev_segment != segment)

    state_doc = {
        "customer_id": query_id,
        "lead_probability": prob,
        "lead_score": score,
        "lead_segment": segment,
        "qualification_status": qual_status,

        # Behavioral score breakdown (explainability)
        "behavioral_score": prediction.get("behavioral_score", score),
        "purchase_intent_score": prediction.get("purchase_intent_score"),
        "product_interest_score": prediction.get("product_interest_score"),
        "engagement_score": prediction.get("engagement_score"),
        "purchase_readiness_score": prediction.get("purchase_readiness_score"),
        "score_reasons": prediction.get("score_reasons", []),
        "active_checkout_override": prediction.get("active_checkout_override", False),
        "is_converted": is_converted,
        "lifecycle_status": lifecycle_status,
        "confidence": prediction.get("confidence", "high"),
        "is_provisional": prediction.get("is_provisional", False),
        "recency_decay_factor": prediction.get("recency_decay_factor"),
        "scoring_method": prediction.get("scoring_method", "behavioral_100pt_rule_based"),

        # XGBoost secondary reference
        "raw_model_score": prediction.get("raw_model_score"),
        "raw_model_probability": prediction.get("raw_model_probability"),
        "has_purchase_intent": prediction.get("has_purchase_intent"),
        "model_version": model_version,

        "previous_probability": prev_prob,
        "previous_score": prev_score,
        "previous_segment": prev_segment,
        "previous_qualification_status": prev_qual_status,

        "qualification_transition": transition,
        "is_newly_qualified": is_newly_qualified,
        "segment_changed": segment_changed,

        "first_qualified_at": first_qual_at,
        "last_qualified_at": last_qual_at,
        "last_scored_at": now_iso,
        "updated_at": now_iso,
        "created_at": created_at,
    }

    state_col.update_one(
        {"customer_id": query_id},
        {"$set": state_doc},
        upsert=True
    )

    # Trigger marketing automation for qualification transitions
    if is_newly_qualified or transition == "not_qualified_to_qualified":
        try:
            from marketing_automation_service import (
                create_automation_event_for_qualification,
                process_marketing_automation_event,
            )
            event = create_automation_event_for_qualification(query_id, state_doc, db)
            if event:
                process_marketing_automation_event(event["_id"], db)
        except Exception:
            # Ignore automation triggering errors if running in partial/mock DB context
            pass

    return state_doc
