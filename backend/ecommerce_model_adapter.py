"""E-Commerce ML lead scoring inference adapter.

Loads dedicated e-commerce model artifacts and executes read-only lead scoring inference
on canonical customer_features documents.
"""

from datetime import datetime, timezone
from functools import lru_cache
import json
import math
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

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
    return joblib.load(ECOMMERCE_MODEL_PATH)


@lru_cache(maxsize=1)
def load_ecommerce_scaler():
    """Load the dedicated e-commerce StandardScaler binary."""
    if not ECOMMERCE_SCALER_PATH.exists():
        raise FileNotFoundError(f"Scaler file not found at {ECOMMERCE_SCALER_PATH}")
    return joblib.load(ECOMMERCE_SCALER_PATH)


@lru_cache(maxsize=1)
def load_ecommerce_feature_columns():
    """Load the immutable 23 feature column order used during training."""
    if not ECOMMERCE_FEATURE_COLUMNS_PATH.exists():
        raise FileNotFoundError(f"Feature columns file not found at {ECOMMERCE_FEATURE_COLUMNS_PATH}")
    return joblib.load(ECOMMERCE_FEATURE_COLUMNS_PATH)


@lru_cache(maxsize=1)
def load_ecommerce_metadata():
    """Load the model training metadata dictionary."""
    if not ECOMMERCE_METADATA_PATH.exists():
        raise FileNotFoundError(f"Metadata file not found at {ECOMMERCE_METADATA_PATH}")
    with open(ECOMMERCE_METADATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


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
    sessions = float(base_dict.get("sessions_count", 0))
    cart_items = float(base_dict.get("cart_item_count", 0))
    checkout_attempts = float(base_dict.get("checkout_attempts", 0))
    high_intent = float(base_dict.get("high_intent_page_visits", 0))
    page_views = float(base_dict.get("page_views_count", 0))
    product_interactions = float(base_dict.get("product_interactions", 0))

    cart_to_session = round(cart_items / sessions, 3) if sessions > 0 else 0.0
    checkout_to_cart = round(checkout_attempts / max(cart_items, 1.0), 3)
    high_intent_ratio = round(high_intent / max(page_views, 1.0), 3)
    product_density = round(product_interactions / sessions, 3) if sessions > 0 else 0.0

    return {
        "cart_to_session_ratio": cart_to_session,
        "checkout_to_cart_ratio": checkout_to_cart,
        "high_intent_ratio": high_intent_ratio,
        "product_interaction_density": product_density,
    }


def predict_customer_features(customer_features):
    """Run lead scoring inference on one customer feature document.

    Args:
        customer_features (dict): Feature document for a customer.

    Returns:
        dict: Inference results with lead probability, score, segment, and model metadata.

    Raises:
        ValueError: If customer_features is not a dict, is missing required base fields,
                    or contains invalid non-numeric values.
    """
    if not isinstance(customer_features, dict):
        raise ValueError("customer_features must be a dictionary")

    # Validate presence of required base features
    missing_fields = [f for f in REQUIRED_BASE_FEATURES if f not in customer_features]
    if missing_fields:
        raise ValueError(f"Missing required customer feature fields: {missing_fields}")

    # Compute derived features
    derived = compute_derived_features(customer_features)

    # Build feature dictionary
    merged_features = dict(customer_features)
    for k, v in derived.items():
        if k not in merged_features or merged_features[k] is None:
            merged_features[k] = v

    # Handle nullable days_since_last_activity
    if merged_features.get("days_since_last_activity") is None:
        merged_features["days_since_last_activity"] = 0.0

    feature_cols = load_ecommerce_feature_columns()
    vector = []

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

        vector.append(val_float)

    # Load artifacts and scale input
    scaler = load_ecommerce_scaler()
    model = load_ecommerce_model()
    metadata = load_ecommerce_metadata()

    X_raw = pd.DataFrame([vector], columns=feature_cols)
    X_scaled = scaler.transform(X_raw)

    prob = float(model.predict_proba(X_scaled)[0][1])
    prob = max(0.0, min(1.0, prob))
    lead_score = int(round(prob * 100))

    # Segment mapping based on provisional synthetic thresholds
    if prob >= 0.70:
        segment = "Hot"
    elif prob >= 0.35:
        segment = "Warm"
    else:
        segment = "Cold"

    customer_id = customer_features.get("customer_id", customer_features.get("_id", ""))

    return {
        "customer_id": str(customer_id) if customer_id else None,
        "lead_probability": round(prob, 4),
        "lead_score": lead_score,
        "lead_segment": segment,
        "model_version": metadata.get("model_version", "v2.0_ecommerce_xgb"),
        "scored_at": datetime.now(timezone.utc).isoformat(),
        "threshold_disclaimer": "Provisional synthetic-data thresholds. Hot >= 0.70, Warm 0.35-0.70, Cold < 0.35.",
    }
