"""Tests for the Four Urgent Targeted Fixes.

1. Email delivery: recipient resolution, opt-out checks, dry-run vs real SMTP status distinction,
   provider failure recording, credential safety.
2. Classification: purchase-intent requirement (login-only and page-view-only never Hot; cart,
   wishlist, and orders recognized as Hot intent signals).
3. Behaviour distribution: consistency with KPI metrics and safe zero handling.
4. Timestamps and Chronological ordering: mixed formats (ISO with Z, offset, space-separated,
   naive/aware datetimes, unix seconds/ms) and non-chronological insertion orders.
"""

import unittest
from datetime import datetime, timezone, timedelta
from bson import ObjectId

from timestamp_utils import parse_and_normalize_timestamp, sort_events_chronological
from ecommerce_model_adapter import predict_customer_features, REQUIRED_BASE_FEATURES
from customer_lead_state_service import sync_customer_lead_state
from marketing_service import evaluate_campaign_triggers
from admin_intelligence_service import _build_journey_timeline, _compute_behavior_summary
from communication_provider import (
    CommunicationProvider,
    DryRunCommunicationProvider,
    MultiChannelProvider,
)


class MockCollection:
    """In-memory collection mock for isolated unit testing."""
    def __init__(self, name="mock_col", docs=None):
        self.name = name
        self.docs = list(docs or [])

    def find_one(self, query=None, *args, **kwargs):
        query = query or {}
        for d in self.docs:
            if self._matches(d, query):
                return dict(d)
        return None

    def find(self, query=None, *args, **kwargs):
        query = query or {}
        res = [dict(d) for d in self.docs if self._matches(d, query)]
        # Support sort argument
        sort_arg = kwargs.get("sort")
        if sort_arg:
            key, direction = sort_arg[0]
            res.sort(key=lambda x: str(x.get(key, "")), reverse=(direction == -1))
        limit = kwargs.get("limit")
        if limit is not None:
            res = res[:limit]
        return MockCursor(res)

    def count_documents(self, query=None):
        query = query or {}
        return len([d for d in self.docs if self._matches(d, query)])

    def insert_one(self, doc):
        d = dict(doc)
        if "_id" not in d:
            d["_id"] = ObjectId()
        self.docs.append(d)
        return MockInsertResult(d["_id"])

    def update_one(self, query, update, upsert=False):
        found = False
        upserted_id = None
        for i, d in enumerate(self.docs):
            if self._matches(d, query):
                found = True
                if "$set" in update:
                    self.docs[i].update(update["$set"])
                break
        if not found and upsert:
            new_doc = dict(query)
            if "$set" in update:
                new_doc.update(update["$set"])
            if "_id" not in new_doc:
                new_doc["_id"] = ObjectId()
            upserted_id = new_doc["_id"]
            self.docs.append(new_doc)

        class _MockUpdateResult:
            def __init__(self, uid, matched):
                self.upserted_id = uid
                self.matched_count = matched
                self.modified_count = matched

        return _MockUpdateResult(upserted_id, 1 if found else 0)

    def list_indexes(self):
        return [{"name": "_id_"}]

    def create_index(self, *args, **kwargs):
        pass

    def _matches(self, doc, query):
        if not query:
            return True
        for k, v in query.items():
            if k == "$or":
                if not any(self._matches(doc, sub_q) for sub_q in v):
                    return False
                continue
            if isinstance(v, dict):
                # Handle operators like $gt, $gte, $lt, $lte, $ne, $exists
                doc_val = doc.get(k)
                for op, op_val in v.items():
                    if op == "$gt" and not (doc_val is not None and doc_val > op_val):
                        return False
                    if op == "$gte" and not (doc_val is not None and doc_val >= op_val):
                        return False
                    if op == "$lt" and not (doc_val is not None and doc_val < op_val):
                        return False
                    if op == "$lte" and not (doc_val is not None and doc_val <= op_val):
                        return False
                    if op == "$in" and not (doc_val in op_val):
                        return False
                    if op == "$nin" and (doc_val in op_val):
                        return False
                    if op == "$ne" and doc_val == op_val:
                        return False
                    if op == "$exists":
                        exists = k in doc or (doc_val is not None)
                        if exists != op_val:
                            return False
                continue
            if doc.get(k) != v and str(doc.get(k)) != str(v):
                return False
        return True


class MockCursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, key, direction=1):
        self.docs.sort(key=lambda x: str(x.get(key, "")), reverse=(direction == -1))
        return self

    def limit(self, n):
        self.docs = self.docs[:n]
        return self

    def __iter__(self):
        return iter(self.docs)

    def __len__(self):
        return len(self.docs)


class MockInsertResult:
    def __init__(self, inserted_id):
        self.inserted_id = inserted_id


class MockDatabase:
    def __init__(self, collections=None):
        self.collections = collections or {}

    def __getitem__(self, item):
        if item not in self.collections:
            self.collections[item] = MockCollection(item)
        return self.collections[item]

    def __contains__(self, item):
        return item in self.collections

    def list_collection_names(self):
        return list(self.collections.keys())


class FailingCommunicationProvider(CommunicationProvider):
    """Test double simulating SMTP failure."""
    def send_email(self, recipient, subject, body, metadata=None, html_body=None, **kwargs):
        return {
            "success": False,
            "error": "SMTPAuthenticationError: 535 5.7.8 Bad credentials",
            "provider": "smtp",
            "provider_message_id": None,
        }

    def send_whatsapp(self, recipient, body, metadata=None):
        return {
            "success": False,
            "error": "WhatsApp API timeout",
            "provider": "whatsapp",
            "provider_message_id": None,
        }


class RealSuccessCommunicationProvider(CommunicationProvider):
    """Test double simulating real SMTP acceptance."""
    def send_email(self, recipient, subject, body, metadata=None, html_body=None, **kwargs):
        return {
            "success": True,
            "provider": "smtp",
            "provider_message_id": "smtp-msg-999888",
            "error": None,
        }

    def send_whatsapp(self, recipient, body, metadata=None):
        return {
            "success": True,
            "provider": "whatsapp",
            "provider_message_id": "wa-msg-777",
            "error": None,
        }


# ==============================================================================
# 1. Tests for Email Delivery to Intended Recipient
# ==============================================================================

class TestEmailDelivery(unittest.TestCase):
    def setUp(self):
        self.customer_oid = ObjectId()
        self.customer_email = "test.shopper@example.com"
        self.profiles = MockCollection("user_profiles", [
            {
                "_id": self.customer_oid,
                "email": self.customer_email,
                "full_name": "Test Shopper",
                "email_opt_out": False,
            }
        ])
        self.campaigns = MockCollection("campaigns", [
            {
                "_id": ObjectId(),
                "name": "Cart Recovery",
                "trigger_type": "abandoned_cart",
                "channel": "email",
                "template": "Hello {{name}}, you left items in your cart!",
                "active": True,
            }
        ])
        self.cart = MockCollection("cart", [
            {
                "user_id": str(self.customer_oid),
                "product_id": "prod_1",
                "quantity": 2,
                "updated_at": datetime.now(timezone.utc) - timedelta(hours=3),
            }
        ])
        self.campaign_logs = MockCollection("campaign_logs")
        self.db = MockDatabase({
            "user_profiles": self.profiles,
            "campaigns": self.campaigns,
            "cart": self.cart,
            "campaign_logs": self.campaign_logs,
        })

    def test_recipient_email_resolved_from_profile(self):
        """Trace email dispatch: recipient must be resolved from user profile, not raw ID."""
        prov = RealSuccessCommunicationProvider()
        logs = evaluate_campaign_triggers(
            self.campaigns, self.campaign_logs, self.cart,
            profiles_collection=self.profiles, provider=prov, db=self.db
        )
        self.assertEqual(len(logs), 1)
        log = logs[0]
        self.assertEqual(log["recipient"], self.customer_email)
        self.assertEqual(log["status"], "Sent")
        self.assertEqual(log["provider"], "smtp")
        self.assertEqual(log["provider_message_id"], "smtp-msg-999888")

    def test_opt_out_customer_not_sent(self):
        """Opted-out customer must not receive email dispatch."""
        self.profiles.docs[0]["email_opt_out"] = True
        prov = RealSuccessCommunicationProvider()
        logs = evaluate_campaign_triggers(
            self.campaigns, self.campaign_logs, self.cart,
            profiles_collection=self.profiles, provider=prov, db=self.db
        )
        self.assertEqual(len(logs), 0)
        self.assertEqual(self.campaign_logs.count_documents(), 0)

    def test_anonymous_cart_without_profile_skipped_safely(self):
        """Anonymous carts with no linked email profile must be skipped safely without crashing."""
        self.cart.docs = [{
            "user_id": "anon_unregistered_999",
            "product_id": "prod_1",
            "quantity": 1,
            "updated_at": datetime.now(timezone.utc) - timedelta(hours=3),
        }]
        prov = RealSuccessCommunicationProvider()
        logs = evaluate_campaign_triggers(
            self.campaigns, self.campaign_logs, self.cart,
            profiles_collection=self.profiles, provider=prov, db=self.db
        )
        self.assertEqual(len(logs), 0)

    def test_provider_failure_records_failed_status(self):
        """Provider failure must record status='Failed' and capture provider error without crashing."""
        prov = FailingCommunicationProvider()
        logs = evaluate_campaign_triggers(
            self.campaigns, self.campaign_logs, self.cart,
            profiles_collection=self.profiles, provider=prov, db=self.db
        )
        self.assertEqual(len(logs), 1)
        log = logs[0]
        self.assertEqual(log["status"], "Failed")
        self.assertIn("SMTPAuthenticationError", log["error"])
        self.assertIsNone(log["sent_at"])
        self.assertEqual(log["recipient"], self.customer_email)

    def test_dry_run_provider_marked_as_dry_run_never_sent(self):
        """Dry-run provider must record status='Dry Run', never claiming real SMTP sent."""
        prov = DryRunCommunicationProvider()
        logs = evaluate_campaign_triggers(
            self.campaigns, self.campaign_logs, self.cart,
            profiles_collection=self.profiles, provider=prov, db=self.db
        )
        self.assertEqual(len(logs), 1)
        log = logs[0]
        self.assertEqual(log["status"], "Dry Run")
        self.assertEqual(log["provider"], "dry_run")
        self.assertEqual(log["recipient"], self.customer_email)


# ==============================================================================
# 2. Tests for Hot/Warm/Cold Classification & Purchase Intent
# ==============================================================================

class TestLeadClassification(unittest.TestCase):
    def _base_features(self):
        return {f: 0.0 for f in REQUIRED_BASE_FEATURES}

    def _make_mock_model(self, fixed_prob):
        """Return a mock XGBoost model that always predicts fixed_prob."""
        class _MockModel:
            def predict_proba(self, X):
                import numpy as np
                return np.array([[1 - fixed_prob, fixed_prob]])
        return _MockModel()

    def _make_mock_scaler(self):
        class _MockScaler:
            def transform(self, X):
                return X
        return _MockScaler()

    def _predict_with_mock(self, features, fixed_prob):
        """Run predict_customer_features with mocked model/scaler/metadata."""
        import unittest.mock as mock
        import numpy as np
        mock_model = self._make_mock_model(fixed_prob)
        mock_scaler = self._make_mock_scaler()
        mock_meta = {"model_version": "test_v1"}
        mock_cols = list(REQUIRED_BASE_FEATURES) + [
            "cart_to_session_ratio", "checkout_to_cart_ratio",
            "high_intent_ratio", "product_interaction_density"
        ]
        with mock.patch("ecommerce_model_adapter.load_ecommerce_model", return_value=mock_model), \
             mock.patch("ecommerce_model_adapter.load_ecommerce_scaler", return_value=mock_scaler), \
             mock.patch("ecommerce_model_adapter.load_ecommerce_metadata", return_value=mock_meta), \
             mock.patch("ecommerce_model_adapter.load_ecommerce_feature_columns", return_value=mock_cols):
            return predict_customer_features(features)

    def test_login_only_does_not_qualify_as_hot(self):
        """Browse-only customer with low model score must NOT qualify as Hot."""
        feat = self._base_features()
        feat.update({
            "sessions_count": 2.0,
            "total_events": 2.0,
            "total_time_spent": 120.0,
            "average_session_duration": 60.0,
        })
        # Model returns low probability -> should be Cold
        pred = self._predict_with_mock(feat, fixed_prob=0.20)
        self.assertNotEqual(pred["lead_segment"], "Hot")
        self.assertIn(pred["lead_segment"], ["Cold", "Warm"])
        self.assertFalse(pred["has_purchase_intent"])

    def test_page_views_only_does_not_qualify_as_hot(self):
        """Browse-only customer with moderate model score must be Warm, not Hot."""
        feat = self._base_features()
        feat.update({
            "sessions_count": 10.0,
            "total_events": 80.0,
            "page_views_count": 60.0,
            "total_time_spent": 1800.0,
            "average_session_duration": 180.0,
        })
        # Model returns 0.50 -> Warm (no intent signals to boost)
        pred = self._predict_with_mock(feat, fixed_prob=0.50)
        self.assertEqual(pred["lead_segment"], "Warm")
        self.assertFalse(pred["has_purchase_intent"])

    def test_browse_only_high_model_prob_is_hot(self):
        """Browse-only customer with HIGH model prob (>=0.65) must be Hot — model is primary driver."""
        feat = self._base_features()
        feat.update({"sessions_count": 15.0, "page_views_count": 100.0, "total_events": 120.0})
        pred = self._predict_with_mock(feat, fixed_prob=0.80)
        self.assertEqual(pred["lead_segment"], "Hot")
        self.assertFalse(pred["has_purchase_intent"])

    def test_cart_addition_recognized_as_hot(self):
        """Cart additions must be recognized as meaningful purchase intent, always Hot."""
        feat = self._base_features()
        feat.update({
            "sessions_count": 1.0,
            "total_events": 5.0,
            "page_views_count": 3.0,
            "cart_item_count": 2.0,
            "cart_value": 850.0,
        })
        # Even with low model prob, cart forces Hot with floor 75
        pred = self._predict_with_mock(feat, fixed_prob=0.20)
        self.assertEqual(pred["lead_segment"], "Hot")
        self.assertGreaterEqual(pred["lead_probability"], 0.75)
        self.assertTrue(pred["has_purchase_intent"])

    def test_wishlist_addition_recognized_as_hot(self):
        """Wishlist additions must always produce Hot with score floor 70."""
        feat = self._base_features()
        feat.update({
            "sessions_count": 1.0,
            "total_events": 4.0,
            "page_views_count": 2.0,
            "wishlist_item_count": 1.0,
        })
        pred = self._predict_with_mock(feat, fixed_prob=0.20)
        self.assertEqual(pred["lead_segment"], "Hot")
        self.assertGreaterEqual(pred["lead_probability"], 0.70)
        self.assertTrue(pred["has_purchase_intent"])

    def test_order_placement_recognized_as_hot(self):
        """Actual order placement must always produce Hot with score floor 85."""
        feat = self._base_features()
        feat.update({
            "sessions_count": 1.0,
            "total_events": 6.0,
            "orders_count": 1.0,
            "total_order_value": 1500.0,
            "average_order_value": 1500.0,
        })
        pred = self._predict_with_mock(feat, fixed_prob=0.20)
        self.assertEqual(pred["lead_segment"], "Hot")
        self.assertGreaterEqual(pred["lead_probability"], 0.85)
        self.assertTrue(pred["has_purchase_intent"])

    def test_raw_model_score_preserved_separately(self):
        """Raw model outputs must remain distinct from boosted business score/segment."""
        feat = self._base_features()
        feat.update({"wishlist_item_count": 1.0})
        pred = self._predict_with_mock(feat, fixed_prob=0.20)
        self.assertIn("raw_model_score", pred)
        self.assertIn("raw_model_probability", pred)
        self.assertIsInstance(pred["raw_model_score"], int)
        self.assertIsInstance(pred["raw_model_probability"], float)
        # raw_model_score should reflect actual model output (20), not boosted (70)
        self.assertEqual(pred["raw_model_score"], 20)
        self.assertGreater(pred["lead_score"], pred["raw_model_score"])

    def test_customer_lead_state_agrees_with_intent_rule(self):
        """Customer lead state sync must agree on effective segment and qualification status."""
        import unittest.mock as mock
        cust_id = ObjectId()
        feat = self._base_features()
        feat.update({"customer_id": cust_id, "cart_item_count": 1.0, "cart_value": 300.0})

        feat_col = MockCollection("customer_features", [feat])
        state_col = MockCollection("customer_lead_state")
        db = MockDatabase({"customer_features": feat_col, "customer_lead_state": state_col})

        mock_model = self._make_mock_model(0.20)  # low prob, but cart forces Hot
        mock_scaler = self._make_mock_scaler()
        mock_meta = {"model_version": "test_v1"}
        mock_cols = list(REQUIRED_BASE_FEATURES) + [
            "cart_to_session_ratio", "checkout_to_cart_ratio",
            "high_intent_ratio", "product_interaction_density"
        ]
        with mock.patch("ecommerce_model_adapter.load_ecommerce_model", return_value=mock_model), \
             mock.patch("ecommerce_model_adapter.load_ecommerce_scaler", return_value=mock_scaler), \
             mock.patch("ecommerce_model_adapter.load_ecommerce_metadata", return_value=mock_meta), \
             mock.patch("ecommerce_model_adapter.load_ecommerce_feature_columns", return_value=mock_cols):
            state = sync_customer_lead_state(cust_id, db)

        self.assertEqual(state["lead_segment"], "Hot")
        self.assertEqual(state["qualification_status"], "qualified")
        self.assertTrue(state["has_purchase_intent"])



# ==============================================================================
# 3. Tests for Behaviour Activity Distribution
# ==============================================================================

class TestBehaviourDistribution(unittest.TestCase):
    def test_behavior_summary_counts_align_with_events_without_double_counting(self):
        """Synonym aliases (product_view+product_click, order_placed) must not double count."""
        cust_oid = ObjectId()
        events = [
            {"_id": ObjectId(), "user_id": cust_oid, "event_type": "product_view"},
            {"_id": ObjectId(), "user_id": cust_oid, "event_type": "product_click"},
            {"_id": ObjectId(), "user_id": cust_oid, "event_type": "add_to_cart"},
            {"_id": ObjectId(), "user_id": cust_oid, "event_type": "wishlist_add"},
            {"_id": ObjectId(), "user_id": cust_oid, "event_type": "search"},
            {"_id": ObjectId(), "user_id": cust_oid, "event_type": "filter_apply"},
        ]
        orders = [{"_id": ObjectId(), "user_id": cust_oid, "total_amount": 999}]
        db = MockDatabase({
            "user_profiles": MockCollection("user_profiles"),
            "sessions": MockCollection("sessions"),
            "events": MockCollection("events", events),
            "orders": MockCollection("orders", orders),
            "cart": MockCollection("cart"),
            "wishlist": MockCollection("wishlist"),
        })

        res = _compute_behavior_summary(cust_oid, db)
        bs = res["behavior_summary"]
        self.assertEqual(bs["product_views_count"], 2)
        self.assertEqual(bs["cart_adds_count"], 1)
        self.assertEqual(bs["wishlist_adds_count"], 1)
        self.assertEqual(bs["orders_count"], 1)
        self.assertEqual(bs["searches_count"], 2)

    def test_empty_customer_behavior_handled_safely(self):
        """Empty customer profile with 0 events must handle zero counts without error."""
        cust_oid = ObjectId()
        db = MockDatabase({
            "user_profiles": MockCollection("user_profiles"),
            "sessions": MockCollection("sessions"),
            "events": MockCollection("events"),
            "orders": MockCollection("orders"),
            "cart": MockCollection("cart"),
            "wishlist": MockCollection("wishlist"),
        })
        res = _compute_behavior_summary(cust_oid, db)
        bs = res["behavior_summary"]
        self.assertEqual(bs.get("sessions_count", 0), 0)
        self.assertEqual(bs.get("page_views_count", 0), 0)
        self.assertEqual(bs.get("orders_count", 0), 0)


# ==============================================================================
# 4. Tests for Timestamps and Chronological Ordering
# ==============================================================================

class TestTimestampsAndChronologicalOrdering(unittest.TestCase):
    def test_parse_and_normalize_mixed_formats(self):
        """Normalize mixed timestamp formats to accurate UTC datetimes and ISO strings."""
        # 1. ISO with Z
        dt1, iso1 = parse_and_normalize_timestamp("2026-10-24T12:00:00Z")
        self.assertEqual(dt1.tzinfo, timezone.utc)
        self.assertEqual(dt1.hour, 12)

        # 2. ISO with offset (+05:30) -> 17:30 IST is 12:00 UTC
        dt2, iso2 = parse_and_normalize_timestamp("2026-10-24T17:30:00+05:30")
        self.assertEqual(dt2, dt1)

        # 3. Space separated format
        dt3, iso3 = parse_and_normalize_timestamp("2026-10-24 12:00:00")
        self.assertEqual(dt3, dt1)

        # 4. Naive datetime -> treated as UTC
        dt_naive = datetime(2026, 10, 24, 12, 0, 0)
        dt4, _ = parse_and_normalize_timestamp(dt_naive)
        self.assertEqual(dt4, dt1)

        # 5. Unix epoch seconds
        epoch_sec = dt1.timestamp()
        dt5, _ = parse_and_normalize_timestamp(epoch_sec)
        self.assertEqual(int(dt5.timestamp()), int(dt1.timestamp()))

        # 6. Unix epoch milliseconds
        epoch_ms = epoch_sec * 1000.0
        dt6, _ = parse_and_normalize_timestamp(epoch_ms)
        self.assertEqual(int(dt6.timestamp()), int(dt1.timestamp()))

    def test_sorting_preserves_newest_first_regardless_of_insertion_order(self):
        """Events inserted non-chronologically must be sorted strictly newest first."""
        base_time = datetime(2026, 10, 24, 10, 0, 0, tzinfo=timezone.utc)
        t1 = base_time - timedelta(hours=3) # Oldest
        t2 = base_time - timedelta(hours=2) # 2nd oldest
        t3 = base_time - timedelta(hours=1) # 2nd newest
        t4 = base_time                       # Newest

        # Scrambled insertion order
        events = [
            {"id": "evt_t3", "timestamp": t3.isoformat(), "event_type": "cart_add"},
            {"id": "evt_t1", "timestamp": t1.timestamp(), "event_type": "page_view"}, # unix epoch
            {"id": "evt_t4", "timestamp": "2026-10-24 10:00:00", "event_type": "order"}, # space format
            {"id": "evt_t2", "timestamp": "2026-10-24T13:30:00+05:30", "event_type": "wishlist"}, # 08:00 UTC
        ]

        sorted_events = sort_events_chronological(events, timestamp_key="timestamp", reverse=True, id_keys=["id"])
        ids = [e["id"] for e in sorted_events]
        self.assertEqual(ids, ["evt_t4", "evt_t3", "evt_t2", "evt_t1"])

    def test_equal_timestamps_deterministic_tie_breaker(self):
        """Events with equal timestamps must order deterministically via secondary key."""
        shared_ts = "2026-10-24T12:00:00Z"
        events_order_1 = [
            {"_id": "item_b", "timestamp": shared_ts, "type": "event"},
            {"_id": "item_a", "timestamp": shared_ts, "type": "event"},
        ]
        events_order_2 = [
            {"_id": "item_a", "timestamp": shared_ts, "type": "event"},
            {"_id": "item_b", "timestamp": shared_ts, "type": "event"},
        ]
        sorted_1 = sort_events_chronological(events_order_1, timestamp_key="timestamp", reverse=True, id_keys=["_id"])
        sorted_2 = sort_events_chronological(events_order_2, timestamp_key="timestamp", reverse=True, id_keys=["_id"])
        self.assertEqual([e["_id"] for e in sorted_1], [e["_id"] for e in sorted_2])

    def test_journey_timeline_with_mixed_timestamps_and_order_dedup(self):
        """Journey timeline integration must sort mixed timestamps and retain order amounts."""
        cust_oid = ObjectId()
        order_time = datetime(2026, 10, 24, 15, 0, 0, tzinfo=timezone.utc)
        event_time_newer = datetime(2026, 10, 24, 16, 0, 0, tzinfo=timezone.utc)
        event_time_older = datetime(2026, 10, 24, 14, 0, 0, tzinfo=timezone.utc)

        db = MockDatabase({
            "orders": MockCollection("orders", [
                {"_id": ObjectId(), "user_id": cust_oid, "total_amount": 1499.0, "created_at": order_time}
            ]),
            "events": MockCollection("events", [
                {"_id": ObjectId(), "user_id": cust_oid, "event_type": "page_view", "timestamp": event_time_newer.isoformat()},
                {"_id": ObjectId(), "user_id": cust_oid, "event_type": "product_view", "timestamp": event_time_older.isoformat()},
            ]),
            "marketing_communications": MockCollection("marketing_communications"),
        })

        timeline = _build_journey_timeline(cust_oid, db)
        self.assertEqual(len(timeline), 3)
        self.assertEqual(timeline[0]["event_type"], "page_view")
        self.assertEqual(timeline[1]["type"], "order")
        self.assertEqual(timeline[1]["total_amount"], 1499.0)
        self.assertEqual(timeline[2]["event_type"], "product_view")


# ==============================================================================
# 5. Tests for Checkout Override and Focused Regression Scenarios
# ==============================================================================

class TestCheckoutOverrideAndRegressions(unittest.TestCase):
    """Focused regression tests for checkout override, lifecycle, and model guarantees."""

    def test_01_converted_customer_with_active_checkout_not_promoted_by_override(self):
        """Scenario 1: Converted customer + recent checkout + score 43 must NOT become Hot via override."""
        from behavioral_scoring_service import compute_behavioral_score
        now_iso = datetime.now(timezone.utc).isoformat()
        feat = {
            "orders_count": 1,
            "total_order_value": 750.0,
            "checkout_attempts": 1,
            "days_since_last_activity": 0.05,
            "last_checkout_action_at": now_iso,
        }
        res = compute_behavioral_score(feat)
        self.assertTrue(res["is_converted"])
        self.assertEqual(res["lead_segment"], "Warm")
        self.assertNotEqual(res["lead_segment"], "Hot")
        self.assertNotIn("OVERRIDE: Active checkout within 24h (temporary Hot)", res["score_reasons"])

    def test_02_unconverted_customer_with_active_checkout_qualifies_for_override(self):
        """Scenario 2: Unconverted customer + recent checkout + score >= 50 qualifies for temporary Hot override."""
        from behavioral_scoring_service import compute_behavioral_score
        now_iso = datetime.now(timezone.utc).isoformat()
        feat = {
            "orders_count": 0,
            "total_order_value": 0.0,
            "checkout_attempts": 1,
            "cart_item_count": 1,
            "cart_value": 600.0,
            "products_viewed": 8,
            "unique_products_viewed": 4,
            "sessions_count": 2,
            "days_since_last_activity": 0.05,
            "last_checkout_action_at": now_iso,
        }
        res = compute_behavioral_score(feat)
        self.assertFalse(res["is_converted"])
        self.assertTrue(res["active_checkout_override"])
        self.assertGreaterEqual(res["behavioral_score"], 50)
        self.assertEqual(res["lead_segment"], "Hot")
        self.assertIn("OVERRIDE: Active checkout within 24h (temporary Hot)", res["score_reasons"])

    def test_03_naturally_hot_unconverted_customer_remains_hot(self):
        """Scenario 3: An unconverted customer with score >= 70 remains Hot under standard policy."""
        from behavioral_scoring_service import compute_behavioral_score
        feat = {
            "orders_count": 0,
            "checkout_attempts": 2,
            "cart_item_count": 3,
            "cart_value": 2000.0,
            "products_viewed": 16,
            "unique_products_viewed": 8,
            "wishlist_item_count": 2,
            "product_interactions": 20,
            "high_intent_page_visits": 5,
            "sessions_count": 4,
            "total_time_spent": 1200.0,
            "days_since_last_activity": 0.0,
        }
        res = compute_behavioral_score(feat)
        self.assertFalse(res["is_converted"])
        self.assertGreaterEqual(res["behavioral_score"], 70)
        self.assertEqual(res["lead_segment"], "Hot")

    def test_04_completed_orders_consistently_recognized_in_lifecycle(self):
        """Scenario 4: Completed orders are recognized consistently as converted across customer lifecycle."""
        from behavioral_scoring_service import compute_behavioral_score
        res_order_count = compute_behavioral_score({"orders_count": 1})
        res_order_val = compute_behavioral_score({"total_order_value": 1500.0})
        res_unconverted = compute_behavioral_score({"orders_count": 0, "total_order_value": 0.0})

        self.assertTrue(res_order_count["is_converted"])
        self.assertTrue(res_order_val["is_converted"])
        self.assertFalse(res_unconverted["is_converted"])

    def test_05_page_views_alone_follow_warm_cold_policy(self):
        """Scenario 5: Page views alone follow the intended Warm/Cold policy and never produce Hot without intent/high model prob."""
        import unittest.mock as mock
        class _MockModel:
            def predict_proba(self, X):
                import numpy as np
                return np.array([[0.60, 0.40]])  # prob = 0.40 -> Warm
        class _MockScaler:
            def transform(self, X):
                return X

        feat = {f: 0.0 for f in REQUIRED_BASE_FEATURES}
        feat.update({"page_views_count": 20.0, "sessions_count": 2.0, "total_events": 25.0})

        cols = list(REQUIRED_BASE_FEATURES) + [
            "cart_to_session_ratio", "checkout_to_cart_ratio", "high_intent_ratio", "product_interaction_density"
        ]
        with mock.patch("ecommerce_model_adapter.load_ecommerce_model", return_value=_MockModel()), \
             mock.patch("ecommerce_model_adapter.load_ecommerce_scaler", return_value=_MockScaler()), \
             mock.patch("ecommerce_model_adapter.load_ecommerce_metadata", return_value={"model_version": "test"}), \
             mock.patch("ecommerce_model_adapter.load_ecommerce_feature_columns", return_value=cols):
            res = predict_customer_features(feat)

        self.assertEqual(res["lead_segment"], "Warm")
        self.assertFalse(res["has_purchase_intent"])

    def test_06_cart_and_wishlist_follow_purchase_intent_policy(self):
        """Scenario 6: Cart (floor 75) and wishlist (floor 70) follow intended purchase intent guarantee."""
        import unittest.mock as mock
        class _MockModel:
            def predict_proba(self, X):
                import numpy as np
                return np.array([[0.80, 0.20]])  # low raw prob 0.20
        class _MockScaler:
            def transform(self, X):
                return X

        cols = list(REQUIRED_BASE_FEATURES) + [
            "cart_to_session_ratio", "checkout_to_cart_ratio", "high_intent_ratio", "product_interaction_density"
        ]

        # Cart addition guarantees floor 75 and Hot
        feat_cart = {f: 0.0 for f in REQUIRED_BASE_FEATURES}
        feat_cart.update({"cart_item_count": 1.0, "cart_value": 350.0})

        # Wishlist addition guarantees floor 70 and Hot
        feat_wishlist = {f: 0.0 for f in REQUIRED_BASE_FEATURES}
        feat_wishlist.update({"wishlist_item_count": 1.0})

        with mock.patch("ecommerce_model_adapter.load_ecommerce_model", return_value=_MockModel()), \
             mock.patch("ecommerce_model_adapter.load_ecommerce_scaler", return_value=_MockScaler()), \
             mock.patch("ecommerce_model_adapter.load_ecommerce_metadata", return_value={"model_version": "test"}), \
             mock.patch("ecommerce_model_adapter.load_ecommerce_feature_columns", return_value=cols):
            res_cart = predict_customer_features(feat_cart)
            res_wishlist = predict_customer_features(feat_wishlist)

        self.assertEqual(res_cart["lead_segment"], "Hot")
        self.assertEqual(res_cart["lead_score"], 75)
        self.assertTrue(res_cart["has_purchase_intent"])

        self.assertEqual(res_wishlist["lead_segment"], "Hot")
        self.assertEqual(res_wishlist["lead_score"], 70)
        self.assertTrue(res_wishlist["has_purchase_intent"])

    def test_07_raw_model_score_and_final_score_remain_distinct(self):
        """Scenario 7: Raw model score (from XGBoost prob) remains distinct from boosted final business score."""
        import unittest.mock as mock
        class _MockModel:
            def predict_proba(self, X):
                import numpy as np
                return np.array([[0.75, 0.25]])  # raw prob = 0.25 -> raw score 25
        class _MockScaler:
            def transform(self, X):
                return X

        feat = {f: 0.0 for f in REQUIRED_BASE_FEATURES}
        feat.update({"cart_item_count": 1.0, "cart_value": 450.0})

        cols = list(REQUIRED_BASE_FEATURES) + [
            "cart_to_session_ratio", "checkout_to_cart_ratio", "high_intent_ratio", "product_interaction_density"
        ]
        with mock.patch("ecommerce_model_adapter.load_ecommerce_model", return_value=_MockModel()), \
             mock.patch("ecommerce_model_adapter.load_ecommerce_scaler", return_value=_MockScaler()), \
             mock.patch("ecommerce_model_adapter.load_ecommerce_metadata", return_value={"model_version": "test"}), \
             mock.patch("ecommerce_model_adapter.load_ecommerce_feature_columns", return_value=cols):
            pred = predict_customer_features(feat)

        self.assertEqual(pred["raw_model_score"], 25)
        self.assertEqual(pred["raw_model_probability"], 0.25)
        self.assertEqual(pred["lead_score"], 75)
        self.assertGreater(pred["lead_score"], pred["raw_model_score"])

    def test_08_missing_and_invalid_numeric_features_rejected(self):
        """Scenarios 8 & 9: Missing required features and non-numeric values raise ValueError."""
        feat = {f: 0.0 for f in REQUIRED_BASE_FEATURES}
        del feat["sessions_count"]
        with self.assertRaises(ValueError):
            predict_customer_features(feat)

        feat_bad_val = {f: 0.0 for f in REQUIRED_BASE_FEATURES}
        feat_bad_val["cart_value"] = "invalid"
        with self.assertRaises(ValueError):
            predict_customer_features(feat_bad_val)

    def test_09_whatif_simulator_does_not_mutate_persisted_state(self):
        """Scenario 10: What-if simulation does not mutate persisted customer features or state."""
        from whatif_simulator_service import simulate_lead_score
        cust_id = ObjectId()
        original_doc = {
            "customer_id": cust_id,
            "sessions_count": 2.0,
            "total_events": 10.0,
            "total_time_spent": 120.0,
            "average_session_duration": 60.0,
            "page_views_count": 5.0,
            "days_since_last_activity": 1.0,
            "products_viewed": 3.0,
            "unique_products_viewed": 2.0,
            "product_interactions": 4.0,
            "search_count": 1.0,
            "form_submit_count": 0.0,
            "high_intent_page_visits": 0.0,
            "cart_item_count": 0.0,
            "cart_value": 0.0,
            "wishlist_item_count": 0.0,
            "checkout_attempts": 0.0,
            "orders_count": 0.0,
            "total_order_value": 0.0,
            "average_order_value": 0.0,
        }
        feat_col = MockCollection("customer_features", [dict(original_doc)])
        db = MockDatabase({"customer_features": feat_col})

        # Run simulation with high checkout attempts
        sim_res = simulate_lead_score(cust_id, {"checkout_attempts": 5, "cart_value": 800.0}, db)
        self.assertTrue(sim_res["is_simulation"])

        # Verify underlying feature document was untouched
        persisted = feat_col.find_one({"customer_id": cust_id})
        self.assertEqual(persisted["checkout_attempts"], 0.0)
        self.assertEqual(persisted["cart_value"], 0.0)

    def test_10_transactional_order_confirmation_works_for_converted_customers(self):
        """Scenario 12: Existing transactional order confirmation works cleanly for converted customers."""
        from marketing_automation_service import trigger_order_confirmation_communication
        order_id = ObjectId()
        user_id = ObjectId()
        db = MockDatabase({
            "orders": MockCollection("orders", [{
                "_id": order_id,
                "user_id": user_id,
                "total_amount": 1299.0,
                "items": [{"name": "Casual Shirt", "quantity": 1, "price": 1299.0}],
                "created_at": datetime.now(timezone.utc),
            }]),
            "user_profiles": MockCollection("user_profiles", [{
                "_id": user_id,
                "email": "converted_shopper@example.com",
                "full_name": "Test Shopper",
            }]),
            "marketing_communications": MockCollection("marketing_communications"),
        })

        prov = DryRunCommunicationProvider()
        result = trigger_order_confirmation_communication(order_id, db, provider=prov)
        self.assertIsNotNone(result)
        self.assertIn("email", result)
        self.assertIn(result["email"]["status"], ["Dry Run", "sent", "queued"])


if __name__ == "__main__":
    unittest.main()
