# Lead Magnet — Machine Learning Architecture & Model Documentation

---

## 1. Problem Formulation

The machine learning subsystem in Lead Magnet predicts an e-commerce customer's purchase conversion probability in real time from behavioral interaction telemetry. 

The system maps continuous visitor activity (browsing dwell time, session counts, cart actions, checkout attempts) into a normalized conversion score:
$$\text{Lead Score} \in [0, 100], \quad \text{Lead Probability} \in [0.0, 1.0]$$

This score drives dynamic customer segmentation and qualification in the `customer_lead_state` store:
- **Cold** ($< 0.35$): Low engagement / un-qualified lead (`qualification_status: "not_qualified"`).
- **Warm** ($0.35 \le \text{Score} < 0.70$): Moderate consideration / nurturing lead (`qualification_status: "not_qualified"`).
- **Hot** ($\ge 0.70$): High purchase propensity / qualified lead (`qualification_status: "qualified"`).

---

## 2. Model Architecture & Dual Artifact Suites

Lead Magnet maintains two distinct model suites in `model/`: an active e-commerce lead scoring suite and a legacy demo model suite.

### 2.1 Active E-Commerce Model Suite (Canonical Pipeline)
The active scoring pipeline (`backend/ecommerce_model_adapter.py`, `backend/lead_scoring_engine.py`) exclusively utilizes the dedicated 23-feature model artifacts:

| Artifact | Format | Description |
| :--- | :--- | :--- |
| `ecommerce_xgb_model.pkl` | Binary pickle | Trained `XGBClassifier` (150 trees, max depth 4) tuned for binary conversion classification |
| `ecommerce_scaler.pkl` | Binary pickle | Fitted `StandardScaler` fitted on `X_train` for numeric feature normalization |
| `ecommerce_feature_columns.pkl` | Binary pickle | Ordered list of 23 canonical feature column identifiers |
| `ecommerce_model_metadata.json` | JSON | Model version metadata, performance metrics, calibration status, and operational thresholds |

### 2.2 Legacy Demo Model Suite (Deprecated Routes)
The legacy model artifacts remain persisted for backward compatibility with demo routes (`/predict`, `/track`) and the deprecated `leads` collection:

| Artifact | Format | Description |
| :--- | :--- | :--- |
| `xgb_model.pkl` | Binary pickle | Legacy 11-feature XGBoost binary classifier |
| `scaler.pkl` | Binary pickle | Legacy StandardScaler for 11 features |
| `kmeans_model.pkl` | Binary pickle | Scikit-learn KMeans clustering model (3 clusters) |
| `segment_map.pkl` | Binary pickle | Cluster-to-segment dictionary mapping |

> **Note on Architecture Separation**: The real-time customer intelligence pipeline, SocketIO feed, admin drawer, and marketing automation trigger strictly from the 23-feature active e-commerce model and `customer_lead_state`. Legacy routes remain isolated.

---

## 3. Data Provenance & Calibration Disclosures

### 3.1 Training Data Provenance
- **Dataset Path**: `data/ml/ecommerce_customer_behavior.csv` (6,000 samples, 25 columns).
- **Generator**: `scripts/generate_ecommerce_dataset.py` (`seed=42`).
- **Nature of Data**: **100% synthetic**. Feature distributions are drawn from parametric generators (negative binomial, Poisson, gamma, exponential).
- **Target Label Formula**: The label `converted_in_window` is derived from an artificial logistic log-odds equation with additive Gaussian noise ($\sigma = 0.6$):
  $$\text{log\_odds} = -3.5 + 1.15 \cdot \text{checkout\_attempts} + 0.006 \cdot \text{cart\_value} + 0.30 \cdot \text{high\_intent} + 0.10 \cdot \text{interactions} + 0.18 \cdot \text{wishlist} - 0.045 \cdot \text{inactivity} + 0.50 \cdot \text{orders} + \mathcal{N}(0, 0.6)$$
  $$\text{converted\_in\_window} = \mathbf{1}\left(\frac{1}{1 + e^{-\text{log\_odds}}} \ge 0.50\right)$$

### 3.2 Evaluation Metrics & Interpretation Limitations
Evaluation metrics reported during training (`scripts/train_ecommerce_model.py`):
- **Baseline Logistic Regression**: Test ROC-AUC = 0.9764, Test PR-AUC = 0.9685.
- **Primary XGBoost Classifier**: Test ROC-AUC = 0.9680, Test PR-AUC = 0.9575, Test Precision = 0.8848, Test Recall = 0.8654, Test F1 = 0.8750.

> **CRITICAL VALIDITY DISCLOSURE**:
> These high metrics do **not** establish real-world predictive validity. Because the label was generated from a mathematical combination of 7 input features with small Gaussian noise, the model easily learned the synthetic formula.
> - **Calibration Status**: `"uncalibrated_synthetic"`.
> - **Operational Reality**: Model scores represent relative rankings against the synthetic generative rule, not calibrated empirical conversion probabilities. Real-world deployment requires retraining on observed transaction logs and applying Platt scaling or isotonic calibration.

---

## 4. Feature Engineering Pipeline

The active e-commerce model (`v2.0_ecommerce_xgb`) evaluates an immutable **23-dimensional behavioral feature vector** drawn from `customer_features`:

| Index | Feature Name | Type | Description |
| :---: | :--- | :---: | :--- |
| 1 | `sessions_count` | Integer | Total discrete customer sessions |
| 2 | `total_events` | Integer | Cumulative behavioral events (views, clicks, searches, cart actions) |
| 3 | `total_time_spent` | Float | Total browsing dwell time in seconds across sessions |
| 4 | `average_session_duration` | Float | Mean session length: $\frac{\text{total\_time\_spent}}{\text{sessions\_count}}$ (0.0 if sessions = 0) |
| 5 | `page_views_count` | Integer | Total page impressions logged |
| 6 | `days_since_last_activity` | Float | Recency metric: elapsed days since most recent activity |
| 7 | `products_viewed` | Integer | Gross product view events |
| 8 | `unique_products_viewed` | Integer | Distinct products inspected |
| 9 | `product_interactions` | Integer | Product views, clicks, cart adds, and wishlist additions |
| 10 | `search_count` | Integer | Search queries, filters applied, and sort actions |
| 11 | `form_submit_count` | Integer | Lead, contact, or newsletter submissions |
| 12 | `high_intent_page_visits` | Integer | Visits to pricing, demo, contact, or checkout pages |
| 13 | `cart_item_count` | Integer | Active units present in shopping cart |
| 14 | `cart_value` | Float | Total monetary value of items in cart |
| 15 | `wishlist_item_count` | Integer | Active units saved to wishlist |
| 16 | `checkout_attempts` | Integer | Initiations of the checkout flow (`checkout_start`) |
| 17 | `orders_count` | Integer | Historical orders placed |
| 18 | `total_order_value` | Float | Cumulative historical order spend |
| 19 | `average_order_value` | Float | Mean value per order: $\frac{\text{total\_order\_value}}{\max(1, \text{orders\_count})}$ |
| 20 | `cart_to_session_ratio` | Float | Derived: $\frac{\text{cart\_item\_count}}{\text{sessions\_count}}$ (0.0 if sessions = 0) |
| 21 | `checkout_to_cart_ratio` | Float | Derived: $\frac{\text{checkout\_attempts}}{\max(1.0, \text{cart\_item\_count})}$ |
| 22 | `high_intent_ratio` | Float | Derived: $\frac{\text{high\_intent\_page\_visits}}{\max(1.0, \text{page\_views\_count})}$ |
| 23 | `product_interaction_density` | Float | Derived: $\frac{\text{product\_interactions}}{\text{sessions\_count}}$ (0.0 if sessions = 0) |

---

## 5. Inference & Explainability Integration

### 5.1 Real-Time Adapter (`backend/ecommerce_model_adapter.py`)
- **Latency**: $< 15\text{ ms}$ per customer prediction.
- **Contract**: Rejects missing base features, non-numeric values, booleans, and NaNs with `ValueError`.
- **Output Schema**:
  ```json
  {
    "customer_id": "cust_12345",
    "lead_probability": 0.8421,
    "lead_score": 84,
    "lead_segment": "Hot",
    "model_version": "v2.0_ecommerce_xgb",
    "scored_at": "2026-10-23T20:15:30.123456+00:00",
    "threshold_disclaimer": "Provisional synthetic-data thresholds. Hot >= 0.70, Warm 0.35-0.70, Cold < 0.35."
  }
  ```

### 5.2 Heuristic Model Explainability (`backend/model_explainability_service.py`)
Provides deterministic score attribution for the admin customer drawer:
- **Methodology**: Combines global XGBoost feature importances with normalized feature deviations (z-scores relative to population means).
- **Polarity Handling**: Features with negative behavioral polarity (`days_since_last_activity`) have their directional sign inverted (`polarity = -1.0`), ensuring prolonged inactivity correctly registers as a negative score contributor while recent activity registers as positive.
- **Classification**: Explicitly labeled as a deterministic heuristic approximation (`is_heuristic: true`), not a per-prediction TreeSHAP local causal attribution.

---

## 6. Model Retraining Safety & Reproducibility

To re-execute training:
```bash
python scripts/generate_ecommerce_dataset.py
python scripts/validate_ecommerce_dataset.py
python scripts/train_ecommerce_model.py
```
`scripts/train_ecommerce_model.py` utilizes `build_model_metadata()` to ensure safety disclosures (`calibration_status: "uncalibrated_synthetic"` and threshold rationales) are permanently preserved in `model/ecommerce_model_metadata.json`.
