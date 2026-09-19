"""Orchestrate session aggregation, model adaptation, prediction, and lead storage."""

from bson import ObjectId
from bson.errors import InvalidId

from feature_aggregation import aggregate_session_features
from model_adapter import adapt_behavioral_features
from prediction_service import predict_session


class SessionNotFoundError(Exception):
    """Raised when processing is requested for a session that does not exist."""


def _to_object_id(session_id):
    try:
        return ObjectId(session_id)
    except (InvalidId, TypeError):
        raise SessionNotFoundError("Session not found") from None


def _load_session_events(events_collection, session_object_id):
    event_cursor = events_collection.find({"session_id": session_object_id})
    if hasattr(event_cursor, "sort"):
        try:
            event_cursor = event_cursor.sort("timestamp", 1)
        except TypeError:
            # Lists used by lightweight callers/tests are already iterable.
            pass
    return list(event_cursor)


def _build_source_summary(features):
    return {
        "landing_source": features["landing_source"],
        "landing_page": features["landing_page"],
        "event_count": features["event_count"],
        "page_views": features["page_views"],
        "high_intent_page_visits": features["high_intent_page_visits"],
        "form_submit_count": features["form_submit_count"],
    }


def process_session(session_id, sessions_collection, events_collection, leads_collection):
    """Process a completed session and persist its lead result.

    Collections are passed in by the caller to keep this service independent of
    Flask. A future ``/api/session/end`` route can supply its module-level
    PyMongo collections directly.
    """
    session_object_id = _to_object_id(session_id)
    session = sessions_collection.find_one({"_id": session_object_id})
    if not session:
        raise SessionNotFoundError("Session not found")

    events = _load_session_events(events_collection, session_object_id)
    feature_snapshot = aggregate_session_features(session, events)
    model_input = adapt_behavioral_features(feature_snapshot)
    prediction = predict_session(model_input)

    lead_document = {
        "visitor_id": session.get("visitor_id", "unknown"),
        "anonymous_id": session.get("anonymous_id"),
        "user_id": session.get("user_id"),
        "session_id": session_object_id,
        "score": prediction["score"],
        "segment": prediction["segment"],
        "next_action": prediction["next_action"],
        "prediction_time": prediction["prediction_time"],
        "model_version": prediction["model_version"],
        "feature_snapshot": feature_snapshot,
        "source_summary": _build_source_summary(feature_snapshot),
        "processing_status": "processed",
    }
    result = leads_collection.insert_one(lead_document)
    lead_document["_id"] = result.inserted_id

    return lead_document
