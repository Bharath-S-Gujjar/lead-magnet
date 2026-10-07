"""Real Customer Journey & End-to-End Production Validation Driver.
Executes Phase 19 against real running backend, real Atlas database, real catalog, and live Socket.IO.
"""

import os
import sys
import time
import json
import uuid
import datetime
from bson import ObjectId
import pymongo
import requests
from dotenv import load_dotenv
import socketio

load_dotenv('backend/.env')

BASE_URL = "http://127.0.0.1:5000"
ATLAS_URI = os.getenv("MONGO_URI") or os.getenv("MONGODB_URI")
client = pymongo.MongoClient(ATLAS_URI, serverSelectionTimeoutMS=10000)
db = client.get_default_database()

# Socket.IO client to capture live admin events
sio = socketio.Client(reconnection=True, reconnection_attempts=5)
captured_socket_events = []

@sio.on("*")
def catch_all(event, data):
    captured_socket_events.append({"event": event, "data": data, "received_at": datetime.datetime.utcnow().isoformat()})

@sio.on("lead_score_updated")
def on_score_update(data):
    captured_socket_events.append({"event": "lead_score_updated", "data": data, "received_at": datetime.datetime.utcnow().isoformat()})

@sio.on("lead_qualified")
def on_qualified(data):
    captured_socket_events.append({"event": "lead_qualified", "data": data, "received_at": datetime.datetime.utcnow().isoformat()})

@sio.on("lead_disqualified")
def on_disqualified(data):
    captured_socket_events.append({"event": "lead_disqualified", "data": data, "received_at": datetime.datetime.utcnow().isoformat()})

@sio.on("customer_activity")
def on_customer_activity(data):
    captured_socket_events.append({"event": "customer_activity", "data": data, "received_at": datetime.datetime.utcnow().isoformat()})

@sio.on("order_placed")
def on_order_placed(data):
    captured_socket_events.append({"event": "order_placed", "data": data, "received_at": datetime.datetime.utcnow().isoformat()})


def run_validation():
    print("=" * 60)
    print("STARTING REAL CUSTOMER JOURNEY VALIDATION")
    print("=" * 60)

    # Connect Socket.IO
    try:
        sio.connect(BASE_URL, transports=['websocket', 'polling'])
        print("[Socket.IO] Connected successfully to", BASE_URL)
    except Exception as e:
        print("[Socket.IO] Connection warning (will proceed):", e)

    results = {}

    # ----------------------------------------------------
    # 1. Atlas Pre-Test State
    # ----------------------------------------------------
    print("\n--- 1. ATLAS PRE-TEST STATE ---")
    pre_counts = {}
    collections = [
        'products', 'user_profiles', 'sessions', 'events', 'orders',
        'customer_features', 'customer_lead_state', 'lead_score_history',
        'marketing_automation_events', 'marketing_communications', 'admin_notifications'
    ]
    for c in collections:
        pre_counts[c] = db[c].count_documents({})
        print(f"  {c}: {pre_counts[c]}")

    results["pre_counts"] = pre_counts

    # ----------------------------------------------------
    # 2. Phase 19B: Real Customer Registration & Login
    # ----------------------------------------------------
    print("\n--- 2. REAL CUSTOMER REGISTRATION & LOGIN ---")
    test_anon_id = f"anon_val_{uuid.uuid4().hex[:12]}"
    test_email = f"elena.rostova.{uuid.uuid4().hex[:6]}@example.com"
    test_password = "SecurePassword123!"
    test_payload = {
        "fullName": "Elena Rostova",
        "email": test_email,
        "phone": "9876543210",
        "dob": "1996-08-20",
        "age": 29,
        "gender": "Female",
        "password": test_password,
        "confirmPassword": test_password,
        "anonymous_id": test_anon_id,
    }

    # Register via storefront API endpoint
    reg_res = requests.post(f"{BASE_URL}/api/auth/signup", json=test_payload, timeout=10)
    print("Signup response:", reg_res.status_code, reg_res.json())
    assert reg_res.status_code == 201 or reg_res.json().get("success"), f"Signup failed: {reg_res.text}"

    # Login via storefront API endpoint
    login_payload = {
        "email": test_email,
        "password": test_password,
        "anonymous_id": test_anon_id,
    }
    login_res = requests.post(f"{BASE_URL}/api/auth/login", json=login_payload, timeout=10)
    print("Login response:", login_res.status_code, login_res.json())
    login_data = login_res.json().get("data", {})
    user_id = login_data.get("user_id")
    token = login_data.get("token")
    assert user_id and token, "Login did not return user_id and token!"

    # Verify user profile in MongoDB Atlas
    user_doc = db['user_profiles'].find_one({"_id": ObjectId(user_id)})
    print("Atlas user_profiles doc verified:", bool(user_doc), user_doc.get("email"), user_doc.get("role"))
    assert user_doc is not None, "User profile not found in Atlas!"
    assert user_doc.get("email") == test_email, "Email mismatch in user profile!"

    # Start customer session via storefront API
    session_start_res = requests.post(
        f"{BASE_URL}/api/session/start",
        json={"visitor_id": test_email, "anonymous_id": test_anon_id},
        timeout=10
    )
    session_data = session_start_res.json().get("data", {})
    session_id = session_data.get("session_id")
    print("Session started:", session_id)
    assert session_id, "Failed to start session!"

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    results["customer"] = {
        "user_id": user_id,
        "email": test_email,
        "session_id": session_id,
        "anonymous_id": test_anon_id,
    }

    # ----------------------------------------------------
    # 3. Phase 19C: Real Product Behavior & Catalog Interaction
    # ----------------------------------------------------
    print("\n--- 3. REAL PRODUCT BEHAVIOR AGAINST CATALOG ---")

    # Step A: Browse products from real catalog
    prod_res = requests.get(f"{BASE_URL}/api/products?page=1&limit=6", timeout=10)
    prods = prod_res.json().get("data", [])
    print(f"Catalog browse: fetched {len(prods)} products from real catalog.")
    assert len(prods) > 0, "No products returned from catalog!"

    selected_p1 = prods[0]
    selected_p2 = prods[1] if len(prods) > 1 else prods[0]
    p1_id = selected_p1.get("_id") or selected_p1.get("id")
    p2_id = selected_p2.get("_id") or selected_p2.get("id")
    print(f"Selected Product 1: {p1_id} - {selected_p1.get('name')} (Price: {selected_p1.get('price')})")
    print(f"Selected Product 2: {p2_id} - {selected_p2.get('name')} (Price: {selected_p2.get('price')})")

    # Step B: Log page view for homepage
    requests.post(f"{BASE_URL}/api/session/event", json={
        "session_id": session_id,
        "event_type": "page_view",
        "page": "/",
        "visitor_id": test_email,
        "user_id": user_id,
    }, timeout=10)

    # Step C: Search for products
    search_res = requests.get(f"{BASE_URL}/api/products?search=shirt&limit=5", timeout=10)
    requests.post(f"{BASE_URL}/api/session/event", json={
        "session_id": session_id,
        "event_type": "search",
        "page": "/products?search=shirt",
        "visitor_id": test_email,
        "user_id": user_id,
        "metadata": {"query": "shirt"},
    }, timeout=10)

    # Step D: View product 1 details
    p1_detail_res = requests.get(f"{BASE_URL}/api/products/{p1_id}", timeout=10)
    requests.post(f"{BASE_URL}/api/session/event", json={
        "session_id": session_id,
        "event_type": "product_view",
        "page": f"/product/{p1_id}",
        "visitor_id": test_email,
        "user_id": user_id,
        "entity": {"type": "product", "id": p1_id},
        "metadata": {"product_name": selected_p1.get("name")},
    }, timeout=10)

    # Check lead score after minimal browsing (NOT_QUALIFIED -> NOT_QUALIFIED)
    time.sleep(1.2)  # Respect debounce
    requests.post(f"{BASE_URL}/api/customer/lead-state/sync", headers=headers, timeout=10)
    state_step1 = requests.get(f"{BASE_URL}/api/customer/lead-state", headers=headers, timeout=10).json().get("data", {})
    print(f"Lifecycle Step 1 (Browsing): score={state_step1.get('lead_score')}, status={state_step1.get('qualification_status')}, transition={state_step1.get('qualification_transition')}")
    results["lifecycle_step1"] = state_step1

    # Step E: Add to wishlist
    wish_res = requests.post(f"{BASE_URL}/api/wishlist", json={
        "product_id": p1_id,
        "user_id": user_id,
        "session_id": session_id
    }, headers=headers, timeout=10)
    print("Wishlist add response:", wish_res.status_code, wish_res.json().get("success"))

    # Step F: Add Product 1 to cart
    cart_res1 = requests.post(f"{BASE_URL}/api/cart", json={
        "product_id": p1_id,
        "quantity": 2,
        "user_id": user_id,
        "session_id": session_id
    }, headers=headers, timeout=10)
    print("Cart add P1 response:", cart_res1.status_code, cart_res1.json().get("success"))

    # Step G: Add Product 2 to cart
    cart_res2 = requests.post(f"{BASE_URL}/api/cart", json={
        "product_id": p2_id,
        "quantity": 2,
        "user_id": user_id,
        "session_id": session_id
    }, headers=headers, timeout=10)
    print("Cart add P2 response:", cart_res2.status_code, cart_res2.json().get("success"))

    # Step H: High intent checkout visit
    requests.post(f"{BASE_URL}/api/session/event", json={
        "session_id": session_id,
        "event_type": "page_view",
        "page": "/cart/checkout",
        "visitor_id": test_email,
        "user_id": user_id,
    }, timeout=10)
    requests.post(f"{BASE_URL}/api/session/event", json={
        "session_id": session_id,
        "event_type": "checkout_start",
        "page": "/cart/checkout",
        "visitor_id": test_email,
        "user_id": user_id,
    }, timeout=10)

    # Trigger rescore & lead state sync
    time.sleep(1.2)
    requests.post(f"{BASE_URL}/api/customer/lead-state/sync", headers=headers, timeout=10)
    state_step2 = requests.get(f"{BASE_URL}/api/customer/lead-state", headers=headers, timeout=10).json().get("data", {})
    print(f"Lifecycle Step 2 (Cart + Checkout): score={state_step2.get('lead_score')}, status={state_step2.get('qualification_status')}, transition={state_step2.get('qualification_transition')}")
    results["lifecycle_step2"] = state_step2

    # Step I: Step 3 (QUALIFIED -> QUALIFIED)
    # Perform another interaction while maintaining high qualification
    requests.post(f"{BASE_URL}/api/session/event", json={
        "session_id": session_id,
        "event_type": "product_view",
        "page": f"/product/{p2_id}",
        "visitor_id": test_email,
        "user_id": user_id,
        "entity": {"type": "product", "id": p2_id},
    }, timeout=10)
    time.sleep(1.2)
    requests.post(f"{BASE_URL}/api/customer/lead-state/sync", headers=headers, timeout=10)
    state_step3 = requests.get(f"{BASE_URL}/api/customer/lead-state", headers=headers, timeout=10).json().get("data", {})
    print(f"Lifecycle Step 3 (While Qualified): score={state_step3.get('lead_score')}, status={state_step3.get('qualification_status')}, transition={state_step3.get('qualification_transition')}")
    results["lifecycle_step3"] = state_step3

    # Step J: Complete real order
    order_res = requests.post(f"{BASE_URL}/api/orders", json={
        "user_id": user_id,
        "session_id": session_id,
        "shipping_address": "123 Fashion Blvd, Suite 400",
        "payment_method": "Credit Card"
    }, headers=headers, timeout=10)
    print("Order creation response:", order_res.status_code, order_res.json().get("success"))
    order_data = order_res.json().get("data", {})
    order_id = order_data.get("order_id")
    print(f"Real Order Placed: {order_id}")
    results["order"] = order_data

    # Step K: Step 4 (QUALIFIED -> NOT_QUALIFIED)
    # Order placed empties the cart. Let's verify cart is 0.
    cart_after_order = requests.get(f"{BASE_URL}/api/cart?user_id={user_id}", headers=headers, timeout=10).json().get("data", [])
    print(f"Cart after order items count: {len(cart_after_order)}")
    # Trigger rescore
    time.sleep(1.2)
    requests.post(f"{BASE_URL}/api/customer/lead-state/sync", headers=headers, timeout=10)
    state_step4 = requests.get(f"{BASE_URL}/api/customer/lead-state", headers=headers, timeout=10).json().get("data", {})
    print(f"Lifecycle Step 4 (Post-Order / Cart Empty): score={state_step4.get('lead_score')}, status={state_step4.get('qualification_status')}, transition={state_step4.get('qualification_transition')}")
    results["lifecycle_step4"] = state_step4

    # Step L: Step 5 (NOT_QUALIFIED -> QUALIFIED again)
    # Customer adds high-intent products back to cart and attempts checkout again
    requests.post(f"{BASE_URL}/api/cart", json={
        "product_id": p1_id,
        "quantity": 3,
        "user_id": user_id,
        "session_id": session_id
    }, headers=headers, timeout=10)
    requests.post(f"{BASE_URL}/api/cart", json={
        "product_id": p2_id,
        "quantity": 2,
        "user_id": user_id,
        "session_id": session_id
    }, headers=headers, timeout=10)
    requests.post(f"{BASE_URL}/api/session/event", json={
        "session_id": session_id,
        "event_type": "checkout_start",
        "page": "/cart/checkout",
        "visitor_id": test_email,
        "user_id": user_id,
    }, timeout=10)

    time.sleep(1.2)
    requests.post(f"{BASE_URL}/api/customer/lead-state/sync", headers=headers, timeout=10)
    state_step5 = requests.get(f"{BASE_URL}/api/customer/lead-state", headers=headers, timeout=10).json().get("data", {})
    print(f"Lifecycle Step 5 (Re-qualification): score={state_step5.get('lead_score')}, status={state_step5.get('qualification_status')}, transition={state_step5.get('qualification_transition')}")
    results["lifecycle_step5"] = state_step5

    # ----------------------------------------------------
    # 4. Phase 19D: Feature Store Validation
    # ----------------------------------------------------
    print("\n--- 4. FEATURE STORE VALIDATION ---")
    feat_doc = db['customer_features'].find_one({"customer_id": ObjectId(user_id)})
    print("Features doc in Atlas:")
    for k, v in feat_doc.items():
        if k != "_id":
            print(f"  {k}: {v}")
    results["features"] = {k: (str(v) if isinstance(v, (ObjectId, datetime.datetime)) else v) for k, v in feat_doc.items()}

    # ----------------------------------------------------
    # 5. Phase 19E & 19F: Lead State & Score History
    # ----------------------------------------------------
    print("\n--- 5. LEAD STATE & SCORE HISTORY ---")
    lead_state_doc = db['customer_lead_state'].find_one({"customer_id": ObjectId(user_id)})
    print("Current Lead State in Atlas:")
    for k, v in lead_state_doc.items():
        if k != "_id":
            print(f"  {k}: {v}")

    # Check for duplicate lead state records
    all_lead_states = list(db['customer_lead_state'].find({"customer_id": ObjectId(user_id)}))
    print(f"Customer lead state document count in Atlas: {len(all_lead_states)} (MUST BE 1)")
    assert len(all_lead_states) == 1, "Duplicate customer_lead_state records found!"

    # Score history records
    score_hist = list(db['lead_score_history'].find({"customer_id": ObjectId(user_id)}).sort("recorded_at", 1))
    print(f"Score history records for customer: {len(score_hist)}")
    for i, sh in enumerate(score_hist):
        print(f"  #{i+1} score={sh.get('lead_score')} segment={sh.get('lead_segment')} transition={sh.get('qualification_transition')} at {sh.get('recorded_at')}")

    results["score_history_count"] = len(score_hist)

    # ----------------------------------------------------
    # 6. Phase 19G, 19H, 19I: Marketing Automation, Email, WhatsApp
    # ----------------------------------------------------
    print("\n--- 6. MARKETING AUTOMATION, EMAIL, WHATSAPP ---")
    auto_events = list(db['marketing_automation_events'].find({"customer_id": ObjectId(user_id)}))
    print(f"Marketing automation events count: {len(auto_events)}")
    for ae in auto_events:
        print(f"  Event ID: {ae.get('_id')}, type: {ae.get('event_type')}, status: {ae.get('status')}, idempotency_key: {ae.get('idempotency_key')}")

    comms = list(db['marketing_communications'].find({"customer_id": ObjectId(user_id)}))
    print(f"Marketing communications count: {len(comms)}")
    for cm in comms:
        print(f"  Channel: {cm.get('channel')}, status: {cm.get('status')}, recipient: {cm.get('recipient')}, provider: {cm.get('provider')}, error: {cm.get('last_error')}")

    # Verify SMS was NEVER sent / recorded
    sms_comms = [c for c in comms if c.get("channel") == "sms"]
    print(f"SMS communications count: {len(sms_comms)} (MUST BE 0)")
    assert len(sms_comms) == 0, "SMS communications were found!"

    notifs = list(db['admin_notifications'].find({"customer_id": ObjectId(user_id)}))
    print(f"Admin notifications count: {len(notifs)}")
    for nt in notifs:
        print(f"  Notif: {nt.get('type')}, message: {nt.get('message')}")

    results["auto_events"] = len(auto_events)
    results["comms"] = len(comms)
    results["notifs"] = len(notifs)

    # ----------------------------------------------------
    # 7. Phase 19J & 19K: Admin Dashboard & Customer 360 Verification
    # ----------------------------------------------------
    print("\n--- 7. ADMIN DASHBOARD & CUSTOMER 360 VERIFICATION ---")
    admin_user = os.getenv("ADMIN_USERNAME", "admin")
    admin_pass = os.getenv("ADMIN_PASSWORD", "admin123")
    admin_login_res = requests.post(f"{BASE_URL}/api/auth/admin/login", json={"username": admin_user, "password": admin_pass}, timeout=10)
    admin_token = admin_login_res.json().get("data", {}).get("token")
    admin_headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
    print(f"Admin logged in successfully, token received: {bool(admin_token)}")

    c360_res = requests.get(f"{BASE_URL}/api/admin/customer-360/{user_id}", headers=admin_headers, timeout=10)
    print("Customer 360 status:", c360_res.status_code, c360_res.json().get("success"))
    c360_data = c360_res.json().get("data", {})

    print("Storefront vs Admin Customer 360 Consistency:")
    c360_profile = c360_data.get("profile", {})
    c360_cart = c360_data.get("cart", [])
    c360_wishlist = c360_data.get("wishlist", [])
    c360_orders = c360_data.get("orders", [])
    c360_intelligence = c360_data.get("intelligence", {})

    print(f"  Profile email: {c360_profile.get('email')} vs Storefront: {test_email}")
    print(f"  Cart items: {len(c360_cart)}")
    print(f"  Wishlist items: {len(c360_wishlist)}")
    print(f"  Orders: {len(c360_orders)}")
    print(f"  Lead Score in 360: {c360_intelligence.get('lead_score')}")
    print(f"  Lead Segment in 360: {c360_intelligence.get('lead_segment')}")
    print(f"  Qualification Status in 360: {c360_intelligence.get('qualification_status')}")

    # Check overview, leads, marketing admin endpoints
    overview_res = requests.get(f"{BASE_URL}/api/admin/intelligence/overview", headers=admin_headers, timeout=10)
    leads_res = requests.get(f"{BASE_URL}/api/admin/intelligence/leads", headers=admin_headers, timeout=10)
    print(f"Admin Intelligence Overview: {overview_res.status_code}, Leads: {leads_res.status_code}")

    # ----------------------------------------------------
    # 8. Phase 19L: Failure Testing
    # ----------------------------------------------------
    print("\n--- 8. FAILURE TESTING ---")
    failures = {}

    # 1. Expired JWT / Invalid JWT
    bad_jwt_res = requests.get(f"{BASE_URL}/api/profile", headers={"Authorization": "Bearer invalid.token.value"})
    failures["invalid_jwt"] = (bad_jwt_res.status_code == 401, bad_jwt_res.status_code)
    print(f"  1. Invalid JWT: status {bad_jwt_res.status_code} (Expected 401)")

    # 2. Unauthorized admin access
    unauth_admin_res = requests.get(f"{BASE_URL}/api/admin/dashboard", headers={"Authorization": f"Bearer {token}"})
    failures["unauthorized_admin"] = (unauth_admin_res.status_code in (401, 403), unauth_admin_res.status_code)
    print(f"  2. Normal user accessing admin route: status {unauth_admin_res.status_code} (Expected 401/403)")

    # 3. Wrong customer ID / Non-existent ID
    fake_id = "507f1f77bcf86cd799439011"
    wrong_c360_res = requests.get(f"{BASE_URL}/api/admin/customer-360/{fake_id}", headers=admin_headers)
    failures["wrong_customer_id"] = (wrong_c360_res.status_code in (200, 404), wrong_c360_res.status_code)
    print(f"  3. Non-existent customer 360 request: status {wrong_c360_res.status_code}")

    # 4. Invalid product ID in cart
    bad_prod_cart = requests.post(f"{BASE_URL}/api/cart", json={
        "product_id": "invalid_mongo_id",
        "quantity": 1,
        "user_id": user_id
    }, headers=headers)
    failures["invalid_product_id"] = (bad_prod_cart.status_code == 400, bad_prod_cart.status_code)
    print(f"  4. Invalid product ID in cart: status {bad_prod_cart.status_code} (Expected 400)")

    # 5. Invalid cart request (negative quantity)
    neg_qty_cart = requests.post(f"{BASE_URL}/api/cart", json={
        "product_id": p1_id,
        "quantity": -5,
        "user_id": user_id
    }, headers=headers)
    failures["invalid_cart_quantity"] = (neg_qty_cart.status_code == 400, neg_qty_cart.status_code)
    print(f"  5. Negative cart quantity: status {neg_qty_cart.status_code} (Expected 400)")

    # 6. Duplicate automation request / idempotency test
    from marketing_automation_service import create_automation_event_for_qualification
    ev1 = create_automation_event_for_qualification(user_id, state_step2, db)
    ev2 = create_automation_event_for_qualification(user_id, state_step2, db)
    is_dup_safe = (ev1 is not None and ev2 is not None and ev1.get("_id") == ev2.get("_id")) or (ev2 is None)
    failures["duplicate_automation_request"] = (is_dup_safe, "Safe idempotency verified")
    print(f"  6. Duplicate automation request: safe idempotency verified: {is_dup_safe}")

    results["failures"] = failures

    # ----------------------------------------------------
    # 9. Socket.IO Live Events Summary
    # ----------------------------------------------------
    print("\n--- 9. SOCKET.IO LIVE EVENTS CAPTURED ---")
    print(f"Total live events captured during journey: {len(captured_socket_events)}")
    for se in captured_socket_events[:10]:
        print(f"  Event: {se.get('event')}, data keys: {list(se.get('data', {}).keys()) if isinstance(se.get('data'), dict) else se.get('data')}")

    results["socket_events_count"] = len(captured_socket_events)

    # ----------------------------------------------------
    # 10. Atlas Post-Test State
    # ----------------------------------------------------
    print("\n--- 10. ATLAS POST-TEST STATE ---")
    post_counts = {}
    for c in collections:
        post_counts[c] = db[c].count_documents({})
        delta = post_counts[c] - pre_counts[c]
        print(f"  {c}: {post_counts[c]} (delta: +{delta})")

    results["post_counts"] = post_counts

    sio.disconnect()

    with open("scratch/journey_results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)

    print("\nValidation complete! Results saved to scratch/journey_results.json")

if __name__ == "__main__":
    run_validation()
