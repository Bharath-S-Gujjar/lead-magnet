"""ReefAPI client for live Myntra clothing product catalog.

Provides search and detail endpoints with normalization into Lead Magnet's
internal product schema. Adheres to credit safety and secure key handling.
"""

from __future__ import annotations

import datetime
import os
from typing import Any, Dict, List, Optional, Tuple, Union

import requests
from dotenv import load_dotenv

REEF_API_BASE_URL = "https://api.reefapi.com"
MYNTRA_SEARCH_ENDPOINT = "/myntra/v1/search"
MYNTRA_DETAIL_ENDPOINT = "/myntra/v1/product/detail"


class ReefAPIError(Exception):
    """Base exception for all ReefAPI client operations."""
    pass


class ReefAPIConfigError(ReefAPIError):
    """Raised when configuration such as REEF_API_KEY is missing or invalid."""
    pass


class ReefAPIResponseError(ReefAPIError):
    """Raised when ReefAPI returns an error response, non-2xx status, or ok=false."""
    pass


class ReefAPITimeoutError(ReefAPIError):
    """Raised when a request to ReefAPI times out."""
    pass


class ReefAPIConnectionError(ReefAPIError):
    """Raised when network connection to ReefAPI fails."""
    pass


def _load_env_if_needed() -> None:
    """Ensure environment variables are loaded from backend/.env if not present."""
    if not os.getenv("REEF_API_KEY"):
        backend_dir = os.path.dirname(os.path.abspath(__file__))
        env_path = os.path.join(backend_dir, ".env")
        if os.path.exists(env_path):
            load_dotenv(dotenv_path=env_path, override=False)
        else:
            load_dotenv(override=False)


def _sanitize_message(message: str, secret: Optional[str]) -> str:
    """Scrub secret credentials from error messages and log outputs."""
    if secret and secret in message:
        return message.replace(secret, "[REDACTED]")
    return message


def _parse_numeric(val: Any) -> Optional[Union[int, float]]:
    """Safely parse numbers without inventing values."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return val
    if isinstance(val, str):
        cleaned = val.replace(",", "").strip()
        if not cleaned:
            return None
        try:
            if "." in cleaned:
                return float(cleaned)
            return int(cleaned)
        except ValueError:
            return None
    return None


def extract_images(raw_data: dict) -> Tuple[Optional[str], List[str]]:
    """Extract and deduplicate product images in original order.

    Preserves the full images array and selects the first valid image as
    the primary image.
    """
    images: List[str] = []
    seen = set()

    def _add_url(u: Any) -> None:
        if not u or not isinstance(u, str):
            return
        cleaned = u.strip()
        if not cleaned:
            return
        if cleaned.startswith("//"):
            cleaned = f"https:{cleaned}"
        if cleaned not in seen:
            seen.add(cleaned)
            images.append(cleaned)

    # 1. Process images array if present
    raw_images = raw_data.get("images")
    if isinstance(raw_images, list):
        for item in raw_images:
            if isinstance(item, str):
                _add_url(item)
            elif isinstance(item, dict):
                for key in ("src", "url", "image", "secure_url"):
                    val = item.get(key)
                    if isinstance(val, str):
                        _add_url(val)
                        break

    # 2. Check single image fields
    for single_key in ("image", "primary_image", "img", "thumbnail", "photo"):
        single_val = raw_data.get(single_key)
        if isinstance(single_val, str):
            _add_url(single_val)

    primary_image = images[0] if images else None
    return primary_image, images


def normalize_myntra_product(raw_data: dict, is_detail: bool = False) -> Dict[str, Any]:
    """Normalize a raw Myntra product dict from search or detail into our internal structure.

    Guarantees all required fields:
      product_id, title, brand, category, gender, url, primary_image, images,
      price, mrp, price_before_discount, discount_amount, discount_percent,
      currency, rating, stock, availability_status, source, source_product_id,
      fetched_at.
    """
    if not isinstance(raw_data, dict):
        raw_data = {}

    # Product identifiers
    raw_id = raw_data.get("product_id") or raw_data.get("id") or raw_data.get("style_id") or ""
    source_product_id = str(raw_id).strip()
    product_id = f"myntra_{source_product_id}" if source_product_id else ""

    # Descriptive fields
    title = str(raw_data.get("title") or raw_data.get("name") or "").strip()
    brand = str(raw_data.get("brand") or "").strip()
    category = str(
        raw_data.get("category")
        or raw_data.get("sub_category")
        or raw_data.get("subCategory")
        or raw_data.get("articleType")
        or raw_data.get("master_category")
        or raw_data.get("masterCategory")
        or ""
    ).strip()
    gender = str(raw_data.get("gender") or raw_data.get("genderType") or "").strip()

    # URL
    url = str(raw_data.get("url") or "").strip()
    if url and not url.startswith("http://") and not url.startswith("https://"):
        url = f"https://www.myntra.com/{url.lstrip('/')}"

    # Images
    primary_image, images = extract_images(raw_data)

    # Prices and discounts (preserve exactly from ReefAPI, never calculate/invent)
    price = _parse_numeric(raw_data.get("price"))
    mrp = _parse_numeric(raw_data.get("mrp"))
    price_before_discount = _parse_numeric(raw_data.get("price_before_discount"))
    discount_amount = _parse_numeric(raw_data.get("discount_amount"))
    discount_percent = _parse_numeric(raw_data.get("discount_percent"))
    currency = str(raw_data.get("currency") or "INR").strip()

    # Rating
    rating = _parse_numeric(raw_data.get("rating"))

    # Stock & Availability
    stock = _parse_numeric(raw_data.get("stock"))
    if stock is None:
        featured_sku = raw_data.get("featured_sku")
        if isinstance(featured_sku, dict) and "stock" in featured_sku:
            stock = _parse_numeric(featured_sku.get("stock"))

    raw_avail = raw_data.get("availability") or raw_data.get("availability_status")
    if raw_avail:
        availability_status = str(raw_avail).lower().strip()
    else:
        featured_sku = raw_data.get("featured_sku")
        if isinstance(featured_sku, dict) and featured_sku.get("available") is False:
            availability_status = "out_of_stock"
        elif stock is not None and stock <= 0:
            availability_status = "out_of_stock"
        else:
            availability_status = "in_stock"

    stock_val = int(stock) if stock is not None else None

    # Timestamp
    fetched_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

    return {
        "product_id": product_id,
        "title": title,
        "brand": brand,
        "category": category,
        "gender": gender,
        "url": url,
        "primary_image": primary_image,
        "images": images,
        "price": price,
        "mrp": mrp,
        "price_before_discount": price_before_discount,
        "discount_amount": discount_amount,
        "discount_percent": discount_percent,
        "currency": currency,
        "rating": rating,
        "stock": stock_val,
        "availability_status": availability_status,
        "source": "myntra",
        "source_product_id": source_product_id,
        "fetched_at": fetched_at,
    }


class ReefAPIClient:
    """Client for ReefAPI Myntra live endpoints.

    Designed for credit preservation, explicit error handling, and zero key leakage.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = REEF_API_BASE_URL,
        timeout: float = 30.0,
    ) -> None:
        _load_env_if_needed()
        key = api_key or os.getenv("REEF_API_KEY")
        if not key or not str(key).strip():
            raise ReefAPIConfigError(
                "ReefAPI key is missing. Set REEF_API_KEY in backend/.env or pass api_key."
            )

        self._api_key = str(key).strip()
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def __repr__(self) -> str:
        # Never expose API key in repr
        return f"<ReefAPIClient base_url={self.base_url!r}>"

    def _post(self, endpoint: str, payload: dict) -> dict:
        """Execute a POST request against ReefAPI with error masking and credit safety."""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self._api_key,
        }

        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=self.timeout)
        except requests.exceptions.Timeout as exc:
            raise ReefAPITimeoutError("ReefAPI request timed out") from exc
        except requests.exceptions.ConnectionError as exc:
            raise ReefAPIConnectionError("Failed to connect to ReefAPI service") from exc
        except requests.exceptions.RequestException as exc:
            clean_msg = _sanitize_message(str(exc), self._api_key)
            raise ReefAPIError(f"ReefAPI request failed: {clean_msg}") from exc

        # Handle HTTP status errors
        if resp.status_code >= 400:
            error_detail = ""
            try:
                err_json = resp.json()
                error_detail = err_json.get("error") or err_json.get("message") or str(err_json)
            except Exception:
                error_detail = resp.text[:200]
            clean_detail = _sanitize_message(str(error_detail), self._api_key)
            raise ReefAPIResponseError(
                f"ReefAPI error (HTTP {resp.status_code}): {clean_detail}"
            )

        # Parse JSON
        try:
            data = resp.json()
        except Exception as exc:
            raise ReefAPIResponseError("ReefAPI returned invalid non-JSON response") from exc

        # Check ReefAPI's ok status flag
        if isinstance(data, dict) and data.get("ok") is False:
            err_msg = data.get("error") or "Unknown error"
            clean_err = _sanitize_message(str(err_msg), self._api_key)
            raise ReefAPIResponseError(f"ReefAPI returned ok=false: {clean_err}")

        return data

    def search_products(
        self,
        query: str,
        page: int = 1,
        limit: int = 20,
        sort: Optional[str] = None,
        brand: Optional[Union[str, List[str]]] = None,
        gender: Optional[Union[str, List[str]]] = None,
        category: Optional[Union[str, List[str]]] = None,
        color: Optional[Union[str, List[str]]] = None,
        size: Optional[Union[str, List[str]]] = None,
        price_min: Optional[Union[int, float]] = None,
        price_max: Optional[Union[int, float]] = None,
        min_discount: Optional[int] = None,
        **extra_filters: Any,
    ) -> Dict[str, Any]:
        """Search Myntra products via ReefAPI.

        Default limit is conservative (20) to preserve credits.
        """
        if not query or not str(query).strip():
            raise ValueError("Query string cannot be empty")

        # Clamp limit to reasonable safe bounds (1 - 100)
        bounded_limit = max(1, min(int(limit), 100))
        page_num = max(1, int(page))

        payload: Dict[str, Any] = {
            "query": str(query).strip(),
            "page": page_num,
            "limit": bounded_limit,
        }

        if sort:
            payload["sort"] = str(sort).strip()
        if brand is not None:
            payload["brand"] = [brand] if isinstance(brand, str) else list(brand)
        if gender is not None:
            payload["gender"] = [gender] if isinstance(gender, str) else list(gender)
        if category is not None:
            payload["category"] = [category] if isinstance(category, str) else list(category)
        if color is not None:
            payload["color"] = [color] if isinstance(color, str) else list(color)
        if size is not None:
            payload["size"] = [size] if isinstance(size, str) else list(size)
        if price_min is not None:
            payload["price_min"] = price_min
        if price_max is not None:
            payload["price_max"] = price_max
        if min_discount is not None:
            payload["min_discount"] = min_discount

        for k, v in extra_filters.items():
            if v is not None:
                payload[k] = v

        resp_data = self._post(MYNTRA_SEARCH_ENDPOINT, payload)

        # Extract items list
        raw_items: List[dict] = []
        data_field = resp_data.get("data")
        if isinstance(data_field, dict) and "results" in data_field:
            raw_items = data_field["results"]
        elif isinstance(data_field, list):
            raw_items = data_field
        elif "results" in resp_data and isinstance(resp_data["results"], list):
            raw_items = resp_data["results"]

        normalized_products = [normalize_myntra_product(item) for item in raw_items]

        return {
            "ok": True,
            "products": normalized_products,
            "count": len(normalized_products),
            "page": page_num,
            "limit": bounded_limit,
            "total_results": (
                (data_field.get("total_results") if isinstance(data_field, dict) else None)
                or resp_data.get("total_results")
            ),
        }

    def get_product_detail(self, product_id: Union[str, int]) -> Dict[str, Any]:
        """Fetch full product details for a given Myntra product_id."""
        if not product_id:
            raise ValueError("product_id cannot be empty")

        clean_id = str(product_id).strip()
        if clean_id.startswith("myntra_"):
            clean_id = clean_id.replace("myntra_", "", 1)

        payload = {"product_id": clean_id}
        resp_data = self._post(MYNTRA_DETAIL_ENDPOINT, payload)

        raw_product: dict = {}
        data_field = resp_data.get("data")
        if isinstance(data_field, dict):
            raw_product = data_field.get("product") or data_field
        elif "product" in resp_data and isinstance(resp_data["product"], dict):
            raw_product = resp_data["product"]
        else:
            raw_product = resp_data

        normalized_product = normalize_myntra_product(raw_product, is_detail=True)

        return {
            "ok": True,
            "product": normalized_product,
        }
