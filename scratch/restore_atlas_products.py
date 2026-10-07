import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv
import dns.resolver

# Configure public DNS to avoid local router DNS timeouts
try:
    r = dns.resolver.get_default_resolver()
    r.nameservers = ['8.8.8.8', '1.1.1.1'] + r.nameservers
except Exception:
    pass

from pymongo import MongoClient
import certifi

env_path = Path("backend/.env")
if not env_path.exists():
    raise RuntimeError("backend/.env not found")
load_dotenv(dotenv_path=env_path, override=True)

mongo_uri = os.getenv("MONGO_URI")
db_name = os.getenv("MONGO_DB_NAME", "leadmagnet")

print(f"Connecting to Atlas at: {mongo_uri[:25]}... DB: {db_name}")
client = MongoClient(
    mongo_uri,
    tls=True,
    tlsCAFile=certifi.where(),
    serverSelectionTimeoutMS=15000
)
client.admin.command('ping')
print("Successfully connected to MongoDB Atlas.")

db = client[db_name]

catalog_path = Path("data/catalog/cleaned_clothing_catalog.json")
if not catalog_path.exists():
    raise RuntimeError("data/catalog/cleaned_clothing_catalog.json not found")

print("Loading cleaned catalog...", flush=True)
with open(catalog_path, "r", encoding="utf-8") as f:
    incoming_catalog = json.load(f)

source_count = len(incoming_catalog)
print(f"Loaded {source_count} products from local catalog.", flush=True)

# Check current count
current_count = db["products"].count_documents({})
print(f"Current Atlas product count: {current_count}", flush=True)

if current_count < source_count:
    existing_pids = set(d["product_id"] for d in db["products"].find({}, {"product_id": 1}) if "product_id" in d)
    missing = [p for p in incoming_catalog if p["product_id"] not in existing_pids]
    print(f"Found {len(missing)} missing products to insert.", flush=True)
    
    BATCH_SIZE = 5000
    total_inserted = 0
    for i in range(0, len(missing), BATCH_SIZE):
        batch = [dict(doc) for doc in missing[i:i + BATCH_SIZE]]
        res = db["products"].insert_many(batch, ordered=False)
        total_inserted += len(res.inserted_ids)
        print(f"  Inserted batch {i // BATCH_SIZE + 1} ({len(res.inserted_ids)} docs) - Total: {total_inserted}/{len(missing)}", flush=True)

# Create indexes
print("Ensuring indexes on leadmagnet.products...")
indexes = [
    ("product_id_1", [("product_id", 1)], {"unique": True, "sparse": True}),
    ("category_1", [("category", 1)], {}),
    ("gender_1", [("gender", 1)], {}),
    ("brand_1", [("brand", 1)], {}),
    ("name_1", [("name", 1)], {}),
    ("price_1", [("price", 1)], {})
]
existing_indexes = {idx["name"]: idx for idx in db["products"].list_indexes()}
for idx_name, keys, opts in indexes:
    if idx_name not in existing_indexes:
        print(f"Creating index {idx_name}...")
        db["products"].create_index(keys, name=idx_name, background=True, **opts)

final_count = db["products"].count_documents({})
print(f"\nFinal Atlas Products Count: {final_count} (Expected: {source_count})")
print("Done!")
