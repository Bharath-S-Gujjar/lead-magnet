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


def get_store_url():
    """Return configured user storefront URL, defaulting to local user dev port http://localhost:3001.

    Controlled by environment variables in priority order:
        1. STORE_URL
        2. FRONTEND_USER_URL
        3. FRONTEND_URL

    DEVELOPMENT NOTE:
        If the resolved URL contains 'localhost', this is a local development configuration.
        Customer-facing emails sent with a localhost URL will be treated as spam by
        most inbox providers. Set STORE_URL to a real public URL before production deployment.
    """
    import warnings
    url = os.getenv("STORE_URL") or os.getenv("FRONTEND_USER_URL") or os.getenv("FRONTEND_URL")
    if url:
        first = url.split(",")[0].strip()
        resolved = first.rstrip("/")
    else:
        resolved = "http://localhost:3001"

    if "localhost" in resolved or "127.0.0.1" in resolved:
        warnings.warn(
            f"STORE_URL resolves to a localhost address ({resolved}). "
            "Emails containing localhost URLs will be classified as spam by inbox providers. "
            "Set STORE_URL to a real public URL before sending production emails.",
            stacklevel=2
        )
    return resolved


DEFAULT_CHANNEL_POLICY = {
    "email": {"enabled": True},
    "whatsapp": {"enabled": True},
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
                sparse=True,
                name="automation_event_channel_unique",
                background=True
            )
        if "idempotency_key_1" not in existing_comm_idx:
            comm_col.create_index(
                [("idempotency_key", 1)],
                unique=True,
                sparse=True,
                name="idempotency_key_1",
                background=True
            )
        if "customer_id_1" not in existing_comm_idx:
            comm_col.create_index([("customer_id", 1)], name="customer_id_1", background=True)

        existing_notif_idx = {idx["name"] for idx in notif_col.list_indexes()}
        if "customer_id_1" not in existing_notif_idx:
            notif_col.create_index([("customer_id", 1)], name="customer_id_1", background=True)

        try:
            from opportunity_engine import ensure_marketing_opportunities_indexes
            ensure_marketing_opportunities_indexes(db)
        except Exception:
            pass
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

    Supported channels: email, whatsapp ONLY. NO SMS.

    Args:
        user_profile (dict): User profile document from user_profiles collection.
        policy (dict, optional): Channel policy flags. Defaults to DEFAULT_CHANNEL_POLICY.

    Returns:
        dict: Eligibility mapping for email, whatsapp.
    """
    merged_policy = {
        "email": True,
        "whatsapp": True,
    }
    if policy:
        if "email" in policy or "email_enabled" in policy:
            merged_policy["email"] = _is_channel_enabled(policy, "email")
        if "whatsapp" in policy or "whatsapp_enabled" in policy:
            merged_policy["whatsapp"] = _is_channel_enabled(policy, "whatsapp")

    profile = user_profile or {}

    email_val = profile.get("email")
    has_valid_email = isinstance(email_val, str) and "@" in email_val and bool(email_val.strip())

    phone_val = profile.get("phone")
    has_valid_phone = isinstance(phone_val, str) and bool(phone_val.strip())

    email_enabled = merged_policy["email"]
    whatsapp_enabled = merged_policy["whatsapp"]

    email_eligible = email_enabled and has_valid_email
    whatsapp_eligible = whatsapp_enabled and has_valid_phone

    return {
        "email": {
            "eligible": email_eligible,
            "recipient": email_val if has_valid_email else None,
            "reason": "eligible" if email_eligible else ("No valid email address found" if not has_valid_email else "Email channel disabled by policy")
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
        {
            "customer_id": query_id,
            "status": "sent",
            "campaign_type": {"$nin": ["registration", "order_confirmation"]},
        },
        sort=[("sent_at", -1)]
    )

    if not last_sent:
        # Try string query fallback
        if isinstance(customer_id, str) and c_oid:
            last_sent = comms_col.find_one(
                {
                    "customer_id": str(c_oid),
                    "status": "sent",
                    "campaign_type": {"$nin": ["registration", "order_confirmation"]},
                },
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

        cust_name = (profile.get("full_name") or profile.get("username") or "there") if profile else "there"
        subject = "You might be interested in these products — Lead Magnet"

        if channel == "email":
            body = (
                f"Hi {cust_name},\n\n"
                "We noticed you were browsing our latest collection! Here are items handpicked for you.\n\n"
                "Continue shopping:\n"
                f"{get_store_url()}/shop\n\n"
                "Best regards,\n"
                "The Lead Magnet Team"
            )
            res = provider.send_email(recipient, subject, body, metadata={"event_id": str(event["_id"])})
        elif channel == "whatsapp":
            body = f"Hi {cust_name} 👋 We noticed you were interested in our latest styles! Continue shopping: {get_store_url()}/shop"
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

    # Create internal admin notification once per qualification event
    existing_notif = notif_col.find_one({
        "customer_id": str(c_id),
        "type": "lead_qualified",
        "metadata.automation_event_id": str(event["_id"]),
    })
    if not existing_notif:
        cust_display = (profile.get("full_name") or profile.get("email") or str(c_id)) if profile else str(c_id)
        notif_doc = {
            "type": "lead_qualified",
            "title": "New Hot Lead",
            "customer_id": str(c_id),
            "message": f"Customer {cust_display} was newly qualified as a Hot lead.",
            "metadata": {"automation_event_id": str(event["_id"])},
            "read": False,
            "created_at": now_iso,
        }
        notif_res = notif_col.insert_one(notif_doc)
        notif_doc["id"] = str(notif_res.inserted_id)

    return {
        "event_id": str(event["_id"]),
        "customer_id": str(c_id),
        "status": "completed",
        "processed_at": now_iso,
        "communications": dispatched_communications,
    }


# ==============================================================================
# Phase 3 Communication Engine Triggers (Registration, Cart, Wishlist, Order)
# ==============================================================================

def dispatch_communication(
    db,
    customer_id,
    campaign_type,
    channel,
    recipient,
    subject=None,
    body="",
    metadata=None,
    idempotency_key=None,
    provider=None,
    automation_event_id=None,
    html_body=None,
):
    """Deterministically dispatch a single communication on a channel and log to marketing_communications.

    Evaluates channel independently.
    Ensures safe error handling if provider fails or credentials are missing.
    Does NOT report 'sent' when provider delivery failed or was skipped.
    """
    comm_col = db["marketing_communications"]
    c_oid = _to_object_id(customer_id)
    query_id = c_oid if c_oid else customer_id
    now_iso = datetime.now(timezone.utc).isoformat()

    # 1. Idempotency Check
    if idempotency_key:
        existing = comm_col.find_one({"idempotency_key": idempotency_key})
        if existing:
            # If already sent, do not resend
            if existing.get("status") == "sent":
                return existing
            # If already skipped or processing, return existing
            if existing.get("status") in ("skipped", "processing"):
                return existing

    # 2. Recipient validation
    if not recipient or not str(recipient).strip():
        comm_doc = {
            "customer_id": query_id,
            "automation_event_id": automation_event_id,
            "campaign_type": campaign_type,
            "channel": channel,
            "status": "skipped",
            "provider": getattr(provider, "__class__", type).__name__ if provider else "none",
            "provider_message_id": None,
            "attempt_count": 0,
            "last_error": f"Missing or invalid recipient for {channel}",
            "recipient": None,
            "subject": subject,
            "body": body,
            "metadata": metadata or {},
            "idempotency_key": idempotency_key,
            "created_at": now_iso,
            "sent_at": None,
            "updated_at": now_iso,
        }
        if idempotency_key:
            res_up = comm_col.update_one({"idempotency_key": idempotency_key}, {"$set": comm_doc}, upsert=True)
            if res_up.upserted_id:
                comm_doc["_id"] = res_up.upserted_id
            else:
                existing = comm_col.find_one({"idempotency_key": idempotency_key}, {"_id": 1})
                if existing:
                    comm_doc["_id"] = existing["_id"]
        else:
            res = comm_col.insert_one(comm_doc)
            comm_doc["_id"] = res.inserted_id
        return comm_doc

    if channel == "email" and "@" not in str(recipient):
        comm_doc = {
            "customer_id": query_id,
            "automation_event_id": automation_event_id,
            "campaign_type": campaign_type,
            "channel": channel,
            "status": "skipped",
            "provider": getattr(provider, "__class__", type).__name__ if provider else "none",
            "provider_message_id": None,
            "attempt_count": 0,
            "last_error": f"Invalid email format: {recipient}",
            "recipient": recipient,
            "subject": subject,
            "body": body,
            "metadata": metadata or {},
            "idempotency_key": idempotency_key,
            "created_at": now_iso,
            "sent_at": None,
            "updated_at": now_iso,
        }
        if idempotency_key:
            res_up = comm_col.update_one({"idempotency_key": idempotency_key}, {"$set": comm_doc}, upsert=True)
            if res_up.upserted_id:
                comm_doc["_id"] = res_up.upserted_id
            else:
                existing = comm_col.find_one({"idempotency_key": idempotency_key}, {"_id": 1})
                if existing:
                    comm_doc["_id"] = existing["_id"]
        else:
            res = comm_col.insert_one(comm_doc)
            comm_doc["_id"] = res.inserted_id
        return comm_doc

    # 3. Provider resolution
    if provider is None:
        provider = get_communication_provider()

    # 4. Dispatch
    if channel == "email":
        img_url = None
        if isinstance(metadata, dict):
            img_url = metadata.get("primary_image") or metadata.get("image_url") or metadata.get("product_image")
        rendered_html = html_body if html_body else (metadata.get("html_body") if isinstance(metadata, dict) else None)
        if not rendered_html and img_url:
            from communication_provider import _build_html_body
            rendered_html = _build_html_body(body, image_url=img_url)

        try:
            res = provider.send_email(
                recipient,
                subject or "Lead Magnet",
                body,
                metadata=metadata,
                html_body=rendered_html,
            )
        except TypeError:
            res = provider.send_email(
                recipient,
                subject or "Lead Magnet",
                body,
                metadata=metadata,
            )
    elif channel == "whatsapp":
        res = provider.send_whatsapp(recipient, body, metadata=metadata)
    else:
        # SMS or unsupported channels are ignored
        return None

    success = bool(res.get("success", False))
    status = "sent" if success else "failed"
    prov_name = res.get("provider", "unknown")
    prov_msg_id = res.get("provider_message_id")
    error_msg = res.get("error") if not success else None

    comm_doc = {
        "customer_id": query_id,
        "automation_event_id": automation_event_id,
        "campaign_type": campaign_type,
        "channel": channel,
        "status": status,
        "provider": prov_name,
        "provider_message_id": prov_msg_id,
        "attempt_count": 1,
        "last_error": error_msg,
        "recipient": recipient,
        "subject": subject,
        "body": body,
        "metadata": metadata or {},
        "idempotency_key": idempotency_key,
        "created_at": now_iso,
        "sent_at": now_iso if success else None,
        "updated_at": now_iso,
    }

    if idempotency_key:
        res_up = comm_col.update_one({"idempotency_key": idempotency_key}, {"$set": comm_doc}, upsert=True)
        if res_up.upserted_id:
            comm_doc["_id"] = res_up.upserted_id
        else:
            existing = comm_col.find_one({"idempotency_key": idempotency_key}, {"_id": 1})
            if existing:
                comm_doc["_id"] = existing["_id"]
    else:
        res_db = comm_col.insert_one(comm_doc)
        comm_doc["_id"] = res_db.inserted_id

    return comm_doc


def trigger_registration_communication(customer_id, db, provider=None, policy=None):
    """Trigger customer registration welcome communication.

    Classification: TRANSACTIONAL
        Sent once per customer upon account creation.
        Not subject to marketing unsubscribe.
        Does not contain lead scores, ML probabilities, or internal intelligence.

    Channels:
        Email: One welcome email.
        WhatsApp: One welcome message only if phone number present and allowed.

    Frequency:
        ONE TIME PER CUSTOMER. Idempotent key per customer and channel.
    """
    profiles_col = db["user_profiles"]
    c_oid = _to_object_id(customer_id)
    profile = profiles_col.find_one({"_id": c_oid}) if c_oid else profiles_col.find_one({"_id": customer_id})
    if not profile and isinstance(customer_id, str):
        profile = profiles_col.find_one({"user_id": customer_id})

    if not profile:
        return {}

    eligibility = evaluate_channel_eligibility(profile, policy)
    name = profile.get("full_name") or profile.get("username") or "there"

    # TRANSACTIONAL - subject accurately describes the email, no fake Re:/Fwd:
    email_subject = "Welcome to Lead Magnet"
    email_body = (
        f"Hi {name},\n\n"
        "Welcome to Lead Magnet! We're thrilled to have you with us.\n"
        "Explore our latest clothing collections and discover styles tailored for you.\n\n"
        "Start shopping:\n"
        f"{get_store_url()}\n\n"
        "Best regards,\n"
        "The Lead Magnet Team"
    )

    wa_body = (
        f"Hi {name} 👋 Welcome to Lead Magnet! "
        f"Explore our latest clothing collections: {get_store_url()}"
    )

    results = {}

    # Email
    email_key = f"welcome:{str(customer_id)}:email"
    email_info = eligibility["email"]
    if email_info["eligible"]:
        results["email"] = dispatch_communication(
            db, customer_id, "registration", "email",
            email_info["recipient"], subject=email_subject, body=email_body,
            idempotency_key=email_key, provider=provider
        )
    else:
        results["email"] = dispatch_communication(
            db, customer_id, "registration", "email",
            None, subject=email_subject, body=email_body,
            idempotency_key=email_key, provider=provider
        )

    # WhatsApp (only when eligible)
    wa_key = f"welcome:{str(customer_id)}:whatsapp"
    wa_info = eligibility["whatsapp"]
    if wa_info["eligible"]:
        results["whatsapp"] = dispatch_communication(
            db, customer_id, "registration", "whatsapp",
            wa_info["recipient"], body=wa_body,
            idempotency_key=wa_key, provider=provider
        )
    else:
        results["whatsapp"] = dispatch_communication(
            db, customer_id, "registration", "whatsapp",
            None, body=wa_body,
            idempotency_key=wa_key, provider=provider
        )

    return results


def trigger_lead_qualification_communication(customer_id, lead_state_doc=None, db=None, provider=None, policy=None):
    """Trigger personalized marketing communication when customer newly qualifies as Hot lead.

    Classification: MARKETING
        Triggered when customer transitions from not qualified to qualified/Hot.
        Subject to marketing cooldowns (72h) and unsubscribe preferences.
        Rich content with current cart/wishlist/views.
        NEVER exposes internal lead score, ML probability, or model metadata.

    Policy:
        - Trigger ONLY on NOT QUALIFIED -> QUALIFIED / HOT.
        - NOT on Hot -> Hot.
        - NOT on Warm (0.35 <= prob < 0.70).
        - NOT on Cold (prob < 0.35).
        - Enforces 72-hour cooldown.
    """
    if db is None:
        return None

    c_oid = _to_object_id(customer_id)
    if lead_state_doc is None:
        lead_state_doc = db["customer_lead_state"].find_one({"customer_id": c_oid or customer_id}) or {}

    transition = lead_state_doc.get("qualification_transition")
    is_newly = lead_state_doc.get("is_newly_qualified", False)
    segment = lead_state_doc.get("lead_segment")
    prob = float(lead_state_doc.get("lead_probability") or 0.0)
    score = int(lead_state_doc.get("lead_score") or 0)

    # Check 1: ONLY Hot / Qualified leads (prob >= 0.70 or score >= 70 or segment == "Hot")
    if segment != "Hot" and prob < 0.70 and score < 70:
        return {"skipped": True, "reason": "Customer is not a Hot qualified lead"}

    # Check 2: MUST be a transition into qualified (Not Qualified -> Qualified)
    if transition != "not_qualified_to_qualified" and not is_newly:
        return {"skipped": True, "reason": "No qualification transition (Hot -> Hot ignored)"}

    # Check 3: Cooldown check (72 hours)
    if _is_within_cooldown(customer_id, db):
        return {"skipped": True, "reason": f"Within {MARKETING_COOLDOWN_HOURS}h qualification cooldown"}

    profile = db["user_profiles"].find_one({"_id": c_oid}) if c_oid else db["user_profiles"].find_one({"_id": customer_id})
    name = (profile.get("full_name") or profile.get("username") or "there") if profile else "there"

    # Context 1: Current cart (do not reconstruct from history)
    cart = db["cart"].find_one({"$or": [{"user_id": c_oid}, {"user_id": str(c_oid)}]}) if c_oid else None
    cart_items = (cart.get("items") or []) if cart else []
    cart_total = float(cart.get("total_amount") or 0.0) if cart else 0.0

    # Context 2: Current wishlist
    wishlist = db["wishlist"].find_one({"$or": [{"user_id": c_oid}, {"user_id": str(c_oid)}]}) if c_oid else None
    wishlist_items = (wishlist.get("items") or []) if wishlist else []

    # Context 3: Recent views
    recent_events = list(db["events"].find(
        {"$or": [{"user_id": c_oid}, {"user_id": str(c_oid)}], "type": "product_view"},
        sort=[("timestamp", -1)]
    ).limit(5)) if c_oid else []

    interested_names = []
    for it in cart_items[:2]:
        t = it.get("title") or it.get("name")
        if t and t not in interested_names:
            interested_names.append(t)
    for it in wishlist_items[:2]:
        t = it.get("title") or it.get("name")
        if t and t not in interested_names:
            interested_names.append(t)
    for ev in recent_events[:2]:
        t = (ev.get("product_data") or {}).get("name") or (ev.get("product_data") or {}).get("title")
        if t and t not in interested_names:
            interested_names.append(t)

    items_text = "\n".join([f"• {item}" for item in interested_names]) if interested_names else "• Premium Trending Apparel"
    cart_context = f"\nYour cart currently contains {len(cart_items)} item(s).\n" if cart_items else ""

    # MARKETING - subject accurately describes content, no fake Re:/Fwd:, no deceptive urgency
    # Internal lead scores and ML probabilities are NEVER included in customer-facing content
    email_subject = "You may be interested in these products — Lead Magnet"
    email_body = (
        f"Hi {name},\n\n"
        "We noticed you were browsing our latest collection! Here are items handpicked for you:\n\n"
        f"{items_text}\n"
        f"{cart_context}\n"
        "Continue shopping:\n"
        f"{get_store_url()}/shop\n\n"
        "Best regards,\n"
        "The Lead Magnet Team"
    )

    first_item = interested_names[0] if interested_names else "our latest styles"
    wa_cart_text = f"Your current cart contains {len(cart_items)} item(s). " if cart_items else ""
    wa_body = (
        f"Hi {name} 👋\n\n"
        f"We noticed you were interested in: {first_item}.\n"
        f"{wa_cart_text}"
        f"Continue shopping: {get_store_url()}/shop"
    )

    last_qual = lead_state_doc.get("last_qualified_at") or lead_state_doc.get("first_qualified_at") or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    eligibility = evaluate_channel_eligibility(profile, policy)
    results = {}

    email_key = f"lead_qualified:{str(customer_id)}:{last_qual}:email"
    email_info = eligibility["email"]
    if email_info["eligible"]:
        results["email"] = dispatch_communication(
            db, customer_id, "lead_qualified", "email",
            email_info["recipient"], subject=email_subject, body=email_body,
            idempotency_key=email_key, provider=provider
        )
    else:
        results["email"] = dispatch_communication(
            db, customer_id, "lead_qualified", "email",
            None, subject=email_subject, body=email_body,
            idempotency_key=email_key, provider=provider
        )

    wa_key = f"lead_qualified:{str(customer_id)}:{last_qual}:whatsapp"
    wa_info = eligibility["whatsapp"]
    if wa_info["eligible"]:
        results["whatsapp"] = dispatch_communication(
            db, customer_id, "lead_qualified", "whatsapp",
            wa_info["recipient"], body=wa_body,
            idempotency_key=wa_key, provider=provider
        )
    else:
        results["whatsapp"] = dispatch_communication(
            db, customer_id, "lead_qualified", "whatsapp",
            None, body=wa_body,
            idempotency_key=wa_key, provider=provider
        )

    return results


def trigger_cart_abandonment_communication(customer_id, db, provider=None, policy=None, abandonment_delay_hours=1):
    """Trigger cart abandonment reminder based on CURRENT cart state.

    Classification: MARKETING
        Triggered when customer leaves active items in cart after configured delay.
        Subject to marketing cooldowns and unsubscribe preferences.
        Cancelled if order placed.

    Rules:
        - Must have active cart items.
        - Does NOT reconstruct cart from historical events.
        - If cart empty: DO NOT send.
        - If order was placed AFTER cart was last updated: DO NOT send (order invalidates reminder).
        - Max 1 communication per cart cycle.
    """
    if db is None or not customer_id:
        return {"skipped": True, "reason": "Missing db or customer_id"}

    c_oid = _to_object_id(customer_id)
    cart = db["cart"].find_one({"$or": [{"user_id": c_oid}, {"user_id": str(c_oid)}]}) if c_oid else None
    if not cart or not cart.get("items"):
        return {"skipped": True, "reason": "Cart is currently empty"}

    items = cart.get("items", [])
    if len(items) == 0:
        return {"skipped": True, "reason": "Cart is currently empty"}

    cart_updated = cart.get("updated_at")
    if isinstance(cart_updated, str):
        try:
            cart_updated_dt = datetime.fromisoformat(cart_updated)
        except Exception:
            cart_updated_dt = datetime.now(timezone.utc)
    elif isinstance(cart_updated, datetime):
        cart_updated_dt = cart_updated
    else:
        cart_updated_dt = datetime.now(timezone.utc)

    if cart_updated_dt.tzinfo is None:
        cart_updated_dt = cart_updated_dt.replace(tzinfo=timezone.utc)

    # Check if customer placed an order after cart was last updated
    latest_order = db["orders"].find_one(
        {"$or": [{"user_id": c_oid}, {"user_id": str(c_oid)}]},
        sort=[("created_at", -1)]
    ) if c_oid else None

    if latest_order:
        order_created = latest_order.get("created_at")
        if isinstance(order_created, str):
            try:
                order_created_dt = datetime.fromisoformat(order_created)
            except Exception:
                order_created_dt = datetime.now(timezone.utc)
        elif isinstance(order_created, datetime):
            order_created_dt = order_created
        else:
            order_created_dt = datetime.now(timezone.utc)

        if order_created_dt.tzinfo is None:
            order_created_dt = order_created_dt.replace(tzinfo=timezone.utc)

        if order_created_dt >= cart_updated_dt:
            return {"skipped": True, "reason": "Completed order invalidates cart abandonment reminder"}

    # Configurable delay check
    if abandonment_delay_hours > 0:
        elapsed_sec = (datetime.now(timezone.utc) - cart_updated_dt).total_seconds()
        if elapsed_sec < (abandonment_delay_hours * 3600):
            return {"skipped": True, "reason": "Abandonment delay period has not elapsed"}

    profile = db["user_profiles"].find_one({"_id": c_oid}) if c_oid else None
    name = (profile.get("full_name") or profile.get("username") or "there") if profile else "there"

    total_amount = float(cart.get("total_amount") or 0.0)
    total_qty = sum(int(it.get("quantity") or 1) for it in items)

    item_lines = "\n".join([f"• {it.get('title') or it.get('name', 'Product')} x{it.get('quantity', 1)} — ₹{float(it.get('price', 0)):,.2f}" for it in items[:3]])

    # MARKETING - accurate descriptive subject, no fake Re:/Fwd:, no deceptive urgency
    email_subject = "You left items in your Lead Magnet cart"
    email_body = (
        f"Hi {name},\n\n"
        "You left items waiting in your shopping cart:\n\n"
        f"{item_lines}\n\n"
        f"Total: ₹{total_amount:,.2f}\n\n"
        "Complete your purchase here:\n"
        f"{get_store_url()}/cart\n\n"
        "Best regards,\n"
        "The Lead Magnet Team"
    )

    wa_body = (
        f"Hi {name} 👋 You left {total_qty} item(s) in your cart! "
        f"Complete your order here: {get_store_url()}/cart"
    )

    cart_updated_key = cart_updated_dt.strftime("%Y-%m-%dT%H")
    eligibility = evaluate_channel_eligibility(profile, policy)
    results = {}

    email_key = f"cart_abandoned:{str(customer_id)}:{cart_updated_key}:email"
    email_info = eligibility["email"]
    if email_info["eligible"]:
        results["email"] = dispatch_communication(
            db, customer_id, "cart_abandoned", "email",
            email_info["recipient"], subject=email_subject, body=email_body,
            idempotency_key=email_key, provider=provider
        )
    else:
        results["email"] = dispatch_communication(
            db, customer_id, "cart_abandoned", "email",
            None, subject=email_subject, body=email_body,
            idempotency_key=email_key, provider=provider
        )

    wa_key = f"cart_abandoned:{str(customer_id)}:{cart_updated_key}:whatsapp"
    wa_info = eligibility["whatsapp"]
    if wa_info["eligible"]:
        results["whatsapp"] = dispatch_communication(
            db, customer_id, "cart_abandoned", "whatsapp",
            wa_info["recipient"], body=wa_body,
            idempotency_key=wa_key, provider=provider
        )
    else:
        results["whatsapp"] = dispatch_communication(
            db, customer_id, "cart_abandoned", "whatsapp",
            None, body=wa_body,
            idempotency_key=wa_key, provider=provider
        )

    return results


def trigger_wishlist_reminder_communication(customer_id, db, provider=None, policy=None, reminder_delay_days=7):
    """Trigger wishlist reminder based on CURRENT wishlist state.

    Classification: MARKETING
        Triggered for customers with saved items in current wishlist.
        Subject to 7-day cooldown and unsubscribe preferences.

    Rules:
        - Must have items in CURRENT wishlist.
        - Empty wishlist prevents reminder.
        - Enforces 7-day cooldown between wishlist reminders.
    """
    if db is None or not customer_id:
        return {"skipped": True, "reason": "Missing db or customer_id"}

    c_oid = _to_object_id(customer_id)
    wishlist = db["wishlist"].find_one({"$or": [{"user_id": c_oid}, {"user_id": str(c_oid)}]}) if c_oid else None
    if not wishlist or not wishlist.get("items"):
        return {"skipped": True, "reason": "Wishlist is currently empty"}

    items = wishlist.get("items", [])
    if len(items) == 0:
        return {"skipped": True, "reason": "Wishlist is currently empty"}

    # Cooldown check: 7 days
    if reminder_delay_days > 0:
        last_reminder = db["marketing_communications"].find_one(
            {"customer_id": c_oid or customer_id, "campaign_type": "wishlist_reminder", "status": "sent"},
            sort=[("sent_at", -1)]
        )
        if last_reminder and last_reminder.get("sent_at"):
            sent_at_val = last_reminder["sent_at"]
            if isinstance(sent_at_val, str):
                try:
                    sent_at_dt = datetime.fromisoformat(sent_at_val)
                except Exception:
                    sent_at_dt = datetime.now(timezone.utc)
            elif isinstance(sent_at_val, datetime):
                sent_at_dt = sent_at_val
            else:
                sent_at_dt = datetime.now(timezone.utc)

            if sent_at_dt.tzinfo is None:
                sent_at_dt = sent_at_dt.replace(tzinfo=timezone.utc)

            if datetime.now(timezone.utc) < (sent_at_dt + timedelta(days=reminder_delay_days)):
                return {"skipped": True, "reason": f"Wishlist reminder within {reminder_delay_days}-day cooldown"}

    profile = db["user_profiles"].find_one({"_id": c_oid}) if c_oid else None
    name = (profile.get("full_name") or profile.get("username") or "there") if profile else "there"

    item_lines = "\n".join([f"• {it.get('title') or it.get('name', 'Saved Item')} — ₹{float(it.get('price', 0)):,.2f}" for it in items[:3]])

    # MARKETING - accurate descriptive subject, no fake Re:/Fwd:, no deceptive urgency
    email_subject = "Items you saved are still waiting for you"
    email_body = (
        f"Hi {name},\n\n"
        "Items in your wishlist are still waiting for you:\n\n"
        f"{item_lines}\n\n"
        "View your wishlist and shop:\n"
        f"{get_store_url()}/wishlist\n\n"
        "Best regards,\n"
        "The Lead Magnet Team"
    )

    wa_body = (
        f"Hi {name} 👋 Items you saved in your wishlist are still waiting for you! "
        f"Take a look: {get_store_url()}/wishlist"
    )

    window = datetime.now(timezone.utc).strftime("%Y-W%W")
    eligibility = evaluate_channel_eligibility(profile, policy)
    results = {}

    email_key = f"wishlist_reminder:{str(customer_id)}:{window}:email"
    email_info = eligibility["email"]
    if email_info["eligible"]:
        results["email"] = dispatch_communication(
            db, customer_id, "wishlist_reminder", "email",
            email_info["recipient"], subject=email_subject, body=email_body,
            idempotency_key=email_key, provider=provider
        )
    else:
        results["email"] = dispatch_communication(
            db, customer_id, "wishlist_reminder", "email",
            None, subject=email_subject, body=email_body,
            idempotency_key=email_key, provider=provider
        )

    wa_key = f"wishlist_reminder:{str(customer_id)}:{window}:whatsapp"
    wa_info = eligibility["whatsapp"]
    if wa_info["eligible"]:
        results["whatsapp"] = dispatch_communication(
            db, customer_id, "wishlist_reminder", "whatsapp",
            wa_info["recipient"], body=wa_body,
            idempotency_key=wa_key, provider=provider
        )
    else:
        results["whatsapp"] = dispatch_communication(
            db, customer_id, "wishlist_reminder", "whatsapp",
            None, body=wa_body,
            idempotency_key=wa_key, provider=provider
        )

    return results


def trigger_order_confirmation_communication(order_id, db, provider=None, policy=None):
    """Trigger transactional order confirmation communication.

    Classification: TRANSACTIONAL
        Sent once per successfully created order.
        Not subject to marketing unsubscribe.
        Does not contain marketing promotions, lead scores, or internal intelligence.

    Policy:
        - Transactional (NOT lead qualification marketing).
        - One confirmation per successfully created order.
        - Idempotency key per order_id and channel.
        - NO lead score or ML metrics.
    """
    if db is None or not order_id:
        return {}

    o_oid = _to_object_id(order_id)
    order = db["orders"].find_one({"_id": o_oid}) if o_oid else db["orders"].find_one({"_id": order_id})
    if not order and isinstance(order_id, str):
        order = db["orders"].find_one({"order_id": order_id})

    if not order:
        return {}

    user_id = order.get("user_id")
    profile = db["user_profiles"].find_one({"_id": _to_object_id(user_id)}) if user_id else None

    name = (
        (profile.get("full_name") or profile.get("username") or profile.get("email"))
        if profile else (order.get("customer_name") or order.get("customer_email") or "Customer")
    )

    recipient_email = (profile.get("email") if profile else None) or order.get("customer_email")
    recipient_phone = (profile.get("phone") if profile else None) or order.get("customer_phone")

    items = order.get("items") or []
    total_amount = float(order.get("total_amount") or 0.0)
    order_status = order.get("status", "placed")

    item_lines = "\n".join([f"• {it.get('title') or it.get('name', 'Item')} x{it.get('quantity', 1)} — ₹{float(it.get('price', 0)):,.2f}" for it in items[:4]])

    # TRANSACTIONAL - accurate descriptive subject, no fake Re:/Fwd:, no deceptive urgency
    email_subject = f"Your Lead Magnet order confirmation (Order #{str(order_id)[:8]})"
    email_body = (
        f"Hi {name},\n\n"
        f"Thank you for your order! We've received order #{str(order_id)[:8]}.\n\n"
        f"Items:\n{item_lines}\n\n"
        f"Total Amount: ₹{total_amount:,.2f}\n"
        f"Status: {order_status.capitalize()}\n\n"
        "View your order details:\n"
        f"{get_store_url()}/account\n\n"
        "Best regards,\n"
        "The Lead Magnet Team"
    )

    wa_body = (
        f"Hi {name} 👋 Thank you for your order #{str(order_id)[:8]} of ₹{total_amount:,.2f}! "
        f"Status: {order_status.capitalize()}. View order: {get_store_url()}/account"
    )

    results = {}

    # Email
    email_key = f"order_confirmation:{str(order_id)}:email"
    results["email"] = dispatch_communication(
        db, user_id, "order_confirmation", "email",
        recipient_email, subject=email_subject, body=email_body,
        metadata={"order_id": str(order_id), "total_amount": total_amount},
        idempotency_key=email_key, provider=provider
    )

    # WhatsApp (only when eligible phone exists)
    wa_key = f"order_confirmation:{str(order_id)}:whatsapp"
    results["whatsapp"] = dispatch_communication(
        db, user_id, "order_confirmation", "whatsapp",
        recipient_phone, body=wa_body,
        metadata={"order_id": str(order_id), "total_amount": total_amount},
        idempotency_key=wa_key, provider=provider
    )

    return results


def trigger_opportunity_communication(
    customer_id,
    db,
    provider=None,
    policy=None,
    lead_state_doc=None,
    opportunity_cooldown_hours=24,
    current_time=None,
):
    """Trigger targeted opportunity email communication for an eligible customer.

    Evaluates:
        - Lead status (Hot >= 0.70 or significant Hot -> Warm decline)
        - Customer interests (cart, wishlist, views)
        - Catalog offers / discounts (real discounts only)
        - Similar product recommendations
        - Opportunity idempotency
        - Cooldown safeguards
    """
    from opportunity_engine import process_customer_opportunities
    return process_customer_opportunities(
        customer_id=customer_id,
        db=db,
        provider=provider,
        policy=policy,
        lead_state_doc=lead_state_doc,
        opportunity_cooldown_hours=opportunity_cooldown_hours,
        current_time=current_time,
    )


def trigger_product_price_drop_communication(
    customer_id,
    opportunity_or_key,
    db,
    provider=None,
    policy=None,
    enforce_cooldown=True,
    current_time=None,
):
    """Trigger customer-facing email communication for a product_price_drop opportunity.

    Classification: MARKETING
        Triggered when an eligible price-drop opportunity is detected for an interested customer.
        Subject to 24-hour promotional opportunity cooldown and unsubscribe preferences.
        Reuses existing communication engine and Gmail SMTP provider.
        Contains product name, current price, old price, discount info, product link, and image.
        Customer-facing email NEVER exposes internal lead score, ML probability, or model metadata.

    Args:
        customer_id: ObjectId or string customer identifier.
        opportunity_or_key: Opportunity doc, key string, or ObjectId.
        db: PyMongo database object.
        provider (CommunicationProvider, optional): Communication provider instance.
        policy (dict, optional): Channel policy overrides.
        enforce_cooldown (bool): Whether to enforce 24-hour opportunity cooldown.
        current_time (datetime, optional): Reference time for cooldown/timestamps.

    Returns:
        dict: Result summary with status, communication record, and provider info.
    """
    from price_drop_opportunity_service import dispatch_price_drop_opportunity
    return dispatch_price_drop_opportunity(
        opportunity_or_key=opportunity_or_key,
        db=db,
        provider=provider,
        policy=policy,
        enforce_cooldown=enforce_cooldown,
        current_time=current_time,
    )

