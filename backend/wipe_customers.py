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

# Collections to wipe (customer data only)
# Preserved: products, categories, campaigns, ml models, admin settings
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

total = 0
for col_name in WIPE:
    col = db[col_name]
    before = col.count_documents({})
    col.delete_many({})
    after = col.count_documents({})
    deleted = before - after
    total += deleted
    print(col_name + ': deleted ' + str(deleted) + ' document(s)')

print()
print('Total deleted: ' + str(total))
print('Done. Products, campaigns, and ML models preserved.')
