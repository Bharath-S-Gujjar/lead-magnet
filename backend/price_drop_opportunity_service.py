"""Price-drop opportunity detection and customer matching service.

Identifies customers with active interest (current CART or WISHLIST) in products
that experienced a genuine price drop (old_price > new_price).
Applies customer lead state qualification (Hot, Warm, Hot->Warm eligible; Cold excluded),
enforces deterministic idempotency and communication cooldown, and writes to
the marketing_opportunities collection.
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from bson import ObjectId

from customer_feature_service import _to_object_id
from opportunity_engine import (
    OPP_PRODUCT_PRICE_DROP,
    OPPORTUNITY_COOLDOWN_HOURS,
    _is_within_opportunity_cooldown,
    ensure_marketing_opportunities_indexes,
    build_opportunity_email_content,
)
from marketing_automation_service import (
    dispatch_communication,
    evaluate_channel_eligibility,
    get_store_url,
)
from communication_provider import (
    get_communication_provider,
    DryRunCommunicationProvider,
)


def _build_customer_id_conditions(customer_id: Any) -> List[Dict[str, Any]]:
    """Build standardized user_id query conditions matching ObjectId and string."""
    c_oid = _to_object_id(customer_id)
    id_conds = []
    if c_oid:
        id_conds.append({"user_id": c_oid})
        id_conds.append({"user_id": str(c_oid)})
    if isinstance(customer_id, str):
        id_conds.append({"user_id": customer_id})
    return id_conds


def _normalize_id_string(val: Any) -> str:
    """Normalize any identifier (ObjectId, int, string) into a clean string."""
    if val is None:
        return ""
    return str(val).strip()


def _item_matches_product(
    item_doc: Dict[str, Any],
    product_id: str,
    source_product_id: Optional[str] = None,
    product_url: Optional[str] = None,
) -> bool:
    """Check if a cart or wishlist item matches the target product.

    Matches by:
      - product_id (e.g. 'myntra_28420390' or raw '28420390')
      - source_product_id (e.g. '28420390')
      - URL / SKU match if present in item document.
    """
    if not item_doc or not isinstance(item_doc, dict):
        return False

    target_pid = _normalize_id_string(product_id)
    target_spid = _normalize_id_string(source_product_id) if source_product_id else ""
    target_url = _normalize_id_string(product_url) if product_url else ""

    # Direct product_id field on item
    item_pid = _normalize_id_string(item_doc.get("product_id") or item_doc.get("_id"))
    if item_pid:
        if target_pid and item_pid == target_pid:
            return True
        if target_spid and item_pid == target_spid:
            return True
        if target_pid and f"myntra_{item_pid}" == target_pid:
            return True

    # source_product_id field if present
    item_spid = _normalize_id_string(item_doc.get("source_product_id"))
    if item_spid and target_spid and item_spid == target_spid:
        return True

    # URL field if present
    item_url = _normalize_id_string(item_doc.get("url") or item_doc.get("product_url"))
    if item_url and target_url and item_url == target_url:
        return True

    return False


def find_customers_with_product_in_cart_or_wishlist(
    product_id: str,
    source_product_id: Optional[str] = None,
    product_url: Optional[str] = None,
    db: Any = None,
) -> List[Dict[str, Any]]:
    """Query current active cart and wishlist collections for interested customers.

    STRICT REQUIREMENT: Uses CURRENT STATE ONLY.
    Does NOT query historical events or removed cart/wishlist items.

    Returns:
        List of dicts:
          [
            {
              "customer_id": <id>,
              "interest_source": "cart" | "wishlist" | "cart_and_wishlist",
              "product_id": product_id,
            },
            ...
          ]
    """
    if db is None:
        try:
            import app as app_module
            db = getattr(app_module, "db", None)
        except Exception:
            pass

    if db is None:
        return []

    cart_col = db["cart"]
    wishlist_col = db["wishlist"]

    customer_interests: Dict[str, Dict[str, Any]] = {}

    def _register_interest(cust_id_raw: Any, source: str) -> None:
        if not cust_id_raw:
            return
        cid_str = str(cust_id_raw)
        if cid_str not in customer_interests:
            customer_interests[cid_str] = {
                "customer_id": cust_id_raw,
                "interest_source": source,
                "product_id": product_id,
            }
        else:
            existing_src = customer_interests[cid_str]["interest_source"]
            if existing_src != source and "and" not in existing_src:
                customer_interests[cid_str]["interest_source"] = "cart_and_wishlist"

    # 1. Search Active Cart
    cart_cursor = cart_col.find({})
    for doc in cart_cursor:
        user_id = doc.get("user_id")
        if not user_id:
            continue

        # Item-level cart schema (doc has product_id directly)
        if _item_matches_product(doc, product_id, source_product_id, product_url):
            _register_interest(user_id, "cart")
            continue

        # Container cart schema (doc has 'items' array)
        items_list = doc.get("items")
        if isinstance(items_list, list):
            for it in items_list:
                if _item_matches_product(it, product_id, source_product_id, product_url):
                    _register_interest(user_id, "cart")
                    break

    # 2. Search Active Wishlist
    wl_cursor = wishlist_col.find({})
    for doc in wl_cursor:
        user_id = doc.get("user_id")
        if not user_id:
            continue

        if _item_matches_product(doc, product_id, source_product_id, product_url):
            _register_interest(user_id, "wishlist")
            continue

        items_list = doc.get("items")
        if isinstance(items_list, list):
            for it in items_list:
                if _item_matches_product(it, product_id, source_product_id, product_url):
                    _register_interest(user_id, "wishlist")
                    break

    return list(customer_interests.values())


def evaluate_customer_lead_state_eligibility(
    customer_id: Any,
    db: Any = None,
    lead_state_doc: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
    """Determine customer eligibility based on current lead state rules.

    Eligibility Rules:
      1. Warm customer from beginning: ELIGIBLE
      2. Previously Hot, currently Warm (Hot -> Warm): ELIGIBLE
      3. Currently Hot: ELIGIBLE
      4. Cold customer: NOT ELIGIBLE

    Returns:
        (is_eligible, reason_or_state, lead_state_doc)
    """
    if db is None:
        try:
            import app as app_module
            db = getattr(app_module, "db", None)
        except Exception:
            pass

    if lead_state_doc is None and db is not None:
        c_oid = _to_object_id(customer_id)
        state_col = db["customer_lead_state"]
        query_id = c_oid if c_oid else customer_id
        lead_state_doc = state_col.find_one({"customer_id": query_id})
        if not lead_state_doc and isinstance(customer_id, str):
            lead_state_doc = state_col.find_one({"customer_id": customer_id})

    if not lead_state_doc:
        # If no lead state document exists, customer is unclassified / not eligible
        return False, "no_lead_state", None

    current_segment = str(lead_state_doc.get("lead_segment") or "").strip()
    prob = float(lead_state_doc.get("lead_probability") or 0.0)
    score = int(lead_state_doc.get("lead_score") or 0)

    prev_segment = str(lead_state_doc.get("previous_segment") or "").strip()
    prev_prob = lead_state_doc.get("previous_probability")
    prev_prob_val = float(prev_prob) if prev_prob is not None else None
    prev_score = lead_state_doc.get("previous_score")
    prev_score_val = int(prev_score) if prev_score is not None else None

    # Check Hot
    is_currently_hot = (
        current_segment == "Hot"
        or prob >= 0.70
        or score >= 70
    )
    if is_currently_hot:
        return True, "Hot", lead_state_doc

    # Check Cold
    is_currently_cold = (
        current_segment == "Cold"
        or (prob < 0.35 and score < 35 and current_segment != "Warm")
    )
    if is_currently_cold:
        return False, "Cold", lead_state_doc

    # Check Warm
    is_currently_warm = (
        current_segment == "Warm"
        or (0.35 <= prob < 0.70)
        or (35 <= score < 70)
    )

    if is_currently_warm:
        was_previously_hot = (
            prev_segment == "Hot"
            or (prev_prob_val is not None and prev_prob_val >= 0.70)
            or (prev_score_val is not None and prev_score_val >= 70)
        )
        if was_previously_hot:
            return True, "Hot_to_Warm", lead_state_doc
        return True, "Warm", lead_state_doc

    return False, "unknown_segment", lead_state_doc


def create_price_drop_opportunity(
    customer_id: Any,
    price_drop_event: Dict[str, Any],
    interest_source: str,
    customer_lead_state: str,
    db: Any = None,
    current_time: Optional[datetime.datetime] = None,
) -> Optional[Dict[str, Any]]:
    """Construct and persist a deterministic, idempotent price drop opportunity.

    Key Format:
      opp:{customer_id}:price_drop:{product_id}:{old_price}_{new_price}
    """
    if db is None:
        return None

    c_oid = _to_object_id(customer_id)
    query_id = c_oid if c_oid else customer_id

    product_id = str(price_drop_event.get("product_id") or "").strip()
    old_price = price_drop_event.get("old_price")
    new_price = price_drop_event.get("new_price")

    if not product_id or old_price is None or new_price is None:
        return None

    now = current_time or datetime.datetime.now(datetime.timezone.utc)
    now_iso = now.isoformat()
    expires_iso = (now + datetime.timedelta(days=7)).isoformat()

    discount_amount = round(old_price - new_price, 2)
    discount_percent = int(round((discount_amount / old_price) * 100)) if old_price > 0 else 0

    opp_key = f"opp:{str(query_id)}:price_drop:{product_id}:{old_price}_{new_price}"

    title = str(price_drop_event.get("title") or "").strip()
    brand = str(price_drop_event.get("brand") or "").strip()
    primary_image = price_drop_event.get("primary_image")
    product_url = price_drop_event.get("url")
    source_pid = price_drop_event.get("source_product_id") or product_id.replace("myntra_", "")

    opp_doc = {
        "customer_id": query_id,
        "opportunity_type": OPP_PRODUCT_PRICE_DROP,
        "opportunity_key": opp_key,
        "product_id": product_id,
        "product_name": title,
        "related_product_ids": [],
        "opportunity_state": "detected",
        "metadata": {
            "customer_id": str(query_id),
            "product_id": product_id,
            "source_product_id": source_pid,
            "product_title": title,
            "product_name": title,
            "brand": brand,
            "old_price": old_price,
            "new_price": new_price,
            "discount_amount": discount_amount,
            "discount_percentage": discount_percent,
            "primary_image": primary_image,
            "product_url": product_url,
            "url": product_url,
            "customer_lead_state": customer_lead_state,
            "detected_at": now_iso,
            "source": "myntra",
            "interest_source": interest_source,
        },
        "detected_at": now_iso,
        "communicated_at": None,
        "expires_at": expires_iso,
    }

    ensure_marketing_opportunities_indexes(db)
    opp_col = db["marketing_opportunities"]

    opp_col.update_one(
        {"opportunity_key": opp_key},
        {"$setOnInsert": opp_doc},
        upsert=True,
    )

    saved = opp_col.find_one({"opportunity_key": opp_key})
    return saved or opp_doc


def process_price_drop_event(
    price_drop_event: Dict[str, Any],
    db: Any = None,
    enforce_cooldown: bool = True,
    current_time: Optional[datetime.datetime] = None,
) -> Dict[str, Any]:
    """Process a single detected price drop event.

    Matches against current cart/wishlist customers, checks lead state,
    enforces opportunity cooldown, and creates opportunities.

    Returns:
        dict:
          - product_id
          - old_price
          - new_price
          - customers_matched
          - opportunities_created
          - skipped_reasons
          - opportunities
    """
    product_id = price_drop_event.get("product_id")
    old_price = price_drop_event.get("old_price")
    new_price = price_drop_event.get("new_price")

    # Strict check: genuine price decrease only
    if old_price is None or new_price is None or old_price <= new_price:
        return {
            "product_id": product_id,
            "valid_price_drop": False,
            "opportunities_created": 0,
            "opportunities": [],
            "skipped_reasons": ["Price did not decrease"],
        }

    source_pid = price_drop_event.get("source_product_id")
    url = price_drop_event.get("url")

    # 1. Match current cart and wishlist
    interested_customers = find_customers_with_product_in_cart_or_wishlist(
        product_id=product_id,
        source_product_id=source_pid,
        product_url=url,
        db=db,
    )

    created_opps = []
    skipped_reasons = []

    for cust in interested_customers:
        cid = cust["customer_id"]
        interest_src = cust["interest_source"]

        # 2. Check lead state eligibility
        is_eligible, lead_state_label, _ = evaluate_customer_lead_state_eligibility(cid, db=db)
        if not is_eligible:
            skipped_reasons.append({
                "customer_id": str(cid),
                "reason": f"Customer lead state '{lead_state_label}' is not eligible for price-drop marketing.",
            })
            continue

        # 3. Check opportunity cooldown
        if enforce_cooldown and db is not None:
            if _is_within_opportunity_cooldown(cid, db, cooldown_hours=OPPORTUNITY_COOLDOWN_HOURS):
                skipped_reasons.append({
                    "customer_id": str(cid),
                    "reason": f"Customer is within opportunity cooldown period ({OPPORTUNITY_COOLDOWN_HOURS}h).",
                })
                # Note: We still create the opportunity in DB for audit/future delivery,
                # but flag cooldown in the report.
                opp = create_price_drop_opportunity(
                    customer_id=cid,
                    price_drop_event=price_drop_event,
                    interest_source=interest_src,
                    customer_lead_state=lead_state_label,
                    db=db,
                    current_time=current_time,
                )
                if opp:
                    opp["cooldown_suppressed"] = True
                    created_opps.append(opp)
                continue

        # 4. Create Opportunity
        opp = create_price_drop_opportunity(
            customer_id=cid,
            price_drop_event=price_drop_event,
            interest_source=interest_src,
            customer_lead_state=lead_state_label,
            db=db,
            current_time=current_time,
        )
        if opp:
            created_opps.append(opp)

    return {
        "product_id": product_id,
        "valid_price_drop": True,
        "old_price": old_price,
        "new_price": new_price,
        "customers_matched": len(interested_customers),
        "opportunities_created": len(created_opps),
        "opportunities": created_opps,
        "skipped_reasons": skipped_reasons,
    }


def process_price_drop_opportunities(
    price_drops_list: List[Dict[str, Any]],
    db: Any = None,
    enforce_cooldown: bool = True,
    current_time: Optional[datetime.datetime] = None,
) -> Dict[str, Any]:
    """Batch process a list of price drop events (e.g. from sync_myntra_products)."""
    total_created = 0
    all_opportunities = []
    reports = []

    for event in price_drops_list:
        rep = process_price_drop_event(
            event,
            db=db,
            enforce_cooldown=enforce_cooldown,
            current_time=current_time,
        )
        reports.append(rep)
        total_created += rep.get("opportunities_created", 0)
        all_opportunities.extend(rep.get("opportunities", []))

    return {
        "price_drops_evaluated": len(price_drops_list),
        "total_opportunities_created": total_created,
        "opportunities": all_opportunities,
        "reports": reports,
    }


def dispatch_price_drop_opportunity(
    opportunity_or_key: Union[Dict[str, Any], str, ObjectId],
    db: Any = None,
    provider: Any = None,
    policy: Optional[Dict[str, Any]] = None,
    enforce_cooldown: bool = True,
    current_time: Optional[datetime.datetime] = None,
) -> Dict[str, Any]:
    """Deterministically dispatch an eligible product_price_drop opportunity via Gmail.

    Connects product_price_drop opportunities to the existing marketing communication
    engine and Gmail SMTP provider.

    Flow:
        1. Resolve opportunity document from DB or argument.
        2. Verify channel eligibility for the customer (email channel).
        3. Check idempotency:
           - If opportunity_state == "communicated" or marketing_communications
             already has a 'sent' record for this key, prevent duplicate dispatch.
        4. Enforce 24-hour promotional opportunity cooldown:
           - If within cooldown and enforce_cooldown=True, suppress send.
        5. Generate customer-friendly email content using build_opportunity_email_content:
           - Differs appropriately based on interest source (cart vs wishlist).
           - Includes product name, reduced price, previous price, discount details,
             product link, and rendered HTML with product image.
           - Strictly NEVER exposes lead score, probability, Hot/Warm status,
             model metadata, internal IDs, or opportunity IDs to customer.
        6. Dispatch email via marketing_automation_service.dispatch_communication
           using existing GmailSMTPProvider (or supplied mock/dry-run provider).
        7. Update marketing_opportunities status:
           - "communicated" with communicated_at timestamp ONLY if provider confirms success.
           - "failed" if provider delivery fails.
        8. Return structured dispatch result with communication_id, status, and provider message ID.
    """
    if db is None:
        try:
            import app as app_module
            db = getattr(app_module, "db", None)
        except Exception:
            pass

    if db is None:
        return {"success": False, "status": "failed", "error": "Database unavailable"}

    opp_col = db["marketing_opportunities"]
    comm_col = db["marketing_communications"]

    opp_doc = None
    if isinstance(opportunity_or_key, dict):
        opp_doc = opportunity_or_key
        opp_key = opp_doc.get("opportunity_key")
        if opp_key:
            db_opp = opp_col.find_one({"opportunity_key": opp_key})
            if db_opp:
                opp_doc = db_opp
    elif isinstance(opportunity_or_key, str):
        opp_doc = opp_col.find_one({"opportunity_key": opportunity_or_key})
        if not opp_doc:
            oid = _to_object_id(opportunity_or_key)
            if oid:
                opp_doc = opp_col.find_one({"_id": oid})
    elif isinstance(opportunity_or_key, ObjectId):
        opp_doc = opp_col.find_one({"_id": opportunity_or_key})

    if not opp_doc:
        return {
            "success": False,
            "status": "not_found",
            "error": f"Opportunity not found: {opportunity_or_key}",
        }

    opp_key = opp_doc.get("opportunity_key")
    customer_id = opp_doc.get("customer_id")
    c_oid = _to_object_id(customer_id)
    query_id = c_oid if c_oid else customer_id

    email_idempotency_key = f"{opp_key}:email"

    # 1. Idempotency Check
    if opp_doc.get("opportunity_state") == "communicated":
        existing_comm = comm_col.find_one({"idempotency_key": email_idempotency_key, "status": "sent"})
        return {
            "success": False,
            "status": "already_communicated",
            "opportunity_key": opp_key,
            "communication_id": str(existing_comm.get("_id", "")) if existing_comm else None,
            "provider_message_id": existing_comm.get("provider_message_id") if existing_comm else None,
            "reason": "Opportunity already communicated",
        }

    existing_sent = comm_col.find_one({"idempotency_key": email_idempotency_key, "status": "sent"})
    if existing_sent:
        now_iso = (current_time or datetime.datetime.now(datetime.timezone.utc)).isoformat()
        opp_col.update_one(
            {"opportunity_key": opp_key},
            {"$set": {"opportunity_state": "communicated", "communicated_at": now_iso}}
        )
        return {
            "success": False,
            "status": "already_sent",
            "opportunity_key": opp_key,
            "communication_id": str(existing_sent.get("_id", "")),
            "provider_message_id": existing_sent.get("provider_message_id"),
            "reason": "Communication already sent for this opportunity",
        }

    # 2. 24-hour Opportunity Cooldown Check
    if enforce_cooldown and _is_within_opportunity_cooldown(query_id, db, cooldown_hours=OPPORTUNITY_COOLDOWN_HOURS, current_time=current_time):
        return {
            "success": False,
            "status": "cooldown_suppressed",
            "opportunity_key": opp_key,
            "reason": f"Customer is within {OPPORTUNITY_COOLDOWN_HOURS}-hour promotional opportunity cooldown",
        }

    # 3. Channel eligibility & Recipient resolution
    profiles_col = db["user_profiles"]
    profile = profiles_col.find_one({"_id": c_oid}) if c_oid else None
    if not profile and isinstance(customer_id, str):
        profile = profiles_col.find_one({"_id": customer_id}) or profiles_col.find_one({"user_id": customer_id})

    eligibility = evaluate_channel_eligibility(profile, policy)
    email_info = eligibility.get("email", {})
    if not email_info.get("eligible"):
        return {
            "success": False,
            "status": "skipped",
            "opportunity_key": opp_key,
            "reason": email_info.get("reason", "Customer not eligible for email communication"),
        }

    recipient_email = email_info.get("recipient")
    cust_name = (profile.get("full_name") or profile.get("username") or "there") if profile else "there"
    store_url = get_store_url()

    # 4. Generate customer-facing email content
    subject, body = build_opportunity_email_content(opp_doc, cust_name, store_url)

    opp_meta = opp_doc.get("metadata") or {}
    comm_metadata = {
        "opportunity_key": opp_key,
        "opportunity_type": OPP_PRODUCT_PRICE_DROP,
        "product_id": str(opp_doc.get("product_id") or ""),
        "primary_image": opp_meta.get("primary_image"),
        "product_url": opp_meta.get("product_url") or opp_meta.get("url"),
        "old_price": opp_meta.get("old_price"),
        "new_price": opp_meta.get("new_price"),
        "discount_amount": opp_meta.get("discount_amount"),
        "discount_percentage": opp_meta.get("discount_percentage"),
        "interest_source": opp_meta.get("interest_source"),
    }

    # 5. Dispatch via existing communication provider
    if provider is None:
        provider = get_communication_provider()

    comm_res = dispatch_communication(
        db=db,
        customer_id=query_id,
        campaign_type="product_price_drop",
        channel="email",
        recipient=recipient_email,
        subject=subject,
        body=body,
        metadata=comm_metadata,
        idempotency_key=email_idempotency_key,
        provider=provider,
    )

    success = bool(comm_res and comm_res.get("status") == "sent")
    now_iso = (current_time or datetime.datetime.now(datetime.timezone.utc)).isoformat()

    # 6. Update opportunity state based on provider confirmation
    if success:
        opp_col.update_one(
            {"opportunity_key": opp_key},
            {"$set": {"opportunity_state": "communicated", "communicated_at": now_iso}}
        )
        opp_doc["opportunity_state"] = "communicated"
        opp_doc["communicated_at"] = now_iso
    else:
        last_err = comm_res.get("last_error") if comm_res else "Dispatch failed"
        opp_col.update_one(
            {"opportunity_key": opp_key},
            {"$set": {"opportunity_state": "failed", "last_error": last_err}}
        )
        opp_doc["opportunity_state"] = "failed"
        opp_doc["last_error"] = last_err

    return {
        "success": success,
        "status": comm_res.get("status") if comm_res else "failed",
        "opportunity_key": opp_key,
        "communication_id": str(comm_res.get("_id", "")) if comm_res else None,
        "provider": comm_res.get("provider") if comm_res else "unknown",
        "provider_message_id": comm_res.get("provider_message_id") if comm_res else None,
        "recipient": recipient_email,
        "subject": subject,
        "body": body,
        "error": comm_res.get("last_error") if comm_res else None,
    }
