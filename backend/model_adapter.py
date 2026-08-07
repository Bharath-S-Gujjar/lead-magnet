"""Map live behavioral features into the current demo model's input schema."""

from pathlib import Path

import joblib
import pandas as pd


MODEL_DIRECTORY = Path(__file__).resolve().parent.parent / "model"
FEATURE_COLUMNS_PATH = MODEL_DIRECTORY / "feature_columns.pkl"


LEAD_SOURCE_COLUMNS = {
    "direct": "Lead Source_Direct Traffic",
    "direct traffic": "Lead Source_Direct Traffic",
    "facebook": "Lead Source_Facebook",
    "google": "Lead Source_Google",
    "live chat": "Lead Source_Live Chat",
    "nc_edm": "Lead Source_NC_EDM",
    "olark chat": "Lead Source_Olark Chat",
    "organic search": "Lead Source_Organic Search",
    "pay per click ads": "Lead Source_Pay per Click Ads",
    "press release": "Lead Source_Press_Release",
    "reference": "Lead Source_Reference",
    "referral sites": "Lead Source_Referral Sites",
    "social media": "Lead Source_Social Media",
    "unknown": "Lead Source_Unknown",
    "welearn": "Lead Source_WeLearn",
    "welingak website": "Lead Source_Welingak Website",
    "bing": "Lead Source_bing",
    "blog": "Lead Source_blog",
    "testone": "Lead Source_testone",
    "welearnblog_home": "Lead Source_welearnblog_Home",
    "youtubechannel": "Lead Source_youtubechannel",
}

LEAD_ORIGIN_COLUMNS = {
    "landing page submission": "Lead Origin_Landing Page Submission",
    "lead add form": "Lead Origin_Lead Add Form",
    "lead import": "Lead Origin_Lead Import",
    "quick add form": "Lead Origin_Quick Add Form",
}

LAST_ACTIVITY_COLUMNS = {
    "converted to lead": "Last Activity_Converted to Lead",
    "form submitted on website": "Last Activity_Form Submitted on Website",
    "olark chat conversation": "Last Activity_Olark Chat Conversation",
    "page visited on website": "Last Activity_Page Visited on Website",
    "unknown": "Last Activity_Unknown",
}

LAST_NOTABLE_ACTIVITY_COLUMNS = {
    "form submitted on website": "Last Notable Activity_Form Submitted on Website",
    "olark chat conversation": "Last Notable Activity_Olark Chat Conversation",
    "page visited on website": "Last Notable Activity_Page Visited on Website",
}


def load_feature_columns():
    """Load the immutable column order used by the saved demo model."""
    return joblib.load(FEATURE_COLUMNS_PATH)


def _normalise(value):
    return value.strip().casefold() if isinstance(value, str) else ""


def _set_if_supported(model_features, column):
    if column in model_features:
        model_features[column] = 1


def adapt_behavioral_features(behavioral_features):
    """Return one model-ready DataFrame from a behavioral feature dictionary.

    Every saved model feature starts at zero, matching the current application's
    ``reindex(..., fill_value=0)`` behavior. Only fields that have a controlled
    live-data mapping are populated here. Scaling and prediction deliberately
    belong to a later step.
    """
    feature_columns = load_feature_columns()
    model_features = {column: 0 for column in feature_columns}

    model_features["TotalVisits"] = behavioral_features.get("total_visits", 0)
    model_features["Total Time Spent on Website"] = behavioral_features.get(
        "total_time_seconds", 0
    )
    model_features["Page Views Per Visit"] = behavioral_features.get(
        "page_views_per_visit", 0
    )

    source_column = LEAD_SOURCE_COLUMNS.get(_normalise(behavioral_features.get("landing_source")))
    _set_if_supported(model_features, source_column)

    lead_origin = behavioral_features.get("lead_origin")
    if not lead_origin and behavioral_features.get("form_submit_count", 0) > 0:
        lead_origin = "Landing Page Submission"
    origin_column = LEAD_ORIGIN_COLUMNS.get(_normalise(lead_origin))
    _set_if_supported(model_features, origin_column)

    activity = behavioral_features.get("last_meaningful_activity", "Unknown")
    activity_key = _normalise(activity)
    _set_if_supported(model_features, LAST_ACTIVITY_COLUMNS.get(activity_key))
    _set_if_supported(model_features, LAST_NOTABLE_ACTIVITY_COLUMNS.get(activity_key))

    return pd.DataFrame([model_features]).reindex(columns=feature_columns, fill_value=0)
