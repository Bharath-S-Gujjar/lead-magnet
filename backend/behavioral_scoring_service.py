"""
Lead Magnet: Rule-based Behavioral Lead Scoring Service
=======================================================

100-point transparent scoring system based on four behavioral categories:
  A. Purchase Intent       (cap 40 pts)
  B. Product Interest      (cap 20 pts)
  C. Engagement            (cap 15 pts)
  D. Purchase Readiness    (cap 15 pts)

Segment thresholds (authoritative values from scoring_constants):
  Hot:  >= 70  — high intent, engage immediately
  Warm: >= 35  — meaningful interest, nurture
  Cold: <  35  — low/unproven intent

Override rules (per strategy document):
  - Unconverted customer with active checkout within 24h -> Hot override
    (score stays honest; segment_reason records the override)
  - Completed purchase -> lifecycle 'converted' flag, score reported as-is

Recency decay:
  - Checkout/cart intent decays fast (half-life 2 days for checkout, 4 for cart)
  - General browsing decays slower (half-life 7 days)
"""

import math
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

# -- Import authoritative thresholds from scoring_constants ------------------
from scoring_constants import (
    HOT as THRESHOLD_HOT,
    WARM as THRESHOLD_WARM,
    CHECKOUT_OVERRIDE_HOURS as CHECKOUT_OVERRIDE_WINDOW_HOURS,
    CHECKOUT_WARM_FLOOR_HOURS,
    CART_WARM_FLOOR_HOURS,
    WISHLIST_WARM_FLOOR_DAYS,
    HALFLIFE_CHECKOUT_DAYS,
    HALFLIFE_CART_DAYS,
    HALFLIFE_GENERAL_DAYS,
)

# -- Category Caps ------------------------------------------------------------
CAP_PURCHASE_INTENT = 40
CAP_PRODUCT_INTEREST = 20
CAP_ENGAGEMENT = 15
CAP_PURCHASE_READINESS = 15



def _decay_factor(days_since: float, half_life_days: float) -> float:
    """Exponential decay: S_t = S_0 * 2^(-Δt/H)"""
    if days_since is None or days_since < 0:
        return 1.0
    return math.pow(2.0, -days_since / max(half_life_days, 0.01))


def _days_since_timestamp(ts) -> float:
    """Return fractional days since the given timestamp (datetime or ISO string).
    Returns None if unparseable."""
    if ts is None:
        return None
    try:
        now = datetime.now(timezone.utc)
        if isinstance(ts, datetime):
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            return (now - ts).total_seconds() / 86400.0
        # Try ISO string
        from timestamp_utils import parse_and_normalize_timestamp
        parsed, _ = parse_and_normalize_timestamp(str(ts))
        if parsed:
            return (now - parsed).total_seconds() / 86400.0
    except Exception:
        pass
    return None


def compute_behavioral_score(features: dict) -> dict:
    """
    Compute the 100-point behavioral lead score from aggregated customer features.

    Args:
        features (dict): Aggregated customer features from customer_feature_service.
                         Expected keys (all optional, default 0):
                           cart_item_count, cart_value, checkout_attempts, orders_count,
                           unique_products_viewed, products_viewed, search_count,
                           wishlist_item_count, high_intent_page_visits,
                           sessions_count, total_time_spent, form_submit_count,
                           product_interactions, days_since_last_activity,
                           last_checkout_action_at, last_cart_action_at

    Returns:
        dict with keys:
            behavioral_score          int 0-100
            lead_segment              "Hot" | "Warm" | "Cold"
            lead_probability          float 0.0-1.0  (behavioral_score / 100)
            lead_score                int 0-100  (alias for behavioral_score)
            purchase_intent_score     int (raw, before decay)
            product_interest_score    int (raw, before decay)
            engagement_score          int (raw, before decay)
            purchase_readiness_score  int (raw, before decay)
            recency_decay_factor      float (general decay)
            days_since_last_activity  float
            active_checkout_override  bool
            is_converted              bool (has completed order)
            score_reasons             list[str]
    """
    reasons = []

    # ── Extract features safely ───────────────────────────────────────────────
    def _int(key, default=0):
        v = features.get(key, default)
        try:
            return int(v or 0)
        except (TypeError, ValueError):
            return default

    def _float(key, default=0.0):
        v = features.get(key, default)
        try:
            return float(v or 0.0)
        except (TypeError, ValueError):
            return default

    cart_count        = _int("cart_item_count")
    cart_value        = _float("cart_value")
    checkout_att      = _int("checkout_attempts")
    orders_count      = _int("orders_count")
    order_val         = _float("total_order_value")
    unique_viewed     = _int("unique_products_viewed")
    products_viewed   = _int("products_viewed")
    search_count      = _int("search_count")
    wishlist_count    = _int("wishlist_item_count")
    hint_pages        = _int("high_intent_page_visits")
    sessions          = _int("sessions_count")
    time_spent        = _float("total_time_spent")
    form_submits      = _int("form_submit_count")
    interactions      = _int("product_interactions")
    days_since        = _float("days_since_last_activity")

    last_checkout_ts  = features.get("last_checkout_action_at")
    last_cart_ts      = features.get("last_cart_action_at")
    last_wishlist_ts  = features.get("last_wishlist_action_at")

    # ── Recency timestamps ────────────────────────────────────────────────────
    days_since_checkout = _days_since_timestamp(last_checkout_ts)
    days_since_cart     = _days_since_timestamp(last_cart_ts)
    days_since_wishlist = _days_since_timestamp(last_wishlist_ts)

    # ── Active Checkout Override ──────────────────────────────────────────────
    # Checkout started within 24h is a very strong temporary signal
    active_checkout_override = False
    if days_since_checkout is not None and days_since_checkout <= (CHECKOUT_OVERRIDE_WINDOW_HOURS / 24.0):
        active_checkout_override = True
    elif checkout_att > 0 and days_since <= (CHECKOUT_OVERRIDE_WINDOW_HOURS / 24.0):
        active_checkout_override = True  # checkout_attempts set today

    # ── Converted status ──────────────────────────────────────────────────────
    is_converted = orders_count > 0 or order_val > 0

    # ── A: Purchase Intent (cap 40) ──────────────────────────────────────────
    intent_raw = 0

    # Cart items
    if cart_count >= 1:
        intent_raw += 12
        reasons.append(f"Added {cart_count} item(s) to cart (+12)")
    if cart_count >= 2:
        # +3 per additional item, capped at +6 (2 extra items)
        extra = min((cart_count - 1) * 3, 6)
        intent_raw += extra
        if extra > 0:
            reasons.append(f"Multiple cart items (+{extra})")

    # Checkout started
    if checkout_att >= 1:
        intent_raw += 20
        reasons.append(f"Started checkout ({checkout_att} attempt(s)) (+20)")

    # Orders placed
    if orders_count >= 1:
        intent_raw += 15
        reasons.append(f"Placed {orders_count} order(s) (+15)")
    if orders_count >= 2:
        # Repeat buyer bonus
        intent_raw += 5
        reasons.append(f"Repeat buyer bonus (+5)")

    intent_raw = min(intent_raw, CAP_PURCHASE_INTENT)

    # ── B: Product Interest (cap 20) ─────────────────────────────────────────
    interest_raw = 0

    # Distinct product views: +2 per product, cap 6 (max 3 products)
    view_pts = min(unique_viewed * 2, 6)
    if view_pts > 0:
        interest_raw += view_pts
        reasons.append(f"Viewed {unique_viewed} distinct product(s) (+{view_pts})")

    # Repeat views of the same product: +1 each, cap 3
    repeat_views = max(0, products_viewed - unique_viewed)
    repeat_pts = min(repeat_views, 3)
    if repeat_pts > 0:
        interest_raw += repeat_pts
        reasons.append(f"Repeated product views (+{repeat_pts})")

    # Searches: +3 per search, cap 6
    search_pts = min(search_count * 3, 6)
    if search_pts > 0:
        interest_raw += search_pts
        reasons.append(f"{search_count} product search(es) (+{search_pts})")

    # Wishlist: +5 flat
    if wishlist_count >= 1:
        interest_raw += 5
        reasons.append(f"Added {wishlist_count} item(s) to wishlist (+5)")

    # High-intent page visits (pricing, product details, etc.): +1 each, cap 3
    hint_pts = min(hint_pages, 3)
    if hint_pts > 0:
        interest_raw += hint_pts
        reasons.append(f"{hint_pages} high-intent page visit(s) (+{hint_pts})")

    interest_raw = min(interest_raw, CAP_PRODUCT_INTEREST)

    # ── C: Engagement (cap 15) ────────────────────────────────────────────────
    engagement_raw = 0

    # Return sessions: +3 per return, cap 6 (2 return visits)
    if sessions >= 2:
        sess_pts = min((sessions - 1) * 3, 6)
        engagement_raw += sess_pts
        reasons.append(f"Returned {sessions - 1} time(s) (+{sess_pts})")

    # Meaningful time on site: +2 per 300s (5 min), cap 4
    time_periods = int(time_spent / 300)
    time_pts = min(time_periods * 2, 4)
    if time_pts > 0:
        engagement_raw += time_pts
        reasons.append(f"{int(time_spent)}s time on site (+{time_pts})")

    # Form submissions (signup, contact, support): +3
    if form_submits >= 1:
        engagement_raw += 3
        reasons.append(f"Submitted {form_submits} form(s) (+3)")

    # Product interactions (clicks, recommendations): +2 per 5 interactions, cap 4
    if interactions >= 5:
        inter_pts = min((interactions // 5) * 2, 4)
        engagement_raw += inter_pts
        reasons.append(f"{interactions} product interactions (+{inter_pts})")

    engagement_raw = min(engagement_raw, CAP_ENGAGEMENT)

    # ── D: Purchase Readiness (cap 15) ───────────────────────────────────────
    readiness_raw = 0

    # Progressed through checkout flow (shipping/payment pages): +8
    if checkout_att >= 1:
        readiness_raw += 8
        reasons.append("Progressed through checkout flow (+8)")

    # Active cart value: +2
    if cart_value > 0:
        readiness_raw += 2
        reasons.append(f"Active cart value ₹{cart_value:,.0f} (+2)")

    # Future readiness signals (shipping_view, return_policy_view, coupon_apply)
    # will add here once those events are tracked separately

    readiness_raw = min(readiness_raw, CAP_PURCHASE_READINESS)

    # ── Apply Recency Decay ───────────────────────────────────────────────────
    # Checkout/cart intent decays quickly; browsing/engagement decays slowly
    checkout_decay = _decay_factor(
        days_since_checkout if days_since_checkout is not None else days_since,
        HALFLIFE_CHECKOUT_DAYS
    )
    cart_decay = _decay_factor(
        days_since_cart if days_since_cart is not None else days_since,
        HALFLIFE_CART_DAYS
    )
    general_decay = _decay_factor(days_since, HALFLIFE_GENERAL_DAYS)

    # Intent and readiness decay at checkout/cart speed; interest/engagement at general speed
    intent_decayed     = intent_raw * max(checkout_decay, cart_decay)
    interest_decayed   = interest_raw * general_decay
    engagement_decayed = engagement_raw * general_decay
    readiness_decayed  = readiness_raw * checkout_decay

    raw_total = intent_decayed + interest_decayed + engagement_decayed + readiness_decayed
    behavioral_score = max(0, min(100, int(round(raw_total))))

    # -- Final Segment Classification -----------------------------------------------
    # Primary: score-based
    if behavioral_score >= THRESHOLD_HOT:
        segment = "Hot"
    elif behavioral_score >= THRESHOLD_WARM:
        segment = "Warm"
    else:
        segment = "Cold"

    segment_reason: str = ""

    # -- Minimum-Segment Floor Rules (unconverted customers only) ---------------
    # These rules raise the segment when a strong recency signal exists that the
    # score alone (after decay) may not fully reflect. THE SCORE IS NOT CHANGED.
    # All floors expire as their time-windows pass. Never apply to converted
    # customers (is_converted==True).

    if not is_converted:
        eff_checkout_days = days_since_checkout if days_since_checkout is not None else days_since
        eff_cart_days     = days_since_cart if days_since_cart is not None else days_since
        eff_wishlist_days = days_since_wishlist if days_since_wishlist is not None else days_since

        # Floor 1: Active checkout within 24h -> Hot override
        if active_checkout_override and segment != "Hot":
            segment = "Hot"
            segment_reason = "OVERRIDE: Active checkout within 24h (segment promoted; score unchanged)"
            reasons.append(segment_reason)

        # Floor 2: Checkout started 24-72h ago -> at least Warm
        elif (
            not active_checkout_override
            and checkout_att >= 1
            and eff_checkout_days <= (CHECKOUT_WARM_FLOOR_HOURS / 24.0)
            and segment == "Cold"
        ):
            segment = "Warm"
            segment_reason = (
                f"FLOOR: Checkout started {eff_checkout_days*24:.0f}h ago "
                f"(within {CHECKOUT_WARM_FLOOR_HOURS}h window) -- at least Warm"
            )
            reasons.append(segment_reason)

        # Floor 3: Cart add/update within 72h -> at least Warm
        elif (
            cart_count >= 1
            and eff_cart_days <= (CART_WARM_FLOOR_HOURS / 24.0)
            and segment == "Cold"
        ):
            segment = "Warm"
            segment_reason = (
                f"FLOOR: Cart updated {eff_cart_days*24:.0f}h ago "
                f"(within {CART_WARM_FLOOR_HOURS}h window) -- at least Warm"
            )
            reasons.append(segment_reason)

        # Floor 4: Wishlist add within 7 days -> at least Warm
        elif (
            wishlist_count >= 1
            and eff_wishlist_days <= WISHLIST_WARM_FLOOR_DAYS
            and segment == "Cold"
        ):
            segment = "Warm"
            segment_reason = (
                f"FLOOR: {wishlist_count} wishlist item(s) within "
                f"{WISHLIST_WARM_FLOOR_DAYS} days -- at least Warm"
            )
            reasons.append(segment_reason)

        # Floor 5: >=2 distinct searches AND >=2 distinct product views within 7 days -> at least Warm
        elif (
            search_count >= 2
            and unique_viewed >= 2
            and days_since <= WISHLIST_WARM_FLOOR_DAYS
            and segment == "Cold"
        ):
            segment = "Warm"
            segment_reason = (
                f"FLOOR: {search_count} searches + {unique_viewed} product views "
                f"within {WISHLIST_WARM_FLOOR_DAYS} days -- at least Warm"
            )
            reasons.append(segment_reason)

    # -- Confidence and Provisional Status ----------------------------------------
    # Low confidence when sessions <= 1 and few meaningful events.
    # New or login-only customers receive Cold + provisional.
    has_meaningful_events = (
        cart_count > 0
        or checkout_att > 0
        or wishlist_count > 0
        or orders_count > 0
        or search_count > 0
        or unique_viewed >= 2
        or form_submits > 0
        or interactions >= 5
        or time_spent >= 120.0
    )
    if sessions <= 1 and not has_meaningful_events:
        is_provisional = True
        confidence = "low"
    elif sessions <= 1:
        is_provisional = False
        confidence = "medium"
    else:
        is_provisional = False
        confidence = "high"

    # -- Build return dict -------------------------------------------------------
    lead_probability = round(behavioral_score / 100.0, 4)

    return {
        "behavioral_score": behavioral_score,
        "lead_score": behavioral_score,
        # lead_probability is score/100 -- a score FRACTION, NOT a calibrated ML probability.
        "lead_probability": lead_probability,
        "lead_segment": segment,
        "segment_reason": segment_reason,
        "is_provisional": is_provisional,
        "confidence": confidence,

        # Component breakdown (raw, before decay)
        "purchase_intent_score": intent_raw,
        "product_interest_score": interest_raw,
        "engagement_score": engagement_raw,
        "purchase_readiness_score": readiness_raw,

        # Decayed component scores
        "purchase_intent_score_decayed": int(round(intent_decayed)),
        "product_interest_score_decayed": int(round(interest_decayed)),
        "engagement_score_decayed": int(round(engagement_decayed)),
        "purchase_readiness_score_decayed": int(round(readiness_decayed)),

        "recency_decay_factor": round(general_decay, 4),
        "days_since_last_activity": days_since,
        "active_checkout_override": active_checkout_override,
        "is_converted": is_converted,
        "score_reasons": reasons,
    }
