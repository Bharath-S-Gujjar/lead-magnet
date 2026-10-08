"""Product lookup and normalization helper for Myntra-based catalog.

Supports both:
  1. Live Myntra string product IDs (e.g., 'myntra_28420390').
  2. Legacy MongoDB ObjectId values where required by test fixtures or historical data.
"""

from typing import Any, Dict, Optional, Union
from bson import ObjectId


def resolve_product_doc(
    products_collection: Any,
    product_id: Union[str, ObjectId, None]
) -> Optional[Dict[str, Any]]:
    """Resolve a product document from MongoDB products collection.

    Resolution strategy:
      1. If given an ObjectId, queries {"_id": product_id}.
      2. If string starts with 'myntra_', queries {"product_id": pid_str}.
         Falls back to {"source_product_id": source_id}.
      3. Queries {"product_id": pid_str} directly.
      4. If string is a valid 24-hex ObjectId, queries {"_id": ObjectId(pid_str)} (legacy fallback).
      5. Queries {"source_product_id": pid_str}.
      6. Queries {"product_id": f"myntra_{pid_str}"}.
    """
    if product_id is None or products_collection is None:
        return None

    # Handle ObjectId directly
    if isinstance(product_id, ObjectId):
        doc = products_collection.find_one({"_id": product_id})
        if doc:
            return doc
        return products_collection.find_one({"product_id": str(product_id)})

    pid_str = str(product_id).strip()
    if not pid_str:
        return None

    # 1. Myntra ID string lookup
    if pid_str.startswith("myntra_"):
        doc = products_collection.find_one({"product_id": pid_str})
        if doc:
            return doc
        source_id = pid_str.replace("myntra_", "", 1)
        doc = products_collection.find_one({"source_product_id": source_id})
        if doc:
            return doc

    # 2. Direct product_id match
    doc = products_collection.find_one({"product_id": pid_str})
    if doc:
        return doc

    # 3. Legacy ObjectId match (24 hex characters)
    if ObjectId.is_valid(pid_str):
        try:
            doc = products_collection.find_one({"_id": ObjectId(pid_str)})
            if doc:
                return doc
        except Exception:
            pass

    # 4. Source product ID match
    doc = products_collection.find_one({"source_product_id": pid_str})
    if doc:
        return doc

    # 5. Prefixed 'myntra_{pid_str}' match
    if not pid_str.startswith("myntra_"):
        doc = products_collection.find_one({"product_id": f"myntra_{pid_str}"})
        if doc:
            return doc

    return None


def normalize_product_response(item: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a product document for consistent API responses.

    Guarantees all required fields:
      id, product_id, title, name, brand, category, gender, price, mrp,
      price_before_discount, discount_percent, discount_amount, primary_image,
      images, url, rating, stock, availability_status.
    """
    if not isinstance(item, dict):
        return {}

    doc = dict(item)

    # Serialize _id
    raw_oid = doc.get("_id")
    if raw_oid is not None:
        doc["_id"] = str(raw_oid)

    # Stable identifier (stable Myntra product_id prioritized)
    stable_id = str(doc.get("product_id") or doc.get("id") or doc.get("_id") or "")
    doc["id"] = stable_id
    doc["product_id"] = doc.get("product_id") or stable_id

    # Title & Name
    title = str(doc.get("title") or doc.get("name") or "").strip()
    doc["title"] = title
    doc["name"] = title

    # Images
    primary_image = doc.get("primary_image") or doc.get("image")
    raw_images = doc.get("images")
    if isinstance(raw_images, list) and raw_images:
        images = [str(u) for u in raw_images if u]
    elif primary_image:
        images = [str(primary_image)]
    else:
        images = []

    if not primary_image and images:
        primary_image = images[0]

    doc["primary_image"] = primary_image or ""
    doc["image"] = primary_image or ""
    doc["images"] = images

    # Prices
    price = doc.get("price")
    if price is None:
        price = doc.get("current_price")
    try:
        price_num = float(price) if price is not None else 0.0
    except (ValueError, TypeError):
        price_num = 0.0
    doc["price"] = price_num
    doc["current_price"] = price_num

    mrp = doc.get("mrp")
    if mrp is None:
        mrp = doc.get("price_before_discount")
    try:
        mrp_num = float(mrp) if mrp is not None else None
    except (ValueError, TypeError):
        mrp_num = None
    doc["mrp"] = mrp_num
    doc["price_before_discount"] = doc.get("price_before_discount", mrp_num)

    # Discounts
    disc = doc.get("discount_percent")
    if disc is None:
        disc = doc.get("discount")
    try:
        disc_num = float(disc) if disc is not None else 0.0
    except (ValueError, TypeError):
        disc_num = 0.0
    doc["discount_percent"] = disc_num
    doc["discount"] = disc_num

    disc_amount = doc.get("discount_amount")
    if disc_amount is None and mrp_num is not None and mrp_num > price_num:
        disc_amount = round(mrp_num - price_num, 2)
    doc["discount_amount"] = disc_amount

    # Attributes
    doc["brand"] = str(doc.get("brand") or "").strip()
    doc["category"] = str(doc.get("category") or "").strip()
    doc["gender"] = str(doc.get("gender") or "").strip()
    doc["url"] = str(doc.get("url") or "").strip()

    rating = doc.get("rating")
    try:
        rating_num = float(rating) if rating is not None else 4.2
    except (ValueError, TypeError):
        rating_num = 4.2
    doc["rating"] = rating_num

    stock = doc.get("stock")
    try:
        stock_num = int(stock) if stock is not None else 10
    except (ValueError, TypeError):
        stock_num = 10
    doc["stock"] = stock_num

    doc["availability_status"] = str(doc.get("availability_status") or "in_stock").strip()

    return doc
