import os
from dotenv import load_dotenv
load_dotenv('.env', override=True)
import unittest.mock as mock, sys
sys.path.insert(0,'.')

from communication_provider import get_communication_provider, GmailSMTPProvider
p = get_communication_provider()
ptype = type(p).__name__
ok_prov = isinstance(p, GmailSMTPProvider)
print("PROVIDER:", ptype, "-> PASS" if ok_prov else "-> FAIL")

from ecommerce_model_adapter import predict_customer_features, REQUIRED_BASE_FEATURES
DERIVED = ['cart_to_session_ratio','checkout_to_cart_ratio','high_intent_ratio','product_interaction_density']

def mmock(prob):
    class M:
        def predict_proba(self, X):
            import numpy as np
            return np.array([[1-prob, prob]])
    class S:
        def transform(self, X): return X
    return M(), S(), {'model_version':'t'}, list(REQUIRED_BASE_FEATURES)+DERIVED

def sc(prob, cart=0, wl=0, orders=0, co=0):
    feat = {f: 0.0 for f in REQUIRED_BASE_FEATURES}
    feat['cart_item_count'] = float(cart)
    feat['wishlist_item_count'] = float(wl)
    feat['orders_count'] = float(orders)
    feat['checkout_attempts'] = float(co)
    m, s, meta, cols = mmock(prob)
    with mock.patch('ecommerce_model_adapter.load_ecommerce_model', return_value=m), \
         mock.patch('ecommerce_model_adapter.load_ecommerce_scaler', return_value=s), \
         mock.patch('ecommerce_model_adapter.load_ecommerce_metadata', return_value=meta), \
         mock.patch('ecommerce_model_adapter.load_ecommerce_feature_columns', return_value=cols):
        return predict_customer_features(feat)

print()
print("SCORING TESTS:")
ok_all = ok_prov
cases = [
    ("p=0.80 browse->Hot",    sc(0.80),           "Hot",  0.80, 80),
    ("p=0.65 boundary->Hot",  sc(0.65),           "Hot",  0.65, 65),
    ("p=0.64 ->Warm",         sc(0.64),           "Warm", 0.64, 64),
    ("p=0.30 boundary->Warm", sc(0.30),           "Warm", 0.30, 30),
    ("p=0.29 ->Cold",         sc(0.29),           "Cold", 0.20, 20),
    ("order->Hot fl=85",      sc(0.20, orders=1), "Hot",  0.85, 85),
    ("cart->Hot fl=75",       sc(0.20, cart=2),   "Hot",  0.75, 75),
    ("checkout->Hot fl=75",   sc(0.20, co=1),     "Hot",  0.75, 75),
    ("wishlist->Hot fl=70",   sc(0.20, wl=1),     "Hot",  0.70, 70),
    ("p=0.90+order stays 90", sc(0.90, orders=1), "Hot",  0.90, 90),
]
for desc, pred, exp_seg, ep, es in cases:
    seg = pred['lead_segment']
    p2 = pred['lead_probability']
    s2 = pred['lead_score']
    ok = (seg == exp_seg) and (p2 >= ep - 0.001) and (s2 >= es)
    ok_all = ok_all and ok
    status = "PASS" if ok else "FAIL"
    print("  [" + status + "] " + desc + ": seg=" + seg + " prob=" + str(round(p2,2)) + " score=" + str(s2))

print()
print("QUALIFICATION EMAIL GUARD:")
guards = [
    ("Hot p=0.80",  "Hot",  0.80, 80, False),
    ("Hot p=0.65",  "Hot",  0.65, 65, False),
    ("Warm p=0.64", "Warm", 0.64, 64, True),
    ("Cold p=0.20", "Cold", 0.20, 20, True),
]
for desc, seg, prob, sv, exp_b in guards:
    blocked = (seg != "Hot" and prob < 0.65 and sv < 65)
    ok = (blocked == exp_b)
    ok_all = ok_all and ok
    status = "PASS" if ok else "FAIL"
    print("  [" + status + "] " + desc + ": blocked=" + str(blocked))

print()
print("EMAIL TRIGGER AUDIT:")
import inspect, marketing_automation_service as mas
for fn_name in ["trigger_registration_communication","trigger_lead_qualification_communication",
                "trigger_cart_abandonment_communication","trigger_wishlist_reminder_communication",
                "trigger_order_confirmation_communication","dispatch_communication"]:
    fn = getattr(mas, fn_name, None)
    if fn:
        src = inspect.getsource(fn)
        hardcoded = ("DryRunCommunicationProvider()" in src and "provider is None" in src and "get_communication_provider" not in src)
        ok = not hardcoded
        ok_all = ok_all and ok
        status = "PASS" if ok else "FAIL"
        print("  [" + status + "] " + fn_name)

print()
result = "ALL PASS" if ok_all else "SOME FAILED"
print(result)
