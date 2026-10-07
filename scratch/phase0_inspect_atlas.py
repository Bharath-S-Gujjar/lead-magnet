import os
import pymongo
from dotenv import load_dotenv

load_dotenv('backend/.env')
uri = os.getenv('MONGO_URI') or os.getenv('MONGODB_URI')
db_name_env = os.getenv('MONGO_DB_NAME', 'leadmagnet')

client = pymongo.MongoClient(uri, serverSelectionTimeoutMS=10000)
db = client[db_name_env]

print("=== 1. DATABASE INFO ===")
print("Database Name (from config/Atlas):", db.name)
ping_res = client.admin.command('ping')
print("Atlas cluster ping:", ping_res)

print("\n=== 2. ALL COLLECTIONS IN DATABASE ===")
all_collections = sorted(db.list_collection_names())
for c in all_collections:
    count = db[c].count_documents({})
    print(f"  {c}: {count} documents")

print("\n=== 3. REQUESTED & CUSTOMER-SPECIFIC COLLECTIONS ===")
target_collections = [
    'user_profiles', 'sessions', 'events', 'cart', 'carts',
    'wishlist', 'wishlists', 'orders', 'customer_features',
    'customer_lead_state', 'lead_score_history',
    'marketing_automation_events', 'marketing_communications',
    'admin_notifications', 'products', 'leads', 'campaigns',
    'campaign_logs', 'users'
]
for col_name in target_collections:
    if col_name in all_collections:
        count = db[col_name].count_documents({})
        print(f"  [EXISTS] {col_name}: {count} documents")
    else:
        print(f"  [DOES NOT EXIST] {col_name}: 0 documents")

print("\n=== 4. INSPECT USER_PROFILES & ADMIN CHECK ===")
profiles = list(db['user_profiles'].find())
print(f"Total user_profiles count: {len(profiles)}")
admin_profiles = []
for p in profiles:
    is_admin = p.get('role') == 'admin' or p.get('username') == 'admin' or p.get('email') == 'admin'
    if is_admin:
        admin_profiles.append(p)
    print(f"  ID: {p.get('_id')}, role: {p.get('role')}, email: {p.get('email')}, username: {p.get('username')}, visitor_id: {p.get('visitor_id')}, created_at: {p.get('created_at')}")

print(f"\nAdmin profile documents found in user_profiles: {len(admin_profiles)}")

# Check legacy users collection if it exists
if 'users' in all_collections:
    legacy_users = list(db['users'].find())
    print(f"Total legacy users count: {len(legacy_users)}")
    for lu in legacy_users:
        print(f"  Legacy user: ID={lu.get('_id')}, role={lu.get('role')}, email={lu.get('email')}, username={lu.get('username')}")

# Check admin credentials in backend/.env
admin_username_env = os.getenv("ADMIN_USERNAME")
print(f"\nConfigured ADMIN_USERNAME in backend/.env: {admin_username_env}")

print("\n=== 5. PRODUCTS / CATALOG VERIFICATION ===")
prod_count = db['products'].count_documents({})
print(f"Products count: {prod_count}")
sample_prods = list(db['products'].find().limit(3))
for sp in sample_prods:
    print(f"  Sample: ID={sp.get('_id')}, name={sp.get('name')}, brand={sp.get('brand')}, category={sp.get('category')}, price={sp.get('price')}")

print("\nProducts Indexes:")
for idx in db['products'].list_indexes():
    print(f"  {idx.get('name')}: {idx.get('key')}")
