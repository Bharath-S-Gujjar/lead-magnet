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
from communication_provider import (
    get_communication_provider,
    DryRunCommunicationProvider,
    normalize_whatsapp_phone,
)
from scoring_constants import HOT, WARM, HOT_PROBABILITY_EQUIV, WARM_PROBABILITY_EQUIV


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


TRANSACTIONAL_CAMPAIGNS = {"registration", "order_confirmation"}


def evaluate_channel_eligibility(user_profile, policy=None, campaign_type=None, classification=None):
    """Determine channel eligibility based on contact info, active policy, and explicit consent.

    Supported channels: email, whatsapp ONLY. NO SMS.

    Policy & Consent Rules:
        - Email: eligible if email channel is enabled and valid RFC-compliant email exists.
        - WhatsApp Usability: phone number must exist and be valid E.164 with international
          country code (normalized via normalize_whatsapp_phone).
        - WhatsApp Opt-Out: customer opt-out strictly overrides opt-in and immediately makes
          WhatsApp ineligible for both promotional and transactional messaging.
        - Promotional WhatsApp: strictly requires explicit opt-in (whatsapp_opt_in == True).
          Defaults to False for customers with no recorded consent.
        - Transactional WhatsApp: allowed for transactional campaigns (registration, order_confirmation)
          with a valid usable phone number, provided customer has not opted out. Does not grant
          permission to send marketing/promotional messages.

    Args:
        user_profile (dict): User profile document from user_profiles collection.
        policy (dict, optional): Channel policy flags. Defaults to DEFAULT_CHANNEL_POLICY.
        campaign_type (str, optional): Campaign identifier (e.g. 'registration', 'lead_qualified', 'cart_abandoned').
        classification (str, optional): 'transactional' or 'promotional'. Inferred from campaign_type if None.

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
        if campaign_type is None and "campaign_type" in policy:
            campaign_type = policy["campaign_type"]
        if classification is None and "classification" in policy:
            classification = policy["classification"]

    profile = user_profile or {}

    # Email channel evaluation (unchanged)
    email_val = profile.get("email")
    has_valid_email = isinstance(email_val, str) and "@" in email_val and bool(email_val.strip())
    email_enabled = merged_policy["email"]
    email_eligible = email_enabled and has_valid_email

    # Determine message classification: transactional vs promotional
    is_transactional = False
    if classification:
        is_transactional = str(classification).strip().lower() == "transactional"
    elif campaign_type:
        is_transactional = str(campaign_type).strip().lower() in TRANSACTIONAL_CAMPAIGNS

    # Validate phone and usability for WhatsApp
    phone_val = profile.get("phone")
    has_valid_phone = False
    phone_unusable_reason = None
    clean_phone_str = None

    if not phone_val or not str(phone_val).strip():
        phone_unusable_reason = "No phone number found"
    else:
        clean_phone_str = str(phone_val).strip()
        _, norm_err = normalize_whatsapp_phone(clean_phone_str)
        if norm_err:
            phone_unusable_reason = f"Invalid WhatsApp phone number: {norm_err}"
        else:
            has_valid_phone = True

    # Consent fields: default existing/unspecified customers to False
    whatsapp_opt_out = bool(profile.get("whatsapp_opt_out", False))
    whatsapp_opt_in = bool(profile.get("whatsapp_opt_in", False) or profile.get("whatsapp_promotional_consent", False))
    whatsapp_enabled = merged_policy["whatsapp"]

    if not whatsapp_enabled:
        whatsapp_eligible = False
        whatsapp_reason = "WhatsApp channel disabled by policy"
    elif whatsapp_opt_out:
        # Opt-out strictly overrides opt-in and immediately makes WhatsApp ineligible
        whatsapp_eligible = False
        whatsapp_reason = "Customer has opted out of WhatsApp communications"
    elif not has_valid_phone:
        whatsapp_eligible = False
        whatsapp_reason = phone_unusable_reason
    elif is_transactional:
        # Transactional messages do not require promotional opt-in, provided valid phone & not opted out
        whatsapp_eligible = True
        whatsapp_reason = "eligible"
    else:
        # Promotional / Marketing messages strictly require explicit opt-in
        if whatsapp_opt_in:
            whatsapp_eligible = True
            whatsapp_reason = "eligible"
        else:
            whatsapp_eligible = False
            whatsapp_reason = "Customer has not opted in to promotional WhatsApp messages"

    return {
        "email": {
            "eligible": email_eligible,
            "recipient": email_val if has_valid_email else None,
            "reason": "eligible" if email_eligible else ("No valid email address found" if not has_valid_email else "Email channel disabled by policy")
        },
        "whatsapp": {
            "eligible": whatsapp_eligible,
            "recipient": clean_phone_str if has_valid_phone else None,
            "reason": whatsapp_reason
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
        provider = get_communication_provider()

    if policy is None:
        policy = DEFAULT_CHANNEL_POLICY

    c_id = event["customer_id"]
    c_oid = _to_object_id(c_id)
    profile = profiles_col.find_one({"_id": c_oid}) if c_oid else profiles_col.find_one({"_id": c_id})
    if not profile and isinstance(c_id, str):
        profile = profiles_col.find_one({"user_id": c_id})

    eligibility = evaluate_channel_eligibility(profile, policy, campaign_type="lead_qualification")
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

    eligibility = evaluate_channel_eligibility(profile, policy, campaign_type="registration")
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

    # Check 1: ONLY Hot / Qualified leads (segment == Hot OR prob >= HOT_PROBABILITY_EQUIV OR score >= HOT)
    if segment != "Hot" and prob < HOT_PROBABILITY_EQUIV and score < HOT:
        return {"skipped": True, "reason": f"Customer is not a Hot qualified lead (score < {HOT})"}

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

    from channel_selector_service import (
        select_communication_channel,
        determine_opportunity_preference,
    )

    pref_policy = determine_opportunity_preference("lead_qualified", policy=policy, user_profile=profile)
    selection = select_communication_channel(
        user_profile=profile,
        campaign_type="lead_qualified",
        classification="promotional",
        policy=policy,
        preference_policy=pref_policy,
    )

    if not selection.get("eligible") or not selection.get("channel"):
        return {"skipped": True, "reason": selection.get("reason", "No eligible communication channel available")}

    selected_channel = selection["channel"]
    recipient = selection["recipient"]
    results = {
        "channel": selected_channel,
        "selected_channel": selected_channel,
    }

    if selected_channel == "whatsapp":
        wa_key = f"lead_qualified:{str(customer_id)}:{last_qual}:whatsapp"
        results["whatsapp"] = dispatch_communication(
            db, customer_id, "lead_qualified", "whatsapp",
            recipient, body=wa_body,
            idempotency_key=wa_key, provider=provider
        )
    else:
        email_key = f"lead_qualified:{str(customer_id)}:{last_qual}:email"
        results["email"] = dispatch_communication(
            db, customer_id, "lead_qualified", "email",
            recipient, subject=email_subject, body=email_body,
            idempotency_key=email_key, provider=provider
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
    engine_opp_key = f"opp:{str(c_oid or customer_id)}:cart_abandonment:{cart_updated_key}"

    # Check cross-path and channel idempotency
    existing_comm = db["marketing_communications"].find_one({
        "customer_id": c_oid or customer_id,
        "status": "sent",
        "$or": [
            {"idempotency_key": f"cart_abandoned:{str(customer_id)}:{cart_updated_key}:email"},
            {"idempotency_key": f"cart_abandoned:{str(customer_id)}:{cart_updated_key}:whatsapp"},
            {"idempotency_key": f"{engine_opp_key}:email"},
            {"idempotency_key": f"{engine_opp_key}:whatsapp"},
            {"metadata.opportunity_key": engine_opp_key},
        ]
    })
    if existing_comm:
        channel_used = existing_comm.get("channel", "email")
        return {
            channel_used: existing_comm,
            "channel": channel_used,
            "selected_channel": channel_used,
            "skipped": False,
        }

    from channel_selector_service import (
        select_communication_channel,
        determine_opportunity_preference,
    )

    pref_policy = determine_opportunity_preference("cart_abandoned", policy=policy, user_profile=profile)
    selection = select_communication_channel(
        user_profile=profile,
        campaign_type="cart_abandoned",
        classification="promotional",
        policy=policy,
        preference_policy=pref_policy,
    )

    if not selection.get("eligible") or not selection.get("channel"):
        return {"skipped": True, "reason": selection.get("reason", "No eligible communication channel available")}

    selected_channel = selection["channel"]
    recipient = selection["recipient"]
    results = {
        "channel": selected_channel,
        "selected_channel": selected_channel,
    }

    if selected_channel == "whatsapp":
        wa_key = f"cart_abandoned:{str(customer_id)}:{cart_updated_key}:whatsapp"
        results["whatsapp"] = dispatch_communication(
            db, customer_id, "cart_abandoned", "whatsapp",
            recipient, body=wa_body,
            metadata={"cart_updated_at": cart_updated_dt.isoformat(), "opportunity_key": engine_opp_key},
            idempotency_key=wa_key, provider=provider
        )
    else:
        email_key = f"cart_abandoned:{str(customer_id)}:{cart_updated_key}:email"
        results["email"] = dispatch_communication(
            db, customer_id, "cart_abandoned", "email",
            recipient, subject=email_subject, body=email_body,
            metadata={"cart_updated_at": cart_updated_dt.isoformat(), "opportunity_key": engine_opp_key},
            idempotency_key=email_key, provider=provider
        )

    # Sync state with marketing_opportunities if present
    comm_record = results.get(selected_channel)
    if comm_record and comm_record.get("status") == "sent":
        try:
            if "marketing_opportunities" in db.list_collection_names() or hasattr(db, "__getitem__"):
                db["marketing_opportunities"].update_one(
                    {"opportunity_key": engine_opp_key},
                    {"$set": {
                        "opportunity_state": "communicated",
                        "communicated_at": datetime.now(timezone.utc).isoformat(),
                        "channel": selected_channel,
                    }},
                    upsert=False
                )
        except Exception:
            pass

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
            {
                "customer_id": c_oid or customer_id,
                "campaign_type": {"$in": ["wishlist_reminder", "opportunity_wishlist_inactivity"]},
                "status": "sent",
            },
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

    from channel_selector_service import (
        select_communication_channel,
        determine_opportunity_preference,
    )

    pref_policy = determine_opportunity_preference("wishlist_reminder", policy=policy, user_profile=profile)
    selection = select_communication_channel(
        user_profile=profile,
        campaign_type="wishlist_reminder",
        classification="promotional",
        policy=policy,
        preference_policy=pref_policy,
    )

    if not selection.get("eligible") or not selection.get("channel"):
        return {"skipped": True, "reason": selection.get("reason", "No eligible communication channel available")}

    selected_channel = selection["channel"]
    recipient = selection["recipient"]
    results = {
        "channel": selected_channel,
        "selected_channel": selected_channel,
    }

    if selected_channel == "whatsapp":
        wa_key = f"wishlist_reminder:{str(customer_id)}:{window}:whatsapp"
        results["whatsapp"] = dispatch_communication(
            db, customer_id, "wishlist_reminder", "whatsapp",
            recipient, body=wa_body,
            idempotency_key=wa_key, provider=provider
        )
    else:
        email_key = f"wishlist_reminder:{str(customer_id)}:{window}:email"
        results["email"] = dispatch_communication(
            db, customer_id, "wishlist_reminder", "email",
            recipient, subject=email_subject, body=email_body,
            idempotency_key=email_key, provider=provider
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
    shipping_addr = order.get("shipping_address") if isinstance(order.get("shipping_address"), dict) else {}
    raw_phone = (profile.get("phone") if profile else None) or order.get("customer_phone") or shipping_addr.get("phone")

    recipient_phone = None
    if profile and profile.get("whatsapp_opt_out"):
        recipient_phone = None
    elif raw_phone:
        clean_phone, norm_err = normalize_whatsapp_phone(raw_phone)
        if not norm_err and clean_phone:
            recipient_phone = clean_phone
        else:
            recipient_phone = None

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


# ==============================================================================
# Qualified Leads Inactivity (4h) Category Best-Rated Item Recovery Email
# ==============================================================================

def send_qualified_lead_category_best_recovery_email(
    customer_id,
    db,
    provider=None,
    policy=None,
    inactivity_hours=4.0,
    force=False,
    current_time=None,
):
    """Send an email recovery reminder to a qualified lead who has been inactive for >= 4 hours.

    If the customer has multiple items of the same category in their active cart,
    the email highlights the single highest-rated item in that category (by customer rating & reviews).

    Invariants:
        - Customer must be currently a qualified lead (qualification_status == "qualified").
        - Must have active items in cart.
        - Must be inactive for at least `inactivity_hours` (default 4.0 hours).
        - Must have at least one category with >= 2 items in cart (comparing/undecided).
        - Dispatches via RFC-compliant email channel to customer's registered email.
        - Idempotent and logged to marketing_communications and admin_notifications.
    """
    if db is None or not customer_id:
        return {"skipped": True, "reason": "Missing db or customer_id"}

    from product_lookup import resolve_product_doc

    c_oid = _to_object_id(customer_id)
    query_id = c_oid if c_oid else customer_id
    now_dt = current_time or datetime.now(timezone.utc)
    if now_dt.tzinfo is None:
        now_dt = now_dt.replace(tzinfo=timezone.utc)

    # 1. Verify qualification status
    lead_state = db["customer_lead_state"].find_one({"customer_id": query_id})
    if not lead_state and isinstance(customer_id, str) and c_oid:
        lead_state = db["customer_lead_state"].find_one({"customer_id": str(c_oid)})

    if not lead_state or lead_state.get("qualification_status") != "qualified":
        return {"skipped": True, "reason": "Customer is not currently a qualified lead"}

    # 2. Check customer profile & email eligibility
    profile = db["user_profiles"].find_one({"_id": query_id})
    if not profile and isinstance(customer_id, str) and c_oid:
        profile = db["user_profiles"].find_one({"_id": c_oid})
    if not profile and isinstance(customer_id, str):
        profile = db["user_profiles"].find_one({"user_id": customer_id})

    eligibility = evaluate_channel_eligibility(profile, policy, campaign_type="cart_abandoned")
    if not eligibility.get("email", {}).get("eligible"):
        return {"skipped": True, "reason": eligibility.get("email", {}).get("reason", "Email channel ineligible")}

    recipient_email = eligibility["email"]["recipient"]
    cust_name = (profile.get("full_name") or profile.get("username") or "there") if profile else "there"

    # 3. Retrieve active cart items
    cart_col = db["cart"]
    cart_query = [{"user_id": query_id}]
    if c_oid:
        cart_query.append({"user_id": str(c_oid)})
        cart_query.append({"user_id": c_oid})
    if isinstance(customer_id, str):
        cart_query.append({"user_id": customer_id})

    raw_cart_items = list(cart_col.find({"$or": cart_query}))
    # Support both single-item-per-doc and multi-item embedded document schemes
    cart_items = []
    latest_cart_time = None

    for doc in raw_cart_items:
        if "items" in doc and isinstance(doc["items"], list):
            for it in doc["items"]:
                cart_items.append(it)
            c_time = doc.get("updated_at") or doc.get("created_at")
            if c_time:
                latest_cart_time = max(latest_cart_time or c_time, c_time)
        elif "product_id" in doc:
            cart_items.append(doc)
            c_time = doc.get("updated_at") or doc.get("added_at")
            if c_time:
                latest_cart_time = max(latest_cart_time or c_time, c_time)

    if not cart_items:
        return {"skipped": True, "reason": "Cart is currently empty"}

    # 4. Check completed orders (if placed after cart update, cart is converted -> skip)
    orders_col = db["orders"]
    latest_order = orders_col.find_one(
        {"$or": cart_query},
        sort=[("created_at", -1)]
    )
    if latest_order:
        o_created = latest_order.get("created_at")
        if isinstance(o_created, str):
            try:
                o_created_dt = datetime.fromisoformat(o_created)
            except Exception:
                o_created_dt = None
        elif isinstance(o_created, datetime):
            o_created_dt = o_created
        else:
            o_created_dt = None

        if o_created_dt:
            if o_created_dt.tzinfo is None:
                o_created_dt = o_created_dt.replace(tzinfo=timezone.utc)
            if latest_cart_time:
                if isinstance(latest_cart_time, str):
                    try:
                        latest_cart_time_dt = datetime.fromisoformat(latest_cart_time)
                    except Exception:
                        latest_cart_time_dt = None
                elif isinstance(latest_cart_time, datetime):
                    latest_cart_time_dt = latest_cart_time
                else:
                    latest_cart_time_dt = None

                if latest_cart_time_dt:
                    if latest_cart_time_dt.tzinfo is None:
                        latest_cart_time_dt = latest_cart_time_dt.replace(tzinfo=timezone.utc)
                    if o_created_dt >= latest_cart_time_dt:
                        return {"skipped": True, "reason": "Completed order invalidates cart recovery"}

    # 5. Inactivity check (>= inactivity_hours)
    # Check across customer_features, cart, and events
    activity_timestamps = []
    features_col = db["customer_features"]
    feat_doc = features_col.find_one({"customer_id": query_id})
    if not feat_doc and c_oid:
        feat_doc = features_col.find_one({"customer_id": str(c_oid)})

    if feat_doc:
        for fld in ["last_active_at", "last_activity_time", "updated_at"]:
            val = feat_doc.get(fld)
            if isinstance(val, str):
                try:
                    activity_timestamps.append(datetime.fromisoformat(val))
                except Exception:
                    pass
            elif isinstance(val, datetime):
                activity_timestamps.append(val)

    if latest_cart_time:
        if isinstance(latest_cart_time, str):
            try:
                activity_timestamps.append(datetime.fromisoformat(latest_cart_time))
            except Exception:
                pass
        elif isinstance(latest_cart_time, datetime):
            activity_timestamps.append(latest_cart_time)

    latest_ev = db["events"].find_one({"$or": cart_query}, sort=[("timestamp", -1)])
    if latest_ev and latest_ev.get("timestamp"):
        ev_ts = latest_ev["timestamp"]
        if isinstance(ev_ts, str):
            try:
                activity_timestamps.append(datetime.fromisoformat(ev_ts))
            except Exception:
                pass
        elif isinstance(ev_ts, datetime):
            activity_timestamps.append(ev_ts)

    if activity_timestamps:
        latest_activity_dt = max(activity_timestamps)
        if latest_activity_dt.tzinfo is None:
            latest_activity_dt = latest_activity_dt.replace(tzinfo=timezone.utc)
        elapsed_hours = (now_dt - latest_activity_dt).total_seconds() / 3600.0
        if not force and elapsed_hours < float(inactivity_hours):
            return {
                "skipped": True,
                "reason": f"Customer was active {elapsed_hours:.1f}h ago; requires >= {inactivity_hours}h of inactivity",
                "elapsed_hours": round(elapsed_hours, 2),
            }
    elif not force:
        # No recorded timestamps at all
        pass

    # 6. Group cart items by category and look up product ratings
    products_col = db["myntra_products"] if "myntra_products" in db.list_collection_names() else db["products"]
    resolved_items = []
    category_groups = {}

    for item in cart_items:
        p_id = item.get("product_id") or item.get("id") or item.get("_id")
        prod = resolve_product_doc(products_col, p_id) if p_id else None

        title = (
            (prod.get("title") or prod.get("name"))
            if prod else (item.get("title") or item.get("name") or "Product")
        )
        cat = (
            (prod.get("category"))
            if prod else (item.get("category") or "General")
        )
        cat_key = str(cat or "General").strip().title()

        # Parse numeric rating
        rating_raw = prod.get("rating") if prod else item.get("rating")
        try:
            rating = float(rating_raw) if rating_raw is not None else 4.2
        except (ValueError, TypeError):
            rating = 4.2

        # Parse rating count
        count_raw = prod.get("rating_count") or prod.get("reviews_count") if prod else item.get("rating_count")
        try:
            rating_count = int(count_raw) if count_raw is not None else 120
        except (ValueError, TypeError):
            rating_count = 120

        # Price
        price_raw = prod.get("price") if prod else item.get("price")
        try:
            price = float(price_raw) if price_raw is not None else 0.0
        except (ValueError, TypeError):
            price = 0.0

        img = (
            (prod.get("primary_image") or prod.get("image") or (prod.get("images", [None])[0] if isinstance(prod.get("images"), list) and prod.get("images") else None))
            if prod else (item.get("image") or item.get("primary_image"))
        )

        resolved_item = {
            "product_id": str(p_id),
            "title": title,
            "category": cat_key,
            "rating": rating,
            "rating_count": rating_count,
            "price": price,
            "image": img,
            "brand": (prod.get("brand") if prod else item.get("brand")) or "Featured Brand",
        }
        resolved_items.append(resolved_item)

        if cat_key not in category_groups:
            category_groups[cat_key] = []
        category_groups[cat_key].append(resolved_item)

    # 7. Check condition: multiple items of the SAME category
    categories_with_multiples = {cat: items for cat, items in category_groups.items() if len(items) >= 2}

    if not categories_with_multiples and not force:
        return {
            "skipped": True,
            "reason": "Cart does not contain multiple items of the same category",
            "categories_found": list(category_groups.keys()),
        }

    # 8. For categories with multiples, select the best item in terms of rating
    best_picks = []
    target_categories = categories_with_multiples if categories_with_multiples else category_groups

    for cat_name, cat_items in target_categories.items():
        # Sort by rating (descending), rating_count (descending), then lower price
        sorted_items = sorted(
            cat_items,
            key=lambda x: (x["rating"], x["rating_count"], -x["price"]),
            reverse=True
        )
        best_item_in_cat = sorted_items[0]
        other_items_in_cat = sorted_items[1:]
        best_picks.append({
            "category": cat_name,
            "best_item": best_item_in_cat,
            "competing_items": other_items_in_cat,
            "total_items_in_category": len(cat_items),
        })

    # Sort overall best picks so the highest rated category lead is first
    best_picks.sort(key=lambda x: (x["best_item"]["rating"], x["best_item"]["rating_count"]), reverse=True)
    primary_pick = best_picks[0]
    top_product = primary_pick["best_item"]
    top_cat = primary_pick["category"]
    competing_count = len(primary_pick["competing_items"])

    # 9. Cooldown & Idempotency check
    window_key = now_dt.strftime("%Y-%m-%d")
    idempotency_key = f"qualified_category_best:{str(query_id)}:{top_product['product_id']}:{window_key}"

    existing_comm = db["marketing_communications"].find_one({
        "customer_id": query_id,
        "campaign_type": "qualified_cart_category_best",
        "status": "sent",
        "$or": [
            {"idempotency_key": idempotency_key},
            {"sent_at": {"$gte": (now_dt - timedelta(hours=24)).isoformat()}},
        ],
    })
    if existing_comm and not force:
        return {
            "skipped": True,
            "reason": "Category best-rated recovery email already sent within 24h",
            "communication_id": str(existing_comm.get("_id")),
        }

    # 10. Compose customer-facing email (clean, transparent, no fake urgency)
    subject = f"Still deciding on your {top_cat}? Here is our highest-rated pick from your cart ⭐"

    competing_note = (
        f"We noticed you have {competing_count + 1} {top_cat} items waiting in your shopping cart. "
        "To help you choose with confidence, here is our customers' top-rated favorite:"
    )

    rating_stars = "★" * int(round(top_product["rating"])) + "☆" * (5 - int(round(top_product["rating"])))
    price_str = f"₹{top_product['price']:,.2f}" if top_product["price"] > 0 else "Special Price"

    email_body = (
        f"Hi {cust_name},\n\n"
        f"{competing_note}\n\n"
        f"⭐ {top_product['title']}\n"
        f"Brand: {top_product['brand']}\n"
        f"Category: {top_cat}\n"
        f"Rating: {rating_stars} {top_product['rating']:.1f}/5.0 ({top_product['rating_count']}+ customer reviews)\n"
        f"Price: {price_str}\n\n"
        "Ready to finish your order?\n"
        f"Complete your purchase here:\n{get_store_url()}/cart\n\n"
        "Best regards,\n"
        "The Lead Magnet Team"
    )

    # HTML body with rich styling
    img_html = ""
    if top_product.get("image"):
        img_html = f"""
        <div style="text-align: center; margin-bottom: 20px;">
            <img src="{top_product['image']}" alt="{top_product['title']}" style="max-width: 240px; max-height: 300px; border-radius: 8px; object-fit: cover; box-shadow: 0 4px 12px rgba(0,0,0,0.1);" />
        </div>
        """

    html_body = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 24px; background: #ffffff; color: #1e293b; border: 1px solid #e2e8f0; border-radius: 12px;">
        <div style="border-bottom: 2px solid #6366f1; padding-bottom: 12px; margin-bottom: 20px;">
            <h2 style="color: #0f172a; margin: 0; font-size: 20px;">Still Deciding on Your {top_cat}?</h2>
            <p style="color: #64748b; margin: 4px 0 0 0; font-size: 14px;">Here is the highest-rated choice from your cart</p>
        </div>
        <p style="font-size: 15px; line-height: 1.6;">Hi <strong>{cust_name}</strong>,</p>
        <p style="font-size: 14px; line-height: 1.6; color: #475569;">
            {competing_note}
        </p>
        {img_html}
        <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 16px; margin: 20px 0;">
            <div style="display: inline-block; background: #fef3c7; color: #92400e; font-size: 12px; font-weight: 700; padding: 3px 8px; border-radius: 4px; margin-bottom: 8px;">
                ⭐ TOP-RATED PICK IN {top_cat.upper()}
            </div>
            <h3 style="margin: 4px 0; font-size: 17px; color: #0f172a;">{top_product['title']}</h3>
            <p style="margin: 2px 0 8px 0; color: #64748b; font-size: 13px;">by <strong>{top_product['brand']}</strong></p>
            <div style="margin: 8px 0; font-size: 14px; color: #f59e0b; font-weight: 600;">
                <span style="font-size: 16px;">{rating_stars}</span>
                <span style="color: #0f172a; margin-left: 6px;">{top_product['rating']:.1f}</span>
                <span style="color: #64748b; font-weight: 400; font-size: 12px;">({top_product['rating_count']}+ customer reviews)</span>
            </div>
            <div style="font-size: 20px; font-weight: 700; color: #0f172a; margin-top: 8px;">
                {price_str}
            </div>
        </div>
        <div style="text-align: center; margin: 28px 0;">
            <a href="{get_store_url()}/cart" style="display: inline-block; background: #4f46e5; color: #ffffff; text-decoration: none; font-weight: 600; font-size: 15px; padding: 12px 32px; border-radius: 8px; box-shadow: 0 4px 12px rgba(79, 70, 229, 0.3);">
                Complete Order in Cart →
            </a>
        </div>
        <p style="font-size: 12px; color: #94a3b8; text-align: center; margin-top: 24px; border-top: 1px solid #f1f5f9; padding-top: 16px;">
            You received this recommendation because this item is currently in your Lead Magnet shopping cart.<br />
            Lead Magnet Fashion Store.
        </p>
    </div>
    """

    # 11. Dispatch communication
    comm_doc = dispatch_communication(
        db=db,
        customer_id=query_id,
        campaign_type="qualified_cart_category_best",
        channel="email",
        recipient=recipient_email,
        subject=subject,
        body=email_body,
        html_body=html_body,
        metadata={
            "product_id": top_product["product_id"],
            "category": top_cat,
            "rating": top_product["rating"],
            "rating_count": top_product["rating_count"],
            "competing_count": competing_count,
            "primary_image": top_product.get("image"),
        },
        idempotency_key=idempotency_key,
        provider=provider,
    )

    # 12. Create admin notification for visibility
    if comm_doc and comm_doc.get("status") == "sent":
        try:
            notif_col = db["admin_notifications"]
            notif_doc = {
                "type": "qualified_cart_category_best",
                "title": f"Top-Rated Pick Recovery Sent: {top_cat}",
                "customer_id": str(query_id),
                "message": (
                    f"Sent category best pick ({top_product['title'][:30]}, rating {top_product['rating']}) "
                    f"to qualified lead {cust_name} after {inactivity_hours}h inactivity."
                ),
                "metadata": {
                    "product_id": top_product["product_id"],
                    "category": top_cat,
                    "rating": top_product["rating"],
                },
                "read": False,
                "created_at": now_dt.isoformat(),
            }
            notif_col.insert_one(notif_doc)
        except Exception:
            pass

    return {
        "status": "sent" if comm_doc.get("status") == "sent" else "failed",
        "customer_id": str(query_id),
        "featured_category": top_cat,
        "featured_product": top_product,
        "competing_items_count": competing_count,
        "communication": comm_doc,
    }


def evaluate_qualified_leads_inactivity_cart_recovery(
    db,
    inactivity_hours=4.0,
    provider=None,
    policy=None,
    current_time=None,
    max_leads=100,
):
    """Scan all qualified leads and send recovery emails for those inactive for >= 4h with multiple same-category items in cart."""
    if db is None:
        return {"status": "skipped", "reason": "Database unavailable"}

    state_col = db["customer_lead_state"]
    qualified_docs = list(state_col.find(
        {"qualification_status": "qualified"},
        {"customer_id": 1}
    ).limit(max_leads))

    processed = 0
    sent_count = 0
    skipped_count = 0
    results = []

    for doc in qualified_docs:
        cid = doc.get("customer_id")
        if not cid:
            continue
        processed += 1
        try:
            res = send_qualified_lead_category_best_recovery_email(
                customer_id=cid,
                db=db,
                provider=provider,
                policy=policy,
                inactivity_hours=inactivity_hours,
                current_time=current_time,
            )
            if res.get("status") == "sent":
                sent_count += 1
            else:
                skipped_count += 1
            results.append({"customer_id": str(cid), "result": res})
        except Exception as exc:
            results.append({"customer_id": str(cid), "error": str(exc)})
            skipped_count += 1

    return {
        "status": "completed",
        "qualified_leads_scanned": processed,
        "emails_sent": sent_count,
        "skipped": skipped_count,
        "timestamp": (current_time or datetime.now(timezone.utc)).isoformat(),
        "details": results,
    }


def send_post_purchase_smart_recommendation_email(
    customer_id,
    db,
    provider=None,
    policy=None,
    force=False,
    current_time=None,
):
    """Dispatch smart post-purchase recommendation email to a converted buyer.

    Logic:
        Customer ordered item X (e.g. 'RARE RABBIT Men Casual Shirt').
        Recommends:
        1. Item Y from the SAME brand in that category ('From the same brand you love').
        2. Item Z of the SAME high quality from a DIFFERENT brand at a LOWER price ('Quality alternative at a lower price').
    """
    if db is None:
        return {"status": "skipped", "reason": "Database unavailable"}

    c_oid = _to_object_id(customer_id)
    query_id = c_oid if c_oid else customer_id

    # 1. Fetch customer profile
    profile = db["user_profiles"].find_one({"_id": query_id})
    if not profile and isinstance(customer_id, str):
        profile = db["user_profiles"].find_one({"_id": customer_id})

    recipient_email = profile.get("email") if profile else None
    if not recipient_email or "@" not in recipient_email:
        return {"status": "skipped", "reason": "No valid email address for customer"}

    cust_name = (profile.get("full_name") or profile.get("username") or "there").strip()

    # 2. Fetch completed orders
    from customer_feature_service import is_completed_order
    order_query = []
    if c_oid:
        order_query.append({"user_id": c_oid})
        order_query.append({"user_id": str(c_oid)})
    if isinstance(customer_id, str):
        order_query.append({"user_id": customer_id})

    raw_orders = list(db["orders"].find({"$or": order_query}).sort("created_at", -1)) if order_query else []
    completed_orders = [o for o in raw_orders if is_completed_order(o)]

    if not completed_orders:
        return {"status": "skipped", "reason": "Customer has no completed orders"}

    # 3. Extract all purchased item IDs and determine recent anchor order item
    purchased_ids = set()
    anchor_item = None

    for order in completed_orders:
        items = order.get("items") or []
        for it in items:
            raw_pid = str(it.get("product_id") or it.get("id") or it.get("_id") or "")
            if raw_pid:
                purchased_ids.add(raw_pid)
            if not anchor_item and (it.get("name") or it.get("title")):
                anchor_item = it

    if not anchor_item:
        return {"status": "skipped", "reason": "No valid purchased items found in customer order history"}

    ordered_title = anchor_item.get("name") or anchor_item.get("title") or "Clothing Item"
    ordered_category = str(anchor_item.get("category") or "Clothing").strip()
    ordered_brand = str(anchor_item.get("brand") or "Fashion").strip()
    try:
        ordered_price = float(anchor_item.get("price") or 0.0)
    except (ValueError, TypeError):
        ordered_price = 0.0
    ordered_pid = str(anchor_item.get("product_id") or anchor_item.get("id") or "")

    # 4. Resolve candidate products in the same category from products collection
    col_names = db.list_collection_names() if hasattr(db, "list_collection_names") else []
    if "myntra_products" in col_names and "products" not in col_names:
        products_col = db["myntra_products"]
    else:
        products_col = db["products"] if hasattr(db, "__getitem__") else getattr(db, "products", None)
    if products_col is None:
        return {"status": "skipped", "reason": "Products collection unavailable"}

    raw_candidates = list(products_col.find({"category": ordered_category}).sort("rating", -1).limit(60))
    if len(raw_candidates) < 6:
        # Fallback to broader category search
        raw_candidates.extend(list(products_col.find({}).sort("rating", -1).limit(40)))

    # Normalize products and exclude already purchased
    valid_cands = []
    seen_cand_ids = set()
    for p in raw_candidates:
        pid = str(p.get("product_id") or p.get("id") or p.get("_id") or "")
        if not pid or pid in purchased_ids or pid in seen_cand_ids or pid == ordered_pid:
            continue
        seen_cand_ids.add(pid)

        p_title = p.get("title") or p.get("name") or "Product"
        p_brand = str(p.get("brand") or "Fashion").strip()
        p_cat = str(p.get("category") or ordered_category).strip()
        try:
            p_price = float(p.get("price") or p.get("current_price") or 0.0)
        except (ValueError, TypeError):
            p_price = 0.0
        try:
            p_rating = float(p.get("rating") or 4.2)
        except (ValueError, TypeError):
            p_rating = 4.2
        p_img = p.get("primary_image") or p.get("image") or (p.get("images")[0] if isinstance(p.get("images"), list) and p.get("images") else "")

        valid_cands.append({
            "product_id": pid,
            "title": p_title,
            "brand": p_brand,
            "category": p_cat,
            "price": p_price,
            "rating": p_rating,
            "image": p_img,
        })

    if not valid_cands:
        return {"status": "skipped", "reason": "No unpurchased recommendation candidates available"}

    # 5. Smart Selection:
    # Choice 1: Same Brand Pick
    same_brand_cands = [p for p in valid_cands if p["brand"].casefold() == ordered_brand.casefold()]
    same_brand_cands.sort(key=lambda x: x["rating"], reverse=True)
    same_brand_pick = same_brand_cands[0] if same_brand_cands else None

    # Choice 2: Same Quality in a Different Brand at a Lower Price
    lower_price_cands = [
        p for p in valid_cands
        if p["brand"].casefold() != ordered_brand.casefold()
        and (ordered_price <= 0 or p["price"] < ordered_price)
        and p["rating"] >= 4.0
    ]
    lower_price_cands.sort(key=lambda x: x["price"])  # best price advantage
    lower_price_pick = lower_price_cands[0] if lower_price_cands else None

    # Fallback logic if either slot is missing
    if not same_brand_pick:
        remaining = [p for p in valid_cands if p != lower_price_pick]
        same_brand_pick = remaining[0] if remaining else valid_cands[0]

    if not lower_price_pick:
        remaining = [p for p in valid_cands if p != same_brand_pick]
        lower_price_pick = remaining[0] if remaining else valid_cands[-1]

    # Calculate savings on lower price pick
    has_savings = ordered_price > lower_price_pick["price"] and lower_price_pick["price"] > 0
    diff_amount = max(0.0, ordered_price - lower_price_pick["price"]) if has_savings else 0.0
    percent_saved = round((diff_amount / ordered_price) * 100) if (has_savings and ordered_price > 0) else 0

    # 6. Cooldown & Idempotency check (72 hours default)
    now_dt = current_time or datetime.now(timezone.utc)
    idempotency_key = f"post_purchase_recs:{str(query_id)}:{ordered_pid}:{now_dt.strftime('%Y-%m-%d')}"

    existing_comm = db["marketing_communications"].find_one({
        "customer_id": query_id,
        "campaign_type": "post_purchase_smart_recommendations",
        "status": "sent",
        "$or": [
            {"idempotency_key": idempotency_key},
            {"sent_at": {"$gte": (now_dt - timedelta(hours=72)).isoformat()}},
        ],
    })
    if existing_comm and not force:
        return {
            "skipped": True,
            "reason": "Post-purchase recommendation email already sent within 72h cooldown",
            "communication_id": str(existing_comm.get("_id")),
        }

    # 7. Compose Customer Email
    subject = f"Loved your '{ordered_title}'? You may like this from {ordered_brand} & quality picks at lower prices!"

    same_brand_stars = "★" * int(round(same_brand_pick["rating"])) + "☆" * (5 - int(round(same_brand_pick["rating"])))
    lower_price_stars = "★" * int(round(lower_price_pick["rating"])) + "☆" * (5 - int(round(lower_price_pick["rating"])))

    email_body = (
        f"Hi {cust_name},\n\n"
        f"Thank you for ordering '{ordered_title}' from {ordered_brand}!\n"
        f"Based on what you purchased, our stylists handpicked these complementary recommendations for you:\n\n"
        f"1. FROM THE SAME BRAND ({ordered_brand}):\n"
        f"   ⭐ {same_brand_pick['title']}\n"
        f"   Brand: {same_brand_pick['brand']}\n"
        f"   Price: ₹{same_brand_pick['price']:,.2f}\n"
        f"   Rating: {same_brand_stars} {same_brand_pick['rating']:.1f}/5.0\n\n"
        f"2. SAME QUALITY IN A DIFFERENT BRAND AT LOWER PRICE:\n"
        f"   🏷️ {lower_price_pick['title']}\n"
        f"   Brand: {lower_price_pick['brand']}\n"
        f"   Price: ₹{lower_price_pick['price']:,.2f}"
        + (f" (Save ₹{diff_amount:,.2f} / {percent_saved}% less than your recent order!)" if has_savings else "") + "\n"
        f"   Rating: {lower_price_stars} {lower_price_pick['rating']:.1f}/5.0\n\n"
        f"Explore these styles in our store:\n"
        f"{get_store_url()}/shop\n\n"
        f"Best regards,\n"
        f"The Lead Magnet Team"
    )

    # HTML Email Template
    same_brand_img_html = f'<img src="{same_brand_pick["image"]}" alt="{same_brand_pick["title"]}" style="width: 100%; max-height: 220px; object-fit: cover; border-radius: 8px;" />' if same_brand_pick.get("image") else ''
    lower_price_img_html = f'<img src="{lower_price_pick["image"]}" alt="{lower_price_pick["title"]}" style="width: 100%; max-height: 220px; object-fit: cover; border-radius: 8px;" />' if lower_price_pick.get("image") else ''

    savings_badge_html = f"""
    <div style="margin-top: 8px; background: #ecfdf5; border: 1px solid #10b981; color: #065f46; font-size: 13px; font-weight: 700; padding: 6px 10px; border-radius: 6px;">
        💰 Save ₹{diff_amount:,.2f} ({percent_saved}% less vs your previous order!)
    </div>
    """ if has_savings else ""

    html_body = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; max-width: 620px; margin: 0 auto; padding: 24px; background: #ffffff; color: #1e293b; border: 1px solid #e2e8f0; border-radius: 12px; box-shadow: 0 4px 20px rgba(0,0,0,0.06);">
        <!-- Header -->
        <div style="border-bottom: 2px solid #6366f1; padding-bottom: 14px; margin-bottom: 20px;">
            <div style="display: inline-block; background: #ede9fe; color: #4338ca; font-size: 12px; font-weight: 700; padding: 3px 8px; border-radius: 4px; text-transform: uppercase; margin-bottom: 6px;">
                ✦ Post-Purchase Recommendations
            </div>
            <h2 style="color: #0f172a; margin: 0; font-size: 20px;">Tailored Picks Just for You</h2>
            <p style="color: #64748b; margin: 4px 0 0 0; font-size: 14px;">Because you ordered <strong>{ordered_title}</strong></p>
        </div>

        <p style="font-size: 15px; line-height: 1.6;">Hi <strong>{cust_name}</strong>,</p>
        <p style="font-size: 14px; line-height: 1.6; color: #475569;">
            We hope you love your recent order of <strong>{ordered_title}</strong> from <strong>{ordered_brand}</strong>!
            Based on your interest, here are two handpicked options: a complementary style from the <strong>same brand</strong>, and an equally premium piece in a <strong>different brand at a lower price</strong>:
        </p>

        <!-- Product Comparison Grid -->
        <div style="margin: 24px 0; display: flex; flex-direction: column; gap: 20px;">
            <!-- Pick 1: Same Brand -->
            <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 18px;">
                <div style="display: inline-block; background: #e0e7ff; color: #3730a3; font-size: 11px; font-weight: 700; padding: 3px 8px; border-radius: 4px; margin-bottom: 10px;">
                    👔 FROM THE SAME BRAND YOU LOVE ({ordered_brand.upper()})
                </div>
                {same_brand_img_html}
                <h3 style="margin: 10px 0 4px 0; font-size: 16px; color: #0f172a;">{same_brand_pick['title']}</h3>
                <div style="font-size: 13px; color: #64748b; margin-bottom: 8px;">by <strong>{same_brand_pick['brand']}</strong> • {same_brand_pick['category']}</div>
                <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;">
                    <div style="font-size: 18px; font-weight: 700; color: #0f172a;">₹{same_brand_pick['price']:,.2f}</div>
                    <div style="font-size: 13px; color: #f59e0b; font-weight: 600;">{same_brand_stars} {same_brand_pick['rating']:.1f}/5.0</div>
                </div>
            </div>

            <!-- Pick 2: Lower Price in Different Brand -->
            <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 18px;">
                <div style="display: inline-block; background: #fef3c7; color: #92400e; font-size: 11px; font-weight: 700; padding: 3px 8px; border-radius: 4px; margin-bottom: 10px;">
                    🏷️ SAME QUALITY IN DIFFERENT BRAND AT LOWER PRICE
                </div>
                {lower_price_img_html}
                <h3 style="margin: 10px 0 4px 0; font-size: 16px; color: #0f172a;">{lower_price_pick['title']}</h3>
                <div style="font-size: 13px; color: #64748b; margin-bottom: 8px;">by <strong>{lower_price_pick['brand']}</strong> • {lower_price_pick['category']}</div>
                <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;">
                    <div style="font-size: 18px; font-weight: 700; color: #059669;">₹{lower_price_pick['price']:,.2f}</div>
                    <div style="font-size: 13px; color: #f59e0b; font-weight: 600;">{lower_price_stars} {lower_price_pick['rating']:.1f}/5.0</div>
                </div>
                {savings_badge_html}
            </div>
        </div>

        <!-- CTA Button -->
        <div style="text-align: center; margin: 30px 0 16px 0;">
            <a href="{get_store_url()}/shop" style="display: inline-block; background: #4f46e5; color: #ffffff; text-decoration: none; font-weight: 600; font-size: 15px; padding: 14px 36px; border-radius: 8px; box-shadow: 0 4px 14px rgba(79, 70, 229, 0.35);">
                Explore All Matching Styles →
            </a>
        </div>

        <!-- Footer -->
        <p style="font-size: 12px; color: #94a3b8; text-align: center; margin-top: 24px; border-top: 1px solid #f1f5f9; padding-top: 16px;">
            You received this recommendation based on your recent order at Lead Magnet.<br />
            Lead Magnet Fashion Store.
        </p>
    </div>
    """

    # 8. Dispatch Communication via provider (Gmail SMTP)
    comm_doc = dispatch_communication(
        db=db,
        customer_id=query_id,
        campaign_type="post_purchase_smart_recommendations",
        channel="email",
        recipient=recipient_email,
        subject=subject,
        body=email_body,
        html_body=html_body,
        metadata={
            "ordered_product_id": ordered_pid,
            "ordered_title": ordered_title,
            "ordered_brand": ordered_brand,
            "same_brand_pick_id": same_brand_pick["product_id"],
            "lower_price_pick_id": lower_price_pick["product_id"],
            "savings_amount": diff_amount,
            "percent_saved": percent_saved,
        },
        idempotency_key=idempotency_key,
        provider=provider,
    )

    # 9. Admin Notification for visibility
    if comm_doc and comm_doc.get("status") == "sent":
        try:
            notif_col = db["admin_notifications"]
            notif_doc = {
                "type": "post_purchase_smart_recommendations",
                "title": f"Smart Recommendations Sent: {ordered_title[:25]}",
                "customer_id": str(query_id),
                "message": (
                    f"Sent post-purchase recommendations to {cust_name} ({recipient_email}) "
                    f"featuring {same_brand_pick['brand']} & {lower_price_pick['brand']}."
                ),
                "metadata": {
                    "ordered_title": ordered_title,
                    "same_brand": same_brand_pick["brand"],
                    "lower_price_brand": lower_price_pick["brand"],
                    "savings": diff_amount,
                },
                "read": False,
                "created_at": now_dt.isoformat(),
            }
            notif_col.insert_one(notif_doc)
        except Exception:
            pass

    return {
        "status": "sent" if (comm_doc and comm_doc.get("status") == "sent") else "failed",
        "customer_id": str(query_id),
        "ordered_item": {
            "title": ordered_title,
            "brand": ordered_brand,
            "price": ordered_price,
            "category": ordered_category,
        },
        "same_brand_recommendation": same_brand_pick,
        "lower_price_recommendation": lower_price_pick,
        "savings_amount": diff_amount,
        "percent_saved": percent_saved,
        "communication": comm_doc,
    }


def evaluate_periodic_post_purchase_recommendations(
    db,
    provider=None,
    policy=None,
    current_time=None,
    max_customers=50,
):
    """Periodically scan converted customers and send smart post-purchase recommendation emails."""
    if db is None:
        return {"status": "skipped", "reason": "Database unavailable"}

    lead_state_col = db["customer_lead_state"]
    # Converted customers or repeat customers
    converted_docs = list(lead_state_col.find(
        {"lifecycle_status": {"$in": ["converted", "repeat_customer"]}},
        {"customer_id": 1}
    ).limit(max_customers))

    # Also check orders collection for customers with orders if lead_state is unpopulated
    if not converted_docs:
        order_user_ids = db["orders"].distinct("user_id")
        converted_docs = [{"customer_id": uid} for uid in order_user_ids if uid][:max_customers]

    scanned = 0
    sent_count = 0
    skipped_count = 0
    results = []

    for doc in converted_docs:
        cid = doc.get("customer_id")
        if not cid:
            continue
        scanned += 1
        try:
            res = send_post_purchase_smart_recommendation_email(
                customer_id=cid,
                db=db,
                provider=provider,
                policy=policy,
                force=False,
                current_time=current_time,
            )
            if res.get("status") == "sent":
                sent_count += 1
            else:
                skipped_count += 1
            results.append({"customer_id": str(cid), "result": res})
        except Exception as exc:
            results.append({"customer_id": str(cid), "error": str(exc)})
            skipped_count += 1

    return {
        "status": "completed",
        "converted_customers_scanned": scanned,
        "emails_sent": sent_count,
        "skipped": skipped_count,
        "timestamp": (current_time or datetime.now(timezone.utc)).isoformat(),
        "details": results,
    }


