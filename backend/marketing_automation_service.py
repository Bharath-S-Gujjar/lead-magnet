"""Marketing automation service handling events, communications, and policy triggers.

Translates customer qualification transitions into deterministic, idempotent automation events
and communication dispatch records.

Cooldown Policy:
    After sending a qualification campaign, the system enforces a cooldown period
    (MARKETING_COOLDOWN_HOURS, default 72h) before sending another campaign to the
    same customer. This prevents repeated sends when a customer oscillates around
    the qualification threshold.

Channels:
    EMAIL, WHATSAPP only. NO SMS.
"""

import os
from datetime import datetime, timezone, timedelta
from bson import ObjectId

from customer_feature_service import _to_object_id
from communication_provider import get_communication_provider, DryRunCommunicationProvider


# Configurable cooldown period — prevents repeated marketing sends
MARKETING_COOLDOWN_HOURS = int(os.getenv("MARKETING_COOLDOWN_HOURS", "72"))

DEFAULT_CHANNEL_POLICY = {
    "email": {"enabled": True},
    "whatsapp": {"enabled": False},
}


def ensure_marketing_automation_indexes(db):
    """Safely ensure unique indexes on marketing collections."""
    try:
        if hasattr(db, "__getitem__") and "marketing_automation_events" in db:
            events_col = db["marketing_automation_events"]
            comm_col = db["marketing_communications"]
            notif_col = db["admin_notifications"]
        else:
            return

        existing_events_idx = {idx["name"] for idx in events_col.list_indexes()}
        if "idempotency_key_1" not in existing_events_idx:
            events_col.create_index(
                [("idempotency_key", 1)],
                unique=True,
                name="idempotency_key_1",
                background=True
            )
        if "customer_id_1" not in existing_events_idx:
            events_col.create_index([("customer_id", 1)], name="customer_id_1", background=True)

        existing_comm_idx = {idx["name"] for idx in comm_col.list_indexes()}
        if "automation_event_channel_unique" not in existing_comm_idx:
            comm_col.create_index(
                [("automation_event_id", 1), ("channel", 1)],
                unique=True,
                name="automation_event_channel_unique",
                background=True
            )
        if "customer_id_1" not in existing_comm_idx:
            comm_col.create_index([("customer_id", 1)], name="customer_id_1", background=True)

        existing_notif_idx = {idx["name"] for idx in notif_col.list_indexes()}
        if "customer_id_1" not in existing_notif_idx:
            notif_col.create_index([("customer_id", 1)], name="customer_id_1", background=True)
    except Exception:
        # Ignore indexing errors if testing with mock collections
        pass


def _is_channel_enabled(policy, channel_name):
    if not policy:
        return False
    if channel_name in policy:
        val = policy[channel_name]
        if isinstance(val, dict):
            return bool(val.get("enabled", False))
        return bool(val)
    key_name = f"{channel_name}_enabled"
    if key_name in policy:
        return bool(policy[key_name])
    return False


def evaluate_channel_eligibility(user_profile, policy=None):
    """Determine channel eligibility based on contact info and active policy.

    Args:
        user_profile (dict): User profile document from user_profiles collection.
        policy (dict, optional): Channel policy flags. Defaults to DEFAULT_CHANNEL_POLICY.

    Returns:
        dict: Eligibility mapping for email, sms, whatsapp.
    """
    merged_policy = {
        "email": True,
        "sms": False,
        "whatsapp": False,
    }
    if policy:
        if "email" in policy or "email_enabled" in policy:
            merged_policy["email"] = _is_channel_enabled(policy, "email")
        if "sms" in policy or "sms_enabled" in policy:
            merged_policy["sms"] = _is_channel_enabled(policy, "sms")
        if "whatsapp" in policy or "whatsapp_enabled" in policy:
            merged_policy["whatsapp"] = _is_channel_enabled(policy, "whatsapp")

    profile = user_profile or {}

    email_val = profile.get("email")
    has_valid_email = isinstance(email_val, str) and "@" in email_val and bool(email_val.strip())

    phone_val = profile.get("phone")
    has_valid_phone = isinstance(phone_val, str) and bool(phone_val.strip())

    email_enabled = merged_policy["email"]
    sms_enabled = merged_policy["sms"]
    whatsapp_enabled = merged_policy["whatsapp"]

    email_eligible = email_enabled and has_valid_email
    sms_eligible = sms_enabled and has_valid_phone
    whatsapp_eligible = whatsapp_enabled and has_valid_phone

    return {
        "email": {
            "eligible": email_eligible,
            "recipient": email_val if has_valid_email else None,
            "reason": "eligible" if email_eligible else ("No valid email address found" if not has_valid_email else "Email channel disabled by policy")
        },
        "sms": {
            "eligible": sms_eligible,
            "recipient": phone_val if has_valid_phone else None,
            "reason": "eligible" if sms_eligible else ("No phone number found" if not has_valid_phone else "SMS channel disabled by policy")
        },
        "whatsapp": {
            "eligible": whatsapp_eligible,
            "recipient": phone_val if has_valid_phone else None,
            "reason": "eligible" if whatsapp_eligible else ("No phone number found" if not has_valid_phone else "WhatsApp channel disabled by policy")
        },
    }


def _is_within_cooldown(customer_id, db):
    """Check if customer's last marketing campaign is within cooldown period.

    Returns:
        bool: True if within cooldown (should NOT send), False if safe to send.
    """
    if MARKETING_COOLDOWN_HOURS <= 0:
        return False  # Cooldown disabled

    comms_col = db["marketing_communications"]
    c_oid = _to_object_id(customer_id)
    query_id = c_oid if c_oid else customer_id

    last_sent = comms_col.find_one(
        {"customer_id": query_id, "status": "sent"},
        sort=[("sent_at", -1)]
    )

    if not last_sent:
        # Try string query fallback
        if isinstance(customer_id, str) and c_oid:
            last_sent = comms_col.find_one(
                {"customer_id": str(c_oid), "status": "sent"},
                sort=[("sent_at", -1)]
            )

    if not last_sent:
        return False

    sent_at_raw = last_sent.get("sent_at")
    if not sent_at_raw:
        return False

    try:
        if isinstance(sent_at_raw, str):
            sent_at = datetime.fromisoformat(sent_at_raw)
        elif isinstance(sent_at_raw, datetime):
            sent_at = sent_at_raw
        else:
            return False

        if sent_at.tzinfo is None:
            sent_at = sent_at.replace(tzinfo=timezone.utc)

        cooldown_expiry = sent_at + timedelta(hours=MARKETING_COOLDOWN_HOURS)
        return datetime.now(timezone.utc) < cooldown_expiry
    except (ValueError, TypeError):
        return False


def create_automation_event_for_qualification(customer_id, lead_state_doc=None, db=None, **kwargs):
    """Create a marketing automation event when a customer becomes newly qualified.

    Respects cooldown policy: if a campaign was sent within MARKETING_COOLDOWN_HOURS,
    no new event is created. This prevents repeated sends when a customer oscillates
    around the qualification threshold.

    Args:
        customer_id: ObjectId or string customer identifier.
        lead_state_doc (dict, optional): Current lead state document from customer_lead_state.
        db (PyMongo DB, optional): PyMongo database object.

    Returns:
        dict or None: Created or existing marketing_automation_events document.
    """
    if db is None and "db" in kwargs:
        db = kwargs.pop("db")

    if not customer_id:
        return None

    if lead_state_doc is None:
        lead_state_doc = {
            "qualification_transition": kwargs.get("qualification_transition", "not_qualified_to_qualified"),
            "is_newly_qualified": kwargs.get("is_newly_qualified", True),
            "lead_score": kwargs.get("lead_score"),
            "lead_probability": kwargs.get("lead_probability"),
            "lead_segment": kwargs.get("lead_segment"),
            "model_version": kwargs.get("model_version"),
            "first_qualified_at": kwargs.get("first_qualified_at", datetime.now(timezone.utc).isoformat()),
        }

    if db is None:
        return None

    transition = lead_state_doc.get("qualification_transition")
    is_newly = lead_state_doc.get("is_newly_qualified")

    # ONLY trigger for not_qualified -> qualified transitions!
    if transition != "not_qualified_to_qualified" and not is_newly:
        return None

    c_oid = _to_object_id(customer_id)
    query_id = c_oid if c_oid else customer_id

    # Check cooldown policy before creating event
    if _is_within_cooldown(query_id, db):
        return None

    # Time-window idempotency key: uses last_qualified_at (updated each re-qualification)
    # instead of first_qualified_at, allowing new events after cooldown expires
    last_qual = lead_state_doc.get("last_qualified_at") or lead_state_doc.get("first_qualified_at") or lead_state_doc.get("updated_at")
    idempotency_key = f"{str(query_id)}_lead_qualified_{last_qual}"

    events_col = db["marketing_automation_events"]
    ensure_marketing_automation_indexes(db)

    existing = events_col.find_one({"idempotency_key": idempotency_key})
    if existing:
        return existing

    now_iso = datetime.now(timezone.utc).isoformat()
    event_doc = {
        "customer_id": query_id,
        "event_type": "lead_qualified",
        "lead_state_transition": "not_qualified_to_qualified",
        "lead_score": lead_state_doc.get("lead_score"),
        "lead_probability": lead_state_doc.get("lead_probability"),
        "lead_segment": lead_state_doc.get("lead_segment"),
        "model_version": lead_state_doc.get("model_version"),
        "status": "pending",
        "idempotency_key": idempotency_key,
        "cooldown_hours": MARKETING_COOLDOWN_HOURS,
        "created_at": now_iso,
        "processed_at": None,
    }

    res = events_col.insert_one(event_doc)
    event_doc["_id"] = res.inserted_id
    return event_doc


def process_marketing_automation_event(event_id, db, provider=None, policy=None):
    """Idempotently process an automation event and dispatch communications.

    Args:
        event_id: ObjectId or string identifier of marketing_automation_events doc.
        db: PyMongo database object.
        provider (CommunicationProvider, optional): Communication provider instance. Defaults to DryRunCommunicationProvider.
        policy (dict, optional): Channel policy overrides. Defaults to DEFAULT_CHANNEL_POLICY.

    Returns:
        dict: Summary of processing execution and communication results.
    """
    events_col = db["marketing_automation_events"]
    comm_col = db["marketing_communications"]
    profiles_col = db["user_profiles"]
    notif_col = db["admin_notifications"]

    ensure_marketing_automation_indexes(db)

    e_oid = _to_object_id(event_id)
    query_id = e_oid if e_oid else event_id

    event = events_col.find_one({"_id": query_id})
    if not event and isinstance(event_id, str):
        event = events_col.find_one({"_id": event_id})

    if not event:
        raise ValueError(f"Automation event not found: {event_id}")

    if provider is None:
        provider = DryRunCommunicationProvider()

    if policy is None:
        policy = DEFAULT_CHANNEL_POLICY

    c_id = event["customer_id"]
    c_oid = _to_object_id(c_id)
    profile = profiles_col.find_one({"_id": c_oid}) if c_oid else profiles_col.find_one({"_id": c_id})
    if not profile and isinstance(c_id, str):
        profile = profiles_col.find_one({"user_id": c_id})

    eligibility = evaluate_channel_eligibility(profile, policy)
    now_iso = datetime.now(timezone.utc).isoformat()

    events_col.update_one({"_id": event["_id"]}, {"$set": {"status": "processing"}})

    dispatched_communications = []

    for channel in ["email", "whatsapp"]:
        info = eligibility[channel]
        is_eligible = info["eligible"]
        recipient = info["recipient"]
        reason = info["reason"]

        existing_comm = comm_col.find_one({
            "automation_event_id": event["_id"],
            "channel": channel
        })

        if existing_comm and existing_comm.get("status") == "sent":
            dispatched_communications.append(existing_comm)
            continue

        if not is_eligible:
            comm_doc = {
                "customer_id": c_id,
                "automation_event_id": event["_id"],
                "channel": channel,
                "campaign_type": "lead_qualification",
                "status": "skipped",
                "provider": "dry_run",
                "provider_message_id": None,
                "attempt_count": 0,
                "last_error": reason,
                "recipient": recipient,
                "created_at": existing_comm.get("created_at") if existing_comm else now_iso,
                "sent_at": None,
                "updated_at": now_iso,
            }
            comm_col.update_one(
                {"automation_event_id": event["_id"], "channel": channel},
                {"$set": comm_doc},
                upsert=True
            )
            dispatched_communications.append(comm_doc)
            continue

        # Invoke communication provider
        prev_attempts = existing_comm.get("attempt_count", 0) if existing_comm else 0
        current_attempts = prev_attempts + 1

        body = f"Congratulations! You've unlocked VIP status (Lead Score: {event.get('lead_score')}). Enjoy 20% off your next purchase!"
        subject = "Exclusive VIP Priority Offer — Lead Magnet"

        if channel == "email":
            res = provider.send_email(recipient, subject, body, metadata={"event_id": str(event["_id"])})
        elif channel == "sms":
            res = provider.send_sms(recipient, body, metadata={"event_id": str(event["_id"])})
        elif channel == "whatsapp":
            res = provider.send_whatsapp(recipient, body, metadata={"event_id": str(event["_id"])})

        success = res.get("success", False)
        status = "sent" if success else "failed"
        prov_msg_id = res.get("provider_message_id")
        error_msg = res.get("error") if not success else None

        comm_doc = {
            "customer_id": c_id,
            "automation_event_id": event["_id"],
            "channel": channel,
            "campaign_type": "lead_qualification",
            "status": status,
            "provider": res.get("provider", "dry_run"),
            "provider_message_id": prov_msg_id,
            "attempt_count": current_attempts,
            "last_error": error_msg,
            "recipient": recipient,
            "created_at": existing_comm.get("created_at") if existing_comm else now_iso,
            "sent_at": now_iso if success else None,
            "updated_at": now_iso,
        }

        comm_col.update_one(
            {"automation_event_id": event["_id"], "channel": channel},
            {"$set": comm_doc},
            upsert=True
        )
        dispatched_communications.append(comm_doc)

    events_col.update_one(
        {"_id": event["_id"]},
        {"$set": {"status": "completed", "processed_at": now_iso}}
    )

    # Create internal admin notification
    cust_display = (profile.get("email") or str(c_id)) if profile else str(c_id)
    notif_doc = {
        "type": "lead_qualified",
        "customer_id": c_id,
        "message": f"Customer {cust_display} was newly qualified as a Hot lead (Score: {event.get('lead_score')}).",
        "read": False,
        "created_at": now_iso,
    }
    notif_col.insert_one(notif_doc)

    return {
        "event_id": str(event["_id"]),
        "customer_id": str(c_id),
        "status": "completed",
        "processed_at": now_iso,
        "communications": dispatched_communications,
    }
