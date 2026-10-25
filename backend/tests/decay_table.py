import sys
sys.path.insert(0, 'backend')
from behavioral_scoring_service import compute_behavioral_score, _decay_factor
from datetime import datetime, timezone, timedelta

def days_ago(d):
    return (datetime.now(timezone.utc) - timedelta(days=d)).isoformat()

def maxed(days_inactive, co_days=None, ca_days=None):
    co_d = co_days if co_days is not None else days_inactive
    ca_d = ca_days if ca_days is not None else days_inactive
    co_ts = days_ago(co_d)
    ca_ts = days_ago(ca_d)
    return compute_behavioral_score({
        'sessions_count': 10, 'total_time_spent': 1500.0,
        'unique_products_viewed': 10, 'products_viewed': 15,
        'search_count': 5, 'days_since_last_activity': days_inactive,
        'cart_item_count': 5, 'cart_value': 999.0, 'wishlist_item_count': 3,
        'checkout_attempts': 5, 'orders_count': 0, 'total_order_value': 0,
        'form_submit_count': 2, 'product_interactions': 20,
        'high_intent_page_visits': 3,
        'last_checkout_action_at': co_ts, 'last_cart_action_at': ca_ts,
        'average_session_duration': 0, 'page_views_count': 0,
    })

print("Maxed customer decay table (new half-lives: co=3d, cart=7d, gen=14d)")
print("{:>6} | {:>5} | {:<10} | {}".format("Days", "Score", "Segment", "Segment reason"))
print("-" * 75)
for d in [0, 1, 3, 7, 14, 30]:
    r = maxed(d)
    print("{:>6} | {:>5} | {:<10} | {}".format(
        d, r["lead_score"], r["lead_segment"], r["segment_reason"] or "-"))

print()
print("Half-lives sanity check:")
for hl_name, hl in [("checkout hl=3d", 3), ("cart hl=7d", 7), ("general hl=14d", 14)]:
    vals = ["  {} at {:>2}d: {:.4f}".format(hl_name, d, _decay_factor(d, hl))
            for d in [1, 3, 7, 14, 30]]
    for v in vals:
        print(v)
    print()
