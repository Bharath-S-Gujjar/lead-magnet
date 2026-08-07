"""Anonymous-visitor identity creation and authenticated-user resolution."""

from datetime import datetime, timezone
from uuid import uuid4


def generate_anonymous_id():
    """Return an opaque ID suitable for storing in a browser and session record."""
    return f"anon_{uuid4().hex}"


def resolve_anonymous_identity(
    anonymous_id,
    user_id,
    users_collection,
    sessions_collection,
    events_collection,
    leads_collection,
):
    """Associate existing anonymous records with an authenticated user.

    Raw events remain tied to their session IDs. Adding ``user_id`` to both the
    sessions and events allows either collection to be queried by the resolved
    identity without changing the event schema's existing session reference.
    """
    if not anonymous_id or not user_id:
        return {"sessions_merged": 0, "events_merged": 0, "leads_merged": 0}

    session_query = {
        "$or": [
            {"anonymous_id": anonymous_id},
            {"visitor_id": anonymous_id},
        ]
    }
    matching_sessions = list(sessions_collection.find(session_query, {"_id": 1}))
    session_ids = [session["_id"] for session in matching_sessions]
    now = datetime.now(timezone.utc)

    sessions_result = sessions_collection.update_many(
        session_query,
        {
            "$set": {
                "user_id": user_id,
                "identity_status": "authenticated",
                "identity_resolved_at": now,
            }
        },
    )

    events_merged = 0
    if session_ids:
        events_result = events_collection.update_many(
            {"session_id": {"$in": session_ids}},
            {"$set": {"user_id": user_id, "identity_resolved_at": now}},
        )
        events_merged = events_result.modified_count

    leads_result = leads_collection.update_many(
        {"visitor_id": anonymous_id},
        {"$set": {"user_id": user_id, "identity_resolved_at": now}},
    )
    users_collection.update_one(
        {"_id": user_id},
        {"$addToSet": {"anonymous_ids": anonymous_id}},
    )

    return {
        "sessions_merged": sessions_result.modified_count,
        "events_merged": events_merged,
        "leads_merged": leads_result.modified_count,
    }
