# Clothing Catalog Ingestion & Data Cleaning Report

**Date**: 2026-09-27  
**Source Repository**: [suchanabhowal/Myntra-salesdataset](https://github.com/suchanabhowal/Myntra-salesdataset)  
**Datasets Processed**: `Kids.xlsx`, `WOMEN.xlsx`, `myntra-MEN.xlsx`  
**Output Files**:
- Cleaned CSV Catalog: `data/catalog/cleaned_clothing_catalog.csv` (11.4 MB)
- Cleaned JSON Catalog: `data/catalog/cleaned_clothing_catalog.json` (34.5 MB)
- Profiling Summary: `data/catalog/profiling_summary.json`

---

## 1. Executive Summary

A clean, standardized multi-gender clothing catalog was constructed from the three raw Myntra sales datasets (`Kids.xlsx`, `WOMEN.xlsx`, and `myntra-MEN.xlsx`).

Across the 3 datasets, the raw scraping process had captured heavy duplicate rows caused by pagination and snapshot repeats (567,001 source rows reduced to 120,466 unique canonical products). Records were cleaned, normalized, and unified into an authoritative schema without inventing or fabricating any missing values (such as inventory stock, SKU, reviews, or missing prices/ratings).

---

## 2. Source vs. Cleaned Row Counts & Deduplication

### 2.1 Overview Table

| Dataset | File Name | Source Rows | Usable Rows | Unusable Filtered | Unique Cleaned Products | Duplicates Removed | Reduction Ratio |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Kids** | `Kids.xlsx` | 94,750 | 94,750 | 0 | 910 | 93,840 | 99.04% |
| **Women** | `WOMEN.xlsx` | 210,245 | 210,234 | 11 | 68,088 | 142,146 | 67.61% |
| **Men** | `myntra-MEN.xlsx` | 262,006 | 262,005 | 1 | 51,468 | 210,537 | 80.36% |
| **TOTAL** | — | **567,001** | **566,989** | **12** | **120,466** | **446,523** | **78.75%** |

### 2.2 Unusable Name Removal
Only 12 raw rows across the entire 567,001-row corpus failed product name integrity checks and were dropped:
- **Excel Formula Errors**: 2 occurrences of `'#NAME?'` in `WOMEN.xlsx` (scraped formula evaluation failures).
- **Non-Product Demographic/Material Tokens**: 10 rows where the scraped title was only a demographic tag or fabric noun with no apparel description (`'Women'`, `'Girls'`, `'Cotton'`).

### 2.3 Deduplication & Record Selection Strategy
Because scrapers repeatedly scraped the same product across category pages and pagination batches:
- Products were grouped by canonical tuple: `(gender, brand.lower(), name.lower())`.
- For each group, the **most complete snapshot** was selected using a deterministic priority scoring:
  1. Records with an active, valid selling price were prioritized over out-of-stock / null price snapshots.
  2. Highest verified buyer count was prioritized (representing the freshest snapshot).
  3. Valid ratings were prioritized over null ratings.
  4. Active discount percentages were preserved.

---

## 3. Data Transformations & Parsing Rules

1. **Internal Stable `product_id`**:
   - Generated deterministically as `prod_<hex16>` using SHA-256 over `f"{gender}:{brand.strip().lower()}:{name.strip().lower()}"`.
   - Guaranteed unique, idempotent, collision-free, and reproducible.
2. **Price (`price_inr`)**:
   - Cleaned currency strings (e.g., `'Rs.769'`, `'Rs. 1,499'`) to float (`769.0`, `1499.0`).
   - Out-of-stock items with missing price are preserved as `null` (never fabricated).
3. **Discount (`discount_percent`)**:
   - Cleaned percentage strings (e.g., `'65% OFF'`) to float (`65.0`).
   - Converted flat cash-off strings (e.g., `'Rs. 500 OFF'` on price `499.0` with original price `999.0`) to calculated discount percentage (`50.1%`).
   - Missing discounts preserved as `null`.
4. **Ratings (`rating`)**:
   - Normalized to 1-decimal float within standard bounds `[1.0, 5.0]`. Missing ratings preserved as `null`.
5. **Verified Buyers (`verified_buyers`)**:
   - Converted alphanumeric strings (e.g., `'6.8k'` $\rightarrow$ `6800`, `'284'` $\rightarrow$ `284`) into standard integers. Missing counts preserved as `null`.
6. **Zero-Fabrication Guarantee**:
   - In accordance with project requirements, no stock counts, synthetic reviews, SKU codes, or fake images were generated. Missing values remain explicitly null.

---

## 4. Missing Values Analysis

In the final cleaned catalog of **120,466 unique products**:

| Field | Total Records | Populated Count | Missing / Null Count | Null Percentage | Notes |
| :--- | :---: | :---: | :---: | :---: | :--- |
| `product_id` | 120,466 | 120,466 | 0 | 0.00% | Mandatory stable identifier |
| `name` | 120,466 | 120,466 | 0 | 0.00% | Verified apparel title |
| `brand` | 120,466 | 120,466 | 0 | 0.00% | Preserved manufacturer brand |
| `gender` | 120,466 | 120,466 | 0 | 0.00% | Segregated: Men, Women, Kids |
| `category` | 120,466 | 120,466 | 0 | 0.00% | Categorized apparel taxonomy |
| `price_inr` | 120,466 | 110,325 | 10,141 | 8.42% | Missing in all scraped snapshots (out of stock) |
| `discount_percent` | 120,466 | 110,325 | 10,141 | 8.42% | Correlates directly with missing price |
| `rating` | 120,466 | 70,217 | 50,249 | 41.71% | Unrated / newly listed items on Myntra |
| `verified_buyers` | 120,466 | 70,217 | 50,249 | 41.71% | No verified reviews recorded |

---

## 5. Catalog Distributions

### 5.1 Gender Distribution

| Gender | Cleaned Products | Percentage of Catalog |
| :--- | :---: | :---: |
| **Women** | 68,088 | 56.52% |
| **Men** | 51,468 | 42.72% |
| **Kids** | 910 | 0.76% |
| **TOTAL** | **120,466** | **100.00%** |

### 5.2 Category Distribution

| Category | Product Count | Share (%) |
| :--- | :---: | :---: |
| **T-Shirts** | 29,770 | 24.71% |
| **Kurtas & Kurta Sets** | 23,375 | 19.40% |
| **Tops & Tunics** | 15,732 | 13.06% |
| **Shirts** | 9,509 | 7.89% |
| **Sweaters & Sweatshirts** | 9,426 | 7.82% |
| **Trousers & Pants** | 6,988 | 5.80% |
| **Jeans** | 5,556 | 4.61% |
| **Innerwear & Sleepwear** | 5,240 | 4.35% |
| **Skirts** | 4,936 | 4.10% |
| **Jackets & Coats** | 4,702 | 3.90% |
| **Shorts** | 2,987 | 2.48% |
| **Dresses & Jumpsuits** | 1,199 | 1.00% |
| **Other Clothing** | 502 | 0.42% |
| **Track Pants & Joggers** | 339 | 0.28% |
| **Ethnic Wear** | 55 | 0.05% |
| **Leggings & Churidars** | 48 | 0.04% |
| **Nightwear & Loungewear** | 40 | 0.03% |
| **Footwear** | 26 | 0.02% |
| **Co-ords & Clothing Sets** | 22 | 0.02% |
| **Accessories** | 13 | 0.01% |
| **Swimwear** | 1 | <0.01% |

---

## 6. Price Analysis (INR)

Evaluated across **110,325** products with active pricing:

| Metric | Value (INR) |
| :--- | :---: |
| **Minimum Price** | ₹123.00 |
| **25th Percentile (est.)** | ₹599.00 |
| **Median Price** | ₹839.00 |
| **Mean Price** | ₹1,125.56 |
| **75th Percentile (est.)** | ₹1,349.00 |
| **Maximum Price** | ₹144,000.00 |

---

## 7. Brand Analysis

- **Total Unique Brands**: **2,773** brands represented.

### Top 20 Brands by Product Count:
1. **Roadster**: 2,196 products
2. **Trendyol**: 1,482 products
3. **BAESD**: 1,337 products
4. **DressBerry**: 1,281 products
5. **KALINI**: 1,188 products
6. **Tokyo Talkies**: 1,177 products
7. **HERE&NOW**: 1,103 products
8. **H&M**: 1,061 products
9. **Anouk**: 1,039 products
10. **Mast & Harbour**: 978 products
11. **Puma**: 964 products
12. **FOREVER 21**: 930 products
13. **max**: 899 products
14. **Sangria**: 873 products
15. **SHOWOFF**: 837 products
16. **MANGO**: 766 products
17. **V-Mart**: 712 products
18. **StyleCast**: 699 products
19. **SASSAFRAS**: 652 products
20. **LULU & SKY**: 607 products

---

## 8. Rating Distribution

Evaluated across **70,217** rated products (Mean Rating: **4.07** out of 5.0):

| Rating Bucket | Products Count | Percentage of Rated Products |
| :--- | :---: | :---: |
| **4.5 – 5.0 (Excellent)** | 11,798 | 16.80% |
| **4.0 – 4.4 (Good / High Demand)** | 36,740 | 52.32% |
| **3.5 – 3.9 (Average)** | 15,349 | 21.86% |
| **3.0 – 3.4 (Below Average)** | 4,515 | 6.43% |
| **Below 3.0 (Low)** | 1,815 | 2.58% |

---

## 9. Final Cleaned Catalog Schema

The cleaned dataset is stored locally in `data/catalog/cleaned_clothing_catalog.csv` and `data/catalog/cleaned_clothing_catalog.json`.

| Field | Type | Nullable | Description | Example |
| :--- | :---: | :---: | :--- | :--- |
| `product_id` | string | No | Deterministic SHA-256 hash prefix (`prod_<hex16>`) | `"prod_c877ae3c24fe331f"` |
| `name` | string | No | Cleaned apparel title | `"Boys Straight Fit Jeans"` |
| `brand` | string | No | Manufacturer brand name | `"HERE&NOW"` |
| `gender` | string | No | Target demographic (`Men`, `Women`, `Kids`) | `"Kids"` |
| `category` | string | No | Cleaned apparel category classification | `"Jeans"` |
| `price_inr` | float | Yes | Current selling price in INR | `839.0` |
| `discount_percent` | float | Yes | Parsed discount percentage (0 - 100) | `65.0` |
| `rating` | float | Yes | Customer rating normalized to 1 decimal place | `4.1` |
| `verified_buyers` | integer | Yes | Parsed count of verified customer purchasers | `240` |

---

## 10. Verification of Operational Constraints

- **MongoDB Atlas**: Unmodified. No reads/writes or schema modifications were sent to Atlas.
- **Existing Atlas Products (195 documents)**: Preserved completely intact.
- **Git Repository**: No commit or push was executed.
