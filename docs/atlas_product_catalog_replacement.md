# MongoDB Atlas Product Catalog Replacement Operation Report

**Date**: 2026-09-27  
**Database**: `leadmagnet` (MongoDB Atlas)  
**Target Collection**: `products`  
**Source Catalog**: `data/catalog/cleaned_clothing_catalog.json`  
**Backup Location**: `data/catalog/backup/atlas_products_before_replacement.json`  

---

## 1. Executive Summary

The legacy synthetic products collection (195 documents) in MongoDB Atlas (`leadmagnet.products`) was completely backed up, verified, and replaced with the authoritative, validated clothing catalog (120,466 products) compiled from the Myntra sales dataset.

The operation was performed under strict non-destructive safeguards:
- All 195 original products were exported to `data/catalog/backup/atlas_products_before_replacement.json`.
- All incoming 120,466 records passed schema, integrity, and anti-fabrication validations before insertion.
- Customer, session, event, order, feature store, and intelligence collections remained completely untouched.
- Index creation was evaluated and applied idempotently.
- A 20-product random sample was validated against the local source with 100% precision.
- Backend catalog tests passed without failures.

---

## 2. Quantitative Summary

| Metric | Value |
| :--- | :--- |
| **Initial Atlas Products Count** | 195 |
| **Cleaned Catalog Source Count** | 120,466 |
| **Pre-Insertion Validation Status** | **100% PASS** (0 validation errors across 120,466 rows) |
| **Backup File Created** | `data/catalog/backup/atlas_products_before_replacement.json` (101,525 bytes, 195 docs) |
| **Batch Insertion Execution** | 25,000 initial batch + 40,000 progress + 55,466 resume batches |
| **Final Atlas Products Count** | **120,466** |
| **Unique `product_id` Count** | **120,466** |
| **Total Missing / Dropped Records** | **0** |

---

## 3. Product Catalog Demographics & Distributions

### 3.1 Gender Breakdown

| Gender | Count | Percentage |
| :--- | :---: | :---: |
| **Women** | 68,088 | 56.52% |
| **Men** | 51,468 | 42.72% |
| **Kids** | 910 | 0.76% |
| **TOTAL** | **120,466** | **100.00%** |

### 3.2 Key Attributes Ingested
- **Internal Identifier**: Stable deterministic SHA-256 string (`prod_<hex16>`).
- **Price (`price` / `price_inr`)**: Numeric INR float; null preserved for out-of-stock items (zero fabricated).
- **Discount (`discount` / `discount_percent`)**: Numeric percentage float (0.0 – 100.0).
- **Rating**: Float between 1.0 and 5.0 (unrated products remain null).
- **Verified Buyers**: Numeric count of verified purchasers.

---

## 4. Safeguard Verification: Customer & Activity Collections

All customer and activity collections were confirmed before and after the replacement:

| Collection | Count Before Replacement | Count After Replacement | Status |
| :--- | :---: | :---: | :---: |
| `user_profiles` | 0 | 0 | **UNTOUCHED** |
| `sessions` | 0 | 0 | **UNTOUCHED** |
| `events` | 0 | 0 | **UNTOUCHED** |
| `orders` | 0 | 0 | **UNTOUCHED** |
| `customer_features` | 0 | 0 | **UNTOUCHED** |
| `customer_lead_state` | 0 | 0 | **UNTOUCHED** |
| `lead_score_history` | 0 | 0 | **UNTOUCHED** |
| `marketing_automation_events` | 0 | 0 | **UNTOUCHED** |
| `marketing_communications` | 0 | 0 | **UNTOUCHED** |
| `admin_notifications` | 0 | 0 | **UNTOUCHED** |
| `leads` | 5 | 5 | **UNTOUCHED** |
| `users` | 0 | 0 | **UNTOUCHED** |

---

## 5. Atlas Product Indexes

The following indexes are actively registered on `leadmagnet.products`:

| Index Name | Key Specification | Unique | Purpose / Query Path |
| :--- | :--- | :---: | :--- |
| `_id_` | `{"_id": 1}` | False | MongoDB primary key lookup (`/api/products/<_id>`) |
| `product_id_1` | `{"product_id": 1}` | **True** | Guaranteed deduplication and stable external ID lookup |
| `category_1` | `{"category": 1}` | False | Category filtering (`/api/products?category=...`) |
| `gender_1` | `{"gender": 1}` | False | Gender filtering (Men, Women, Kids) |
| `brand_1` | `{"brand": 1}` | False | Brand filtering and brand affinity aggregations |
| `name_1` | `{"name": 1}` | False | Alphabetical sorting and search queries |
| `price_1` | `{"price": 1}` | False | Price range filtering and catalog sort queries |

---

## 6. Live Random Sample Validation (20 Products)

20 random products sampled directly from MongoDB Atlas were validated against the local source catalog:

| # | Product ID | Gender | Brand | Product Name | Price (₹) | Rating | Result |
| :---: | :--- | :---: | :--- | :--- | :---: | :---: | :---: |
| 1 | `prod_1415f781b20c63f7` | Women | Belle Fille | Women Hooded Sweatshirt | ₹1,049.0 | 4.7 | **PASS** |
| 2 | `prod_6210be38c94d485a` | Women | Riara | Women Printed A-Line Skirt | ₹3,644.0 | null | **PASS** |
| 3 | `prod_9dd0ff03c9eb0221` | Women | H&M | Women Fine-knit cardigan | null | 4.5 | **PASS** |
| 4 | `prod_cdc9533477da0b27` | Women | FNOCKS | Women Boyfriend Fit Jeans | ₹989.0 | 3.3 | **PASS** |
| 5 | `prod_af7932fbe938e705` | Women | Globus | Women Stretchable Ripped Jeans | ₹689.0 | 4.0 | **PASS** |
| 6 | `prod_23a88765f1f13fa7` | Women | Roadster | Cable Knit Pullover & Cardigan | ₹1,154.0 | 4.3 | **PASS** |
| 7 | `prod_07ecd05e259765fe` | Women | IX IMPRESSION | Women Printed Pencil Mini Skirt | ₹959.0 | 4.0 | **PASS** |
| 8 | `prod_6d4b82092958db4b` | Women | AMERICAN EAGLE OUTFITTERS | Women Bootcut Jeans | ₹2,799.0 | 4.1 | **PASS** |
| 9 | `prod_00ec0f58a41ca85f` | Women | Chemistry | Women Ruched A-Line Skirt | ₹524.0 | 2.4 | **PASS** |
| 10 | `prod_0db0fd1ff026bd38` | Women | PATRORNA | Women Skirt | ₹1,049.0 | null | **PASS** |
| 11 | `prod_bf24e76f3c28746d` | Women | RAREISM | Mock Collar Cotton Sweatshirt | ₹1,649.0 | 4.6 | **PASS** |
| 12 | `prod_c4c97363427b0b39` | Women | max | Women Plus Size Bootcut Jeans | null | null | **PASS** |
| 13 | `prod_fa6a5b5ae6fdd29a` | Women | IUGA | Printed Open Front Shrug | ₹619.0 | 4.0 | **PASS** |
| 14 | `prod_a1797e5a4c8aa7bc` | Women | Levis | Women Super Straight Fit Jeans | ₹4,419.0 | 4.2 | **PASS** |
| 15 | `prod_9cb680305144e2a7` | Women | Rute | Women Typography Shorts | null | null | **PASS** |
| 16 | `prod_9e91add5916d3f6b` | Women | Marie Claire | Round Neck Cotton Sweatshirt | ₹735.0 | null | **PASS** |
| 17 | `prod_6f4eb8d23b1f7482` | Women | JC Collection | Training or Gym Sports Shorts | ₹2,379.0 | null | **PASS** |
| 18 | `prod_45258f4beda66bbe` | Women | RAJOVATI | Women Slim Fit Regular Shorts | ₹524.0 | null | **PASS** |
| 19 | `prod_bdc0dafaaa91e686` | Women | FREAKINS | Women Straight Fit Jeans | ₹2,116.0 | 4.1 | **PASS** |
| 20 | `prod_6d8b356f7633e99c` | Women | Aditi Wasan | Floral Ruffled Mini Skirt | ₹699.0 | null | **PASS** |

---

## 7. Backend Test Suite Verification

Ran isolated product suite tests:
```bash
pytest backend/tests/test_products.py -v
```

**Results**:
- `test_get_products_with_empty_catalog`: **PASSED**
- `test_products_category_filter_only_returns_matching_items`: **PASSED**
- `test_products_collection_has_safe_indexes`: **PASSED**
- `test_valid_product_lookup_and_malformed_id`: **PASSED**
- **Summary**: `4 passed, 0 failed in 0.13s`

---

## 8. Operational Constraints Confirmed

1. **Flask Application**: Not started.
2. **Application Source Code**: No source code was modified.
3. **Git Hygiene**: No commits or push actions were performed.
