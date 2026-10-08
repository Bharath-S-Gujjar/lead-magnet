"""Hybrid Personalized Product Recommendation Engine for Myntra catalog."""

from bson import ObjectId
from customer_profile_service import get_customer_profile
from cart_service import get_user_cart
from wishlist_service import get_user_wishlist
from product_lookup import normalize_product_response


def get_personalized_recommendations(
    products_collection,
    profiles_collection,
    cart_collection,
    wishlist_collection,
    user_id=None,
    visitor_id=None,
    limit=8
):
    """Return top-N personalized product recommendations from Myntra catalog.

    Algorithm Strategy:
    1. Retrieve user profile (favorite categories, favorite brands).
    2. Retrieve items in user's active cart and wishlist.
    3. Score products by brand/category affinity + cart co-occurrence.
    4. Fallback to top-rated/popular products if user history is insufficient.
    5. Return normalized product payloads.
    """
    if products_collection is None:
        return []

    all_products = list(products_collection.find({}))
    if not all_products:
        return []

    profile = get_customer_profile(profiles_collection, user_id, visitor_id)
    cart_items = get_user_cart(cart_collection, products_collection, user_id, visitor_id) if (user_id or visitor_id) else []
    wishlist_items = get_user_wishlist(wishlist_collection, products_collection, user_id, visitor_id) if (user_id or visitor_id) else []

    fav_categories = (profile.get("favorite_categories") or {}) if profile else {}
    fav_brands = (profile.get("favorite_brands") or {}) if profile else {}

    cart_categories = {str(item["category"]).casefold() for item in cart_items if item.get("category")}
    cart_product_ids = {str(item["product_id"]) for item in cart_items if item.get("product_id")}
    wishlist_product_ids = {str(item["product_id"]) for item in wishlist_items if item.get("product_id")}

    scored_products = []
    for product in all_products:
        canonical_pid = str(product.get("product_id") or product.get("_id") or "")
        oid_str = str(product.get("_id") or "")

        # Exclude items already in cart or wishlist from recommendations
        if canonical_pid in cart_product_ids or canonical_pid in wishlist_product_ids:
            continue
        if oid_str in cart_product_ids or oid_str in wishlist_product_ids:
            continue

        score = 0.0
        p_category = str(product.get("category") or "").casefold()
        p_brand = str(product.get("brand") or "").casefold()

        # Category affinity boost
        for cat_name, cat_count in fav_categories.items():
            if str(cat_name).casefold() == p_category:
                score += float(cat_count) * 3.0

        # Brand affinity boost
        for brand_name, brand_count in fav_brands.items():
            if str(brand_name).casefold() == p_brand:
                score += float(brand_count) * 2.0

        # Co-occurrence with cart categories
        if p_category in cart_categories:
            score += 5.0

        # Base popularity boost (rating + discount)
        try:
            rating_val = float(product.get("rating") or 4.0)
        except (ValueError, TypeError):
            rating_val = 4.0
        score += rating_val

        disc = product.get("discount_percent")
        if disc is None:
            disc = product.get("discount", 0)
        try:
            disc_val = float(disc or 0)
        except (ValueError, TypeError):
            disc_val = 0.0
        if disc_val > 0:
            score += (disc_val / 10.0)

        scored_products.append((score, product))

    # Sort descending by recommendation score
    scored_products.sort(key=lambda x: x[0], reverse=True)
    recommended = [normalize_product_response(item[1]) for item in scored_products[:limit]]

    # If recommendations are fewer than requested limit, fill with remaining products
    if len(recommended) < limit:
        recommended_ids = {str(p.get("product_id") or p.get("id")) for p in recommended}
        for product in all_products:
            p_norm = normalize_product_response(product)
            pid = str(p_norm.get("product_id") or p_norm.get("id"))
            if pid not in recommended_ids:
                recommended.append(p_norm)
                recommended_ids.add(pid)
                if len(recommended) >= limit:
                    break

    return recommended
