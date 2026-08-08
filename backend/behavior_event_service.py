"""Rich behavior event ingestion for visitor sessions.

This service keeps Flask routes thin while preserving the existing event
tracking behavior used by the lead scoring pipeline.
"""

import datetime

from bson import ObjectId
from bson.errors import InvalidId


SUPPORTED_EVENT_TYPES = {
    "page_view": ("navigation", "view"),
    "click": ("engagement", "click"),
    "scroll": ("engagement", "scroll"),
    "form_open": ("engagement", "open"),
    "form_submit": ("engagement", "submit"),
    "product_view": ("product", "view"),
    "product_click": ("product", "click"),
    "search": ("search", "submit"),
    "filter_apply": ("search", "filter"),
    "sort_apply": ("search", "sort"),
    "add_to_cart": ("commerce", "add"),
    "remove_from_cart": ("commerce", "remove"),
    "wishlist_add": ("commerce", "add"),
    "wishlist_remove": ("commerce", "remove"),
    "checkout_start": ("commerce", "start"),
    "purchase": ("commerce", "purchase"),
    "recommendation_view": ("recommendation", "view"),
    "recommendation_click": ("recommendation", "click"),
    "banner_view": ("engagement", "view"),
    "banner_click": ("engagement", "click"),
    "lead_capture": ("lead", "capture"),
}


class BehaviorEventError(Exception):
    """Base error for behavior event ingestion failures."""

    status_code = 400

    def __init__(self, message):
        self.message = message
        super().__init__(message)


class MissingEventFieldsError(BehaviorEventError):
    """Raised when required event fields are missing."""


class UnsupportedEventTypeError(BehaviorEventError):
    """Raised when an event type is not supported by the event bus."""

    def __init__(self):
        super().__init__("Unsupported event_type")


class InvalidSessionIdError(BehaviorEventError):
    """Raised when a session id cannot be parsed as a Mongo ObjectId."""

    status_code = 404

    def __init__(self):
        super().__init__("Session not found")


class SessionNotFoundError(BehaviorEventError):
    """Raised when an event references a missing session."""

    status_code = 404

    def __init__(self):
        super().__init__("Session not found")


def _object_payload(value):
    return value if isinstance(value, dict) else {}


def _session_object_id(session_id):
    try:
        return ObjectId(session_id)
    except (InvalidId, TypeError):
        raise InvalidSessionIdError() from None


def build_behavior_event(data, session):
    """Build a normalized rich event document from a request payload."""
    session_id = data.get("session_id")
    event_type = data.get("event_type")

    if not session_id or not event_type:
        raise MissingEventFieldsError("session_id and event_type required")

    if event_type not in SUPPORTED_EVENT_TYPES:
        raise UnsupportedEventTypeError()

    default_category, default_action = SUPPORTED_EVENT_TYPES[event_type]

    return {
        "session_id": _session_object_id(session_id),
        "visitor_id": session.get("visitor_id"),
        "anonymous_id": session.get("anonymous_id"),
        "user_id": session.get("user_id"),
        "event_type": event_type,
        "event_category": data.get("event_category") or default_category,
        "event_action": data.get("event_action") or default_action,
        "page": data.get("page"),
        "timestamp": datetime.datetime.utcnow(),
        "entity": _object_payload(data.get("entity")),
        "metadata": _object_payload(data.get("metadata")),
        "context": _object_payload(data.get("context")),
        "schema_version": data.get("schema_version") or 2,
    }


def log_behavior_event(data, sessions_collection, events_collection):
    """Validate, store, and apply session updates for one behavior event."""
    session_id = data.get("session_id")
    event_type = data.get("event_type")

    if not session_id or not event_type:
        raise MissingEventFieldsError("session_id and event_type required")

    if event_type not in SUPPORTED_EVENT_TYPES:
        raise UnsupportedEventTypeError()

    session_object_id = _session_object_id(session_id)
    session = sessions_collection.find_one({"_id": session_object_id})
    if not session:
        raise SessionNotFoundError()

    event_doc = build_behavior_event(data, session)
    result = events_collection.insert_one(event_doc)

    update_fields = {"last_active_at": datetime.datetime.utcnow()}
    inc_fields = {}
    if event_type == "page_view":
        inc_fields["page_views"] = 1

    sessions_collection.update_one(
        {"_id": session_object_id},
        {"$set": update_fields, **({"$inc": inc_fields} if inc_fields else {})},
    )

    return str(result.inserted_id)
