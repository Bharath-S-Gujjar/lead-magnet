import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv
from pymongo import MongoClient
import certifi
from bson import ObjectId

# 1. Load backend .env for Atlas credentials
env_path = Path("backend/.env")
if not env_path.exists():
    raise RuntimeError("backend/.env not found")
load_dotenv(dotenv_path=env_path, override=True)

mongo_uri = os.getenv("MONGO_URI")
db_name = os.getenv("MONGO_DB_NAME", "leadmagnet")

if not mongo_uri:
    raise RuntimeError("MONGO_URI not configured in backend/.env")

print(f"Connecting to MongoDB Atlas at URI: {mongo_uri[:25]}... DB: {db_name}")
client = MongoClient(
    mongo_uri,
    tls=True,
    tlsCAFile=certifi.where(),
    serverSelectionTimeoutMS=10000
)
client.admin.command('ping')
print("Successfully connected and pinged MongoDB Atlas.")

db = client[db_name]

# Safety collections to check
CUSTOMER_ACTIVITY_COLLECTIONS = [
    "user_profiles",
    "sessions",
    "events",
    "orders",
    "customer_features",
    "customer_lead_state",
    "lead_score_history",
    "marketing_automation_events",
    "marketing_communications",
    "admin_notifications",
    "leads",
    "users"
]

def get_collection_counts():
    counts = {}
    for c_name in CUSTOMER_ACTIVITY_COLLECTIONS:
        counts[c_name] = db[c_name].count_documents({})
    counts["products"] = db["products"].count_documents({})
    return counts

# Step 1: Initial Collection Counts Check
counts_before = get_collection_counts()
print("\n--- Current Atlas Collection Counts ---")
for k, v in counts_before.items():
    print(f"  {k}: {v}")

# Verify customer collections are clean
for c in ["user_profiles", "sessions", "events", "orders", "customer_features", "customer_lead_state", "lead_score_history", "marketing_automation_events", "marketing_communications", "admin_notifications", "users"]:
    if counts_before[c] != 0:
        raise RuntimeError(f"Safety violation: {c} is expected to be 0, but found {counts_before[c]}")

# Step 2: Load local cleaned catalog
catalog_path = Path("data/catalog/cleaned_clothing_catalog.json")
if not catalog_path.exists():
    raise RuntimeError("data/catalog/cleaned_clothing_catalog.json not found")

with open(catalog_path, "r", encoding="utf-8") as f:
    incoming_catalog = json.load(f)

source_count = len(incoming_catalog)
print(f"\nLoaded {source_count} products from local catalog.")
local_lookup = {p["product_id"]: p for p in incoming_catalog}

# Step 3: Read existing product_ids from Atlas
print("\nReading existing product_id values from Atlas leadmagnet.products...")
existing_docs = list(db["products"].find({}, {"product_id": 1, "name": 1, "brand": 1, "gender": 1}))
existing_pids = set(d.get("product_id") for d in existing_docs if d.get("product_id"))
existing_count = len(existing_pids)
missing_count = source_count - existing_count

print(f"\nSOURCE_COUNT: {source_count}")
print(f"EXISTING_COUNT: {existing_count}")
print(f"MISSING_COUNT: {missing_count}")

# Safety validations
if existing_count > source_count:
    raise RuntimeError(f"Aborting: existing_count ({existing_count}) > source_count ({source_count})")

# Check that existing IDs all belong to cleaned catalog
foreign_pids = existing_pids - set(local_lookup.keys())
if foreign_pids:
    raise RuntimeError(f"Aborting: Found {len(foreign_pids)} foreign product IDs in Atlas that do not belong to the cleaned catalog! Sample: {list(foreign_pids)[:5]}")

print("Verification passed: All existing product IDs match the cleaned catalog.")

# Check representative sample of existing records
print("\nVerifying representative existing records against cleaned catalog...")
sample_check_errors = []
for doc in existing_docs[:50]:
    pid = doc["product_id"]
    local_p = local_lookup[pid]
    if doc.get("name") != local_p.get("name") or doc.get("brand") != local_p.get("brand"):
        sample_check_errors.append(f"Mismatch for {pid}: db={doc} vs local={local_p}")

if sample_check_errors:
    raise RuntimeError(f"Representative schema check failed: {sample_check_errors[:3]}")

print("Representative existing records match the cleaned catalog perfectly.")

# Step 4: Filter missing products
missing_products = [p for p in incoming_catalog if p["product_id"] not in existing_pids]
if len(missing_products) != missing_count:
    raise RuntimeError(f"Mismatch: filtered missing products count ({len(missing_products)}) != calculated missing count ({missing_count})")

print(f"\nPrepared {len(missing_products)} missing products for batch insertion.")

# Step 5: Duplicate-safe Batch Insertion
BATCH_SIZE = 5000
total_inserted_this_run = 0

if missing_products:
    for i in range(0, len(missing_products), BATCH_SIZE):
        batch = missing_products[i:i + BATCH_SIZE]
        batch_docs = [dict(doc) for doc in batch]
        res = db["products"].insert_many(batch_docs, ordered=False)
        total_inserted_this_run += len(res.inserted_ids)
        current_db_count = db["products"].count_documents({})
        print(f"  Inserted batch {i // BATCH_SIZE + 1} ({len(res.inserted_ids)} docs) - Run Inserted: {total_inserted_this_run} - Atlas Total: {current_db_count}/{source_count}")
else:
    print("No missing products to insert.")

# Step 6: Create / Verify Product Indexes
print("\nEvaluating and verifying product indexes on leadmagnet.products...")
existing_indexes = {idx["name"]: idx for idx in db["products"].list_indexes()}
print("Current index names:", list(existing_indexes.keys()))

required_indexes = [
    ("product_id_1", [("product_id", 1)], {"unique": True}),
    ("category_1", [("category", 1)], {}),
    ("gender_1", [("gender", 1)], {}),
    ("brand_1", [("brand", 1)], {}),
    ("name_1", [("name", 1)], {}),
    ("price_1", [("price", 1)], {})
]

for idx_name, keys, opts in required_indexes:
    if idx_name not in existing_indexes:
        print(f"Creating index {idx_name} on {keys} (opts: {opts})...")
        db["products"].create_index(keys, name=idx_name, background=True, **opts)
    else:
        print(f"Index {idx_name} already exists.")

final_indexes = list(db["products"].list_indexes())
print(f"Final indexes count: {len(final_indexes)}")
for idx in final_indexes:
    print(f"  {idx['name']}: {idx.get('key')} (unique: {idx.get('unique', False)})")

# Step 7: Post-Replacement Verifications
print("\n--- Post-Replacement Verifications ---")
final_product_count = db["products"].count_documents({})
print(f"Total products in Atlas: {final_product_count} (Expected: 120466)")
if final_product_count != 120466:
    raise RuntimeError(f"Final product count {final_product_count} != 120466")

unique_pids_final = len(db["products"].distinct("product_id"))
print(f"Unique product_id count in Atlas: {unique_pids_final} (Expected: 120466)")
if unique_pids_final != 120466:
    raise RuntimeError(f"Unique product IDs {unique_pids_final} != 120466")

gender_counts = {
    "Men": db["products"].count_documents({"gender": "Men"}),
    "Women": db["products"].count_documents({"gender": "Women"}),
    "Kids": db["products"].count_documents({"gender": "Kids"}),
}
print("Gender distribution in Atlas:", gender_counts)
if gender_counts["Men"] <= 0 or gender_counts["Women"] <= 0 or gender_counts["Kids"] <= 0:
    raise RuntimeError("Gender counts invalid: All genders must be > 0")

counts_after = get_collection_counts()
print("\nVerifying customer/activity collection counts before vs after:")
for c_name in CUSTOMER_ACTIVITY_COLLECTIONS:
    b = counts_before[c_name]
    a = counts_after[c_name]
    print(f"  {c_name}: Before={b}, After={a} [{'MATCH' if b == a else 'MISMATCH'}]")
    if b != a:
        raise RuntimeError(f"Safety violation: {c_name} count changed from {b} to {a}!")

# Step 8: Validate 20 Random Products from Atlas against local catalog
print("\nSampling 20 random products from Atlas and validating against local source...")
sample_docs = list(db["products"].aggregate([{"$sample": {"size": 20}}]))
sample_validations = []

for sample in sample_docs:
    pid = sample["product_id"]
    local_p = local_lookup.get(pid)
    if not local_p:
        raise RuntimeError(f"Sample {pid} not found in local catalog!")
    
    mismatches = []
    for field in ["name", "brand", "gender", "category", "price", "price_inr", "discount", "discount_percent", "rating", "verified_buyers"]:
        s_val = sample.get(field)
        l_val = local_p.get(field)
        if s_val != l_val:
            mismatches.append(f"{field}: atlas={s_val} vs local={l_val}")
            
    res_entry = {
        "product_id": pid,
        "name": sample.get("name"),
        "brand": sample.get("brand"),
        "gender": sample.get("gender"),
        "category": sample.get("category"),
        "price": sample.get("price"),
        "discount": sample.get("discount"),
        "rating": sample.get("rating"),
        "verified_buyers": sample.get("verified_buyers"),
        "status": "PASS" if not mismatches else f"FAIL: {mismatches}"
    }
    sample_validations.append(res_entry)
    print(f"  [{res_entry['status']}] {pid} | {res_entry['gender']} | {res_entry['brand']} - {res_entry['name']} | Price: {res_entry['price']} | Rating: {res_entry['rating']}")

# Step 9: Save operation summary for documentation
operation_summary = {
    "source_count": source_count,
    "existing_count_before_resume": existing_count,
    "missing_count_inserted": total_inserted_this_run,
    "final_total_products": final_product_count,
    "unique_product_ids": unique_pids_final,
    "gender_counts": gender_counts,
    "counts_before": counts_before,
    "counts_after": counts_after,
    "indexes": [{"name": idx["name"], "key": dict(idx["key"]), "unique": idx.get("unique", False)} for idx in final_indexes],
    "sample_validations": sample_validations
}

with open("data/catalog/resume_operation_summary.json", "w", encoding="utf-8") as f:
    json.dump(operation_summary, f, indent=2)

print("\nOperation summary saved to data/catalog/resume_operation_summary.json")
print("Resume import finished successfully!")
