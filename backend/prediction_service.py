"""Standalone prediction service for the existing demo model artifacts."""

from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import joblib

from action_recommendations import get_next_action


MODEL_DIRECTORY = Path(__file__).resolve().parent.parent / "model"
MODEL_VERSION = "xgb_model.pkl"


@lru_cache(maxsize=1)
def load_prediction_artifacts():
    """Load the unchanged scaler, prediction model, clustering model, and map."""
    return {
        "scaler": joblib.load(MODEL_DIRECTORY / "scaler.pkl"),
        "model": joblib.load(MODEL_DIRECTORY / "xgb_model.pkl"),
        "kmeans": joblib.load(MODEL_DIRECTORY / "kmeans_model.pkl"),
        "segment_map": joblib.load(MODEL_DIRECTORY / "segment_map.pkl"),
    }


def predict_session(model_input):
    """Return a prediction dictionary for one model-ready feature DataFrame."""
    artifacts = load_prediction_artifacts()
    scaled_features = artifacts["scaler"].transform(model_input)

    probability = artifacts["model"].predict_proba(scaled_features)[0][1]
    cluster_id = artifacts["kmeans"].predict(scaled_features)[0]
    segment = artifacts["segment_map"][cluster_id]

    return {
        "score": float(probability),
        "segment": segment,
        "next_action": get_next_action(segment),
        "model_version": MODEL_VERSION,
        "prediction_time": datetime.now(timezone.utc).isoformat(),
    }
