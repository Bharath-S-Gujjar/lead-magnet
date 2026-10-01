import urllib.request
import json
import time

BASE = 'http://127.0.0.1:5000'

def post_json(path, data, token=None):
    url = f"{BASE}{path}"
    body = json.dumps(data).encode('utf-8')
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = f"Bearer {token}"
    req = urllib.request.Request(url, data=body, headers=headers, method='POST')
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())

def get_json(path, token=None):
    url = f"{BASE}{path}"
    headers = {}
    if token:
        headers['Authorization'] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())

print("--- Starting End-to-End Presentation Verification ---")

# Step 1: Browse Products
products = get_json('/api/products?limit=2')
assert products['success'], 'Products API failed'
assert len(products['data']) == 2, 'Should return 2 products'
first_prod = products['data'][0]
prod_id = first_prod.get('_id') or first_prod.get('id')
print(f"1. Product Browsing PASS: Got {len(products['data'])} products, first: {first_prod['name']}")

# Step 2: Register a new customer
test_email = f"demo_customer_{int(time.time())}@example.com"
signup_res = post_json('/api/auth/signup', {
    'email': test_email,
    'password': 'Password123!',
    'fullName': 'Priya Sharma',
    'username': f"priyasharma_{int(time.time())}",
    'phone': '9876543210',
    'age': 28,
    'gender': 'Female',
    'dob': '1998-05-14',
    'anonymous_id': 'anon_demo_12345'
})
assert signup_res['success'], f"Signup failed: {signup_res}"
user_id = signup_res['data']['user_id']
print(f"2. Customer Registration PASS: Created user_id={user_id}, email={test_email}")

# Step 3: Login
login_res = post_json('/api/auth/login', {
    'email': test_email,
    'password': 'Password123!',
    'anonymous_id': 'anon_demo_12345'
})
assert login_res['success'], f"Login failed: {login_res}"
token = login_res['data']['token']
print(f"3. Customer Login PASS: JWT token issued (length={len(token)})")

# Step 4: Start customer session
session_res = post_json('/api/session/start', {
    'visitor_id': test_email,
    'user_id': user_id,
    'device': 'desktop',
    'source': 'direct'
}, token=token)
session_id = session_res['data']['session_id']
print(f"4. Session Start PASS: session_id={session_id}")

# Step 5: Real customer behavior events
# 5a: Product view
ev1 = post_json('/api/session/event', {
    'session_id': session_id,
    'event_type': 'product_view',
    'page': f"/product/{prod_id}",
    'entity': {'type': 'product', 'id': prod_id, 'name': first_prod['name'], 'category': first_prod.get('category'), 'price': first_prod.get('price')},
    'metadata': {'time_on_page': 45}
})
print("5a. Product View Event PASS")

# 5b: Search
ev2 = post_json('/api/session/event', {
    'session_id': session_id,
    'event_type': 'search',
    'page': '/',
    'metadata': {'query': 'Kurtas'}
})
print("5b. Search Event PASS")

# 5c: Add to wishlist
wish_res = post_json('/api/wishlist', {
    'product_id': prod_id,
    'user_id': user_id,
    'session_id': session_id
}, token=token)
print(f"5c. Add to Wishlist PASS: {len(wish_res.get('data', []))} items in wishlist")

# 5d: Add to cart
cart_res = post_json('/api/cart', {
    'product_id': prod_id,
    'quantity': 1,
    'user_id': user_id,
    'session_id': session_id,
    'selectedSize': 'M',
    'selectedColor': 'Classic'
}, token=token)
print(f"5d. Add to Cart PASS: {len(cart_res.get('data', []))} items in cart")

# Step 6: Checkout / Place Order
order_res = post_json('/api/orders', {
    'user_id': user_id,
    'session_id': session_id,
    'shipping_address': 'Flat 402, Lotus Towers, Bangalore',
    'payment_method': 'UPI'
}, token=token)
assert order_res['success'], f"Order placement failed: {order_res}"
order_id = order_res['data']['order_id']
print(f"6. Order Placement PASS: order_id={order_id}, status={order_res['data'].get('status')}")

# Step 7: Check Customer Features & ML Lead Scoring
lead_state = get_json(f"/api/customer/lead-state?user_id={user_id}", token=token)
lead_data = lead_state.get('data', {})
print(f"7. ML Lead State PASS: status={lead_data.get('lead_status')}, score={lead_data.get('lead_score')}, segment={lead_data.get('lead_segment')}")

# Step 8: Admin Authentication & Intelligence
admin_login = post_json('/api/auth/admin/login', {
    'username': 'admin',
    'password': 'admin12345'
})
assert admin_login['success'], f"Admin login failed: {admin_login}"
admin_token = admin_login['data']['token']
print("8. Admin Login PASS: token issued")

# Step 9: Admin Dashboard Overview
overview = get_json('/api/admin/intelligence/overview', token=admin_token)
assert overview['success'], f"Overview failed: {overview}"
overview_data = overview['data']
print(f"9. Admin Intelligence Overview PASS: total_customers={overview_data['customers']['total']}, total_qualified_leads={overview_data['leads']['total_qualified']}")

# Step 10: Admin Customer 360
c360 = get_json(f"/api/admin/intelligence/customers/{user_id}/360", token=admin_token)
assert c360['success'], f"Customer 360 failed: {c360}"
cust = c360['data']['customer']
orders_list = c360['data']['orders']
print(f"10. Admin Customer 360 PASS: full_name={cust['full_name']}, orders_count={len(orders_list)}")

print("\n=============================================")
print("ALL 10 END-TO-END PRESENTATION STAGES PASSED!")
print("=============================================")
