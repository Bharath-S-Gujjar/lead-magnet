"""Lead score history and prediction audit service.

Records each scoring event into the `lead_score_history` collection to provide
an auditable timeline of how a customer's lead score changed over time.

Schema per document:
    customer_id, timestamp, model_version, lead_probability, lead_score,
    lead_segment, qualification_status, qualification_transition,
    previous_score, score_delta, feature_snapshot_ref
"""

from datetime import datetime, timezone
from bson import ObjectId

from customer_feature_service import _to_object_id


def ensure_score_history_indexes(db):
    """Create compound index on (customer_id, timestamp) for efficient queries."""
    try:
        col = db["lead_score_history"]
        existing = {idx["name"] for idx in col.list_indexes()}
        if "customer_id_1_timestamp_-1" not in existing:
            col.create_index(
                [("customer_id", 1), ("timestamp", -1)],
                name="customer_id_1_timestamp_-1",
                background=True,
            )
    except Exception:
        pass


def record_score_history(customer_id, prediction, lead_state, db):
    """Write one score history entry after a rescoring event.

    Args:
        customer_id: ObjectId or string customer identifier.
        prediction (dict): Output from predict_customer_features().
        lead_state (dict): Current lead state document from sync_customer_lead_state().
        db: PyMongo database object.

    Returns:
        dict: The inserted score history document (without _id for serialisation safety).
    """
    if not customer_id or not prediction or db is None:
        return None

    col = db["lead_score_history"]

    c_oid = _to_object_id(customer_id)
    query_id = c_oid if c_oid else customer_id

    now_iso = datetime.now(timezone.utc).isoformat()

    previous_score = lead_state.get("previous_score")
    current_score = prediction.get("lead_score", 0)
    score_delta = None
    if previous_score is not None:
        try:
            score_delta = int(current_score) - int(previous_score)
        except (ValueError, TypeError):
            score_delta = None

    doc = {
        "customer_id": query_id,
        "timestamp": now_iso,
        "model_version": prediction.get("model_version"),
        "lead_probability": prediction.get("lead_probability"),
        "lead_score": prediction.get("lead_score"),
        "lead_segment": prediction.get("lead_segment"),
        "qualification_status": lead_state.get("qualification_status"),
        "qualification_transition": lead_state.get("qualification_transition"),
        "previous_score": previous_score,
        "score_delta": score_delta,
        "feature_snapshot_ref": str(lead_state.get("customer_id", "")),
    }

    try:
        col.insert_one(doc)
    except Exception:
        pass

    # Remove _id for serialisation
    doc.pop("_id", None)
    return doc


def get_score_history(customer_id, db, limit=50):
    """Retrieve chronological score history for a customer.

    Args:
        customer_id: ObjectId or string customer identifier.
        db: PyMongo database object.
        limit (int): Maximum number of history entries to return.

    Returns:
        list[dict]: Score history documents, most recent first.
    """
    if not customer_id or db is None:
        return []

    col = db["lead_score_history"]
    c_oid = _to_object_id(customer_id)
    query_id = c_oid if c_oid else customer_id

    cursor = col.find({"customer_id": query_id}).sort("timestamp", -1).limit(limit)

    results = []
    for doc in cursor:
        doc.pop("_id", None)
        if isinstance(doc.get("customer_id"), ObjectId):
            doc["customer_id"] = str(doc["customer_id"])
        results.append(doc)

    # If no results with ObjectId, try string
    if not results and isinstance(customer_id, str):
        cursor = col.find({"customer_id": customer_id}).sort("timestamp", -1).limit(limit)
        for doc in cursor:
            doc.pop("_id", None)
            results.append(doc)

    return results
