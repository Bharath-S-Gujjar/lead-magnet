import os, sys, pymongo, time
from bson import ObjectId
from dotenv import load_dotenv

load_dotenv('backend/.env')
sys.path.append('backend')
from lead_scoring_engine import rescore_customer

db = pymongo.MongoClient(os.getenv('MONGO_URI') or os.getenv('MONGODB_URI')).get_default_database()
u_id = ObjectId('6abf414a174193a1e085a3e9')

print('--- Test QUALIFIED -> QUALIFIED ---')
time.sleep(1.2)
res2 = rescore_customer(u_id, db)
print('Step 3 result transition:', res2.get('qualification_transition'), 'score:', res2.get('lead_score'), 'status:', res2.get('qualification_status'))

auto2 = list(db['marketing_automation_events'].find({'customer_id': u_id}))
print('Marketing automation events count after QUALIFIED->QUALIFIED:', len(auto2))

print('--- Test QUALIFIED -> NOT_QUALIFIED (Clear cart) ---')
db['cart'].delete_many({'user_id': u_id})
time.sleep(1.2)
res3 = rescore_customer(u_id, db)
print('Step 4 result transition:', res3.get('qualification_transition'), 'score:', res3.get('lead_score'), 'status:', res3.get('qualification_status'))

print('--- Test NOT_QUALIFIED -> QUALIFIED again (Add back to cart) ---')
# Insert cart items back
db['cart'].insert_one({
    'user_id': u_id,
    'product_id': ObjectId('6abea218b1be5d8af65cfa8f'), # price 1059
    'quantity': 5
})
time.sleep(1.2)
res4 = rescore_customer(u_id, db)
print('Step 5 result transition:', res4.get('qualification_transition'), 'score:', res4.get('lead_score'), 'status:', res4.get('qualification_status'))

auto3 = list(db['marketing_automation_events'].find({'customer_id': u_id}))
print('Marketing automation events count after requalification (cooldown check):', len(auto3))

hist = list(db['lead_score_history'].find({'customer_id': u_id}))
print('Total score history count now:', len(hist))
for i, h in enumerate(hist):
    print(f"  #{i+1}: score={h.get('lead_score')}, segment={h.get('lead_segment')}, transition={h.get('qualification_transition')}")
