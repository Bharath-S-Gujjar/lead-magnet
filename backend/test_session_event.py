import requests

BASE = "http://127.0.0.1:5000"

# Use a real session_id from your last test_session_start.py run
session_id = "6a76061c63631989a03df54e"

r = requests.post(f"{BASE}/api/session/event", json={
    "session_id": session_id,
    "event_type": "page_view",
    "page": "/pricing",
    "metadata": {"scroll_depth": 40}
})
print(r.status_code)
print(r.json())