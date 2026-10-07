import os
import pymongo
from dotenv import load_dotenv

load_dotenv('backend/.env')
uri = os.getenv('MONGO_URI') or os.getenv('MONGODB_URI')
db_name_env = os.getenv('MONGO_DB_NAME', 'leadmagnet')

client = pymongo.MongoClient(uri, serverSelectionTimeoutMS=10000)
db = client[db_name_env]

print("==================================================")
print("PHASE 0: EXECUTE CUSTOMER/TEST DATA RESET")
print("==================================================")

# Step 1: Pre-deletion verification
print(f"DATABASE NAME: {db.name}")
assert db.name == "leadmagnet", f"CRITICAL ERROR: Database is {db.name}, expected 'leadmagnet'!"

target_collections = [
    'user_profiles',
    'sessions',
    'events',
    'cart',
    'wishlist',
    'orders',
    'customer_features',
    'customer_lead_state',
    'lead_score_history',
    'marketing_automation_events',
    'marketing_communications',
    'admin_notifications',
    'leads'
]

print("\n--- PRE-DELETION COUNTS ---")
before_counts = {}
for col in target_collections:
    count = db[col].count_documents({})
    before_counts[col] = count
    print(f"  {col}: {count} documents")

prod_count_before = db['products'].count_documents({})
print(f"\nPRODUCTS COUNT (BEFORE): {prod_count_before}")
assert prod_count_before == 120466, f"CRITICAL ERROR: Products count is {prod_count_before}, expected 120,466!"

# Capture products indexes before
prod_indexes_before = {idx['name']: idx['key'] for idx in db['products'].list_indexes()}
print(f"PRODUCTS INDEXES COUNT (BEFORE): {len(prod_indexes_before)}")

# Step 2: Perform document deletion (delete_many, NOT drop)
print("\n--- PERFORMING DELETE_MANY ON CUSTOMER/TEST COLLECTIONS ---")
delete_results = {}
for col in target_collections:
    res = db[col].delete_many({})
    delete_results[col] = res.deleted_count
    print(f"  Deleted from {col}: {res.deleted_count} documents")

# Step 3: Post-deletion verification
print("\n--- POST-DELETION VERIFICATION ---")
after_counts = {}
all_zero = True
for col in target_collections:
    count = db[col].count_documents({})
    after_counts[col] = count
    print(f"  {col}: {count} documents (must be 0)")
    if count != 0:
        all_zero = False

assert all_zero, "CRITICAL ERROR: Not all targeted collections have 0 documents!"

prod_count_after = db['products'].count_documents({})
print(f"\nPRODUCTS COUNT (AFTER): {prod_count_after}")
assert prod_count_after == 120466, f"CRITICAL ERROR: Products count changed to {prod_count_after}!"

prod_indexes_after = {idx['name']: idx['key'] for idx in db['products'].list_indexes()}
print(f"PRODUCTS INDEXES COUNT (AFTER): {len(prod_indexes_after)}")
assert prod_indexes_before == prod_indexes_after, "CRITICAL ERROR: Products indexes were altered!"

print("\n--- PRODUCTS INDEXES VERIFIED ---")
for name, key in prod_indexes_after.items():
    print(f"  {name}: {key}")

# Verify database name
assert db.name == "leadmagnet", "CRITICAL ERROR: Database changed!"
print(f"\nDATABASE VERIFIED: {db.name}")

# Verify admin authentication configuration
admin_user = os.getenv("ADMIN_USERNAME")
admin_pass = bool(os.getenv("ADMIN_PASSWORD"))
print(f"ADMIN CONFIGURATION: username='{admin_user}', password_set={admin_pass}")

print("\n==================================================")
print("RESET EXECUTION COMPLETED SUCCESSFULLY WITH ZERO CORRUPTION")
print("==================================================")
