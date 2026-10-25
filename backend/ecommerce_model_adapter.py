"""E-Commerce Lead Scoring Inference Adapter.

Primary scoring: rule-based 100-point behavioral system (behavioral_scoring_service).
Secondary signal: XGBoost model probability (reported as metadata only).

The behavioral score is the authoritative source for lead_segment, lead_score,
and lead_probability. XGBoost is retained as a reference model until sufficient
e-commerce conversion data is accumulated for retraining and validation.

Scoring Architecture:
    1. Compute 100-point behavioral score from customer features.
    2. Classify segment: Hot (70-100), Warm (35-69), Cold (0-34).
    3. Optionally run XGBoost and report its probability as 'ml_model_probability'.
    4. Return combined result — behavioral score drives all downstream decisions.
"""

from datetime import datetime, timezone
from functools import lru_cache
import json
import logging
import math
from pathlib import Path

logger = logging.getLogger(__name__)

MODEL_DIRECTORY = Path(__file__).resolve().parent.parent / "model"
ECOMMERCE_MODEL_PATH = MODEL_DIRECTORY / "ecommerce_xgb_model.pkl"
ECOMMERCE_SCALER_PATH = MODEL_DIRECTORY / "ecommerce_scaler.pkl"
ECOMMERCE_FEATURE_COLUMNS_PATH = MODEL_DIRECTORY / "ecommerce_feature_columns.pkl"
ECOMMERCE_METADATA_PATH = MODEL_DIRECTORY / "ecommerce_model_metadata.json"


@lru_cache(maxsize=1)
def load_ecommerce_model():
    """Load the dedicated e-commerce XGBoost model binary."""
    if not ECOMMERCE_MODEL_PATH.exists():
        raise FileNotFoundError(f"Model file not found at {ECOMMERCE_MODEL_PATH}")
    import joblib
    return joblib.load(ECOMMERCE_MODEL_PATH)


@lru_cache(maxsize=1)
def load_ecommerce_scaler():
    """Load the dedicated e-commerce StandardScaler binary."""
    if not ECOMMERCE_SCALER_PATH.exists():
        raise FileNotFoundError(f"Scaler file not found at {ECOMMERCE_SCALER_PATH}")
    import joblib
    return joblib.load(ECOMMERCE_SCALER_PATH)


@lru_cache(maxsize=1)
def load_ecommerce_feature_columns():
    """Load the immutable feature column order used during model training."""
    if not ECOMMERCE_FEATURE_COLUMNS_PATH.exists():
        raise FileNotFoundError(f"Feature columns file not found at {ECOMMERCE_FEATURE_COLUMNS_PATH}")
    import joblib
    return joblib.load(ECOMMERCE_FEATURE_COLUMNS_PATH)


@lru_cache(maxsize=1)
def load_ecommerce_metadata():
    """Load the model training metadata dictionary."""
    if not ECOMMERCE_METADATA_PATH.exists():
        raise FileNotFoundError(f"Metadata file not found at {ECOMMERCE_METADATA_PATH}")
    with open(ECOMMERCE_METADATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# Required base feature keys (used for XGBoost input; behavioral scoring uses a subset)
REQUIRED_BASE_FEATURES = {
    "sessions_count",
    "total_events",
    "total_time_spent",
    "average_session_duration",
    "page_views_count",
    "days_since_last_activity",
    "products_viewed",
    "unique_products_viewed",
    "product_interactions",
    "search_count",
    "form_submit_count",
    "high_intent_page_visits",
    "cart_item_count",
    "cart_value",
    "wishlist_item_count",
    "checkout_attempts",
    "orders_count",
    "total_order_value",
    "average_order_value",
}

DERIVED_FEATURES = {
    "cart_to_session_ratio",
    "checkout_to_cart_ratio",
    "high_intent_ratio",
    "product_interaction_density",
}


def compute_derived_features(base_dict):
    """Deterministically calculate derived feature ratios from base canonical fields."""
    sessions = float(base_dict.get("sessions_count", 0) or 0)
    cart_items = float(base_dict.get("cart_item_count", 0) or 0)
    checkout_attempts = float(base_dict.get("checkout_attempts", 0) or 0)
    high_intent = float(base_dict.get("high_intent_page_visits", 0) or 0)
    page_views = float(base_dict.get("page_views_count", 0) or 0)
    product_interactions = float(base_dict.get("product_interactions", 0) or 0)

    return {
        "cart_to_session_ratio": round(cart_items / sessions, 3) if sessions > 0 else 0.0,
        "checkout_to_cart_ratio": round(checkout_attempts / max(cart_items, 1.0), 3),
        "high_intent_ratio": round(high_intent / max(page_views, 1.0), 3),
        "product_interaction_density": round(product_interactions / sessions, 3) if sessions > 0 else 0.0,
    }


def _run_xgboost_inference(merged_features):
    """
    Attempt to run XGBoost inference as a secondary/reference signal.

    Returns:
        dict with 'ml_model_probability' and 'ml_model_score', or error info.
    """
    try:
        import pandas as pd
        feature_cols = load_ecommerce_feature_columns()
        scaler = load_ecommerce_scaler()
        model = load_ecommerce_model()

        vector = []
        for col in feature_cols:
            val = merged_features.get(col, 0.0)
            if val is None:
                val = 0.0
            try:
                val_float = float(val)
                if math.isnan(val_float) or math.isinf(val_float):
                    val_float = 0.0
            except (TypeError, ValueError):
                val_float = 0.0
            vector.append(val_float)

        X_raw = pd.DataFrame([vector], columns=feature_cols)
        X_scaled = scaler.transform(X_raw)
        ml_prob = float(model.predict_proba(X_scaled)[0][1])
        ml_prob = max(0.0, min(1.0, ml_prob))

        return {
            "ml_model_probability": round(ml_prob, 4),
            "ml_model_score": int(round(ml_prob * 100)),
            "ml_model_available": True,
            "ml_model_error": None,
        }
    except Exception as e:
        logger.debug("XGBoost inference skipped (secondary signal only): %s", e)
        return {
            "ml_model_probability": None,
            "ml_model_score": None,
            "ml_model_available": False,
            "ml_model_error": str(e),
        }
def predict_customer_features(customer_features):
    """
    Run lead scoring inference on one customer feature document.

    PRIMARY (authoritative): Rule-based 100-point behavioral scoring system
        (compute_behavioral_score).  lead_score, lead_segment and
        lead_probability all come EXCLUSIVELY from this scorer.

    SECONDARY (reference only): XGBoost model probability, reported as
        ml_model_probability / raw_model_probability.  Labelled
        "synthetic reference" — trained on synthetic data, not yet validated
        against real e-commerce conversions.  It has NO effect on segment or
        score decisions.

    lead_probability is defined as behavioral_score / 100.  It is a score
        FRACTION, not a calibrated conversion probability.

    Scoring method tag: "behavioral_100pt_rule_based"

    Args:
        customer_features (dict): Feature document for a customer.

    Returns:
        dict: Inference results with lead_score, lead_probability, lead_segment
              (all from behavioral scoring), XGBoost reference metadata, and
              the full behavioral breakdown.

    Raises:
        ValueError: If customer_features is not a dict or is missing required
                    base fields.
    """
    if not isinstance(customer_features, dict):
        raise ValueError("customer_features must be a dictionary")

    # Auto-fill defaults for missing base features so partial dictionaries work cleanly
    merged_features = dict(customer_features)
    for f in REQUIRED_BASE_FEATURES:
        if f not in merged_features or merged_features[f] is None:
            merged_features[f] = 0

    # Compute derived features
    derived = compute_derived_features(merged_features)
    for k, v in derived.items():
        if k not in merged_features or merged_features[k] is None:
            merged_features[k] = v

    # Handle nullable days_since_last_activity
    if merged_features.get("days_since_last_activity") is None:
        merged_features["days_since_last_activity"] = 0.0

    # Validate required model feature values (for XGBoost; catches bad data early)
    import pandas as pd
    feature_cols = load_ecommerce_feature_columns()

    for col in feature_cols:
        val = merged_features.get(col)

        if val is None:
            raise ValueError(f"Missing value for required model feature '{col}'")

        if isinstance(val, bool):
            raise ValueError(f"Invalid boolean value for feature '{col}': {val}")

        try:
            val_float = float(val)
        except (ValueError, TypeError):
            raise ValueError(f"Non-numeric value for feature '{col}': {val}")

        if math.isnan(val_float) or math.isinf(val_float):
            raise ValueError(f"Invalid numeric value (NaN/Inf) for feature '{col}': {val}")

    # ── PRIMARY: Direct XGBoost Model Scoring ─────────────────────────────────
    scaler = load_ecommerce_scaler()
    model = load_ecommerce_model()
    metadata = load_ecommerce_metadata()

    # Converted status
    orders_count = int(merged_features.get("orders_count", 0) or 0)
    total_order_val = float(merged_features.get("total_order_value", 0) or 0)
    is_converted = orders_count > 0 or total_order_val > 0

    # Evaluate active behavioral shopping intent:
    # A customer's lead score reflects current pre-purchase shopping behavior (cart, checkout, browsing).
    # Past completed orders do not artificially force a converted customer to remain "Hot".
    eval_features = dict(merged_features)
    if is_converted:
        eval_features["orders_count"] = 0
        eval_features["total_order_value"] = 0.0
        eval_features["average_order_value"] = 0.0

    vector = [float(eval_features[col]) for col in feature_cols]
    X_raw = pd.DataFrame([vector], columns=feature_cols)
    X_scaled = scaler.transform(X_raw)

    prob = float(model.predict_proba(X_scaled)[0][1])
    prob = max(0.0, min(1.0, prob))
    lead_score = int(round(prob * 100))
    lead_probability = round(prob, 4)

    # Segment mapping from scoring_constants
    from scoring_constants import HOT, WARM, CHECKOUT_OVERRIDE_HOURS
    if lead_score >= HOT:
        lead_segment = "Hot"
    elif lead_score >= WARM:
        lead_segment = "Warm"
    else:
        lead_segment = "Cold"

    # Active Checkout Override: unconverted customer with checkout within 24h
    active_checkout_override = False
    checkout_attempts = int(merged_features.get("checkout_attempts", 0) or 0)
    days_since = float(merged_features.get("days_since_last_activity", 0) or 0)
    segment_reason = ""
    if not is_converted and checkout_attempts > 0 and days_since <= (CHECKOUT_OVERRIDE_HOURS / 24.0):
        active_checkout_override = True
        lead_segment = "Hot"
        segment_reason = "OVERRIDE: Active checkout within 24h (segment promoted by XGBoost model pipeline)"

    # Confidence and provisional status
    sessions_count = int(merged_features.get("sessions_count", 1) or 1)
    has_purchase_intent = bool(
        float(merged_features.get("cart_item_count", 0) or 0) > 0
        or float(merged_features.get("cart_value", 0) or 0) > 0
        or float(merged_features.get("wishlist_item_count", 0) or 0) > 0
        or orders_count > 0
        or checkout_attempts > 0
    )
    products_viewed = int(merged_features.get("products_viewed", 0) or 0)

    if sessions_count <= 1 and not has_purchase_intent and products_viewed == 0:
        is_provisional = True
        confidence = "low"
    elif sessions_count <= 1:
        is_provisional = False
        confidence = "medium"
    else:
        is_provisional = False
        confidence = "high"

    customer_id = customer_features.get("customer_id", customer_features.get("_id", ""))

    return {
        "customer_id": str(customer_id) if customer_id else None,

        # Authoritative XGBoost model outputs
        "lead_score": lead_score,
        "lead_probability": lead_probability,
        "lead_segment": lead_segment,
        "segment_reason": segment_reason,
        "confidence": confidence,
        "is_provisional": is_provisional,

        # Model and Lifecycle metadata
        "is_converted": is_converted,
        "active_checkout_override": active_checkout_override,
        "has_purchase_intent": has_purchase_intent,
        "ml_model_probability": lead_probability,
        "raw_model_probability": lead_probability,
        "ml_model_score": lead_score,
        "raw_model_score": lead_score,
        "ml_model_available": True,
        "ml_model_error": None,

        # Operational metadata
        "model_version": metadata.get("model_version", "v2.0_ecommerce_xgb"),
        "scored_at": datetime.now(timezone.utc).isoformat(),
        "scoring_method": "xgboost_direct_ml_model",
        "threshold_disclaimer": f"XGBoost direct inference: Hot>={HOT}, Warm>={WARM}, Cold<{WARM}.",
    }

