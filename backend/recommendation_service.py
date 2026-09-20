"""Hybrid Personalized Product Recommendation Engine."""

from bson import ObjectId
from customer_profile_service import get_customer_profile
from cart_service import get_user_cart
from wishlist_service import get_user_wishlist


def get_personalized_recommendations(
    products_collection,
    profiles_collection,
    cart_collection,
    wishlist_collection,
    user_id=None,
    visitor_id=None,
    limit=8
):
    """Return top-N personalized product recommendations.

    Algorithm Strategy:
    1. Retrieve user profile (favorite categories, favorite brands).
    2. Retrieve items in user's active cart and wishlist.
    3. Score products by brand/category affinity + cart co-occurrence.
    4. Fallback to top-rated/popular products if user history is insufficient.
    """
    all_products = list(products_collection.find({}))
    if not all_products:
        return []

    profile = get_customer_profile(profiles_collection, user_id, visitor_id)
    cart_items = get_user_cart(cart_collection, products_collection, user_id, visitor_id) if (user_id or visitor_id) else []
    wishlist_items = get_user_wishlist(wishlist_collection, products_collection, user_id, visitor_id) if (user_id or visitor_id) else []

    fav_categories = (profile.get("favorite_categories") or {}) if profile else {}
    fav_brands = (profile.get("favorite_brands") or {}) if profile else {}

    cart_categories = {item["category"].casefold() for item in cart_items if item.get("category")}
    cart_product_ids = {str(item["product_id"]) for item in cart_items}
    wishlist_product_ids = {str(item["product_id"]) for item in wishlist_items}

    scored_products = []
    for product in all_products:
        p_id = str(product["_id"])
        # Exclude items already in cart or wishlist from pure recommendations
        if p_id in cart_product_ids or p_id in wishlist_product_ids:
            continue

        score = 0.0
        p_category = (product.get("category") or "").casefold()
        p_brand = (product.get("brand") or "").casefold()

        # Category affinity boost
        for cat_name, cat_count in fav_categories.items():
            if cat_name.casefold() == p_category:
                score += cat_count * 3.0

        # Brand affinity boost
        for brand_name, brand_count in fav_brands.items():
            if brand_name.casefold() == p_brand:
                score += brand_count * 2.0

        # Co-occurrence with cart categories
        if p_category in cart_categories:
            score += 5.0

        # Base popularity boost (rating + stock availability + discount)
        score += float(product.get("rating", 4.0))
        if product.get("discount", 0) > 0:
            score += (product.get("discount", 0) / 10.0)

        scored_products.append((score, product))

    # Sort descending by recommendation score
    scored_products.sort(key=lambda x: x[0], reverse=True)
    recommended = [item[1] for item in scored_products[:limit]]

    # If recommendations are fewer than requested limit, fill with remaining popular products
    if len(recommended) < limit:
        recommended_ids = {str(p["_id"]) for p in recommended}
        for product in all_products:
            if str(product["_id"]) not in recommended_ids:
                recommended.append(product)
                if len(recommended) >= limit:
                    break

    return recommended
