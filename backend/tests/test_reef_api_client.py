"""Unit tests for ReefAPI client and Myntra catalog normalization.

All tests are completely offline and mock HTTP requests to prevent consuming
ReefAPI credits.
"""

import os
import unittest
from unittest.mock import MagicMock, patch

import requests

from reef_api_client import (
    ReefAPIClient,
    ReefAPIConfigError,
    ReefAPIConnectionError,
    ReefAPIError,
    ReefAPIResponseError,
    ReefAPITimeoutError,
    extract_images,
    normalize_myntra_product,
)


class TestReefAPIClientConfig(unittest.TestCase):
    """Tests for API client configuration and key safety."""

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_api_key_raises_config_error(self):
        """Instantiating without key in env or args raises ReefAPIConfigError."""
        with patch("reef_api_client._load_env_if_needed"):
            with self.assertRaises(ReefAPIConfigError) as ctx:
                ReefAPIClient(api_key=None)
            self.assertIn("missing", str(ctx.exception).lower())

    def test_explicit_api_key_configuration(self):
        """Client accepts explicit key and sets default parameters."""
        client = ReefAPIClient(api_key="test_dummy_key_123")
        self.assertEqual(client.base_url, "https://api.reefapi.com")
        self.assertEqual(client.timeout, 30.0)

    def test_api_key_not_leaked_in_repr_or_str(self):
        """API key must never appear in repr or string output."""
        secret_key = "ak_live_supersecretkey999"
        client = ReefAPIClient(api_key=secret_key)
        repr_str = repr(client)
        self.assertNotIn(secret_key, repr_str)
        self.assertIn("ReefAPIClient", repr_str)


class TestResponseNormalization(unittest.TestCase):
    """Tests for normalizing Myntra search and detail responses."""

    def setUp(self):
        self.sample_raw_product = {
            "product_id": "24981120",
            "title": "Men Slim Fit Cotton Casual Shirt",
            "brand": "Roadster",
            "category": "Shirts",
            "gender": "men",
            "url": "https://www.myntra.com/shirts/roadster/men-shirt/24981120/buy",
            "image": "https://assets.myntassets.com/h_720,q_90,w_540/v1/assets/images/24981120/img1.jpg",
            "images": [
                "https://assets.myntassets.com/h_720,q_90,w_540/v1/assets/images/24981120/img1.jpg",
                "https://assets.myntassets.com/h_720,q_90,w_540/v1/assets/images/24981120/img2.jpg",
                "https://assets.myntassets.com/h_720,q_90,w_540/v1/assets/images/24981120/img3.jpg",
            ],
            "price": 799,
            "mrp": 1599,
            "price_before_discount": 1599,
            "discount_amount": 800,
            "discount_percent": 50,
            "currency": "INR",
            "rating": 4.1,
            "featured_sku": {"sku_id": "1001", "size": "M", "stock": 14, "available": True},
        }

    def test_successful_response_normalization_fields(self):
        """Ensures all required internal structure fields exist and have correct values."""
        normalized = normalize_myntra_product(self.sample_raw_product)

        required_fields = [
            "product_id",
            "title",
            "brand",
            "category",
            "gender",
            "url",
            "primary_image",
            "images",
            "price",
            "mrp",
            "price_before_discount",
            "discount_amount",
            "discount_percent",
            "currency",
            "rating",
            "stock",
            "availability_status",
            "source",
            "source_product_id",
            "fetched_at",
        ]

        for field in required_fields:
            self.assertIn(field, normalized, f"Missing field: {field}")

        self.assertEqual(normalized["product_id"], "myntra_24981120")
        self.assertEqual(normalized["source_product_id"], "24981120")
        self.assertEqual(normalized["source"], "myntra")
        self.assertEqual(normalized["title"], "Men Slim Fit Cotton Casual Shirt")
        self.assertEqual(normalized["brand"], "Roadster")
        self.assertEqual(normalized["category"], "Shirts")
        self.assertEqual(normalized["gender"], "men")
        self.assertEqual(normalized["currency"], "INR")
        self.assertEqual(normalized["rating"], 4.1)
        self.assertEqual(normalized["stock"], 14)
        self.assertEqual(normalized["availability_status"], "in_stock")
        self.assertTrue(normalized["fetched_at"].endswith("+00:00") or normalized["fetched_at"].endswith("Z"))

    def test_relative_url_handling(self):
        """Relative product URLs are converted to full myntra.com URLs."""
        raw = {"product_id": "123", "url": "/shirts/roadster/123/buy"}
        normalized = normalize_myntra_product(raw)
        self.assertEqual(normalized["url"], "https://www.myntra.com/shirts/roadster/123/buy")


class TestImageExtraction(unittest.TestCase):
    """Tests for image parsing, preservation, and fallback handling."""

    def test_complete_images_array_preserved_and_first_used_as_primary(self):
        """All images preserved in original order and first valid image set as primary."""
        raw = {
            "image": "https://example.com/single.jpg",
            "images": [
                "https://example.com/img1.jpg",
                "https://example.com/img2.jpg",
                "//example.com/img3.jpg",
            ],
        }
        primary, images = extract_images(raw)
        self.assertEqual(primary, "https://example.com/img1.jpg")
        self.assertEqual(
            images,
            [
                "https://example.com/img1.jpg",
                "https://example.com/img2.jpg",
                "https://example.com/img3.jpg",
                "https://example.com/single.jpg",
            ],
        )

    def test_single_image_only(self):
        """When only single image field is present, images array holds it."""
        raw = {"image": "https://example.com/only_one.jpg"}
        primary, images = extract_images(raw)
        self.assertEqual(primary, "https://example.com/only_one.jpg")
        self.assertEqual(images, ["https://example.com/only_one.jpg"])

    def test_missing_image_handling(self):
        """When product has no images, returns None primary_image and empty list."""
        raw = {"title": "No Image Product"}
        primary, images = extract_images(raw)
        self.assertIsNone(primary)
        self.assertEqual(images, [])

        normalized = normalize_myntra_product(raw)
        self.assertIsNone(normalized["primary_image"])
        self.assertEqual(normalized["images"], [])

    def test_dict_based_image_list_extraction(self):
        """Handles images provided as list of dicts with url/src."""
        raw = {
            "images": [
                {"src": "https://example.com/dict1.jpg"},
                {"url": "https://example.com/dict2.jpg"},
            ]
        }
        primary, images = extract_images(raw)
        self.assertEqual(primary, "https://example.com/dict1.jpg")
        self.assertEqual(images, ["https://example.com/dict1.jpg", "https://example.com/dict2.jpg"])


class TestPriceAndDiscountExtraction(unittest.TestCase):
    """Tests for price, MRP, and discount preservation without inventing values."""

    def test_exact_price_mrp_discount_preserved(self):
        """Preserves ReefAPI values accurately."""
        raw = {
            "price": 1249,
            "mrp": 2499,
            "price_before_discount": 2499,
            "discount_amount": 1250,
            "discount_percent": 50,
        }
        normalized = normalize_myntra_product(raw)
        self.assertEqual(normalized["price"], 1249)
        self.assertEqual(normalized["mrp"], 2499)
        self.assertEqual(normalized["price_before_discount"], 2499)
        self.assertEqual(normalized["discount_amount"], 1250)
        self.assertEqual(normalized["discount_percent"], 50)

    def test_no_discount_invented_when_absent(self):
        """When ReefAPI does not supply discount, none is calculated."""
        raw = {
            "price": 1999,
            "mrp": 1999,
            "price_before_discount": None,
            "discount_amount": None,
            "discount_percent": None,
        }
        normalized = normalize_myntra_product(raw)
        self.assertEqual(normalized["price"], 1999)
        self.assertEqual(normalized["mrp"], 1999)
        self.assertIsNone(normalized["price_before_discount"])
        self.assertIsNone(normalized["discount_amount"])
        self.assertIsNone(normalized["discount_percent"])

    def test_string_numeric_parsing(self):
        """Parses string formatted prices with commas."""
        raw = {
            "price": "1,499.50",
            "mrp": "2,999",
            "discount_percent": "50",
        }
        normalized = normalize_myntra_product(raw)
        self.assertEqual(normalized["price"], 1499.50)
        self.assertEqual(normalized["mrp"], 2999)
        self.assertEqual(normalized["discount_percent"], 50)


class TestReefAPIClientRequestsAndErrors(unittest.TestCase):
    """Tests client requests, credit limits, and mock error handling."""

    def setUp(self):
        self.client = ReefAPIClient(api_key="ak_live_mock_key_test")

    @patch("requests.post")
    def test_search_products_request_structure(self, mock_post):
        """Search request sends correct headers, endpoint, and bounded limit."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "ok": True,
            "data": {
                "results": [
                    {
                        "product_id": "111",
                        "title": "Jeans",
                        "price": 999,
                        "image": "https://example.com/j.jpg",
                    }
                ],
                "total_results": 1,
            },
        }
        mock_post.return_value = mock_resp

        result = self.client.search_products("jeans", page=1, limit=5, gender="men")

        # Verify endpoint called
        mock_post.assert_called_once()
        call_args, call_kwargs = mock_post.call_args
        self.assertEqual(call_args[0], "https://api.reefapi.com/myntra/v1/search")

        # Verify x-api-key header
        headers = call_kwargs.get("headers", {})
        self.assertEqual(headers.get("x-api-key"), "ak_live_mock_key_test")
        self.assertEqual(headers.get("Content-Type"), "application/json")

        # Verify payload params
        payload = call_kwargs.get("json", {})
        self.assertEqual(payload.get("query"), "jeans")
        self.assertEqual(payload.get("page"), 1)
        self.assertEqual(payload.get("limit"), 5)
        self.assertEqual(payload.get("gender"), ["men"])

        # Verify return structure
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["products"]), 1)
        self.assertEqual(result["products"][0]["product_id"], "myntra_111")
        self.assertEqual(result["products"][0]["title"], "Jeans")

    @patch("requests.post")
    def test_get_product_detail_request_structure(self, mock_post):
        """Product detail request strips 'myntra_' prefix and sends product_id."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "ok": True,
            "data": {
                "product": {
                    "product_id": "40301489",
                    "title": "Trainers Shoes",
                    "price": 2499,
                    "image": "https://example.com/shoe.jpg",
                    "availability": "in_stock",
                }
            },
        }
        mock_post.return_value = mock_resp

        res = self.client.get_product_detail("myntra_40301489")

        call_args, call_kwargs = mock_post.call_args
        self.assertEqual(call_args[0], "https://api.reefapi.com/myntra/v1/product/detail")
        payload = call_kwargs.get("json", {})
        self.assertEqual(payload.get("product_id"), "40301489")

        self.assertTrue(res["ok"])
        self.assertEqual(res["product"]["product_id"], "myntra_40301489")
        self.assertEqual(res["product"]["availability_status"], "in_stock")

    @patch("requests.post")
    def test_timeout_raises_reefapi_timeout_error(self, mock_post):
        """Network timeout translates to ReefAPITimeoutError."""
        mock_post.side_effect = requests.exceptions.Timeout("Connection timed out")
        with self.assertRaises(ReefAPITimeoutError):
            self.client.search_products("kurtas")

    @patch("requests.post")
    def test_connection_error_raises_reefapi_connection_error(self, mock_post):
        """Network connection failure translates to ReefAPIConnectionError."""
        mock_post.side_effect = requests.exceptions.ConnectionError("Name resolution failed")
        with self.assertRaises(ReefAPIConnectionError):
            self.client.search_products("kurtas")

    @patch("requests.post")
    def test_http_401_error_handled_safely(self, mock_post):
        """HTTP error raises ReefAPIResponseError without leaking the API key."""
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.json.return_value = {"error": "Invalid API key ak_live_mock_key_test"}
        mock_post.return_value = mock_resp

        with self.assertRaises(ReefAPIResponseError) as ctx:
            self.client.search_products("shirts")

        err_msg = str(ctx.exception)
        self.assertIn("HTTP 401", err_msg)
        self.assertNotIn("ak_live_mock_key_test", err_msg)
        self.assertIn("[REDACTED]", err_msg)

    @patch("requests.post")
    def test_ok_false_response_raises_response_error(self, mock_post):
        """When ReefAPI returns ok=false in envelope, raises ReefAPIResponseError."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "ok": False,
            "error": "Rate limit exceeded. Please retry in 60s.",
        }
        mock_post.return_value = mock_resp

        with self.assertRaises(ReefAPIResponseError) as ctx:
            self.client.search_products("shoes")
        self.assertIn("Rate limit exceeded", str(ctx.exception))

    @patch("requests.post")
    def test_invalid_json_response_raises_response_error(self, mock_post):
        """Non-JSON response raises ReefAPIResponseError."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.side_effect = ValueError("Invalid JSON")
        mock_post.return_value = mock_resp

        with self.assertRaises(ReefAPIResponseError):
            self.client.search_products("shoes")

    def test_sparse_product_missing_fields_handled_gracefully(self):
        """Product with missing/sparse fields normalizes cleanly."""
        sparse = {}
        normalized = normalize_myntra_product(sparse)
        self.assertEqual(normalized["product_id"], "")
        self.assertEqual(normalized["title"], "")
        self.assertIsNone(normalized["primary_image"])
        self.assertEqual(normalized["images"], [])
        self.assertIsNone(normalized["price"])
        self.assertEqual(normalized["availability_status"], "in_stock")
        self.assertEqual(normalized["source"], "myntra")


if __name__ == "__main__":
    unittest.main()
