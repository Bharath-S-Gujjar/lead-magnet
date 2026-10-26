import os, sys
sys.path.insert(0, '.')
from pathlib import Path
from dotenv import load_dotenv
env_path = Path(__file__).resolve().parent / '.env'
load_dotenv(env_path, override=True)
import pymongo

mongo_uri = os.environ.get('MONGO_URI', 'mongodb://localhost:27017')
client = pymongo.MongoClient(mongo_uri, serverSelectionTimeoutMS=8000)
db = client[os.environ.get('MONGO_DB_NAME', 'leadmagnet')]

# Collections to wipe (customer data and event activity only)
# Preserved: products, myntra_products, campaigns, catalog_sync_metadata
WIPE = [
    'user_profiles',
    'users',
    'orders',
    'cart',
    'wishlist',
    'events',
    'sessions',
    'leads',
    'customer_features',
    'customer_lead_state',
    'lead_score_history',
    'marketing_communications',
    'marketing_automation_events',
    'marketing_opportunities',
    'admin_notifications',
    'whatsapp_webhook_events',
]

# Old migration backup/test collections to drop for clean production DB
DROP_LEGACY = [
    'admin_notifications_backup_20261013_170331',
    'customer_features_backup_20261013_170331',
    'customer_lead_state_backup_20261013_170331',
    'leads_backup_20261013_170331',
    'marketing_automation_events_backup_20261013_170331',
    'marketing_communications_backup_20261013_170331',
    'user_profiles_backup_20261013_170331',
    'products_unit_test',
    'test_myntra_cart_migration',
    'test_myntra_orders_migration',
    'test_myntra_products_migration',
    'test_myntra_wishlist_migration',
]

total = 0
for col_name in WIPE:
    col = db[col_name]
    before = col.count_documents({})
    col.delete_many({})
    after = col.count_documents({})
    deleted = before - after
    total += deleted
    print(f"{col_name}: deleted {deleted} document(s) (now {after})")

print("\nCleaning legacy backup & test collections...")
for col_name in DROP_LEGACY:
    if col_name in db.list_collection_names():
        count = db[col_name].count_documents({})
        db.drop_collection(col_name)
        print(f"Dropped legacy collection {col_name} (removed {count} documents)")

print()
print('Total deleted from active customer collections: ' + str(total))
print('Done. Products, campaigns, and catalog metadata preserved.')

