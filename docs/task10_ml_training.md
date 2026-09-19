# Task 10 Phase 2A — Generic E-Commerce ML Training Pipeline Documentation

> **DISCLAIMER**: The dataset used in this phase (`data/ml/ecommerce_customer_behavior.csv`) is **SYNTHETIC** and engineered specifically for generic e-commerce behavioral lead scoring. High performance metrics reported below reflect model learning behavior on synthetic distributions and serve as a prototype baseline until real production customer conversion data is accumulated.

---

## 1. Why the Old Model Was Rejected
- **Domain Mismatch**: The legacy `model/xgb_model.pkl` was trained on Kaggle's "X Education" course lead dataset (`Leads.csv`). 161 of its 166 input columns expect course specializations, tradeshow tags, and course lead sources (`Specialization_Business Administration`, `Tags_Will revert after reading the email`, `A free copy of Mastering The Interview_Yes`).
- **Feature Gap**: It cannot ingest modern e-commerce shopping intent metrics such as `cart_value`, `cart_item_count`, `wishlist_item_count`, `orders_count`, `total_order_value`, `checkout_attempts`, or product recency timestamps.
- **Incompatible Mapping**: `model_adapter.py` filled 161 out of 166 features with `0`, rendering predictions inaccurate for e-commerce user behavior.

---

## 2. Synthetic Dataset Design
- **Path**: `data/ml/ecommerce_customer_behavior.csv`
- **Total Observations**: 6,000 rows, 25 columns.
- **Unit of Observation**: ONE CUSTOMER at ONE OBSERVATION POINT (`customer_id`).
- **Domain Independence**: Contains ZERO clothing-specific categories, brand names, or education course fields. Works universally across clothing, electronics, groceries, beauty, and general retail.

---

## 3. Feature Schema (23 Behavioral Features)

### Core Engagement & Behavioral Features
- `sessions_count` (int): Total sessions recorded for customer.
- `total_events` (int): Total behavioral events logged.
- `total_time_spent` (float): Total seconds spent across sessions.
- `average_session_duration` (float): `total_time_spent / sessions_count`.
- `page_views_count` (int): Total page views.
- `days_since_last_activity` (float): Days elapsed since last activity.
- `products_viewed` (int): Total product views.
- `unique_products_viewed` (int): Count of distinct products viewed.
- `product_interactions` (int): Sum of product views, clicks, cart adds, wishlist adds.
- `search_count` (int): Search and filter query actions.
- `form_submit_count` (int): Form submit actions.
- `high_intent_page_visits` (int): Visits to high-intent pages (`pricing`, `demo`, `contact`, `checkout`).

### Shopping Intent & Commerce Features
- `cart_item_count` (int): Active items in cart.
- `cart_value` (float): Total monetary value of active cart items.
- `wishlist_item_count` (int): Items saved in wishlist.
- `checkout_attempts` (int): Count of checkout start actions.
- `orders_count` (int): Historical completed orders count.
- `total_order_value` (float): Total monetary value of completed orders.
- `average_order_value` (float): `total_order_value / max(orders_count, 1)`.

### Derived Ratios
- `cart_to_session_ratio` (`cart_item_count / sessions_count`)
- `checkout_to_cart_ratio` (`checkout_attempts / max(cart_item_count, 1)`)
- `high_intent_ratio` (`high_intent_page_visits / max(page_views_count, 1)`)
- `product_interaction_density` (`product_interactions / sessions_count`)

---

## 4. Target Definition & Synthetic Generation Assumptions
- **Column Name**: `converted_in_window`
- **Definition**:
  - `1`: Customer completes a purchase/conversion within the 30-day prediction window following observation ($T > T_{obs}$).
  - `0`: Customer does not complete a purchase within that window.
- **Generation Assumptions**:
  The target label is generated probabilistically via a non-deterministic logistic log-odds formula with additive Gaussian noise ($\mu=0, \sigma=0.6$):

  $$\text{log\_odds} = -3.5 + 1.15 \cdot \text{checkout\_attempts} + 0.006 \cdot \text{cart\_value} + 0.30 \cdot \text{high\_intent\_visits} + 0.10 \cdot \text{product\_interactions} + 0.18 \cdot \text{wishlist\_items} - 0.045 \cdot \text{days\_inactive} + 0.50 \cdot \text{orders\_count} + \epsilon$$

  $$\text{probability} = \frac{1}{1 + e^{-\text{log\_odds}}}$$

  $$\text{converted\_in\_window} = \begin{cases} 1 & \text{if } \text{probability} \ge 0.50 \\ 0 & \text{otherwise} \end{cases}$$

- **Synthetic vs Real Production Performance**:
  High validation metrics ($\text{ROC-AUC} \approx 0.96 - 0.97$) are an expected outcome of learning from a known mathematical generation function. They represent benchmark capability on synthetic intent distributions, **not** real-world production accuracy.

---

## 5. Leakage & Temporal Audit
- **Temporal Constraint**: All 23 feature variables represent historical activity occurring strictly BEFORE observation time $T_{obs}$.
- **Feature Review**:
  - `orders_count`, `total_order_value`, `average_order_value`: Represent historical completed orders prior to $T_{obs}$.
  - `cart_value`, `checkout_attempts`, `product_interactions`: Represent active shopping intent prior to $T_{obs}$.
  - `converted_in_window`: Evaluates future order completion occurring strictly AFTER $T_{obs}$ ($(T_{obs}, T_{obs} + 30\text{ days}]$).
- **Leakage Status**: **ZERO LEAKAGE.** No post-observation features or future conversion metrics leak into the training matrix.

---

## 6. Dataset Statistics
- **Total Rows**: 6,000
- **Missing Values**: 0
- **Duplicate Customer IDs**: 0
- **Class Distribution**:
  - Class `0` (Non-converted): 3,573 rows (**59.55%**)
  - Class `1` (Converted): 2,427 rows (**40.45%**)
- **Top Feature Correlations with Target**:
  1. `checkout_attempts`: +0.4928
  2. `cart_value`: +0.4594
  3. `cart_item_count`: +0.4013
  4. `product_interactions`: +0.3772
  5. `products_viewed`: +0.3701
  6. `days_since_last_activity`: -0.1494

---

## 7. Training & Evaluation Strategy
- **Reproducibility**: Fixed random seed at `42` (`np.random.seed(42)`, `random_state=42`).
- **Data Splits**:
  - **Train Set**: 4,200 rows (**70%**)
  - **Validation Set**: 900 rows (**15%**)
  - **Test Set**: 900 rows (**15%**)
- **Preprocessing**: `StandardScaler` fitted on `X_train`.

---

## 8. Baseline vs XGBoost Model Comparison & Model Selection

| Model | Split | ROC-AUC | PR-AUC | Precision | Recall | F1-Score | Precision@Top-10% |
|---|---|---|---|---|---|---|---|
| **Logistic Regression (Baseline)** | Validation | **0.9721** | **0.9620** | **0.8930** | **0.8654** | **0.8790** | **100.00%** |
| **Logistic Regression (Baseline)** | Test | **0.9764** | **0.9685** | **0.8988** | **0.8736** | **0.8860** | **100.00%** |
| **XGBoost Classifier (Candidate)** | Validation | 0.9573 | 0.9417 | 0.8603 | 0.8626 | 0.8615 | 100.00% |
| **XGBoost Classifier (Candidate)** | Test | 0.9680 | 0.9575 | 0.8848 | 0.8654 | 0.8750 | 100.00% |

### Model Selection Audit Rationale
- **Measured Performance**: **Logistic Regression** achieved the higher measured validation/test scores (ROC-AUC `0.9721` vs `0.9573`) because the synthetic dataset label was generated via a logistic log-odds formula.
- **Candidate Prototype Choice**: **XGBoost** is retained as an evaluated candidate prototype model for tree-based non-linear behavior modeling because gradient-boosted trees naturally handle non-linear feature interactions, non-monotonic decision thresholds, and unscaled feature shifts expected in production e-commerce traffic.
- **Provisional Status**: Final model selection remains **provisional** until retrained and evaluated on real e-commerce production data.

### Confusion Matrix (XGBoost Test Set)
- True Negatives (TN): 512
- False Positives (FP): 41
- False Negatives (FN): 49
- True Positives (TP): 298

---

## 9. Top-K Metric Verification

- **Precision@Top-10% Calculation**:
  - Validation set size $N_{val} = 900$. Top 10% ratio = $90$ customers.
  - Predicted probabilities `val_probs` computed strictly on `X_val_scaled` (transformed using scaler fitted on `X_train`).
  - Top 90 highest predicted probability customers selected from `X_val`.
  - Actual positive count in top 90 group = $90 / 90$ = **100.00%**.
- **Precision@Top-20% Calculation**:
  - Top 20% ratio = $180$ customers.
  - Actual positive count in top 180 group = $177 / 180$ = **98.33%**.
- **Data Integrity**: Zero training data leaked into validation ranking.

---

## 10. Feature Importance (XGBoost Gain Weight)

1. `checkout_attempts`: **0.1504**
2. `product_interactions`: **0.1343**
3. `checkout_to_cart_ratio`: **0.1176**
4. `cart_value`: **0.0906**
5. `products_viewed`: **0.0599**
6. `cart_item_count`: **0.0583**
7. `orders_count`: **0.0433**
8. `total_order_value`: **0.0396**

---

## 11. Threshold Selection Methodology

Thresholds correspond to validation Precision@Top-K intent tiers on synthetic data:
- **`Hot` Lead Segment**: `lead_probability >= 0.70` (Precision@Top 10% = **100.00%**).
- **`Warm` Lead Segment**: `0.35 <= lead_probability < 0.70` (Precision@Top 20% = **98.33%**).
- **`Cold` Lead Segment**: `lead_probability < 0.35`.

**Production Note**: These thresholds are configurable prototype guidelines. In production, thresholds will be selected dynamically based on sales team outreach capacity and marketing ROI curves.

---

## 12. Exported Model Artifacts

All new e-commerce model artifacts are saved in `model/` without overwriting legacy files:

- `model/ecommerce_xgb_model.pkl`: `XGBClassifier` model binary.
- `model/ecommerce_scaler.pkl`: `StandardScaler` binary.
- `model/ecommerce_feature_columns.pkl`: List of 23 feature column names.
- `model/ecommerce_model_metadata.json`: Complete JSON metadata registry storing metrics for both Logistic Regression and XGBoost.

---

## 13. Transitioning to Real E-Commerce Production Data

When real customer order history accumulates in the production MongoDB (`user_profiles`, `sessions`, `events`, `orders`):
1. Export real `customer_features` records joined with historical 30-day order outcomes.
2. Replace `data/ml/ecommerce_customer_behavior.csv` with real production observations.
3. Rerun `scripts/train_ecommerce_model.py` to retrain and compare Logistic Regression vs XGBoost on real production data.
