"""Opportunity Engine for Hot Lead Email Intelligence.

Upgrades the Lead Magnet Gmail communication system to be opportunity-driven.

Core Business Logic:
    - HOT STATUS identifies WHO to prioritize (lead_probability >= 0.70).
    - CUSTOMER BEHAVIOUR identifies WHAT the customer is interested in (cart, wishlist, views).
    - PRODUCT/CATALOG INTELLIGENCE identifies WHICH relevant products to recommend.
    - OFFERS/DISCOUNTS identify WHEN there is a strong opportunity to contact the customer.
    - COMMUNICATION INTELLIGENCE decides WHETHER an email should actually be sent (eligibility, cooldown, idempotency).

Opportunity Types:
    1. CART_ITEM_DISCOUNT: A currently active cart item has a meaningful catalog price/discount.
    2. WISHLIST_ITEM_DISCOUNT: A currently active wishlist item has a meaningful catalog price/discount.
    3. SIMILAR_PRODUCT_DISCOUNT: A relevant alternative product related to demonstrated interest has a meaningful discount.
    4. CART_ABANDONMENT: Customer has an active abandoned cart according to cart-abandonment rules.
    5. WISHLIST_INACTIVITY: Customer has active wishlist items that have remained inactive according to wishlist rules.
    6. HOT_TO_WARM_REENGAGEMENT: Customer was previously Hot and experiences a significant decline (>= 0.10 probability or >= 10 score points) into Warm.

Channels:
    EMAIL (Gmail SMTP) ONLY.
    WhatsApp is POSTPONED and untouched.
"""

import os
from datetime import datetime, timezone, timedelta
from bson import ObjectId

from customer_feature_service import _to_object_id
from marketing_automation_service import (
    get_store_url,
    dispatch_communication,
    evaluate_channel_eligibility,
    _is_channel_enabled,
    MARKETING_COOLDOWN_HOURS,
)
from communication_provider import get_communication_provider, DryRunCommunicationProvider

# Configurable opportunity cooldown between successive opportunity emails to the same customer (default 24h)
OPPORTUNITY_COOLDOWN_HOURS = int(os.getenv("OPPORTUNITY_COOLDOWN_HOURS", "24"))

# Canonical Opportunity Types
OPP_CART_ITEM_DISCOUNT = "cart_item_discount"
OPP_WISHLIST_ITEM_DISCOUNT = "wishlist_item_discount"
OPP_SIMILAR_PRODUCT_DISCOUNT = "similar_product_discount"
OPP_CART_ABANDONMENT = "cart_abandonment"
OPP_WISHLIST_INACTIVITY = "wishlist_inactivity"
OPP_HOT_TO_WARM_REENGAGEMENT = "hot_to_warm_reengagement"
OPP_PRODUCT_PRICE_DROP = "product_price_drop"

ALL_OPPORTUNITY_TYPES = [
    OPP_CART_ITEM_DISCOUNT,
    OPP_WISHLIST_ITEM_DISCOUNT,
    OPP_SIMILAR_PRODUCT_DISCOUNT,
    OPP_CART_ABANDONMENT,
    OPP_WISHLIST_INACTIVITY,
    OPP_HOT_TO_WARM_REENGAGEMENT,
    OPP_PRODUCT_PRICE_DROP,
]


def ensure_marketing_opportunities_indexes(db):
    """Safely ensure unique index on opportunity_key in marketing_opportunities."""
    try:
        if hasattr(db, "__getitem__") and "marketing_opportunities" in db:
            opp_col = db["marketing_opportunities"]
        else:
            return

        existing_idx = {idx["name"] for idx in opp_col.list_indexes()}
        if "opportunity_key_1" not in existing_idx:
            opp_col.create_index(
                [("opportunity_key", 1)],
                unique=True,
                name="opportunity_key_1",
                background=True
            )
        if "customer_id_1" not in existing_idx:
            opp_col.create_index([("customer_id", 1)], name="customer_id_1", background=True)
        if "opportunity_type_1" not in existing_idx:
            opp_col.create_index([("opportunity_type", 1)], name="opportunity_type_1", background=True)
        if "detected_at_1" not in existing_idx:
            opp_col.create_index([("detected_at", 1)], name="detected_at_1", background=True)
    except Exception:
        pass


def extract_product_discount(product):
    """Inspect product document and detect genuine catalog discount.

    Recognizes canonical fields from catalog schema:
        - 'discount': integer/float percentage (e.g. 10, 15, 20, 25 from seed_clothing_products)
        - 'discount_percent' / 'discount_percentage'
        - 'original_price' / 'mrp' > 'price'
        - 'sale_price' < 'price'

    Returns:
        dict:
            has_discount (bool): True if real positive discount exists.
            discount_percent (int): Percentage discount (e.g. 20 for 20% off).
            current_price (float): Price after discount.
            original_price (float or None): Original list price if determinable.
    """
    if not product or not isinstance(product, dict):
        return {
            "has_discount": False,
            "discount_percent": 0,
            "current_price": 0.0,
            "original_price": None,
        }

    raw_price = product.get("price") if product.get("price") is not None else product.get("price_inr", 0)
    try:
        current_price = float(raw_price or 0.0)
    except (ValueError, TypeError):
        current_price = 0.0

    raw_discount = product.get("discount")
    if raw_discount is None:
        raw_discount = product.get("discount_percent") or product.get("discount_percentage")

    discount_percent = 0
    original_price = None

    if raw_discount is not None:
        try:
            val = float(raw_discount)
            if val > 0:
                discount_percent = int(round(val))
                if current_price > 0:
                    original_price = round(current_price / (1.0 - (discount_percent / 100.0)), 2)
        except (ValueError, TypeError):
            pass

    # Check original_price / mrp difference if not already established
    if discount_percent <= 0:
        raw_orig = product.get("original_price") or product.get("mrp") or product.get("regular_price")
        if raw_orig is not None:
            try:
                orig_val = float(raw_orig)
                if orig_val > current_price > 0:
                    original_price = orig_val
                    discount_percent = int(round(((orig_val - current_price) / orig_val) * 100))
            except (ValueError, TypeError):
                pass

    has_discount = bool(discount_percent > 0 and current_price > 0)

    return {
        "has_discount": has_discount,
        "discount_percent": discount_percent if has_discount else 0,
        "current_price": current_price,
        "original_price": original_price if has_discount else None,
    }


def _resolve_product_by_id(product_id, products_col):
    """Retrieve full product doc by ObjectId or string id."""
    if not product_id:
        return None
    p_oid = _to_object_id(product_id)
    query_id = p_oid if p_oid else product_id
    prod = products_col.find_one({"_id": query_id})
    if not prod and isinstance(product_id, str):
        prod = products_col.find_one({"_id": product_id}) or products_col.find_one({"product_id": product_id})
    return prod


def detect_customer_interests(customer_id, db):
    """Derive demonstrated product interests from actual customer behavior.

    Inspects:
        - Current cart items
        - Current wishlist items
        - Past orders
        - Product view / interaction events
        - User profile preferences (favorite_categories, favorite_brands)

    Returns:
        dict:
            cart_products (list[dict]): Resolved products in active cart.
            wishlist_products (list[dict]): Resolved products in active wishlist.
            viewed_products (list[dict]): Resolved products recently viewed.
            all_interest_products (list[dict]): Unique list of all interested products.
            primary_categories (list[str]): Top categories customer engaged with.
            primary_brands (list[str]): Top brands customer engaged with.
            genders (list[str]): Genders detected in interests (e.g. 'Men', 'Women', 'Kids').
    """
    c_oid = _to_object_id(customer_id)
    id_conds = []
    if c_oid:
        id_conds.append({"user_id": c_oid})
        id_conds.append({"user_id": str(c_oid)})
    if isinstance(customer_id, str):
        id_conds.append({"user_id": customer_id})

    products_col = db["products"]
    cart_col = db["cart"]
    wishlist_col = db["wishlist"]
    events_col = db["events"]
    profiles_col = db["user_profiles"]

    # 1. Cart Items
    cart_products = []
    seen_cart_ids = set()

    # Query item-level docs
    cart_docs = list(cart_col.find({"$or": id_conds})) if id_conds else []
    for doc in cart_docs:
        # Check if doc has 'items' array
        if "items" in doc and isinstance(doc["items"], list):
            for it in doc["items"]:
                pid = it.get("product_id") or it.get("_id")
                p = _resolve_product_by_id(pid, products_col)
                if not p and (it.get("name") or it.get("title")):
                    p = {
                        "_id": pid,
                        "name": it.get("name") or it.get("title"),
                        "price": it.get("price", 0),
                        "category": it.get("category"),
                        "brand": it.get("brand"),
                        "discount": it.get("discount", 0),
                    }
                if p:
                    str_pid = str(p.get("_id", pid))
                    if str_pid not in seen_cart_ids:
                        seen_cart_ids.add(str_pid)
                        cart_products.append(p)
        else:
            pid = doc.get("product_id")
            p = _resolve_product_by_id(pid, products_col)
            if p:
                str_pid = str(p.get("_id", pid))
                if str_pid not in seen_cart_ids:
                    seen_cart_ids.add(str_pid)
                    cart_products.append(p)

    # 2. Wishlist Items
    wishlist_products = []
    seen_wl_ids = set()

    wl_docs = list(wishlist_col.find({"$or": id_conds})) if id_conds else []
    for doc in wl_docs:
        if "items" in doc and isinstance(doc["items"], list):
            for it in doc["items"]:
                pid = it.get("product_id") or it.get("_id")
                p = _resolve_product_by_id(pid, products_col)
                if not p and (it.get("name") or it.get("title")):
                    p = {
                        "_id": pid,
                        "name": it.get("name") or it.get("title"),
                        "price": it.get("price", 0),
                        "category": it.get("category"),
                        "brand": it.get("brand"),
                        "discount": it.get("discount", 0),
                    }
                if p:
                    str_pid = str(p.get("_id", pid))
                    if str_pid not in seen_wl_ids:
                        seen_wl_ids.add(str_pid)
                        wishlist_products.append(p)
        else:
            pid = doc.get("product_id")
            p = _resolve_product_by_id(pid, products_col)
            if p:
                str_pid = str(p.get("_id", pid))
                if str_pid not in seen_wl_ids:
                    seen_wl_ids.add(str_pid)
                    wishlist_products.append(p)

    # 3. Product View Events
    viewed_products = []
    seen_view_ids = set()
    event_query = {
        "$or": id_conds,
        "$or": [
            {"type": {"$in": ["product_view", "product_click", "add_to_cart", "wishlist_add"]}},
            {"event_type": {"$in": ["product_view", "product_click", "add_to_cart", "wishlist_add"]}},
        ]
    } if id_conds else {"_id": None}

    # Simplified event search matching user
    event_user_conds = []
    if c_oid:
        event_user_conds.append({"user_id": c_oid})
        event_user_conds.append({"user_id": str(c_oid)})
    if isinstance(customer_id, str):
        event_user_conds.append({"user_id": customer_id})

    recent_events = list(events_col.find(
        {"$or": event_user_conds} if event_user_conds else {"_id": None}
    ).sort("timestamp", -1).limit(20))

    for ev in recent_events:
        pid = ev.get("product_id") or (ev.get("product_data") or {}).get("product_id") or (ev.get("product_data") or {}).get("id")
        if pid:
            p = _resolve_product_by_id(pid, products_col)
            if p:
                str_pid = str(p.get("_id", pid))
                if str_pid not in seen_view_ids and str_pid not in seen_cart_ids and str_pid not in seen_wl_ids:
                    seen_view_ids.add(str_pid)
                    viewed_products.append(p)

    # 4. Aggregations of categories, brands, genders
    all_interest_products = []
    seen_all = set()
    category_counts = {}
    brand_counts = {}
    genders = set()

    for p in (cart_products + wishlist_products + viewed_products):
        str_pid = str(p.get("_id", ""))
        if str_pid and str_pid not in seen_all:
            seen_all.add(str_pid)
            all_interest_products.append(p)

        cat = p.get("category")
        if cat:
            category_counts[cat] = category_counts.get(cat, 0) + 1
        brand = p.get("brand")
        if brand:
            brand_counts[brand] = brand_counts.get(brand, 0) + 1
        gender = p.get("gender")
        if gender:
            genders.add(gender)

    # Also incorporate profile favorite categories / brands
    profile = profiles_col.find_one({"_id": c_oid}) if c_oid else None
    if not profile and isinstance(customer_id, str):
        profile = profiles_col.find_one({"_id": customer_id}) or profiles_col.find_one({"user_id": customer_id})
    if profile:
        fav_cats = profile.get("favorite_categories") or {}
        if isinstance(fav_cats, dict):
            for c, cnt in fav_cats.items():
                category_counts[c] = category_counts.get(c, 0) + cnt
        fav_brands = profile.get("favorite_brands") or {}
        if isinstance(fav_brands, dict):
            for b, cnt in fav_brands.items():
                brand_counts[b] = brand_counts.get(b, 0) + cnt

    sorted_categories = sorted(category_counts.keys(), key=lambda k: category_counts[k], reverse=True)
    sorted_brands = sorted(brand_counts.keys(), key=lambda k: brand_counts[k], reverse=True)

    return {
        "cart_products": cart_products,
        "wishlist_products": wishlist_products,
        "viewed_products": viewed_products,
        "all_interest_products": all_interest_products,
        "primary_categories": sorted_categories,
        "primary_brands": sorted_brands,
        "genders": list(genders),
    }


def find_similar_discounted_products(target_product, db, limit=3, exclude_product_ids=None):
    """Find genuinely relevant alternative products from the catalog with active discounts.

    Similarity criteria:
        - Same product category (e.g. 'Hoodies')
        - Same apparel gender if specified (e.g. 'Men', 'Women', 'Kids')
        - Genuine catalog discount (> 0)
        - Excludes target product and exclude_product_ids
        - Ranked by relevance (different brand alternative, higher discount, rating)

    Args:
        target_product (dict): Source product customer demonstrated interest in.
        db: PyMongo database.
        limit (int): Maximum recommendations to return.
        exclude_product_ids (set or list): Product IDs to exclude.

    Returns:
        list[dict]: Relevant discounted alternative products.
    """
    if not target_product or not isinstance(target_product, dict):
        return []

    category = target_product.get("category")
    if not category:
        return []

    target_gender = target_product.get("gender")
    target_id_str = str(target_product.get("_id", ""))

    exclude_set = set(str(pid) for pid in (exclude_product_ids or []))
    if target_id_str:
        exclude_set.add(target_id_str)

    products_col = db["products"]

    # Match category (case-insensitive regex)
    query = {
        "category": {"$regex": f"^{category.strip()}$", "$options": "i"}
    }
    if target_gender:
        query["gender"] = {"$regex": f"^{target_gender.strip()}$", "$options": "i"}

    candidates = list(products_col.find(query))

    matching_discounted = []
    target_brand = (target_product.get("brand") or "").casefold()

    for cand in candidates:
        cand_id_str = str(cand.get("_id", ""))
        if cand_id_str in exclude_set:
            continue
        # Also avoid identical name
        if cand.get("name") and cand.get("name") == target_product.get("name"):
            continue

        disc_info = extract_product_discount(cand)
        if not disc_info["has_discount"]:
            continue

        # Score relevance
        cand_brand = (cand.get("brand") or "").casefold()
        brand_score = 1.5 if (cand_brand and cand_brand != target_brand) else 1.0
        discount_score = disc_info["discount_percent"] * 0.1
        cand_rating = cand.get("rating")
        try:
            rating_score = float(cand_rating) if cand_rating is not None else 4.0
        except (ValueError, TypeError):
            rating_score = 4.0

        total_score = brand_score + discount_score + rating_score

        cand_copy = dict(cand)
        cand_copy["discount_info"] = disc_info
        matching_discounted.append((total_score, cand_copy))

    matching_discounted.sort(key=lambda x: x[0], reverse=True)
    return [item[1] for item in matching_discounted[:limit]]


def _is_within_opportunity_cooldown(customer_id, db, cooldown_hours=OPPORTUNITY_COOLDOWN_HOURS, current_time=None):
    """Check if customer was sent any email within the opportunity cooldown period.

    Prevents multiple emails in rapid succession to the same customer.
    """
    if cooldown_hours <= 0:
        return False

    c_oid = _to_object_id(customer_id)
    comms_col = db["marketing_communications"]
    id_conds = []
    if c_oid:
        id_conds.append({"customer_id": c_oid})
        id_conds.append({"customer_id": str(c_oid)})
    if isinstance(customer_id, str):
        id_conds.append({"customer_id": customer_id})

    last_comm = comms_col.find_one(
        {"$or": id_conds, "channel": "email", "status": "sent"},
        sort=[("sent_at", -1)]
    )
    if not last_comm or not last_comm.get("sent_at"):
        return False

    sent_at_val = last_comm["sent_at"]
    if isinstance(sent_at_val, str):
        try:
            sent_at = datetime.fromisoformat(sent_at_val)
        except Exception:
            return False
    elif isinstance(sent_at_val, datetime):
        sent_at = sent_at_val
    else:
        return False

    if sent_at.tzinfo is None:
        sent_at = sent_at.replace(tzinfo=timezone.utc)

    now_dt = current_time or datetime.now(timezone.utc)
    if now_dt.tzinfo is None:
        now_dt = now_dt.replace(tzinfo=timezone.utc)

    return now_dt < (sent_at + timedelta(hours=cooldown_hours))


def detect_opportunities_for_customer(customer_id, db, lead_state_doc=None, current_time=None):
    """Detect and record all valid opportunities for a Hot customer.

    Rules:
        - Customer is eligible if lead_probability >= 0.70 (or segment == 'Hot' or score >= 70).
        - Exception: HOT_TO_WARM_REENGAGEMENT evaluates customers transitioning from Hot to Warm
          with a significant decline (prob drop >= 0.10 or score drop >= 10).
        - Insignificant fluctuations (< 0.10 / < 10) do NOT trigger re-engagement.
        - Persists detected opportunities idempotently into marketing_opportunities.

    Returns:
        list[dict]: List of detected opportunity documents.
    """
    if db is None or not customer_id:
        return []

    c_oid = _to_object_id(customer_id)
    query_id = c_oid if c_oid else customer_id

    ensure_marketing_opportunities_indexes(db)
    opp_col = db["marketing_opportunities"]

    if lead_state_doc is None:
        lead_state_col = db["customer_lead_state"]
        lead_state_doc = lead_state_col.find_one({"customer_id": query_id})
        if not lead_state_doc and isinstance(customer_id, str):
            lead_state_doc = lead_state_col.find_one({"customer_id": customer_id})

    if not lead_state_doc:
        return []

    lead_prob = float(lead_state_doc.get("lead_probability") or 0.0)
    lead_score = int(lead_state_doc.get("lead_score") or 0)
    lead_segment = str(lead_state_doc.get("lead_segment") or "")

    prev_prob = lead_state_doc.get("previous_probability")
    prev_prob_val = float(prev_prob) if prev_prob is not None else None
    prev_score = lead_state_doc.get("previous_score")
    prev_score_val = int(prev_score) if prev_score is not None else None
    prev_segment = str(lead_state_doc.get("previous_segment") or "")

    is_hot = (lead_prob >= 0.70 or lead_segment == "Hot" or lead_score >= 70)

    # Check Hot -> Warm decline rule
    was_hot = (prev_segment == "Hot" or (prev_prob_val is not None and prev_prob_val >= 0.70) or (prev_score_val is not None and prev_score_val >= 70))
    is_warm = (lead_segment == "Warm" or (0.35 <= lead_prob < 0.70) or (35 <= lead_score < 70))

    prob_drop = (prev_prob_val - lead_prob) if (prev_prob_val is not None) else 0.0
    score_drop = (prev_score_val - lead_score) if (prev_score_val is not None) else 0

    # Rule: Drop of at least 0.10 probability OR 10 score points constitutes significant decline
    is_significant_decline = was_hot and is_warm and (prob_drop >= 0.10 or score_drop >= 10)

    if not is_hot and not is_significant_decline:
        # Neither currently Hot nor in significant Hot->Warm decline
        return []

    now = current_time or datetime.now(timezone.utc)
    now_iso = now.isoformat()
    expires_iso = (now + timedelta(days=7)).isoformat()

    detected_opportunities = []

    # 1. Hot -> Warm Re-engagement Opportunity
    if is_significant_decline:
        opp_key = f"opp:{str(query_id)}:hot_to_warm:{prev_score_val}_{lead_score}"
        opp_doc = {
            "customer_id": query_id,
            "opportunity_type": OPP_HOT_TO_WARM_REENGAGEMENT,
            "opportunity_key": opp_key,
            "product_id": None,
            "product_name": None,
            "related_product_ids": [],
            "opportunity_state": "detected",
            "metadata": {
                "previous_probability": prev_prob_val,
                "current_probability": lead_prob,
                "probability_drop": round(prob_drop, 4),
                "previous_score": prev_score_val,
                "current_score": lead_score,
                "score_drop": score_drop,
                "reason": "Customer transitioned from Hot to Warm with significant score decline",
            },
            "detected_at": now_iso,
            "communicated_at": None,
            "expires_at": expires_iso,
        }
        res = opp_col.update_one(
            {"opportunity_key": opp_key},
            {"$setOnInsert": opp_doc},
            upsert=True
        )
        saved = opp_col.find_one({"opportunity_key": opp_key})
        detected_opportunities.append(saved or opp_doc)

    # If customer is not currently Hot (e.g. only Hot->Warm re-engagement applied), stop here
    if not is_hot:
        return detected_opportunities

    # For Hot Customers: derive product interests
    interests = detect_customer_interests(query_id, db)
    cart_prods = interests["cart_products"]
    wl_prods = interests["wishlist_products"]
    interest_prods = interests["all_interest_products"]

    # Exclude IDs for similar recommendations (items already in cart or wishlist)
    exclude_ids = {str(p["_id"]) for p in (cart_prods + wl_prods) if "_id" in p}

    # 2. CART_ITEM_DISCOUNT
    for p in cart_prods:
        disc = extract_product_discount(p)
        if disc["has_discount"]:
            pid_str = str(p.get("_id", ""))
            pct = disc["discount_percent"]
            opp_key = f"opp:{str(query_id)}:cart_discount:{pid_str}:{pct}"
            opp_doc = {
                "customer_id": query_id,
                "opportunity_type": OPP_CART_ITEM_DISCOUNT,
                "opportunity_key": opp_key,
                "product_id": p.get("_id"),
                "product_name": p.get("name"),
                "related_product_ids": [],
                "opportunity_state": "detected",
                "metadata": {
                    "product_name": p.get("name"),
                    "category": p.get("category"),
                    "brand": p.get("brand"),
                    "discount_percent": pct,
                    "current_price": disc["current_price"],
                    "original_price": disc["original_price"],
                },
                "detected_at": now_iso,
                "communicated_at": None,
                "expires_at": expires_iso,
            }
            opp_col.update_one(
                {"opportunity_key": opp_key},
                {"$setOnInsert": opp_doc},
                upsert=True
            )
            saved = opp_col.find_one({"opportunity_key": opp_key})
            detected_opportunities.append(saved or opp_doc)

    # 3. WISHLIST_ITEM_DISCOUNT
    for p in wl_prods:
        disc = extract_product_discount(p)
        if disc["has_discount"]:
            pid_str = str(p.get("_id", ""))
            pct = disc["discount_percent"]
            opp_key = f"opp:{str(query_id)}:wishlist_discount:{pid_str}:{pct}"
            opp_doc = {
                "customer_id": query_id,
                "opportunity_type": OPP_WISHLIST_ITEM_DISCOUNT,
                "opportunity_key": opp_key,
                "product_id": p.get("_id"),
                "product_name": p.get("name"),
                "related_product_ids": [],
                "opportunity_state": "detected",
                "metadata": {
                    "product_name": p.get("name"),
                    "category": p.get("category"),
                    "brand": p.get("brand"),
                    "discount_percent": pct,
                    "current_price": disc["current_price"],
                    "original_price": disc["original_price"],
                },
                "detected_at": now_iso,
                "communicated_at": None,
                "expires_at": expires_iso,
            }
            opp_col.update_one(
                {"opportunity_key": opp_key},
                {"$setOnInsert": opp_doc},
                upsert=True
            )
            saved = opp_col.find_one({"opportunity_key": opp_key})
            detected_opportunities.append(saved or opp_doc)

    # 4. SIMILAR_PRODUCT_DISCOUNT
    # Look for alternatives for interest items (especially wishlist items or interest products)
    seed_targets = wl_prods if wl_prods else (cart_prods if cart_prods else interest_prods)
    for target in seed_targets[:2]:
        similar_items = find_similar_discounted_products(target, db, limit=2, exclude_product_ids=exclude_ids)
        for rec in similar_items:
            rec_id_str = str(rec.get("_id", ""))
            source_id_str = str(target.get("_id", ""))
            rec_disc = rec.get("discount_info") or extract_product_discount(rec)
            pct = rec_disc["discount_percent"]
            opp_key = f"opp:{str(query_id)}:similar_discount:{source_id_str}:{rec_id_str}:{pct}"
            opp_doc = {
                "customer_id": query_id,
                "opportunity_type": OPP_SIMILAR_PRODUCT_DISCOUNT,
                "opportunity_key": opp_key,
                "product_id": target.get("_id"),
                "product_name": rec.get("name"),
                "related_product_ids": [rec.get("_id")],
                "opportunity_state": "detected",
                "metadata": {
                    "source_product_id": str(target.get("_id", "")),
                    "source_product_name": target.get("name"),
                    "recommended_product_name": rec.get("name"),
                    "category": rec.get("category") or target.get("category"),
                    "brand": rec.get("brand"),
                    "discount_percent": pct,
                    "current_price": rec_disc["current_price"],
                    "original_price": rec_disc["original_price"],
                },
                "detected_at": now_iso,
                "communicated_at": None,
                "expires_at": expires_iso,
            }
            opp_col.update_one(
                {"opportunity_key": opp_key},
                {"$setOnInsert": opp_doc},
                upsert=True
            )
            saved = opp_col.find_one({"opportunity_key": opp_key})
            detected_opportunities.append(saved or opp_doc)

    # 5. CART_ABANDONMENT
    # Check if customer has active cart items and meets abandonment delay
    cart = db["cart"].find_one({"$or": [{"user_id": c_oid}, {"user_id": str(c_oid)}]}) if c_oid else None
    cart_items = []
    cart_updated_dt = None

    if cart and cart.get("items"):
        cart_items = cart.get("items")
        cart_updated = cart.get("updated_at")
        if isinstance(cart_updated, str):
            try:
                cart_updated_dt = datetime.fromisoformat(cart_updated)
            except Exception:
                cart_updated_dt = now
        elif isinstance(cart_updated, datetime):
            cart_updated_dt = cart_updated
        else:
            cart_updated_dt = now
    elif cart_prods:
        cart_items = cart_prods
        cart_updated_dt = now

    if cart_items and cart_updated_dt:
        if cart_updated_dt.tzinfo is None:
            cart_updated_dt = cart_updated_dt.replace(tzinfo=timezone.utc)

        # Check if an order was placed after cart was updated
        latest_order = db["orders"].find_one(
            {"$or": [{"user_id": c_oid}, {"user_id": str(c_oid)}]},
            sort=[("created_at", -1)]
        ) if c_oid else None

        order_invalidates = False
        if latest_order:
            order_created = latest_order.get("created_at")
            if isinstance(order_created, str):
                try:
                    order_created_dt = datetime.fromisoformat(order_created)
                except Exception:
                    order_created_dt = now
            elif isinstance(order_created, datetime):
                order_created_dt = order_created
            else:
                order_created_dt = now
            if order_created_dt.tzinfo is None:
                order_created_dt = order_created_dt.replace(tzinfo=timezone.utc)
            if order_created_dt >= cart_updated_dt:
                order_invalidates = True

        elapsed_sec = (now - cart_updated_dt).total_seconds()
        # Must satisfy abandonment delay (default 1h) and have no subsequent order
        if not order_invalidates and elapsed_sec >= 3600:
            hour_key = cart_updated_dt.strftime("%Y-%m-%dT%H")
            opp_key = f"opp:{str(query_id)}:cart_abandonment:{hour_key}"
            opp_doc = {
                "customer_id": query_id,
                "opportunity_type": OPP_CART_ABANDONMENT,
                "opportunity_key": opp_key,
                "product_id": None,
                "product_name": None,
                "related_product_ids": [],
                "opportunity_state": "detected",
                "metadata": {
                    "item_count": len(cart_items),
                    "cart_updated_at": cart_updated_dt.isoformat(),
                },
                "detected_at": now_iso,
                "communicated_at": None,
                "expires_at": expires_iso,
            }
            opp_col.update_one(
                {"opportunity_key": opp_key},
                {"$setOnInsert": opp_doc},
                upsert=True
            )
            saved = opp_col.find_one({"opportunity_key": opp_key})
            detected_opportunities.append(saved or opp_doc)

    # 6. WISHLIST_INACTIVITY
    # Triggered when wishlist items have remained inactive according to existing 7-day rule,
    # and no active direct wishlist discount opportunity exists
    has_wl_discount = any(o["opportunity_type"] == OPP_WISHLIST_ITEM_DISCOUNT for o in detected_opportunities)
    if wl_prods and not has_wl_discount:
        oldest_wl_dt = None
        wl_id_conds = []
        if c_oid:
            wl_id_conds.append({"user_id": c_oid})
            wl_id_conds.append({"user_id": str(c_oid)})
        if isinstance(customer_id, str):
            wl_id_conds.append({"user_id": customer_id})
        wl_query = {"$or": wl_id_conds} if wl_id_conds else {"user_id": query_id}
        for wl_doc in list(db["wishlist"].find(wl_query)):
            c_at = wl_doc.get("created_at") or wl_doc.get("added_at")
            if isinstance(c_at, str):
                try:
                    c_dt = datetime.fromisoformat(c_at)
                except Exception:
                    c_dt = None
            elif isinstance(c_at, datetime):
                c_dt = c_at
            else:
                c_dt = None
            if c_dt:
                if c_dt.tzinfo is None:
                    c_dt = c_dt.replace(tzinfo=timezone.utc)
                if oldest_wl_dt is None or c_dt < oldest_wl_dt:
                    oldest_wl_dt = c_dt

        # Considered inactive if created/saved at least 7 days ago
        is_inactive = False
        if oldest_wl_dt:
            if (now - oldest_wl_dt).total_seconds() >= (7 * 86400):
                is_inactive = True

        if is_inactive:
            window_key = now.strftime("%Y-W%W")
            opp_key = f"opp:{str(query_id)}:wishlist_inactivity:{window_key}"
            opp_doc = {
                "customer_id": query_id,
                "opportunity_type": OPP_WISHLIST_INACTIVITY,
                "opportunity_key": opp_key,
                "product_id": None,
                "product_name": None,
                "related_product_ids": [],
                "opportunity_state": "detected",
                "metadata": {
                    "item_count": len(wl_prods),
                },
                "detected_at": now_iso,
                "communicated_at": None,
                "expires_at": expires_iso,
            }
            opp_col.update_one(
                {"opportunity_key": opp_key},
                {"$setOnInsert": opp_doc},
                upsert=True
            )
            saved = opp_col.find_one({"opportunity_key": opp_key})
            detected_opportunities.append(saved or opp_doc)

    return detected_opportunities


def build_opportunity_email_content(opportunity, customer_name, store_url):
    """Generate customer-friendly, natural Gmail content for an opportunity.

    CRITICAL RULES:
        - NEVER expose lead scores, ML probabilities, model versions, feature vectors, or internal ranks.
        - State real discounts that actually exist in the catalog.
        - Maintain a natural, personal, helpful tone.
    """
    name = customer_name or "there"
    opp_type = opportunity.get("opportunity_type")
    meta = opportunity.get("metadata") or {}

    if opp_type == OPP_CART_ITEM_DISCOUNT:
        prod_name = meta.get("product_name") or "an item in your cart"
        disc_pct = meta.get("discount_percent", 0)
        curr_price = meta.get("current_price", 0)
        subject = f"Price drop: {prod_name} is now {disc_pct}% off!"
        body = (
            f"Hi {name},\n\n"
            f"Great news! {prod_name} in your cart is now available at a special discount.\n\n"
            f"• {prod_name} — {disc_pct}% off (Now ₹{curr_price:,.2f})\n\n"
            f"Complete your order before the offer ends:\n"
            f"{store_url}/cart\n\n"
            "Best regards,\n"
            "The Lead Magnet Team"
        )
    elif opp_type == OPP_WISHLIST_ITEM_DISCOUNT:
        prod_name = meta.get("product_name") or "an item on your wishlist"
        disc_pct = meta.get("discount_percent", 0)
        curr_price = meta.get("current_price", 0)
        subject = f"Good news! {prod_name} from your wishlist is now on sale"
        body = (
            f"Hi {name},\n\n"
            f"An item you saved to your wishlist is now discounted:\n\n"
            f"• {prod_name} — {disc_pct}% off (Now ₹{curr_price:,.2f})\n\n"
            f"Take a look at your wishlist:\n"
            f"{store_url}/wishlist\n\n"
            "Best regards,\n"
            "The Lead Magnet Team"
        )
    elif opp_type == OPP_SIMILAR_PRODUCT_DISCOUNT:
        src_name = meta.get("source_product_name") or "items you were viewing"
        rec_name = meta.get("recommended_product_name") or "a trending alternative"
        disc_pct = meta.get("discount_percent", 0)
        curr_price = meta.get("current_price", 0)
        cat = meta.get("category") or "styles"
        subject = f"Special offers on {cat.lower()} you might like"
        body = (
            f"Hi {name},\n\n"
            f"We noticed you were browsing {src_name}. We found a matching style currently on special offer that you might love:\n\n"
            f"• {rec_name} — {disc_pct}% off (Now ₹{curr_price:,.2f})\n\n"
            f"Discover our latest collection:\n"
            f"{store_url}/shop\n\n"
            "Best regards,\n"
            "The Lead Magnet Team"
        )
    elif opp_type == OPP_HOT_TO_WARM_REENGAGEMENT:
        subject = "We miss you at Lead Magnet — see what's new"
        body = (
            f"Hi {name},\n\n"
            "We noticed it's been a little while since your last visit. We've refreshed our store with new premium clothing arrivals tailored to your style!\n\n"
            f"Explore the new arrivals:\n"
            f"{store_url}/shop\n\n"
            "Best regards,\n"
            "The Lead Magnet Team"
        )
    elif opp_type == OPP_CART_ABANDONMENT:
        subject = "You left items in your Lead Magnet cart"
        body = (
            f"Hi {name},\n\n"
            "You left items waiting in your shopping cart.\n\n"
            f"Complete your purchase here:\n"
            f"{store_url}/cart\n\n"
            "Best regards,\n"
            "The Lead Magnet Team"
        )
    elif opp_type == OPP_WISHLIST_INACTIVITY:
        subject = "Items you saved are still waiting for you"
        body = (
            f"Hi {name},\n\n"
            "Items in your wishlist are still waiting for you.\n\n"
            f"View your wishlist and shop:\n"
            f"{store_url}/wishlist\n\n"
            "Best regards,\n"
            "The Lead Magnet Team"
        )
    elif opp_type == OPP_PRODUCT_PRICE_DROP:
        prod_name = meta.get("product_title") or meta.get("product_name") or "an item you were interested in"
        old_price = meta.get("old_price", 0)
        curr_price = meta.get("new_price", 0)

        def _fmt_price(val):
            try:
                f_val = float(val)
                if f_val.is_integer():
                    return f"₹{int(f_val)}"
                return f"₹{f_val:,.2f}"
            except (ValueError, TypeError):
                return f"₹{val}"

        old_str = _fmt_price(old_price)
        curr_str = _fmt_price(curr_price)

        interest_src = str(meta.get("interest_source", "cart")).lower()
        if "wishlist" in interest_src and "cart" not in interest_src:
            lead_line = f"Good news! The {prod_name} on your wishlist is now {curr_str}, down from {old_str}."
            target_url = meta.get("product_url") or meta.get("url") or f"{store_url}/wishlist"
        else:
            lead_line = f"Good news! The {prod_name} in your cart is now {curr_str}, down from {old_str}."
            target_url = meta.get("product_url") or meta.get("url") or f"{store_url}/cart"

        disc_amt = meta.get("discount_amount")
        if disc_amt is None and old_price and curr_price and old_price > curr_price:
            disc_amt = round(old_price - curr_price, 2)
        disc_pct = meta.get("discount_percentage") or meta.get("discount_percent")
        if disc_pct is None and old_price and curr_price and old_price > curr_price:
            disc_pct = int(round(((old_price - curr_price) / old_price) * 100))

        discount_line = ""
        if disc_amt and disc_pct:
            discount_line = f"Save {_fmt_price(disc_amt)} ({disc_pct}% off)!"
        elif disc_pct:
            discount_line = f"Save {disc_pct}% off!"
        elif disc_amt:
            discount_line = f"Save {_fmt_price(disc_amt)}!"

        subject = f"Price drop: {prod_name} is now down to {curr_str}!"

        body_lines = [
            f"Hi {name},\n",
            lead_line,
        ]
        if discount_line:
            body_lines.append(discount_line)
        body_lines.extend([
            f"View product:\n{target_url}\n",
            "Best regards,\nThe Lead Magnet Team"
        ])
        body = "\n\n".join([line for line in body_lines if line.strip()])
    else:
        subject = "You might be interested in these collections — Lead Magnet"
        body = (
            f"Hi {name},\n\n"
            f"Check out handpicked styles waiting for you at Lead Magnet:\n"
            f"{store_url}/shop\n\n"
            "Best regards,\n"
            "The Lead Magnet Team"
        )

    return subject, body


def process_customer_opportunities(
    customer_id,
    db,
    provider=None,
    policy=None,
    lead_state_doc=None,
    opportunity_cooldown_hours=OPPORTUNITY_COOLDOWN_HOURS,
    current_time=None,
):
    """Detect and idempotently communicate eligible opportunities for a customer via targeted Gmail.

    Enforces:
        - Lead status qualification
        - Opportunity-level idempotency (never duplicate for same opportunity_key)
        - Customer email cooldown (prevents rapid-fire email sends)
        - Channel eligibility (email only, WhatsApp postponed)
        - Clean status recording in marketing_communications and marketing_opportunities.

    Returns:
        dict:
            detected_count: Number of opportunities detected.
            communicated: List of communication results.
            skipped: List of skipped opportunities with reasons.
    """
    if db is None or not customer_id:
        return {"detected_count": 0, "communicated": [], "skipped": []}

    c_oid = _to_object_id(customer_id)
    query_id = c_oid if c_oid else customer_id

    # 1. Detect Opportunities
    opportunities = detect_opportunities_for_customer(query_id, db, lead_state_doc=lead_state_doc, current_time=current_time)

    opp_col = db["marketing_opportunities"]
    try:
        pending_pd = list(opp_col.find({
            "customer_id": query_id,
            "opportunity_type": OPP_PRODUCT_PRICE_DROP,
            "opportunity_state": "detected",
        }))
        existing_keys = {o.get("opportunity_key") for o in opportunities}
        for pd_opp in pending_pd:
            if pd_opp.get("opportunity_key") not in existing_keys:
                opportunities.append(pd_opp)
                existing_keys.add(pd_opp.get("opportunity_key"))
    except Exception:
        pass

    if not opportunities:
        return {"detected_count": 0, "communicated": [], "skipped": []}

    profiles_col = db["user_profiles"]
    profile = profiles_col.find_one({"_id": c_oid}) if c_oid else None
    if not profile and isinstance(customer_id, str):
        profile = profiles_col.find_one({"_id": customer_id}) or profiles_col.find_one({"user_id": customer_id})

    # Channel eligibility check for email
    eligibility = evaluate_channel_eligibility(profile, policy)
    email_info = eligibility["email"]
    if not email_info["eligible"]:
        return {
            "detected_count": len(opportunities),
            "communicated": [],
            "skipped": [{"opportunity_key": o.get("opportunity_key"), "reason": email_info["reason"]} for o in opportunities],
        }

    recipient_email = email_info["recipient"]
    cust_name = (profile.get("full_name") or profile.get("username") or "there") if profile else "there"
    store_url = get_store_url()

    communicated = []
    skipped = []

    # Check customer-level cooldown
    within_cooldown = _is_within_opportunity_cooldown(query_id, db, cooldown_hours=opportunity_cooldown_hours)

    for opp in opportunities:
        opp_key = opp["opportunity_key"]
        opp_state = opp.get("opportunity_state")

        # 1. Idempotency Check: if already communicated for this opportunity, skip!
        if opp_state == "communicated":
            skipped.append({
                "opportunity_key": opp_key,
                "opportunity_type": opp.get("opportunity_type"),
                "reason": "Opportunity already communicated",
            })
            continue

        # 2. Global / Customer cooldown check: avoid sending rapid emails
        if within_cooldown:
            skipped.append({
                "opportunity_key": opp_key,
                "opportunity_type": opp.get("opportunity_type"),
                "reason": f"Customer is within {opportunity_cooldown_hours}h email cooldown",
            })
            continue

        # 3. Build email content
        subject, body = build_opportunity_email_content(opp, cust_name, store_url)
        email_idempotency_key = f"{opp_key}:email"

        opp_meta = opp.get("metadata") or {}
        comm_meta = {
            "opportunity_key": opp_key,
            "opportunity_type": opp.get("opportunity_type"),
            "product_id": str(opp.get("product_id") or ""),
        }
        if opp_meta.get("primary_image"):
            comm_meta["primary_image"] = opp_meta.get("primary_image")
        if opp_meta.get("product_url"):
            comm_meta["product_url"] = opp_meta.get("product_url")
        if opp_meta.get("old_price") is not None:
            comm_meta["old_price"] = opp_meta.get("old_price")
        if opp_meta.get("new_price") is not None:
            comm_meta["new_price"] = opp_meta.get("new_price")

        # 4. Dispatch Email (Gmail SMTP / dry-run provider)
        comm_res = dispatch_communication(
            db,
            query_id,
            campaign_type=f"opportunity_{opp.get('opportunity_type')}",
            channel="email",
            recipient=recipient_email,
            subject=subject,
            body=body,
            metadata=comm_meta,
            idempotency_key=email_idempotency_key,
            provider=provider,
        )

        success = bool(comm_res and comm_res.get("status") == "sent")

        if success:
            now_iso = (current_time or datetime.now(timezone.utc)).isoformat()
            opp_col.update_one(
                {"opportunity_key": opp_key},
                {"$set": {"opportunity_state": "communicated", "communicated_at": now_iso}}
            )
            opp["opportunity_state"] = "communicated"
            opp["communicated_at"] = now_iso
            communicated.append(opp)
            # Once an email is sent, subsequent opportunities in the same evaluation cycle
            # must observe the customer-level cooldown so we do NOT send multiple emails in rapid succession!
            within_cooldown = True
        else:
            skipped.append({
                "opportunity_key": opp_key,
                "opportunity_type": opp.get("opportunity_type"),
                "reason": comm_res.get("last_error") or "Provider dispatch failed or skipped",
            })

    return {
        "detected_count": len(opportunities),
        "communicated": communicated,
        "skipped": skipped,
    }
