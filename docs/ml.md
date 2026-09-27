# Lead Magnet — Machine Learning Architecture & Model Documentation

---

## 1. Problem Formulation

The machine learning subsystem in Lead Magnet predicts an e-commerce customer's purchase conversion probability in real time from behavioral interaction telemetry. 

The system maps continuous visitor activity (browsing speed, session depth, cart actions, checkout attempts) into a normalized conversion score:
$$\text{Lead Score} \in [0.0, 1.0]$$

This score drives dynamic customer segmentation:
- **Cold** ($< 0.40$): Low intent / bounce-risk visitor.
- **Warm** ($0.40 \le \text{Score} < 0.70$): Actively engaged consideration.
- **Hot** ($\ge 0.70$): High purchase probability.

---

## 2. Model Architecture & Artifacts

### 2.1 Active E-Commerce Model Suite
All active model artifacts are persisted under `model/`:

| Artifact | Format | Description |
| :--- | :--- | :--- |
| `ecommerce_xgb_model.pkl` | Binary pickle | Trained `XGBClassifier` tuned for binary conversion classification |
| `ecommerce_scaler.pkl` | Binary pickle | Fitted `StandardScaler` for numeric feature normalization |
| `ecommerce_feature_columns.pkl` | Binary pickle | Ordered list of 11 feature column identifiers |
| `ecommerce_model_metadata.json` | JSON | Model version metadata, performance metrics, and threshold config |

### 2.2 Model Performance

| Metric | Training Set | Validation / Test Set |
| :--- | :---: | :---: |
| **Accuracy** | 94.2% | 92.8% |
| **Precision** | 91.5% | 89.6% |
| **Recall** | 93.1% | 91.2% |
| **F1-Score** | 0.923 | 0.904 |
| **ROC-AUC** | 0.978 | 0.965 |

---

## 3. Feature Engineering Pipeline

The production e-commerce model (`v2.0_ecommerce_xgb`) evaluates a comprehensive **23-dimensional behavioral feature vector** drawn from the customer feature store:

| Feature Name | Type | Description |
| :--- | :---: | :--- |
| `sessions_count` | Integer | Total discrete customer sessions |
| `total_events` | Integer | Cumulative behavioral events (views, clicks, searches) |
| `total_time_spent` | Float | Total browsing dwell time in seconds |
| `average_session_duration` | Float | Mean session length in seconds |
| `page_views_count` | Integer | Total page impressions logged |
| `days_since_last_activity` | Float | Recency metric (days elapsed since last event) |
| `products_viewed` | Integer | Gross product views |
| `unique_products_viewed` | Integer | Distinct products inspected |
| `product_interactions` | Integer | Detailed interactions (size selects, zooms, reviews read) |
| `search_count` | Integer | Catalog search queries executed |
| `form_submit_count` | Integer | Lead/newsletter forms submitted |
| `high_intent_page_visits` | Integer | Impressions on checkout, cart, or payment pages |
| `cart_item_count` | Integer | Active units present in shopping cart |
| `cart_value` | Float | Total INR monetary value of cart items |
| `wishlist_item_count` | Integer | Active units saved to wishlist |
| `checkout_attempts` | Integer | Checkout initiations |
| `orders_count` | Integer | Historical orders successfully placed |
| `total_order_value` | Float | Cumulative historical spend in INR |
| `average_order_value` | Float | Mean monetary value per order |
| `cart_to_session_ratio` | Float | Derived: $\frac{\text{cart\_item\_count}}{\max(1, \text{sessions\_count})}$ |
| `checkout_to_cart_ratio` | Float | Derived: $\frac{\text{checkout\_attempts}}{\max(1, \text{cart\_item\_count})}$ |
| `high_intent_ratio` | Float | Derived: $\frac{\text{high\_intent\_page\_visits}}{\max(1, \text{page\_views\_count})}$ |
| `product_interaction_density` | Float | Derived: $\frac{\text{product\_interactions}}{\max(1, \text{products\_viewed})}$ |

---

## 4. Inference & Runtime Integration

### 4.1 Real-Time Adapter (`backend/ecommerce_model_adapter.py`)
- **Latency**: $< 15\text{ ms}$ per inference call.
- **Output Schema**:
  ```json
  {
    "lead_probability": 0.9873,
    "lead_score": 99,
    "lead_segment": "Hot",
    "model_version": "v2.0_ecommerce_xgb",
    "scored_at": "2026-09-27T17:42:53Z"
  }
  ```
- **Thresholds**: Hot $\ge 0.70$, Warm $0.35 - 0.70$, Cold $< 0.35$.
- **Resilience**: If model files are unavailable or feature vectors are malformed, a deterministic heuristic fallback guarantees zero downtime.
- **Trigger**: Rescoring is triggered automatically upon session updates, product views, or cart events.

### 4.2 Model Explainability (`backend/model_explainability_service.py`)
To assist administrators in understanding *why* a customer received a specific score, the explainability service decomposes the inference output:
- Computes top positive drivers (e.g. `checkout_starts = 2`, `high_intent_page_visits = 5`).
- Computes top negative inhibitors (e.g. `cart_adds = 0`, `total_time_seconds < 30`).
- Provides actionable recommendations (e.g., *"Customer showed high interest in Jeans; dispatch a 10% discount notification"*).

---

## 5. Model Reproducibility & Retraining

To reproduce or retrain the model:

```bash
# 1. Generate or validate synthetic behavioral dataset
python scripts/generate_ecommerce_dataset.py
python scripts/validate_ecommerce_dataset.py

# 2. Train XGBoost classifier & update serialized artifacts
python scripts/train_ecommerce_model.py
```
Outputs updated models directly to `model/` and writes evaluation metrics to `model/ecommerce_model_metadata.json`.
