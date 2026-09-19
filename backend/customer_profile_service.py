import datetime
from collections import Counter
from bson import ObjectId

HIGH_INTENT_EVENTS = {
    'product_view': 3,
    'add_to_cart': 10,
    'wishlist_add': 6,
    'form_open': 8,
    'form_submit': 15,
    'purchase': 25,
    'order_placed': 25
}

BASE_EVENT_WEIGHTS = {
    'page_view': 1,
    'search': 2,
    'click': 2,
    'scroll': 1
}


def build_profile_update(session_doc, events):
    category_counter = Counter()
    brand_counter = Counter()

    engagement_score = 0

    page_views = 0
    product_views = 0
    cart_adds = 0
    wishlist_adds = 0
    form_submits = 0

    for event in events:
        event_type = event.get('event_type')

        engagement_score += BASE_EVENT_WEIGHTS.get(event_type, 0)
        engagement_score += HIGH_INTENT_EVENTS.get(event_type, 0)

        if event_type == 'page_view':
            page_views += 1

        if event_type == 'product_view':
            product_views += 1

        if event_type == 'add_to_cart':
            cart_adds += 1

        if event_type == 'wishlist_add':
            wishlist_adds += 1

        if event_type == 'form_submit':
            form_submits += 1

        entity = event.get('entity') or {}

        category = entity.get('category')
        if category:
            category_counter[category] += 1

        brand = entity.get('brand')
        if brand:
            brand_counter[brand] += 1

    return {
        'visitor_id': session_doc.get('visitor_id'),
        'user_id': session_doc.get('user_id'),
        'last_active_at': session_doc.get('last_active_at'),
        'updated_at': datetime.datetime.utcnow(),

        'session_increment': 1,
        'page_view_increment': page_views,
        'product_view_increment': product_views,
        'cart_add_increment': cart_adds,
        'wishlist_add_increment': wishlist_adds,
        'form_submit_increment': form_submits,

        'engagement_increment': engagement_score,

        'favorite_categories_increment': dict(category_counter),
        'favorite_brands_increment': dict(brand_counter)
    }

def apply_profile_update(profiles_collection, profile_update):
    visitor_id = profile_update.get('visitor_id')
    user_id = profile_update.get('user_id')

    if not visitor_id and not user_id:
        raise ValueError('visitor_id or user_id required for profile update')

    inc_doc = {
        'session_count': profile_update.get('session_increment', 0),
        'page_view_count': profile_update.get('page_view_increment', 0),
        'product_view_count': profile_update.get('product_view_increment', 0),
        'cart_add_count': profile_update.get('cart_add_increment', 0),
        'wishlist_add_count': profile_update.get('wishlist_add_increment', 0),
        'form_submit_count': profile_update.get('form_submit_increment', 0),
        'engagement_score': profile_update.get('engagement_increment', 0)
    }

    category_inc = {
        f'favorite_categories.{k}': v
        for k, v in profile_update.get('favorite_categories_increment', {}).items()
    }

    brand_inc = {
        f'favorite_brands.{k}': v
        for k, v in profile_update.get('favorite_brands_increment', {}).items()
    }

    inc_doc.update(category_inc)
    inc_doc.update(brand_inc)

    set_doc = {
        'last_active_at': profile_update.get('last_active_at'),
        'updated_at': profile_update.get('updated_at')
    }

    if user_id is not None:
        set_doc['user_id'] = user_id

    identity_query = {'user_id': user_id} if user_id is not None else {'visitor_id': visitor_id}
    set_on_insert = {'created_at': datetime.datetime.utcnow()}
    if visitor_id:
        set_on_insert['visitor_id'] = visitor_id

    profiles_collection.update_one(
        identity_query,
        {
            '$set': set_doc,
            '$inc': inc_doc,
            '$setOnInsert': set_on_insert,
        },
        upsert=True
    )


def get_customer_profile(profiles_collection, user_id=None, visitor_id=None):
    """Retrieve unified customer profile by user_id or visitor_id."""
    if not user_id and not visitor_id:
        return None

    if user_id:
        queries = [{"user_id": str(user_id)}]
        try:
            queries.append({"_id": ObjectId(user_id)})
        except Exception:
            pass
        profile = profiles_collection.find_one({"$or": queries})
        if profile:
            return profile

    if visitor_id:
        profile = profiles_collection.find_one({"$or": [{"visitor_id": str(visitor_id)}, {"anonymous_id": str(visitor_id)}]})
        if profile:
            return profile

    return None
