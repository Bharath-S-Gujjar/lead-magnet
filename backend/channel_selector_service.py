"""Smart Channel Selection Service for Lead Magnet.

Determines the single primary communication channel (WhatsApp or Email/Gmail)
for a given customer and communication event, using:
    - Channel eligibility results (evaluate_channel_eligibility).
    - Message classification (transactional vs. promotional).
    - Customer WhatsApp consent (opt-in / opt-out).
    - Recipient validity (valid email, usable E.164 WhatsApp phone).
    - Deterministic channel preference policy.

Rules & Invariants:
    1. Single Primary Channel: Selects exactly ONE primary channel per communication
       opportunity (smart selection, not blind duplication).
    2. Strict Promotional Consent: Promotional WhatsApp is NEVER selected without
       explicit opt-in (whatsapp_opt_in == True).
    3. Opt-Out Override: whatsapp_opt_out == True strictly overrides opt-in and
       immediately disqualifies WhatsApp across all communication classifications.
    4. Transactional Eligibility: Transactional messages (registration, order confirmation)
       do not require promotional opt-in, provided a valid usable phone is present and the
       customer has not opted out.
    5. Fallback Protection: If the preferred channel is ineligible (e.g. missing consent,
       opted out, invalid recipient), the secondary channel is selected if eligible.
    6. No Eligible Channel: If neither channel is eligible, returns a clear, structured
       result with channel=None and detailed diagnostic reasons.
    7. Determinism: Given identical inputs, selection is 100% deterministic with zero
       side-effects or randomness.
"""

from typing import Any, Dict, List, Optional, Tuple, Union

from marketing_automation_service import (
    evaluate_channel_eligibility,
    TRANSACTIONAL_CAMPAIGNS,
)
from communication_provider import normalize_whatsapp_phone

# Canonical channel identifiers
CHANNEL_EMAIL = "email"
CHANNEL_WHATSAPP = "whatsapp"

# Supported Preference Policies
POLICY_WHATSAPP_FIRST = "whatsapp_first"      # Prefer WhatsApp if eligible, fallback to Email
POLICY_EMAIL_FIRST = "email_first"            # Prefer Email if eligible, fallback to WhatsApp
POLICY_WHATSAPP_PREFERRED = "whatsapp_preferred"
POLICY_EMAIL_PREFERRED = "email_preferred"

DEFAULT_PREFERENCE_POLICY = POLICY_WHATSAPP_FIRST

# High-priority promotional opportunity types
# - cart_item_discount: active cart item discount with immediate purchase intent
# - cart_abandonment / cart_abandoned: active unpurchased cart in time-critical recovery window
# - product_price_drop: detected catalog price drop event on customer-monitored product
HIGH_PRIORITY_PROMOTIONAL_TYPES = {
    "cart_item_discount",
    "cart_abandonment",
    "cart_abandoned",
    "product_price_drop",
}


def is_high_priority_opportunity(opportunity_or_type: Union[str, Dict[str, Any]]) -> bool:
    """Determine whether an opportunity is classified as high-priority promotional.

    High-priority opportunities (prefer WhatsApp when opted in & eligible):
        - cart_item_discount: active cart item discount (immediate purchase intent)
        - cart_abandonment / cart_abandoned: active unpurchased cart (time-critical recovery)
        - product_price_drop: detected catalog price drop on customer-monitored item

    Other promotional flows (lower/standard priority, prefer Gmail):
        - wishlist_item_discount (passive interest)
        - similar_product_discount (exploratory recommendation)
        - wishlist_inactivity (7-day passive reminder)
        - hot_to_warm_reengagement (general nurturing re-engagement)
        - lead_qualified / lead_qualification (general qualification discovery)
    """
    if isinstance(opportunity_or_type, dict):
        if opportunity_or_type.get("priority") == "high":
            return True
        opp_type = opportunity_or_type.get("opportunity_type") or opportunity_or_type.get("campaign_type") or ""
    else:
        opp_type = str(opportunity_or_type or "")

    clean_type = str(opp_type).strip().lower()
    if clean_type.startswith("opportunity_"):
        clean_type = clean_type[len("opportunity_"):]

    return clean_type in HIGH_PRIORITY_PROMOTIONAL_TYPES


def determine_opportunity_preference(
    opportunity_or_type: Union[str, Dict[str, Any]],
    policy: Optional[Dict[str, Any]] = None,
    user_profile: Optional[Dict[str, Any]] = None,
) -> str:
    """Determine channel preference policy based on opportunity priority and explicit configurations.

    Policy:
        - High-priority promotional opportunities -> prefer WhatsApp (POLICY_WHATSAPP_FIRST).
        - Other communication flows -> prefer Gmail (POLICY_EMAIL_FIRST).
        - Explicit overrides in policy or user_profile take precedence.
    """
    if isinstance(policy, dict):
        explicit = policy.get("preference_policy") or policy.get("preferred_channel")
        if explicit:
            return str(explicit)
    if isinstance(user_profile, dict):
        cust_pref = user_profile.get("preferred_channel")
        if cust_pref:
            return str(cust_pref)

    if is_high_priority_opportunity(opportunity_or_type):
        return POLICY_WHATSAPP_FIRST
    return POLICY_EMAIL_FIRST


def _resolve_preference_order(
    preference_policy: Optional[Union[str, List[str]]] = None,
    policy: Optional[Dict[str, Any]] = None,
    user_profile: Optional[Dict[str, Any]] = None,
) -> Tuple[List[str], str]:
    """Resolve the ordered list of channels based on policy and customer preferences.

    Priority resolution order:
        1. Explicit `preference_policy` argument.
        2. `preferred_channel` or `preference_policy` inside `policy` dict.
        3. `preferred_channel` in `user_profile`.
        4. Default: POLICY_WHATSAPP_FIRST (["whatsapp", "email"]).

    Returns:
        Tuple[List[str], str]: (ordered list of channels, canonical policy string).
    """
    pref: Optional[Union[str, List[str]]] = preference_policy

    if pref is None and isinstance(policy, dict):
        pref = policy.get("preference_policy") or policy.get("preferred_channel")

    if pref is None and isinstance(user_profile, dict):
        pref = user_profile.get("preferred_channel")

    if isinstance(pref, list):
        clean_list = [str(c).strip().lower() for c in pref if str(c).strip().lower() in (CHANNEL_WHATSAPP, CHANNEL_EMAIL)]
        if clean_list:
            # Ensure both channels are present in order
            for fallback in (CHANNEL_WHATSAPP, CHANNEL_EMAIL):
                if fallback not in clean_list:
                    clean_list.append(fallback)
            return clean_list, "custom_priority"

    pref_str = str(pref).strip().lower() if pref else DEFAULT_PREFERENCE_POLICY

    if pref_str in (POLICY_EMAIL_FIRST, POLICY_EMAIL_PREFERRED, CHANNEL_EMAIL):
        return [CHANNEL_EMAIL, CHANNEL_WHATSAPP], POLICY_EMAIL_FIRST

    # Default to WhatsApp first
    return [CHANNEL_WHATSAPP, CHANNEL_EMAIL], POLICY_WHATSAPP_FIRST


def select_communication_channel(
    user_profile: Optional[Dict[str, Any]] = None,
    campaign_type: Optional[str] = None,
    classification: Optional[str] = None,
    policy: Optional[Dict[str, Any]] = None,
    preference_policy: Optional[Union[str, List[str]]] = None,
    eligibility: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Select the single primary communication channel for a customer opportunity.

    Args:
        user_profile (dict, optional): Customer profile from user_profiles collection.
        campaign_type (str, optional): Campaign identifier (e.g. 'registration', 'lead_qualified',
            'cart_abandoned', 'wishlist_reminder', 'product_price_drop', 'opportunity').
        classification (str, optional): 'transactional' or 'promotional'. Inferred if omitted.
        policy (dict, optional): Channel enablement and dispatch policy flags.
        preference_policy (str or list, optional): 'whatsapp_first', 'email_first', or custom order.
        eligibility (dict, optional): Pre-computed eligibility dict from evaluate_channel_eligibility.
            If omitted, evaluate_channel_eligibility() is called automatically.

    Returns:
        dict:
            channel (str or None): Primary channel ('whatsapp', 'email', or None).
            selected_channel (str or None): Alias for channel.
            recipient (str or None): Clean recipient address (phone or email).
            eligible (bool): True if a channel was successfully selected.
            reason (str): Human-readable rationale for the selection decision.
            campaign_type (str or None): Active campaign type.
            classification (str): 'transactional' or 'promotional'.
            preference_policy (str): Resolved policy name.
            fallback_available (bool): True if an alternative channel was also eligible.
            fallback_channel (str or None): Alternative channel if available.
            eligibility (dict): Underlying channel eligibility details.
    """
    profile = user_profile or {}

    # 1. Determine classification (transactional vs. promotional)
    resolved_classification = "promotional"
    if classification:
        resolved_classification = str(classification).strip().lower()
    elif policy and "classification" in policy:
        resolved_classification = str(policy["classification"]).strip().lower()
    elif campaign_type and str(campaign_type).strip().lower() in TRANSACTIONAL_CAMPAIGNS:
        resolved_classification = "transactional"

    # 2. Evaluate channel eligibility if not supplied
    if eligibility is None:
        eligibility = evaluate_channel_eligibility(
            user_profile=profile,
            policy=policy,
            campaign_type=campaign_type,
            classification=resolved_classification,
        )

    email_info = eligibility.get(CHANNEL_EMAIL, {})
    wa_info = eligibility.get(CHANNEL_WHATSAPP, {})

    email_eligible = bool(email_info.get("eligible", False))
    wa_eligible = bool(wa_info.get("eligible", False))

    # 3. Hard safety invariants:
    # A customer who opted out can NEVER receive WhatsApp under any circumstance
    if profile.get("whatsapp_opt_out"):
        wa_eligible = False

    # Promotional WhatsApp strictly requires explicit opt-in / promotional consent
    has_whatsapp_consent = bool(profile.get("whatsapp_opt_in") or profile.get("whatsapp_promotional_consent"))
    if resolved_classification == "promotional" and not has_whatsapp_consent:
        wa_eligible = False

    # Validate phone usability if WhatsApp claims eligible
    if wa_eligible:
        phone_raw = wa_info.get("recipient") or profile.get("phone")
        if not phone_raw:
            wa_eligible = False
        else:
            _, err = normalize_whatsapp_phone(str(phone_raw))
            if err:
                wa_eligible = False

    # 4. Resolve channel priority order
    priority_order, canonical_policy = _resolve_preference_order(
        preference_policy=preference_policy,
        policy=policy,
        user_profile=profile,
    )

    selected_channel: Optional[str] = None
    selected_recipient: Optional[str] = None
    selection_reason: str = ""

    for channel in priority_order:
        if channel == CHANNEL_WHATSAPP and wa_eligible:
            selected_channel = CHANNEL_WHATSAPP
            selected_recipient = wa_info.get("recipient") or profile.get("phone")
            selection_reason = (
                "WhatsApp selected as primary channel: customer is eligible, opted in, "
                "and WhatsApp is preferred by policy."
                if resolved_classification == "promotional"
                else "WhatsApp selected as primary channel: transactional message with valid phone."
            )
            break
        elif channel == CHANNEL_EMAIL and email_eligible:
            selected_channel = CHANNEL_EMAIL
            selected_recipient = email_info.get("recipient") or profile.get("email")
            if priority_order[0] == CHANNEL_WHATSAPP:
                wa_reason = wa_info.get("reason", "ineligible")
                selection_reason = f"Gmail selected as fallback: WhatsApp is ineligible ({wa_reason})."
            else:
                selection_reason = "Gmail selected as primary channel: preferred by policy."
            break

    # 5. Handle no eligible channel
    if selected_channel is None:
        wa_reason = wa_info.get("reason", "WhatsApp ineligible")
        em_reason = email_info.get("reason", "Email ineligible")
        selection_reason = f"No eligible channel available (WhatsApp: {wa_reason}; Email: {em_reason})."

    # 6. Fallback availability
    fallback_available = False
    fallback_channel: Optional[str] = None

    if selected_channel == CHANNEL_WHATSAPP:
        fallback_available = email_eligible
        fallback_channel = CHANNEL_EMAIL if email_eligible else None
    elif selected_channel == CHANNEL_EMAIL:
        fallback_available = wa_eligible
        fallback_channel = CHANNEL_WHATSAPP if wa_eligible else None

    fallback_applied = bool(selected_channel and priority_order and selected_channel != priority_order[0])

    return {
        "channel": selected_channel,
        "selected_channel": selected_channel,
        "recipient": selected_recipient,
        "eligible": selected_channel is not None,
        "reason": selection_reason,
        "campaign_type": campaign_type,
        "classification": resolved_classification,
        "preference_policy": canonical_policy,
        "fallback_applied": fallback_applied,
        "fallback_available": fallback_available,
        "fallback_channel": fallback_channel,
        "eligibility": eligibility,
    }
