"""Deterministic model explainability service.

Produces human-readable explanations of why a customer received their lead score
by combining the model's global feature importances with the customer's feature
values relative to population means (z-score direction).

Why not SHAP:
    While XGBoost supports SHAP via TreeExplainer, the current model is loaded
    via lru_cache and SHAP adds significant per-prediction overhead (~50-200ms)
    plus a heavy dependency. This deterministic approach gives interpretable,
    fast explanations aligned with the model's global importances. It computes
    signed directional contribution scores that indicate which features push a
    customer toward or away from qualification.

Explanation method: deterministic_feature_contribution
"""

import json
from pathlib import Path

from ecommerce_model_adapter import (
    load_ecommerce_metadata,
    load_ecommerce_scaler,
    load_ecommerce_feature_columns,
    REQUIRED_BASE_FEATURES,
    compute_derived_features,
)


# Human-readable feature labels for admin display
FEATURE_LABELS = {
    "checkout_attempts": "Checkout Attempts",
    "product_interactions": "Product Interactions",
    "checkout_to_cart_ratio": "Checkout-to-Cart Ratio",
    "cart_value": "Cart Value",
    "products_viewed": "Products Viewed",
    "cart_item_count": "Cart Items",
    "orders_count": "Orders Placed",
    "total_order_value": "Total Order Value",
    "page_views_count": "Page Views",
    "high_intent_page_visits": "High-Intent Page Visits",
    "days_since_last_activity": "Days Since Last Activity",
    "wishlist_item_count": "Wishlist Items",
    "total_events": "Total Events",
    "average_order_value": "Average Order Value",
    "high_intent_ratio": "High-Intent Ratio",
    "unique_products_viewed": "Unique Products Viewed",
    "total_time_spent": "Total Time Spent",
    "sessions_count": "Session Count",
    "cart_to_session_ratio": "Cart-to-Session Ratio",
    "product_interaction_density": "Product Interaction Density",
    "search_count": "Search Count",
    "average_session_duration": "Average Session Duration",
    "form_submit_count": "Form Submissions",
}


def explain_lead_score(customer_features):
    """Generate a deterministic feature-contribution explanation for a customer.

    Args:
        customer_features (dict): Customer feature document from customer_features collection.

    Returns:
        dict: Explanation containing positive_contributors, negative_contributors,
              and metadata about the explanation method.
    """
    if not customer_features or not isinstance(customer_features, dict):
        return {
            "positive_contributors": [],
            "negative_contributors": [],
            "top_driving_factors": [],
            "explanation_method": "deterministic_feature_contribution",
            "error": "No customer features available for explanation",
        }

    try:
        metadata = load_ecommerce_metadata()
        feature_importances = metadata.get("top_feature_importances", {})
        feature_columns = load_ecommerce_feature_columns()
        scaler = load_ecommerce_scaler()
    except Exception as e:
        return {
            "positive_contributors": [],
            "negative_contributors": [],
            "top_driving_factors": [],
            "explanation_method": "deterministic_feature_contribution",
            "error": f"Could not load model artifacts: {e}",
        }

    if not feature_importances:
        return {
            "positive_contributors": [],
            "negative_contributors": [],
            "top_driving_factors": [],
            "explanation_method": "deterministic_feature_contribution",
            "error": "No feature importances available in model metadata",
        }

    # Compute derived features if not present
    derived = compute_derived_features(customer_features)
    merged = dict(customer_features)
    for k, v in derived.items():
        if k not in merged or merged[k] is None:
            merged[k] = v

    if merged.get("days_since_last_activity") is None:
        merged["days_since_last_activity"] = 0.0

    # Get scaler means and scales for z-score computation
    scaler_means = scaler.mean_ if hasattr(scaler, "mean_") else None
    scaler_scales = scaler.scale_ if hasattr(scaler, "scale_") else None

    contributions = []

    for idx, col in enumerate(feature_columns):
        importance = feature_importances.get(col, 0.0)
        if importance == 0:
            continue

        raw_value = merged.get(col)
        if raw_value is None:
            continue

        try:
            val = float(raw_value)
        except (ValueError, TypeError):
            continue

        # Compute z-score direction if scaler stats available
        z_score = 0.0
        if scaler_means is not None and scaler_scales is not None and idx < len(scaler_means):
            mean = scaler_means[idx]
            scale = scaler_scales[idx]
            if scale > 0:
                z_score = (val - mean) / scale

        # Contribution = importance × z_score direction
        # For "days_since_last_activity", higher value = negative for lead score
        contribution = importance * z_score

        label = FEATURE_LABELS.get(col, col.replace("_", " ").title())

        contributions.append({
            "feature": col,
            "label": label,
            "value": round(float(val), 2),
            "importance": round(float(importance), 4),
            "contribution": round(float(contribution), 4),
            "direction": "positive" if contribution > 0 else "negative",
        })

    # Sort by absolute contribution
    contributions.sort(key=lambda x: abs(x["contribution"]), reverse=True)

    positive = [c for c in contributions if c["contribution"] > 0]
    negative = [c for c in contributions if c["contribution"] <= 0]

    top_driving_factors = []
    for c in contributions[:10]:
        c_contrib = float(c["contribution"])
        top_driving_factors.append({
            "feature": c["feature"],
            "description": c["label"],
            "label": c["label"],
            "value": float(c["value"]),
            "contribution": c_contrib,
            "weight": round(abs(c_contrib), 4),
            "direction": c["direction"],
        })

    return {
        "positive_contributors": positive[:10],
        "negative_contributors": negative[:10],
        "top_driving_factors": top_driving_factors,
        "explanation_method": "deterministic_feature_contribution",
        "explanation_note": (
            "Contributions are computed from global feature importances weighted by "
            "the customer's feature values relative to population means. "
            "This is a deterministic approximation, not a per-prediction SHAP value."
        ),
    }
