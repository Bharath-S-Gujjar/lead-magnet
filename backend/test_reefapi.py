"""Manual verification script for ReefAPI Myntra integration.

Makes ONE real Myntra search request fetching 5 products to verify live integration
and response normalization while strictly preserving ReefAPI credits.
"""

import json
import os
import sys

from reef_api_client import ReefAPIClient, ReefAPIError


def run_manual_test() -> None:
    print("=" * 60)
    print("ReefAPI Live Myntra Verification Test (Single Request)")
    print("=" * 60)

    # 1. Initialize client and confirm key is loaded without printing it
    try:
        client = ReefAPIClient()
    except Exception as exc:
        print(f"[ERROR] Failed to initialize ReefAPIClient: {exc}")
        sys.exit(1)

    print("[INFO] REEF_API_KEY loaded successfully.")
    print("[INFO] Making exactly 1 real Myntra search API call (limit=5)...")

    # 2. Make ONE search request with limit=5
    try:
        response = client.search_products(query="shirts", page=1, limit=5)
    except ReefAPIError as exc:
        print(f"[ERROR] ReefAPI call failed: {exc}")
        sys.exit(1)
    except Exception as exc:
        print(f"[ERROR] Unexpected error during search: {exc}")
        sys.exit(1)

    products = response.get("products", [])
    print(f"[SUCCESS] Received {len(products)} normalized products from ReefAPI Myntra.")
    print(f"[INFO] Total available results reported by search: {response.get('total_results')}")
    print("-" * 60)

    # 3. Print required fields for each product
    for idx, product in enumerate(products, 1):
        print(f"Product #{idx}:")
        print(f"  product_id:       {product.get('product_id')}")
        print(f"  title:            {product.get('title')}")
        print(f"  brand:            {product.get('brand')}")
        print(f"  price:            {product.get('price')} {product.get('currency')}")
        print(f"  mrp:              {product.get('mrp')}")
        print(f"  discount_percent: {product.get('discount_percent')}%")
        print(f"  primary_image:    {product.get('primary_image')}")
        print(f"  url:              {product.get('url')}")
        print(f"  images_count:     {len(product.get('images', []))}")
        print(f"  availability:     {product.get('availability_status')}")
        print(f"  stock:            {product.get('stock')}")
        print(f"  source:           {product.get('source')}")
        print(f"  fetched_at:       {product.get('fetched_at')}")
        print("-" * 60)

    # 4. Image presence confirmation
    all_have_primary = all(bool(p.get("primary_image")) for p in products)
    all_have_images = all(len(p.get("images", [])) > 0 for p in products)
    print(f"[CHECK] Primary images present on all items: {all_have_primary}")
    print(f"[CHECK] Complete image arrays populated:     {all_have_images}")
    print("=" * 60)
    print("Completed ONE real ReefAPI call successfully.")
    print("=" * 60)


if __name__ == "__main__":
    run_manual_test()
