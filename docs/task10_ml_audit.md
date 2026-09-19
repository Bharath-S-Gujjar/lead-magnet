# Task 10 — ML Lead Scoring Engine Audit & Architecture (Phase 1)

## Executive Summary

- **Can the existing model be reused?**: **NO.** The existing model artifacts (`model/xgb_model.pkl`) were trained on an legacy education course lead generation dataset (`Leads.csv` for "X Education"). 161 of its 166 input columns expect course specializations, tradeshow tags, and course lead sources. It cannot process e-commerce signals such as `cart_value`, `wishlist_item_count`, `orders_count`, `total_order_value`, or product recency.
- **Does sufficient e-commerce training data exist in the repository?**: **NO.** The repository contains only `Leads.csv` (education leads) and a local database with 4 registered users and 4 orders.
- **What target should be used?**: `purchase_in_next_30_days` or `conversion_after_intent` (binary 0/1 indicator of whether a customer places an order within a target observation window following behavioral intent).
- **What additional data is required?**: A standardized e-commerce behavioral training dataset (5,000+ observations) mapped to the canonical `customer_features` schema.
- **Exact next implementation step**: Phase 2 — Generate/synthesize an e-commerce behavioral training dataset, train a modern e-commerce XGBoost classifier & scaler, and update `backend/model_adapter.py` and `backend/prediction_service.py` to consume `customer_features` documents directly.

---

## 1. Existing Model Audit

### Artifact Inventory
- **`model/xgb_model.pkl`**: `xgboost.sklearn.XGBClassifier` fitted on 166 feature columns.
- **`model/scaler.pkl`**: `sklearn.preprocessing.StandardScaler` fitted on 166 feature columns.
- **`model/feature_columns.pkl`**: Python list of 166 column names (`TotalVisits`, `Total Time Spent on Website`, `Page Views Per Visit`, `Lead Origin_*`, `Lead Source_*`, `Last Activity_*`, `Tags_*`, `Specialization_*`, `City_*`).
- **`model/kmeans_model.pkl`**: `sklearn.cluster.KMeans(n_clusters=3, n_init=10, random_state=42)` fitted on scaled features.
- **`model/segment_map.pkl`**: Python dictionary `{1: 'Hot', 0: 'Warm', 2: 'Cold'}` mapping KMeans cluster IDs to lead segment strings.

### Existing Prediction Pipeline Analysis
- **Model Type**: Supervised Binary Classification (`XGBClassifier`) for conversion probability + Unsupervised Clustering (`KMeans`) for segment categorization.
- **Input Feature Count**: 166 numeric/dummy-encoded columns.
- **Is KMeans actually used in prediction flow?**: **YES.** `backend/prediction_service.py` calls `artifacts["kmeans"].predict(scaled_features)` to obtain `cluster_id`.
- **Is segment_map actually used?**: **YES.** `prediction_service.py` looks up `artifacts["segment_map"][cluster_id]` to return the segment (`Hot`, `Warm`, `Cold`).
- **Semantic Compatibility with `customer_features`**: **INCOMPATIBLE.**
  - The model expects education domain features (`Specialization_Business Administration`, `Tags_Will revert after reading the email`, `A free copy of Mastering The Interview_Yes`).
  - The model does not contain fields for e-commerce commerce metrics (`cart_value`, `cart_item_count`, `wishlist_item_count`, `orders_count`, `total_order_value`, `checkout_attempts`, `product_interactions`).
  - `model_adapter.py` currently fills 161 out of 166 features with `0`, rendering predictions inaccurate for e-commerce users.

---

## 2. Dataset Inventory

Search across the entire project repository revealed the following dataset files:

| Dataset Path | Row Count | Column Count | Key Columns | Target Candidate | E-Commerce Data? | Level | Supervised Suitable? |
|---|---|---|---|---|---|---|---|
| `data/raw/Leads.csv` | 9,240 | 37 | `Prospect ID`, `Lead Origin`, `Lead Source`, `Specialization`, `Tags`, `TotalVisits`, `Total Time Spent on Website`, `Page Views Per Visit`, `Converted` | `Converted` (0/1) | **NO** (Education Course Leads) | Lead submission | No (Education only) |
| `data/cleaned/leads_cleaned.csv` | 9,240 | 28 | `Lead Origin`, `Lead Source`, `Specialization`, `Tags`, `City`, `TotalVisits`, `Total Time Spent on Website`, `Page Views Per Visit`, `Converted` | `Converted` (0/1) | **NO** (Education Course Leads) | Lead submission | No (Education only) |

**Conclusion**: **"Insufficient real labeled e-commerce data for supervised training."**

---

## 3. Training Notebook Audit

### Notebook: `notebooks/01_cleaning.ipynb`
- **Data Loading**: Loads `data/raw/leads.csv`.
- **Cleaning**: Drops columns with >40% missing values, `Prospect ID`, and `Lead Number`. Imputes numerical nulls with median and categorical nulls with mode.
- **Encoding**: One-hot encodes categorical variables into 166 binary dummy columns.
- **Model Training**: Fits `StandardScaler`, `LogisticRegression`, `XGBClassifier(n_estimators=200, max_depth=5, learning_rate=0.1)`, and `KMeans(n_clusters=3)`.
- **Segment Mapping**: Groups conversion rate by KMeans cluster ID (`df.groupby("segment_id")["Converted"].mean()`) and assigns cluster with highest conversion rate as `'Hot'`, middle as `'Warm'`, lowest as `'Cold'`.

---

## 4. ML Target Definition

Based on available data and domain requirements:
- **Primary Supervised Target**: `converted_in_window` (Binary `1` if customer completes an order within a 30-day window following observation, `0` otherwise).
- **Alternative Behavioral Target**: `high_intent_buyer` (Binary `1` if customer reaches checkout or places an order, `0` otherwise).

---

## 5. Generic E-Commerce Requirement

To ensure the ML lead scoring model works universally across product categories (clothing, electronics, groceries, furniture, beauty, general retail):
- **Domain Independence**: The feature schema must NOT depend on specific product category strings ("Hoodies", "Laptops"), specific brand names ("Adidas", "Apple"), or hard-coded product IDs.
- **Generic Behavioral Signals**: The model must rely strictly on abstract behavioral indicators (`cart_value`, `cart_item_count`, `wishlist_item_count`, `orders_count`, `total_order_value`, `sessions_count`, `total_time_spent`, `product_interactions`, `checkout_attempts`, `high_intent_page_visits`, `days_since_last_activity`).

---

## 6. Feature Design & Classification

Task 9's canonical `customer_features` schema is categorized for ML modeling as follows:

### A. Direct Numerical Features
- `sessions_count`
- `total_events`
- `total_time_spent`
- `page_views_count`
- `products_viewed`
- `unique_products_viewed`
- `product_interactions`
- `search_count`
- `form_submit_count`
- `high_intent_page_visits`
- `cart_item_count`
- `cart_value`
- `wishlist_item_count`
- `checkout_attempts`
- `orders_count`
- `total_order_value`

### B. Derived Numerical Ratio Features
- `average_session_duration` (`total_time_spent / max(sessions_count, 1)`)
- `average_order_value` (`total_order_value / max(orders_count, 1)`)
- `cart_to_session_ratio` (`cart_item_count / max(sessions_count, 1)`)
- `checkout_to_cart_ratio` (`checkout_attempts / max(cart_item_count, 1)`)
- `high_intent_ratio` (`high_intent_page_visits / max(page_views_count, 1)`)
- `product_interaction_density` (`product_interactions / max(sessions_count, 1)`)

### C. Temporal & Recency Features
- `days_since_last_activity`
- `days_since_last_product_view` (`(now - last_product_view_at).days`)
- `days_since_last_cart_action` (`(now - last_cart_action_at).days`)
- `days_since_last_wishlist_action` (`(now - last_wishlist_action_at).days`)
- `days_since_last_checkout` (`(now - last_checkout_action_at).days`)
- `customer_tenure_days` (`(now - first_seen_at).days`)

### D. Features Requiring Transformation
- Log-transformation ($\log(x + 1)$) or `RobustScaler` for highly skewed monetary and count fields: `cart_value`, `total_order_value`, `total_time_spent`, `total_events`.

### E. Features Excluded from Model Input
- Raw IDs: `customer_id`, `anonymous_ids`, `_id`.
- ISO Timestamp strings: `last_active_at`, `first_seen_at`, `updated_at`, `last_order_at`, `last_product_view_at`, `last_cart_action_at`, `last_wishlist_action_at`, `last_checkout_action_at`.

---

## 7. Data Leakage Audit & Prevention

- **Leakage Risk**: If predicting whether a customer will purchase in the target window $[T_{obs}, T_{obs} + 30\text{ days}]$, including orders or checkout attempts that occurred *after* $T_{obs}$ into the feature vector will cause data leakage and artificially inflate validation scores.
- **Prevention Strategy**:
  1. Features are computed strictly using events, sessions, cart, wishlist, and order records timestamped $\le T_{obs}$.
  2. Target label `converted` is evaluated using order records timestamped within $(T_{obs}, T_{obs} + 30\text{ days}]$.

---

## 8. Train / Validation / Test Strategy

- **Time-Aware Split**:
  - **Training Set**: Customer activity from Month 1 to Month 4.
  - **Validation Set**: Customer activity from Month 5.
  - **Test Set**: Customer activity from Month 6.
- **Evaluation Metrics**:
  - **ROC-AUC**: Primary metric for lead rank-ordering quality.
  - **PR-AUC**: Primary metric for imbalanced conversion class evaluation.
  - **Precision@Top-10%**: Percentage of top 10% scored leads that actually convert (critical for sales team efficiency).
  - **F1-Score & Brier Score**: Model calibration and classification balance.

---

## 9. Lead Score Design & Prediction Contract

### Score Derivation
1. Model outputs conversion probability $P(\text{conversion} \mid \text{features}) \in [0.00, 1.00]$.
2. `lead_score = int(round(P * 100))`.
3. `lead_segment`:
   - `Hot`: $P \ge 0.70$ (or Top 10% highest intent)
   - `Warm`: $0.35 \le P < 0.70$
   - `Cold`: $P < 0.35$

### Output JSON Schema
```json
{
  "customer_id": "6aae287889fa871c2904c1b5",
  "lead_probability": 0.87,
  "lead_score": 87,
  "lead_segment": "Hot",
  "next_action": "High-priority direct outreach / checkout discount code",
  "model_version": "v2.0_ecommerce_xgb",
  "scored_at": "2026-09-19T16:40:00Z"
}
```

---

## 10. Production Architecture

```
customer_features (MongoDB Collection)
        ↓
Feature Transformer & Scaler (customer_feature_service + model_adapter)
        ↓
E-Commerce Lead Scoring Engine (XGBoost Classifier)
        ↓
Lead Probability (0.00 to 1.00) & Lead Score (0 to 100)
        ↓
customer_lead_state (ONE REGISTERED CUSTOMER = ONE CURRENT LEAD STATE)
```

---

## 11. Read-Only Local MongoDB Inspection

Strictly read-only inspection of local `leadmagnet` MongoDB (no write operations executed):

- **`user_profiles` count**: `4`
- **`registered customers` count**: `2` (`test@gmail.com`, `testuser_test@example.com`)
- **`customer_features` count**: `4`
- **`sessions` count**: `12`
- **`events` count**: `159`
- **`orders` count**: `4`
- **`leads` count**: `9`

---

## 12. Exact Implementation Plan for Task 10 Phase 2

1. **Dataset Preparation**:
   - Synthesize/generate an e-commerce customer behavioral dataset (5,000+ customer records) adhering strictly to Task 9's canonical `customer_features` schema with ground-truth conversion outcomes.
2. **Model Training & Artifact Export**:
   - Train an e-commerce `XGBClassifier` and `StandardScaler` on generic e-commerce behavioral features.
   - Save artifacts: `model/ecommerce_xgb_model.pkl`, `model/ecommerce_scaler.pkl`, `model/ecommerce_feature_columns.pkl`.
3. **Service Integration**:
   - Update `backend/model_adapter.py` to directly transform `customer_features` documents into model feature vectors.
   - Update `backend/prediction_service.py` to compute lead probability, score (0-100), and segment (`Hot`, `Warm`, `Cold`).
4. **Testing & Verification**:
   - Add unit tests in `backend/tests/test_ecommerce_lead_scoring.py`.
   - Verify that one registered customer maps to one current lead state without mutating model pickles unexpectedly.
