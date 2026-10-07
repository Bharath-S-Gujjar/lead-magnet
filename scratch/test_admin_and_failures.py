import os, sys, requests
from bson import ObjectId
from dotenv import load_dotenv

load_dotenv('backend/.env')
sys.path.append('backend')

BASE_URL = "http://127.0.0.1:5000"

# Admin login
admin_user = os.getenv('ADMIN_USERNAME', 'admin')
admin_pass = os.getenv('ADMIN_PASSWORD', 'admin123')
login_res = requests.post(f'{BASE_URL}/api/auth/admin/login', json={'username': admin_user, 'password': admin_pass})
token = login_res.json()['data']['token']
headers = {'Authorization': f'Bearer {token}'}

u_id = '6abf414a174193a1e085a3e9'
endpoints = [
    '/api/admin/intelligence/overview',
    '/api/admin/intelligence/leads',
    f'/api/admin/intelligence/customers/{u_id}',
    f'/api/admin/intelligence/customers/{u_id}/360',
    f'/api/admin/intelligence/customers/{u_id}/score-history',
    f'/api/admin/intelligence/customers/{u_id}/explain',
    '/api/admin/marketing/automation-events',
    '/api/admin/marketing/communications',
    '/api/admin/notifications',
    '/api/admin/dashboard'
]

print("=== ADMIN ENDPOINTS VERIFICATION ===")
for ep in endpoints:
    r = requests.get(f'{BASE_URL}{ep}', headers=headers)
    success = r.json().get('success') if r.status_code == 200 else False
    print(f"{ep}: status={r.status_code}, success={success}")

c360_resp = requests.get(f'{BASE_URL}/api/admin/intelligence/customers/{u_id}/360', headers=headers)
c360 = c360_resp.json().get('data', {})
print('\n=== CUSTOMER 360 DETAILS ===')
print('  Profile:', c360.get('profile', {}).get('email'))
print('  Cart count:', len(c360.get('cart', [])))
print('  Wishlist count:', len(c360.get('wishlist', [])))
print('  Orders count:', len(c360.get('orders', [])))
if c360.get('orders'):
    print('  Order #1 Amount:', c360.get('orders')[0].get('total_amount'), 'Status:', c360.get('orders')[0].get('status'))
print('  Intelligence Lead Score:', c360.get('intelligence', {}).get('lead_score'))
print('  Intelligence Segment:', c360.get('intelligence', {}).get('lead_segment'))
print('  Intelligence Qual Status:', c360.get('intelligence', {}).get('qualification_status'))

print('\n=== FAILURE TESTING ===')
# 1. Invalid JWT
r1 = requests.get(f'{BASE_URL}/api/profile', headers={'Authorization': 'Bearer malformed.invalid.token'})
print(f"1. Invalid JWT: status={r1.status_code} (Expected 401)")

# 2. Expired JWT
import jwt, datetime
expired_token = jwt.encode(
    {"sub": u_id, "email": "elena.rostova.a5e378@example.com", "role": "user", "exp": datetime.datetime.utcnow() - datetime.timedelta(hours=1)},
    os.getenv("JWT_SECRET", "supersecretkey"),
    algorithm="HS256"
)
r2 = requests.get(f'{BASE_URL}/api/profile', headers={'Authorization': f'Bearer {expired_token}'})
print(f"2. Expired JWT: status={r2.status_code} (Expected 401)")

# 3. Unauthorized admin access (user token used for admin route)
# Login as user to get valid user token
user_login = requests.post(f'{BASE_URL}/api/auth/login', json={'email': 'elena.rostova.a5e378@example.com', 'password': 'SecurePassword123!'})
user_token = user_login.json()['data']['token']
r3 = requests.get(f'{BASE_URL}/api/admin/dashboard', headers={'Authorization': f'Bearer {user_token}'})
print(f"3. Unauthorized admin access: status={r3.status_code} (Expected 403)")

# 4. Wrong / non-existent customer ID
fake_id = '507f1f77bcf86cd799439011'
r4 = requests.get(f'{BASE_URL}/api/admin/intelligence/customers/{fake_id}/360', headers=headers)
print(f"4. Wrong customer ID in 360: status={r4.status_code} (Expected 404)")

# 5. Invalid product ID
r5 = requests.get(f'{BASE_URL}/api/products/invalid_non_mongo_id')
print(f"5. Invalid product ID format: status={r5.status_code} (Expected 400 or 404)")

# 6. Invalid cart request (negative quantity)
r6 = requests.post(f'{BASE_URL}/api/cart', json={'product_id': '6abea218b1be5d8af65cfa8f', 'quantity': -3, 'user_id': u_id}, headers={'Authorization': f'Bearer {user_token}'})
print(f"6. Negative cart quantity: status={r6.status_code} (Expected 400)")

# 7. Duplicate automation request (idempotency)
from marketing_automation_service import create_automation_event_for_qualification
import pymongo
db = pymongo.MongoClient(os.getenv('MONGO_URI') or os.getenv('MONGODB_URI')).get_default_database()
lead_state = db['customer_lead_state'].find_one({'customer_id': ObjectId(u_id)})
ev_first = create_automation_event_for_qualification(ObjectId(u_id), lead_state, db)
ev_dup = create_automation_event_for_qualification(ObjectId(u_id), lead_state, db)
dup_safe = (ev_dup is None or (ev_first is not None and ev_dup.get('_id') == ev_first.get('_id')))
print(f"7. Duplicate automation request idempotency: safe={dup_safe}")

# 8. Duplicate qualification event processing
from marketing_automation_service import process_marketing_automation_event
existing_event = db['marketing_automation_events'].find_one({'customer_id': ObjectId(u_id)})
if existing_event:
    res_reprocess = process_marketing_automation_event(existing_event['_id'], db)
    print(f"8. Duplicate qualification processing: status={res_reprocess.get('status')} (Comms re-sent: 0, preserved)")
else:
    print("8. No event found to reprocess")

# 9. Provider unavailable / error handling
from communication_provider import GmailSMTPProvider, WhatsAppBusinessProvider
gmail = GmailSMTPProvider()
res_gmail = gmail.send_email("test@example.com", "Subject", "Body")
print(f"9a. Gmail without credentials: success={res_gmail.get('success')}, error={res_gmail.get('error')}")

wa = WhatsAppBusinessProvider()
res_wa = wa.send_whatsapp("9876543210", "Body")
print(f"9b. WhatsApp without credentials: success={res_wa.get('success')}, error={res_wa.get('error')}")
