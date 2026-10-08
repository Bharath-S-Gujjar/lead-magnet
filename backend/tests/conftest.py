"""Isolated MongoDB configuration for the backend test suite.

Environment values are set before test modules import ``app``.  The suite is
therefore always directed to the local ``leadmagnet_test`` database, never to
the normal development or production database.
"""

import os
import sys
from pathlib import Path

import pytest


TEST_DATABASE_NAME = "leadmagnet_test"
TEST_MONGO_URI = "mongodb://127.0.0.1:27017"

os.environ["MONGO_URI"] = TEST_MONGO_URI
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# ``app`` binds its collections during import.  Rebind them here, before test
# modules import any collection globals from it.
import app as app_module

app_module.app.config["TESTING"] = True
app_module.app.testing = True
app_module.db = app_module.mongo_client[TEST_DATABASE_NAME]
app_module.profiles_collection = app_module.db["user_profiles"]
app_module.legacy_users_collection = app_module.db["users"]
app_module.products_collection = app_module.db["myntra_products"]
app_module.sessions_collection = app_module.db["sessions"]
app_module.events_collection = app_module.db["events"]
app_module.leads_collection = app_module.db["leads"]
app_module.orders_collection = app_module.db["orders"]
app_module.cart_collection = app_module.db["cart"]
app_module.wishlist_collection = app_module.db["wishlist"]
app_module.campaigns_collection = app_module.db["campaigns"]
app_module.campaign_logs_collection = app_module.db["campaign_logs"]
app_module.customer_features_collection = app_module.db["customer_features"]
app_module.customer_lead_state_collection = app_module.db["customer_lead_state"]
app_module.marketing_automation_events_collection = app_module.db["marketing_automation_events"]
app_module.marketing_communications_collection = app_module.db["marketing_communications"]
app_module.admin_notifications_collection = app_module.db["admin_notifications"]
app_module.lead_score_history_collection = app_module.db["lead_score_history"]


@pytest.fixture(autouse=True)
def isolated_test_database():
    """Start and finish every test with an empty, explicitly named test DB."""
    if app_module.db.name != TEST_DATABASE_NAME:
        raise RuntimeError("Refusing to run tests outside the isolated test database")

    app_module.mongo_client.drop_database(TEST_DATABASE_NAME)
    try:
        yield
    finally:
        app_module.mongo_client.drop_database(TEST_DATABASE_NAME)
