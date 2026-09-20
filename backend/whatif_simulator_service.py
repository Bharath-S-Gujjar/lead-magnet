"""What-If lead score simulator.

Admin-only simulation that allows overriding behavioral feature values
and requesting a simulated lead score.

SAFETY GUARANTEES:
    - MUST NOT write to customer_features collection
    - MUST NOT modify lead state
    - MUST NOT create marketing automation events
    - MUST NOT send email or WhatsApp
    - MUST NOT modify production customer data
    - All results are clearly labeled as simulated
"""

from ecommerce_model_adapter import predict_customer_features, REQUIRED_BASE_FEATURES
from customer_feature_service import get_customer_features, _to_object_id


def simulate_lead_score(customer_id, feature_overrides, db):
    """Simulate a lead score with overridden feature values.

    Args:
        customer_id: ObjectId or string customer identifier (optional for baseline).
        feature_overrides (dict): Feature values to override for simulation.
        db: PyMongo database object.

    Returns:
        dict: Simulated lead score results with is_simulation=True.

    Raises:
        ValueError: If no base features can be constructed.
    """
    if not isinstance(feature_overrides, dict):
        raise ValueError("feature_overrides must be a dictionary")

    # Get baseline features
    base_features = None
    if customer_id and db is not None:
        features_col = db["customer_features"]
        base_features = get_customer_features(customer_id, features_col)

    if base_features is None:
        # Build a zero-baseline feature set
        base_features = {f: 0.0 for f in REQUIRED_BASE_FEATURES}

    # Create a COPY — never modify the original
    simulated_features = dict(base_features)

    # Apply overrides
    for key, value in feature_overrides.items():
        if key in REQUIRED_BASE_FEATURES:
            try:
                simulated_features[key] = float(value)
            except (ValueError, TypeError):
                raise ValueError(f"Invalid value for feature '{key}': {value}")

    # Run prediction on the COPY
    try:
        prediction = predict_customer_features(simulated_features)
    except Exception as e:
        raise ValueError(f"Simulation prediction failed: {e}")

    # Build simulated response — clearly labeled
    return {
        "is_simulation": True,
        "simulation_label": "SIMULATED — This result is not stored and does not affect production data.",
        "lead_probability": prediction.get("lead_probability"),
        "lead_score": prediction.get("lead_score"),
        "lead_segment": prediction.get("lead_segment"),
        "model_version": prediction.get("model_version"),
        "feature_overrides_applied": feature_overrides,
        "base_customer_id": str(customer_id) if customer_id else None,
    }
