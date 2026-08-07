import unittest
from unittest.mock import Mock

from identity_service import generate_anonymous_id, resolve_anonymous_identity


class IdentityServiceTests(unittest.TestCase):
    def setUp(self):
        self.users = Mock()
        self.sessions = Mock()
        self.events = Mock()
        self.leads = Mock()

    def test_generates_opaque_anonymous_ids(self):
        anonymous_id = generate_anonymous_id()

        self.assertTrue(anonymous_id.startswith("anon_"))
        self.assertGreater(len(anonymous_id), len("anon_"))

    def test_merges_sessions_events_and_leads_into_user(self):
        self.sessions.find.return_value = [{"_id": "session-1"}, {"_id": "session-2"}]
        self.sessions.update_many.return_value.modified_count = 2
        self.events.update_many.return_value.modified_count = 5
        self.leads.update_many.return_value.modified_count = 1

        result = resolve_anonymous_identity(
            "anon_visitor",
            "user-1",
            self.users,
            self.sessions,
            self.events,
            self.leads,
        )

        self.assertEqual(result, {"sessions_merged": 2, "events_merged": 5, "leads_merged": 1})
        self.sessions.find.assert_called_once()
        self.events.update_many.assert_called_once()
        self.leads.update_many.assert_called_once()
        self.users.update_one.assert_called_once_with(
            {"_id": "user-1"}, {"$addToSet": {"anonymous_ids": "anon_visitor"}}
        )

    def test_empty_identity_does_not_write_records(self):
        result = resolve_anonymous_identity(
            None, "user-1", self.users, self.sessions, self.events, self.leads
        )

        self.assertEqual(result, {"sessions_merged": 0, "events_merged": 0, "leads_merged": 0})
        self.sessions.find.assert_not_called()
        self.sessions.update_many.assert_not_called()
        self.events.update_many.assert_not_called()
        self.leads.update_many.assert_not_called()
