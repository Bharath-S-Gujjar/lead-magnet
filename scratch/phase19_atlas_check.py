import os
import pymongo
from dotenv import load_dotenv

load_dotenv('backend/.env')
uri = os.getenv('MONGO_URI') or os.getenv('MONGODB_URI')
client = pymongo.MongoClient(uri, serverSelectionTimeoutMS=10000)
db = client.get_default_database()

print("DATABASE_NAME:", db.name)
collections = [
    'products', 'user_profiles', 'sessions', 'events', 'orders',
    'customer_features', 'customer_lead_state', 'lead_score_history',
    'marketing_automation_events', 'marketing_communications', 'admin_notifications'
]
for coll in collections:
    count = db[coll].count_documents({})
    print(f"{coll}: {count}")

print("\nPRODUCTS_INDEXES:")
for idx in db['products'].list_indexes():
    print(f"  name: {idx.get('name')}, key: {idx.get('key')}")

print("\nUSERS_SAMPLE:")
for u in db['user_profiles'].find().limit(5):
    print(" ", u.get('user_id'), u.get('email'), u.get('created_at'))

print("\nORDERS_SAMPLE:")
for o in db['orders'].find().limit(5):
    print(" ", o.get('order_id'), o.get('user_id'), o.get('created_at'))
