"""Regression tests for Phase 2 Admin Notification Bell.

Validates:
1. Admin can retrieve notifications.
2. Unread notification count is correct.
3. Customer cannot retrieve admin notifications.
4. Customer cannot mark admin notifications as read.
5. Clicking/marking one notification read decreases unread count.
6. Mark all as read works.
7. Read notifications remain in history.
8. Duplicate mark-read is safe.
9. Socket.IO notification event reaches the admin client.
10. Duplicate initial-load + Socket.IO notification does not create duplicate entries.
11. New notification increments unread count.
12. Existing notification history loads correctly.
"""

import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
import jwt
from bson import ObjectId

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app as app_module
from admin_intelligence_service import (
    get_admin_notifications_list,
    create_admin_notification,
    mark_notification_read,
    mark_all_notifications_read,
)


class AdminNotificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = app_module.app.test_client()
        cls.db = app_module.db
        cls.notifications = app_module.admin_notifications_collection
        cls.jwt_secret = app_module.JWT_SECRET

    def setUp(self):
        # Clean test notifications
        self.notifications.delete_many({})

    def tearDown(self):
        # Clean test notifications
        self.notifications.delete_many({})

    def make_token(self, user_id, role="user"):
        exp_time = datetime.now(timezone.utc) + timedelta(minutes=15)
        return jwt.encode(
            {"sub": str(user_id), "role": role, "exp": exp_time},
            self.jwt_secret,
            algorithm="HS256"
        )

    @property
    def admin_headers(self):
        token = self.make_token("admin_user", role="admin")
        return {"Authorization": f"Bearer {token}"}

    @property
    def customer_headers(self):
        token = self.make_token(ObjectId(), role="user")
        return {"Authorization": f"Bearer {token}"}

    # 1. Admin can retrieve notifications
    def test_01_admin_can_retrieve_notifications(self):
        create_admin_notification(self.db, "lead_qualified", "Elena qualified as Hot lead", title="New Hot Lead")
        create_admin_notification(self.db, "new_customer", "John Doe registered", title="New Customer")

        res = self.client.get("/api/admin/intelligence/notifications", headers=self.admin_headers)
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get("success"))
        items = data["data"]["items"]
        self.assertEqual(len(items), 2)
        # Should also be available on alias
        res_alias = self.client.get("/api/admin/notifications", headers=self.admin_headers)
        self.assertEqual(res_alias.status_code, 200)

    # 2. Unread notification count is correct
    def test_02_unread_notification_count_is_correct(self):
        n1 = create_admin_notification(self.db, "lead_qualified", "Lead 1")
        n2 = create_admin_notification(self.db, "order_placed", "Order 1")
        n3 = create_admin_notification(self.db, "new_customer", "User 1")

        # Mark n1 read manually
        self.notifications.update_one({"_id": ObjectId(n1["id"])}, {"$set": {"read": True}})

        res = self.client.get("/api/admin/intelligence/notifications", headers=self.admin_headers)
        self.assertEqual(res.status_code, 200)
        payload = res.get_json()["data"]
        self.assertEqual(payload["unread_count"], 2)
        self.assertEqual(payload["total"], 3)

    # 3. Customer cannot retrieve admin notifications
    def test_03_customer_cannot_retrieve_admin_notifications(self):
        res = self.client.get("/api/admin/intelligence/notifications", headers=self.customer_headers)
        self.assertEqual(res.status_code, 403)

        res_anon = self.client.get("/api/admin/intelligence/notifications")
        self.assertIn(res_anon.status_code, [401, 403])

        res_alias = self.client.get("/api/admin/notifications", headers=self.customer_headers)
        self.assertEqual(res_alias.status_code, 403)

    # 4. Customer cannot mark admin notifications as read
    def test_04_customer_cannot_mark_admin_notifications_as_read(self):
        n = create_admin_notification(self.db, "lead_qualified", "Hot lead")
        notif_id = n["id"]

        res_single = self.client.patch(
            f"/api/admin/intelligence/notifications/{notif_id}/read",
            headers=self.customer_headers
        )
        self.assertEqual(res_single.status_code, 403)

        res_all = self.client.post(
            "/api/admin/intelligence/notifications/mark-all-read",
            headers=self.customer_headers
        )
        self.assertEqual(res_all.status_code, 403)

    # 5. Clicking/marking one notification read decreases unread count
    def test_05_marking_one_notification_read_decreases_unread_count(self):
        n1 = create_admin_notification(self.db, "lead_qualified", "Lead 1")
        n2 = create_admin_notification(self.db, "lead_qualified", "Lead 2")

        res_before = self.client.get("/api/admin/intelligence/notifications", headers=self.admin_headers)
        self.assertEqual(res_before.get_json()["data"]["unread_count"], 2)

        # Mark n1 read
        res_mark = self.client.patch(
            f"/api/admin/intelligence/notifications/{n1['id']}/read",
            headers=self.admin_headers
        )
        self.assertEqual(res_mark.status_code, 200)
        mark_data = res_mark.get_json()["data"]
        self.assertTrue(mark_data["success"])
        self.assertEqual(mark_data["unread_count"], 1)
        self.assertTrue(mark_data["notification"]["read"])

        # Fetch notifications to verify unread_count updated
        res_after = self.client.get("/api/admin/intelligence/notifications", headers=self.admin_headers)
        self.assertEqual(res_after.get_json()["data"]["unread_count"], 1)

    # 6. Mark all as read works
    def test_06_mark_all_as_read_works(self):
        create_admin_notification(self.db, "lead_qualified", "Lead A")
        create_admin_notification(self.db, "new_customer", "Lead B")
        create_admin_notification(self.db, "order_placed", "Lead C")

        res_mark_all = self.client.post(
            "/api/admin/intelligence/notifications/mark-all-read",
            headers=self.admin_headers
        )
        self.assertEqual(res_mark_all.status_code, 200)
        mark_all_data = res_mark_all.get_json()["data"]
        self.assertTrue(mark_all_data["success"])
        self.assertEqual(mark_all_data["unread_count"], 0)
        self.assertEqual(mark_all_data["modified_count"], 3)

        # Verify through GET
        res_after = self.client.get("/api/admin/intelligence/notifications", headers=self.admin_headers)
        self.assertEqual(res_after.get_json()["data"]["unread_count"], 0)

    # 7. Read notifications remain in history
    def test_07_read_notifications_remain_in_history(self):
        n1 = create_admin_notification(self.db, "lead_qualified", "Lead Stays")
        notif_id = n1["id"]

        self.client.patch(
            f"/api/admin/intelligence/notifications/{notif_id}/read",
            headers=self.admin_headers
        )

        res = self.client.get("/api/admin/intelligence/notifications", headers=self.admin_headers)
        items = res.get_json()["data"]["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], notif_id)
        self.assertTrue(items[0]["read"])

    # 8. Duplicate mark-read is safe (idempotent)
    def test_08_duplicate_mark_read_is_safe(self):
        n = create_admin_notification(self.db, "lead_qualified", "Lead Idempotent")
        notif_id = n["id"]

        # Call once
        res1 = self.client.patch(f"/api/admin/intelligence/notifications/{notif_id}/read", headers=self.admin_headers)
        self.assertEqual(res1.status_code, 200)
        self.assertEqual(res1.get_json()["data"]["unread_count"], 0)

        # Call again
        res2 = self.client.patch(f"/api/admin/intelligence/notifications/{notif_id}/read", headers=self.admin_headers)
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(res2.get_json()["data"]["unread_count"], 0)

        # Mark all read repeated calls
        res_all_1 = self.client.post("/api/admin/intelligence/notifications/mark-all-read", headers=self.admin_headers)
        self.assertEqual(res_all_1.status_code, 200)
        self.assertEqual(res_all_1.get_json()["data"]["modified_count"], 0)

    # 9. Socket.IO notification event reaches the admin client
    def test_09_socketio_notification_event_reaches_admin_client(self):
        sio_client = app_module.socketio.test_client(app_module.app)
        self.assertTrue(sio_client.is_connected())

        create_admin_notification(
            self.db,
            notif_type="lead_qualified",
            title="New Hot Lead",
            message="Elena qualified · Score 98",
            customer_id="cust_elena_123",
            socketio=app_module.socketio
        )

        received = sio_client.get_received()
        sio_client.disconnect()

        admin_notif_events = [e for e in received if e["name"] == "admin_notification"]
        self.assertGreaterEqual(len(admin_notif_events), 1)
        event_payload = admin_notif_events[0]["args"][0]
        self.assertEqual(event_payload["type"], "lead_qualified")
        self.assertEqual(event_payload["title"], "New Hot Lead")
        self.assertEqual(event_payload["customer_id"], "cust_elena_123")
        self.assertFalse(event_payload["read"])

    # 10. Duplicate initial-load + Socket.IO notification does not create duplicate entries
    def test_10_deduplication_of_notification_entries(self):
        n = create_admin_notification(self.db, "lead_qualified", "Duplicate Check Lead")
        initial_list = [n]

        # Emulate frontend deduplication handler
        def frontend_dedup_add(existing_list, incoming):
            incoming_id = incoming.get("id") or incoming.get("_id")
            if any((item.get("id") or item.get("_id")) == incoming_id for item in existing_list):
                return existing_list
            return [incoming] + existing_list

        # Attempt to add same notification as Socket.IO incoming
        updated_list = frontend_dedup_add(initial_list, n)
        self.assertEqual(len(updated_list), 1)

        # Add distinct notification
        n2 = create_admin_notification(self.db, "new_customer", "Distinct Customer")
        updated_list_2 = frontend_dedup_add(updated_list, n2)
        self.assertEqual(len(updated_list_2), 2)

    # 11. New notification increments unread count
    def test_11_new_notification_increments_unread_count(self):
        res0 = self.client.get("/api/admin/intelligence/notifications", headers=self.admin_headers)
        self.assertEqual(res0.get_json()["data"]["unread_count"], 0)

        create_admin_notification(self.db, "order_placed", "Order placed ₹1,200")
        res1 = self.client.get("/api/admin/intelligence/notifications", headers=self.admin_headers)
        self.assertEqual(res1.get_json()["data"]["unread_count"], 1)

        create_admin_notification(self.db, "new_customer", "Customer registered")
        res2 = self.client.get("/api/admin/intelligence/notifications", headers=self.admin_headers)
        self.assertEqual(res2.get_json()["data"]["unread_count"], 2)

    # 12. Existing notification history loads correctly (ordered newest first)
    def test_12_existing_notification_history_loads_correctly_newest_first(self):
        t1 = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 1, 1, 11, 0, tzinfo=timezone.utc)
        t3 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)

        self.notifications.insert_one({"type": "first", "message": "First", "created_at": t1, "read": True})
        self.notifications.insert_one({"type": "second", "message": "Second", "created_at": t2, "read": False})
        self.notifications.insert_one({"type": "third", "message": "Third", "created_at": t3, "read": False})

        res = self.client.get("/api/admin/intelligence/notifications?limit=10", headers=self.admin_headers)
        self.assertEqual(res.status_code, 200)
        items = res.get_json()["data"]["items"]
        self.assertEqual(len(items), 3)
        self.assertEqual(items[0]["type"], "third")
        self.assertEqual(items[1]["type"], "second")
        self.assertEqual(items[2]["type"], "first")
        self.assertEqual(res.get_json()["data"]["unread_count"], 2)


if __name__ == "__main__":
    unittest.main()
