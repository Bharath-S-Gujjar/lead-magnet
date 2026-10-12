"""WhatsApp Webhook Processing Service (Task 5).

Handles Meta WhatsApp Cloud API webhooks:
- GET verification challenge with secure token comparison.
- POST HMAC-SHA256 signature verification against raw request body using constant-time comparison.
- Inbound STOP and opt-out keyword processing (STOP, UNSUBSCRIBE, CANCEL, END, QUIT).
- Sender phone resolution via normalized WhatsApp phone numbers without modifying ambiguous profiles.
- Immediate opt-out persistence with source 'whatsapp_stop'.
- WhatsApp delivery-status event processing (sent, delivered, read, failed).
- Status precedence enforcement preventing out-of-order regressions.
- Idempotency via atomic unique event storage preventing duplicate processing.
- Zero outbound communications or external API calls.
"""

import datetime
import hashlib
import hmac
import logging
import os
import re
from typing import Any, Dict, Optional, Tuple

from pymongo.errors import DuplicateKeyError

from communication_provider import normalize_whatsapp_phone
from customer_profile_service import update_customer_whatsapp_consent

logger = logging.getLogger(__name__)

# Supported opt-out keywords (standard carrier/Meta keywords)
OPT_OUT_KEYWORDS = {
    "STOP",
    "UNSUBSCRIBE",
    "CANCEL",
    "END",
    "QUIT",
    "STOPALL",
}

# Status hierarchy: higher rank supersedes lower rank
STATUS_RANKS = {
    "pending": 0,
    "queued": 0,
    "sent": 1,
    "delivered": 2,
    "read": 3,
}


def verify_webhook_signature(raw_body: bytes, signature_header: Optional[str], app_secret: Optional[str]) -> bool:
    """Validate incoming POST requests using Meta's X-Hub-Signature-256 HMAC-SHA256 signature.

    Rules:
        - Signature calculated against exact raw request body.
        - Constant-time comparison using hmac.compare_digest.
        - Header format: 'sha256=<hex_digest>'.
    """
    if not signature_header or not app_secret:
        return False

    if not isinstance(raw_body, (bytes, bytearray)):
        if isinstance(raw_body, str):
            raw_body = raw_body.encode("utf-8")
        else:
            return False

    prefix = "sha256="
    if not signature_header.startswith(prefix):
        return False

    received_sig = signature_header[len(prefix):].strip()
    expected_sig = hmac.new(
        app_secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected_sig, received_sig)


def verify_webhook_challenge(
    mode: Optional[str],
    token: Optional[str],
    challenge: Optional[str],
    expected_token: Optional[str],
) -> Tuple[bool, Optional[str]]:
    """Validate Meta GET webhook subscription challenge.

    Returns:
        (True, challenge) if mode is 'subscribe' and token matches.
        (False, None) if verification fails.
    """
    if not mode or not token or not challenge or not expected_token:
        return False, None

    if mode != "subscribe":
        return False, None

    if not hmac.compare_digest(str(token).strip(), str(expected_token).strip()):
        return False, None

    return True, challenge


def is_opt_out_keyword(text: Optional[str]) -> bool:
    """Check if incoming message text expresses an explicit opt-out.

    Normalizes message text safely and matches supported keywords without
    treating unrelated sentences as STOP.
    """
    if not text or not isinstance(text, str):
        return False

    cleaned = text.strip()
    # Strip leading/trailing non-alphanumeric punctuation (e.g. "STOP!" or "Stop.")
    cleaned = re.sub(r"^[^\w]+|[^\w]+$", "", cleaned).strip().upper()
    return cleaned in OPT_OUT_KEYWORDS


def ensure_webhook_indexes(db: Any) -> None:
    """Ensure unique index on webhook events collection for atomic idempotency."""
    if db is None:
        return
    try:
        events_col = db["whatsapp_webhook_events"]
        events_col.create_index([("event_id", 1)], unique=True)
    except Exception as e:
        logger.debug("Failed creating webhook index (may already exist): %s", e)


def record_webhook_idempotency(db: Any, event_id: str, event_type: str = "generic") -> bool:
    """Atomically record event ID to prevent duplicate processing.

    Returns:
        True if successfully recorded (new event).
        False if event_id already exists (duplicate event).
    """
    if db is None:
        return True

    events_col = db["whatsapp_webhook_events"]
    try:
        events_col.insert_one({
            "event_id": event_id,
            "event_type": event_type,
            "processed_at": datetime.datetime.now(datetime.timezone.utc),
        })
        return True
    except DuplicateKeyError:
        return False
    except Exception as e:
        # Check for duplicate key error string if running against non-pymongo mock
        if "duplicate" in str(e).lower() or "unique" in str(e).lower():
            return False
        # If collection doesn't have unique index enforced, fallback to check-then-insert safe query
        if events_col.find_one({"event_id": event_id}):
            return False
        try:
            events_col.insert_one({
                "event_id": event_id,
                "event_type": event_type,
                "processed_at": datetime.datetime.now(datetime.timezone.utc),
            })
            return True
        except Exception:
            return False


def resolve_customer_by_phone(db: Any, phone_raw: Optional[str]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Resolve a single customer profile by sender WhatsApp phone number.

    Invariants:
        - Normalizes sender phone number.
        - Resolves to exactly one customer profile.
        - Never modifies another customer's consent if phone is unmatched or ambiguous.

    Returns:
        (profile_doc, None) on unique match.
        (None, 'unmatched') if no profile matches.
        (None, 'ambiguous') if multiple profiles match the same phone number.
    """
    if not phone_raw or not str(phone_raw).strip() or db is None:
        return None, "empty_phone"

    clean_raw = str(phone_raw).strip()
    norm_phone, norm_err = normalize_whatsapp_phone(clean_raw)
    if norm_err or not norm_phone:
        return None, f"invalid_phone: {norm_err}"

    profiles_col = db["user_profiles"]

    # Candidate representations
    candidate_phones = [norm_phone, f"+{norm_phone}"]
    if clean_raw not in candidate_phones:
        candidate_phones.append(clean_raw)

    candidates = list(profiles_col.find({"phone": {"$in": candidate_phones}}))

    # If no direct match, check digits match for formatted numbers (e.g. "+91 98765-43210")
    if not candidates and len(norm_phone) >= 10:
        last_10 = norm_phone[-10:]
        regex_matches = list(profiles_col.find({"phone": {"$regex": re.escape(last_10)}}))
        for p in regex_matches:
            p_phone = p.get("phone")
            if p_phone:
                p_norm, _ = normalize_whatsapp_phone(str(p_phone))
                if p_norm == norm_phone and p["_id"] not in [c["_id"] for c in candidates]:
                    candidates.append(p)

    if len(candidates) == 1:
        return candidates[0], None
    elif len(candidates) > 1:
        return None, "ambiguous"
    else:
        return None, "unmatched"


def process_inbound_message(db: Any, msg_item: Dict[str, Any]) -> Dict[str, Any]:
    """Process an inbound WhatsApp message item.

    Handles STOP / opt-out keywords:
        - Resolves sender to customer profile.
        - Persists opt-out (whatsapp_opt_out=True, whatsapp_opt_in=False, source='whatsapp_stop').
        - Suppresses promotional eligibility immediately.
        - Idempotent against duplicate messages.
    """
    msg_id = msg_item.get("id")
    if not msg_id:
        return {"status": "skipped_no_id"}

    event_id = f"msg:{msg_id}"
    is_new = record_webhook_idempotency(db, event_id, event_type="message")
    if not is_new:
        return {"status": "duplicate", "msg_id": msg_id}

    from_phone = msg_item.get("from")
    body = ""
    if msg_item.get("type") == "text":
        body = msg_item.get("text", {}).get("body", "")

    if is_opt_out_keyword(body):
        customer, reason = resolve_customer_by_phone(db, from_phone)
        if customer:
            update_customer_whatsapp_consent(
                profiles_collection=db["user_profiles"],
                user_id=customer["_id"],
                opt_in=False,
                opt_out=True,
                source="whatsapp_stop",
            )
            return {
                "status": "opt_out_recorded",
                "customer_id": str(customer["_id"]),
                "from": from_phone,
                "msg_id": msg_id,
            }
        else:
            return {
                "status": f"opt_out_{reason}",
                "from": from_phone,
                "msg_id": msg_id,
            }

    # Non-opt-out inbound message: do not re-enable marketing consent or alter flags
    return {
        "status": "ignored_non_opt_out",
        "from": from_phone,
        "msg_id": msg_id,
    }


def process_delivery_status(db: Any, status_item: Dict[str, Any]) -> Dict[str, Any]:
    """Process a WhatsApp delivery status update (sent, delivered, read, failed).

    Enforces status ordering:
        - sent -> delivered -> read
        - Older status cannot overwrite newer status.
        - Provider failure cannot be overwritten by delivery.
        - Idempotent against duplicate status deliveries.
    """
    msg_id = status_item.get("id")
    raw_status = status_item.get("status")
    ts = status_item.get("timestamp")

    if not msg_id or not raw_status:
        return {"status": "skipped_missing_fields"}

    new_status = str(raw_status).strip().lower()
    # Status event idempotency key: keyed on msg_id + new_status only (NOT timestamp) so that
    # Meta retries of the same event with a differing timestamp are also deduplicated.
    # The status-rank guard below prevents DB regression even if the idempotency key misses.
    event_id = f"status:{msg_id}:{new_status}"

    is_new = record_webhook_idempotency(db, event_id, event_type="status")
    if not is_new:
        return {"status": "duplicate", "msg_id": msg_id, "incoming_status": new_status}

    if db is None:
        return {"status": "no_db"}

    comm_col = db["marketing_communications"]
    comm = comm_col.find_one({"provider_message_id": msg_id})
    if not comm:
        return {"status": "unknown_provider_message_id", "msg_id": msg_id}

    current_status = str(comm.get("status", "sent")).strip().lower()

    # Format timestamp
    ts_iso = None
    if ts:
        try:
            ts_int = int(ts)
            ts_iso = datetime.datetime.fromtimestamp(ts_int, tz=datetime.timezone.utc).isoformat()
        except (ValueError, TypeError):
            pass
    if not ts_iso:
        ts_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # Rule: Do not invent a successful delivery when provider reports failure
    if current_status == "failed" and new_status != "failed":
        return {
            "status": "ignored_failed_override",
            "current_status": "failed",
            "incoming_status": new_status,
        }

    # Handle failure event
    if new_status == "failed":
        err_details = status_item.get("errors") or []
        err_msg = "Delivery failed"
        if err_details and isinstance(err_details, list) and isinstance(err_details[0], dict):
            err_msg = err_details[0].get("title") or err_details[0].get("message") or err_msg

        update_fields = {
            "status": "failed",
            "last_error": err_msg,
            "failed_at": ts_iso,
            "updated_at": now_iso,
        }
        history_entry = {"status": "failed", "timestamp": ts_iso, "error": err_details}
        comm_col.update_one(
            {"_id": comm["_id"]},
            {"$set": update_fields, "$push": {"status_history": history_entry}},
        )
        return {"status": "updated", "new_status": "failed", "comm_id": str(comm["_id"])}

    # Check precedence for positive delivery events
    current_rank = STATUS_RANKS.get(current_status, 0)
    new_rank = STATUS_RANKS.get(new_status, 0)

    if new_rank <= current_rank:
        return {
            "status": "ignored_out_of_order",
            "current_status": current_status,
            "incoming_status": new_status,
        }

    # Legitimate progression (sent -> delivered -> read)
    update_fields = {
        "status": new_status,
        "updated_at": now_iso,
    }
    if new_status == "delivered":
        update_fields["delivered_at"] = ts_iso
    elif new_status == "read":
        update_fields["read_at"] = ts_iso

    history_entry = {"status": new_status, "timestamp": ts_iso}
    comm_col.update_one(
        {"_id": comm["_id"]},
        {"$set": update_fields, "$push": {"status_history": history_entry}},
    )

    return {"status": "updated", "new_status": new_status, "comm_id": str(comm["_id"])}


def process_whatsapp_webhook_payload(db: Any, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Parse and process a full Meta WhatsApp Cloud API webhook JSON payload.

    Extracts:
        - messages (inbound customer messages including STOP)
        - statuses (outbound delivery updates: sent, delivered, read, failed)
    """
    summary = {
        "messages_processed": 0,
        "statuses_processed": 0,
        "opt_outs_recorded": 0,
        "duplicates_ignored": 0,
        "unmatched_senders": 0,
        "ambiguous_senders": 0,
    }

    if not isinstance(payload, dict):
        return summary

    ensure_webhook_indexes(db)

    entries = payload.get("entry") or []
    if not isinstance(entries, list):
        return summary

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        changes = entry.get("changes") or []
        if not isinstance(changes, list):
            continue
        for change in changes:
            if not isinstance(change, dict):
                continue
            val = change.get("value") or {}
            if not isinstance(val, dict):
                continue

            # Inbound messages
            messages = val.get("messages") or []
            if isinstance(messages, list):
                for msg in messages:
                    if isinstance(msg, dict):
                        summary["messages_processed"] += 1
                        res = process_inbound_message(db, msg)
                        st = res.get("status", "")
                        if st == "opt_out_recorded":
                            summary["opt_outs_recorded"] += 1
                        elif st == "duplicate":
                            summary["duplicates_ignored"] += 1
                        elif st == "opt_out_unmatched":
                            summary["unmatched_senders"] += 1
                        elif st == "opt_out_ambiguous":
                            summary["ambiguous_senders"] += 1

            # Delivery statuses
            statuses = val.get("statuses") or []
            if isinstance(statuses, list):
                for s in statuses:
                    if isinstance(s, dict):
                        summary["statuses_processed"] += 1
                        res = process_delivery_status(db, s)
                        if res.get("status") == "duplicate":
                            summary["duplicates_ignored"] += 1

    return summary


def validate_whatsapp_production_config() -> Dict[str, Any]:
    """Validate WhatsApp Business and Webhook production configuration.

    Safely inspects environment variables without exposing secret values or tokens.
    Returns structured readiness report for Meta Cloud API integration.
    """
    token = os.getenv("WHATSAPP_API_TOKEN") or os.getenv("META_WHATSAPP_TOKEN", "")
    phone_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID") or os.getenv("META_PHONE_NUMBER_ID", "")
    app_secret = os.getenv("WHATSAPP_APP_SECRET") or os.getenv("META_APP_SECRET", "")
    verify_token = os.getenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN") or os.getenv("META_VERIFY_TOKEN", "")
    waba_id = os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID") or os.getenv("META_WABA_ID", "")
    api_url = os.getenv("WHATSAPP_API_URL", "https://graph.facebook.com/v18.0")
    template_lang = os.getenv("WHATSAPP_TEMPLATE_LANGUAGE", "en_US")

    api_configured = bool(token.strip() and phone_id.strip())
    webhook_configured = bool(app_secret.strip() and verify_token.strip())

    template_vars = {
        "order_confirmation": bool(os.getenv("WHATSAPP_TEMPLATE_ORDER_CONFIRMATION")),
        "cart_abandonment": bool(os.getenv("WHATSAPP_TEMPLATE_CART_ABANDONMENT") or os.getenv("WHATSAPP_TEMPLATE_CART_ABANDONED")),
        "product_price_drop": bool(os.getenv("WHATSAPP_TEMPLATE_PRODUCT_PRICE_DROP")),
        "wishlist_reminder": bool(os.getenv("WHATSAPP_TEMPLATE_WISHLIST_REMINDER")),
        "opportunity_cart_discount": bool(os.getenv("WHATSAPP_TEMPLATE_OPPORTUNITY_CART_ITEM_DISCOUNT")),
        "opportunity_wishlist_discount": bool(os.getenv("WHATSAPP_TEMPLATE_OPPORTUNITY_WISHLIST_ITEM_DISCOUNT")),
    }

    missing_keys = []
    if not token.strip():
        missing_keys.append("WHATSAPP_API_TOKEN")
    if not phone_id.strip():
        missing_keys.append("WHATSAPP_PHONE_NUMBER_ID")
    if not app_secret.strip():
        missing_keys.append("WHATSAPP_APP_SECRET")
    if not verify_token.strip():
        missing_keys.append("WHATSAPP_WEBHOOK_VERIFY_TOKEN")

    return {
        "api_configured": api_configured,
        "webhook_configured": webhook_configured,
        "waba_id_configured": bool(waba_id.strip()),
        "api_url": api_url,
        "template_language": template_lang,
        "templates_configured": template_vars,
        "missing_required_variables": missing_keys,
        "production_ready": bool(api_configured and webhook_configured),
        "webhook_endpoint": "/api/webhook/whatsapp",
        "https_requirement": "Must be served over valid HTTPS with publicly resolvable DNS for Meta delivery.",
        "note": "Credentials and tokens are verified by presence and length only; values are never exposed."
    }
