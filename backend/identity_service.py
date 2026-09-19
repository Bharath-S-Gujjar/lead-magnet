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
    cart_collection=None,
    wishlist_collection=None,
    customer_features_collection=None,
    db=None,
):
    """Associate existing anonymous records with an authenticated user.

    Raw events remain tied to their session IDs. Adding ``user_id`` to both the
    sessions and events allows either collection to be queried by the resolved
    identity without changing the event schema's existing session reference.
    Also merges anonymous cart and wishlist items into the user account and
    updates the customer feature store.
    """
    if not anonymous_id or not user_id:
        return {"sessions_merged": 0, "events_merged": 0, "leads_merged": 0, "cart_merged": 0, "wishlist_merged": 0}

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
        {
            "$set": {
                "user_id": user_id,
                "identity_status": "authenticated",
                "identity_resolved_at": now,
            },
            "$addToSet": {"anonymous_ids": anonymous_id},
        },
    )

    cart_merged = 0
    if cart_collection is not None:
        from cart_service import merge_anonymous_cart
        cart_merged = merge_anonymous_cart(cart_collection, anonymous_id, user_id)

    wishlist_merged = 0
    if wishlist_collection is not None:
        from wishlist_service import merge_anonymous_wishlist
        wishlist_merged = merge_anonymous_wishlist(wishlist_collection, anonymous_id, user_id)

    if customer_features_collection is not None:
        customer_features_collection.delete_many({"customer_id": anonymous_id})

    if db is not None:
        from customer_feature_service import upsert_customer_features
        upsert_customer_features(user_id, db)

    return {
        "sessions_merged": sessions_result.modified_count,
        "events_merged": events_merged,
        "leads_merged": leads_result.modified_count,
        "cart_merged": cart_merged,
        "wishlist_merged": wishlist_merged,
    }
