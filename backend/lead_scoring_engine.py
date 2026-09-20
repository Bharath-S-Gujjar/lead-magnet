"""Central lead scoring engine — event-driven rescoring orchestrator.

Provides a single entry point for rescoring a customer after any behavioral event.
Idempotent: guarded by a debounce timestamp to prevent scoring loops.

Flow:
    customer event → feature update → lead scoring → lead state update
    → score history → transition detection → automation if needed → admin live event
"""

import time
from datetime import datetime, timezone

from customer_feature_service import upsert_customer_features, _to_object_id
from customer_lead_state_service import sync_customer_lead_state
from score_history_service import record_score_history, ensure_score_history_indexes
from ecommerce_model_adapter import predict_customer_features


# In-memory debounce to avoid rescoring the same customer more than once per second
_LAST_RESCORE_TIMESTAMPS = {}
DEBOUNCE_SECONDS = 1.0


def rescore_customer(customer_id, db, socketio=None):
    """Rescore a customer's lead state after a behavioral event.

    This is the central orchestrator that:
    1. Updates customer feature store
    2. Runs ML inference
    3. Syncs lead state (with qualification transition detection)
    4. Records score history
    5. Emits real-time admin events via SocketIO

    Args:
        customer_id: ObjectId or string customer identifier.
        db: PyMongo database object.
        socketio: Flask-SocketIO instance for live admin events (optional).

    Returns:
        dict or None: Updated lead state document, or None if debounced/skipped.
    """
    if not customer_id or db is None:
        return None

    # Debounce check — prevent scoring loops
    c_key = str(customer_id)
    now = time.time()
    last_scored = _LAST_RESCORE_TIMESTAMPS.get(c_key, 0)
    if (now - last_scored) < DEBOUNCE_SECONDS:
        return None

    _LAST_RESCORE_TIMESTAMPS[c_key] = now

    try:
        # 1. Update feature store
        feature_doc = upsert_customer_features(customer_id, db)
        if not feature_doc:
            return None

        # 2. Run ML inference (for score history recording)
        prediction = predict_customer_features(feature_doc)

        # 3. Sync lead state (includes transition detection + marketing automation)
        ensure_score_history_indexes(db)
        lead_state = sync_customer_lead_state(customer_id, db)

        # 4. Record score history
        record_score_history(customer_id, prediction, lead_state, db)

        # 5. Emit real-time events
        if socketio is not None:
            _emit_live_events(socketio, customer_id, prediction, lead_state)

        return lead_state

    except Exception as e:
        # Log but don't crash — rescoring failures should not block user operations
        print(f"[LeadScoringEngine] Rescore failed for {customer_id}: {e}")
        return None


def _emit_live_events(socketio, customer_id, prediction, lead_state):
    """Emit SocketIO events for real-time admin intelligence."""
    try:
        c_id_str = str(customer_id)
        score = prediction.get("lead_score", 0)
        segment = prediction.get("lead_segment", "")
        transition = lead_state.get("qualification_transition", "")

        # Always emit score update
        socketio.emit("lead_score_updated", {
            "customer_id": c_id_str,
            "lead_score": score,
            "lead_segment": segment,
            "qualification_status": lead_state.get("qualification_status"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        # Emit transition-specific events
        if transition == "not_qualified_to_qualified":
            socketio.emit("lead_qualified", {
                "customer_id": c_id_str,
                "lead_score": score,
                "lead_segment": segment,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        elif transition == "qualified_to_not_qualified":
            socketio.emit("lead_disqualified", {
                "customer_id": c_id_str,
                "lead_score": score,
                "previous_score": lead_state.get("previous_score"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

    except Exception:
        # SocketIO emission failures should not block scoring
        pass
