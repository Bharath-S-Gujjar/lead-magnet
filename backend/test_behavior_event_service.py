import unittest
from unittest.mock import Mock

from bson import ObjectId

from behavior_event_service import (
    InvalidSessionIdError,
    MissingEventFieldsError,
    SessionNotFoundError,
    UnsupportedEventTypeError,
    log_behavior_event,
)


class BehaviorEventServiceTests(unittest.TestCase):
    def setUp(self):
        self.session_id = ObjectId()
        self.event_id = ObjectId()
        self.sessions = Mock()
        self.events = Mock()
        self.sessions.find_one.return_value = {
            "_id": self.session_id,
            "visitor_id": "visitor_001",
            "anonymous_id": "anon_001",
            "user_id": ObjectId(),
        }
        self.events.insert_one.return_value.inserted_id = self.event_id

    def test_logs_valid_legacy_payload(self):
        event_id = log_behavior_event(
            {
                "session_id": str(self.session_id),
                "event_type": "page_view",
                "page": "/products",
                "metadata": {"scroll_depth": 80},
            },
            self.sessions,
            self.events,
        )

        inserted_event = self.events.insert_one.call_args.args[0]
        update_payload = self.sessions.update_one.call_args.args[1]

        self.assertEqual(event_id, str(self.event_id))
        self.assertEqual(inserted_event["event_type"], "page_view")
        self.assertEqual(inserted_event["event_category"], "navigation")
        self.assertEqual(inserted_event["event_action"], "view")
        self.assertEqual(inserted_event["metadata"], {"scroll_depth": 80})
        self.assertEqual(inserted_event["schema_version"], 2)
        self.assertIn("$inc", update_payload)
        self.assertEqual(update_payload["$inc"], {"page_views": 1})

    def test_logs_valid_rich_payload(self):
        log_behavior_event(
            {
                "session_id": str(self.session_id),
                "event_type": "product_view",
                "event_category": "product",
                "event_action": "view",
                "page": "/products/123",
                "entity": {"type": "product", "id": "123", "category": "Shoes"},
                "metadata": {"source": "product_grid", "position": 4},
                "context": {"device_type": "mobile"},
                "schema_version": 2,
            },
            self.sessions,
            self.events,
        )

        inserted_event = self.events.insert_one.call_args.args[0]
        update_payload = self.sessions.update_one.call_args.args[1]

        self.assertEqual(inserted_event["event_type"], "product_view")
        self.assertEqual(inserted_event["entity"]["id"], "123")
        self.assertEqual(inserted_event["context"], {"device_type": "mobile"})
        self.assertNotIn("$inc", update_payload)

    def test_rejects_unsupported_event_type(self):
        with self.assertRaises(UnsupportedEventTypeError) as error:
            log_behavior_event(
                {"session_id": str(self.session_id), "event_type": "unknown_event"},
                self.sessions,
                self.events,
            )

        self.assertEqual(error.exception.message, "Unsupported event_type")
        self.events.insert_one.assert_not_called()

    def test_rejects_missing_session_id(self):
        with self.assertRaises(MissingEventFieldsError):
            log_behavior_event({"event_type": "page_view"}, self.sessions, self.events)

        self.events.insert_one.assert_not_called()

    def test_rejects_invalid_session_id(self):
        with self.assertRaises(InvalidSessionIdError):
            log_behavior_event(
                {"session_id": "not-a-valid-object-id", "event_type": "page_view"},
                self.sessions,
                self.events,
            )

        self.events.insert_one.assert_not_called()

    def test_rejects_session_not_found(self):
        self.sessions.find_one.return_value = None

        with self.assertRaises(SessionNotFoundError):
            log_behavior_event(
                {"session_id": str(self.session_id), "event_type": "page_view"},
                self.sessions,
                self.events,
            )

        self.events.insert_one.assert_not_called()


if __name__ == "__main__":
    unittest.main()
