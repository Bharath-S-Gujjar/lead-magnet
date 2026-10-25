import sys, os
sys.path.insert(0, '.')
from dotenv import load_dotenv
load_dotenv('.env', override=True)
import pymongo

client = pymongo.MongoClient(os.environ['MONGO_URI'], serverSelectionTimeoutMS=5000)
db = client[os.environ.get('MONGO_DB_NAME', 'leadmagnet')]

for doc in db['customer_lead_state'].find({}):
    cid = doc.get('customer_id')
    profile = db['user_profiles'].find_one({'_id': cid}, {'full_name': 1, 'email': 1})
    name = profile.get('full_name', '?') if profile else '?'
    email = profile.get('email', '?') if profile else '?'
    seg = doc.get('lead_segment')
    score = doc.get('lead_score')
    status = doc.get('qualification_status')
    reasons = doc.get('score_reasons', [])
    override = doc.get('active_checkout_override', False)
    print(name + ' (' + email + '):')
    print('  segment=' + str(seg) + ', score=' + str(score) + ', status=' + str(status) + ', override=' + str(override))
    for r in reasons:
        print('  - ' + r)
    print()
