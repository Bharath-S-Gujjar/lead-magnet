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


def get_post_purchase_recommendations(
    products_collection,
    orders_collection,
    user_id=None,
    anonymous_id=None,
    limit_per_anchor=4,
    max_anchors=3,
):
    """Generate post-purchase clothing recommendations.

    Header: "Because you purchased '{Product name}':"
    Excludes already purchased items and ranks by category, brand affinity, and rating.
    """
    if products_collection is None or orders_collection is None:
        return {"has_purchases": False, "anchor_count": 0, "carousels": []}

    # 1. Fetch completed orders
    order_query = []
    if user_id:
        try:
            order_query.append({"user_id": ObjectId(user_id)})
        except Exception:
            pass
        order_query.append({"user_id": str(user_id)})
    if anonymous_id:
        order_query.append({"anonymous_id": str(anonymous_id)})

    if not order_query:
        return {"has_purchases": False, "anchor_count": 0, "carousels": []}

    raw_orders = list(orders_collection.find({"$or": order_query}).sort("created_at", -1))
    from customer_feature_service import is_completed_order
    completed_orders = [o for o in raw_orders if is_completed_order(o)]

    if not completed_orders:
        return {"has_purchases": False, "anchor_count": 0, "carousels": []}

    # 2. Extract all purchased product IDs and anchor items
    purchased_product_ids = set()
    anchor_candidates = []
    seen_anchor_keys = set()

    for order in completed_orders:
        items = order.get("items") or []
        for it in items:
            raw_pid = str(it.get("product_id") or it.get("id") or it.get("_id") or "")
            if raw_pid:
                purchased_product_ids.add(raw_pid)

            cat = str(it.get("category") or "").strip()
            name = str(it.get("name") or it.get("title") or "").strip()
            brand = str(it.get("brand") or "").strip()

            anchor_key = f"{cat}::{name}".lower()
            if anchor_key not in seen_anchor_keys and (cat or name):
                seen_anchor_keys.add(anchor_key)
                anchor_candidates.append({
                    "product_id": raw_pid,
                    "title": name or "Product",
                    "category": cat,
                    "brand": brand,
                })

    if not anchor_candidates:
        return {"has_purchases": False, "anchor_count": 0, "carousels": []}

    carousels = []

    for anchor in anchor_candidates[:max_anchors]:
        anchor_title = anchor["title"]
        anchor_cat = anchor["category"]
        anchor_brand = anchor["brand"]

        # Efficiently fetch matching candidate products directly from MongoDB
        # instead of downloading all 120k+ catalog products
        or_clauses = []
        if anchor_cat:
            or_clauses.append({"category": anchor_cat})
        if anchor_brand:
            or_clauses.append({"brand": anchor_brand})

        cand_query = {"$or": or_clauses} if or_clauses else {}
        candidate_products = list(products_collection.find(cand_query).limit(50))

        if len(candidate_products) < limit_per_anchor:
            extra = list(products_collection.find({}).limit(50))
            candidate_products.extend([p for p in extra if str(p.get("_id")) not in {str(cp.get("_id")) for cp in candidate_products}])

        scored = []
        for prod in candidate_products:
            p_norm = normalize_product_response(prod)
            p_id = str(p_norm.get("product_id") or p_norm.get("id") or "")

            # Exclude already purchased products!
            if p_id in purchased_product_ids or str(prod.get("_id") or "") in purchased_product_ids:
                continue

            p_cat = str(prod.get("category") or "").strip()
            p_brand = str(prod.get("brand") or "").strip()

            score = 0.0
            # Same category boost (strongest link: e.g. bought a Shirt -> other Shirts)
            if anchor_cat and p_cat.casefold() == anchor_cat.casefold():
                score += 15.0

            # Same brand boost
            if anchor_brand and p_brand.casefold() == anchor_brand.casefold():
                score += 8.0

            if score <= 0.0:
                continue

            # Rating boost
            try:
                r_val = float(prod.get("rating") or 4.0)
            except (TypeError, ValueError):
                r_val = 4.0
            score += r_val * 2.0

            # Discount boost
            try:
                disc_val = float(prod.get("discount_percent") or prod.get("discount") or 0.0)
            except (TypeError, ValueError):
                disc_val = 0.0
            score += disc_val / 10.0

            scored.append((score, p_norm))

        scored.sort(key=lambda x: x[0], reverse=True)
        top_recs = [item[1] for item in scored[:limit_per_anchor]]

        if top_recs:
            carousels.append({
                "anchor_product_id": anchor["product_id"],
                "anchor_title": anchor_title,
                "anchor_category": anchor_cat or "Fashion",
                "anchor_brand": anchor_brand or "Top Brand",
                "headline": f"Because you purchased '{anchor_title}':",
                "subtitle": f"Top-rated styles in {anchor_cat or 'Fashion'} recommended for you",
                "recommendations": top_recs,
            })

    return {
        "has_purchases": True,
        "anchor_count": len(carousels),
        "carousels": carousels,
    }


# Backwards compatibility alias
get_netflix_style_recommendations = get_post_purchase_recommendations
