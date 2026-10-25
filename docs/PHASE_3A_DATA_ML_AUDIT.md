# Phase 3A: Lead Magnet Data Quality and Machine Learning Validity Audit

**Audit Date**: October 2026  
**Auditor**: Senior Software Architect & ML Engineering Team  
**Scope**: Read-Only Audit of Customer Data Provenance, Feature Engineering, Lead Scoring Model Validity, and Inference Pipelines  
**Status**: Completed — Awaiting Approval for Phase 3B Remediation  

---

## 1. Executive Summary

Lead Magnet's customer intelligence and lead-scoring subsystem was audited to determine whether customer behavioral data, feature aggregation, training pipelines, and scoring models operate reliably, consistently, and with genuine predictive validity.

The audit established that the active scoring system is powered by a dedicated 23-feature XGBoost classifier (`model/ecommerce_xgb_model.pkl`) and customer-level state store (`customer_lead_state`), successfully decoupled from the legacy 11-feature demo model (`model/xgb_model.pkl`). Feature names, order, types, and scaling are strictly synchronized between `scripts/train_ecommerce_model.py` and `backend/ecommerce_model_adapter.py`. Phase 2 telemetry additions (`product_view`, `product_click`, `checkout_start`, `remove_from_cart`) are fully integrated into feature aggregation.

However, the audit revealed **two confirmed defects** and **several high-impact validity risks**:
1. **Confirmed Defect (Admin Overview Display)**: In `backend/admin_intelligence_service.py` (lines 96–98), `warm_leads` and `cold_leads` counts are filtered on `qualification_status: "qualified"`. Because `qualification_status` is defined as `qualified` strictly when `lead_probability >= 0.70` (the exact definition of `"Hot"`), warm and cold leads never qualify. Consequently, the admin intelligence overview always reports `warm: 0` and `cold: 0`, contradicting the segment distribution endpoint.
2. **Confirmed Defect (Model Explainability Direction Bug)**: In `backend/model_explainability_service.py` (lines 139–140), `days_since_last_activity` is multiplied by its positive feature importance without inverting the z-score sign. Inactive customers are erroneously presented to admins as having inactivity as a *positive driver* toward qualification.
3. **High Validity Risk (Synthetic Label Circularity & Uncalibrated Scores)**: The training dataset `data/ml/ecommerce_customer_behavior.csv` was generated synthetically (`scripts/generate_ecommerce_dataset.py`) where the target label `converted_in_window` was calculated from a deterministic log-odds equation using 7 input features with small additive Gaussian noise. The reported test ROC-AUC of 0.968 and PR-AUC of 0.958 do not demonstrate real-world generalization; they merely confirm that XGBoost learned the synthetic equation. Scores represent rankings relative to the synthetic rule, not calibrated real-world conversion probabilities.
4. **Architectural Divergence**: Legacy endpoints (`/predict`, `/track`, and `/api/admin/leads`) still reference the legacy 11-feature model and the deprecated `leads` collection, creating dual paths that must be aligned in remediation.

All findings are documented below with exact file paths, line numbers, categorized impact levels, and a comprehensive remediation and verification plan for Phase 3B.

---

## 2. Source Files and Exact Paths Inspected

The audit inspected the following files in the Lead Magnet repository:

| Component / Subsystem | Source Path | Key Line Ranges Inspected |
| :--- | :--- | :--- |
| **Dataset Generator** | `scripts/generate_ecommerce_dataset.py` | Lines 14–117 (generator), 71–88 (label formula) |
| **Dataset Validator** | `scripts/validate_ecommerce_dataset.py` | Lines 12–71 (integrity, null, correlation, and leakage checks) |
| **Model Training** | `scripts/train_ecommerce_model.py` | Lines 40–76 (data prep, scaling), 96–136 (XGBoost), 144–199 (artifact export) |
| **Model Metadata** | `model/ecommerce_model_metadata.json` | Lines 1–107 (hyperparameters, metrics, calibration status, thresholds) |
| **Model Inference Adapter** | `backend/ecommerce_model_adapter.py` | Lines 24–55 (loaders), 57–85 (vocabularies), 87–107 (derived), 109–196 (prediction) |
| **Feature Aggregation Store** | `backend/customer_feature_service.py` | Lines 79–208 (queries), 209–281 (metrics), 282–388 (recency & output) |
| **Customer Lead State** | `backend/customer_lead_state_service.py` | Lines 16–17 (threshold), 66–188 (sync, transitions, marketing automation trigger) |
| **Lead Scoring Orchestrator** | `backend/lead_scoring_engine.py` | Lines 25–81 (debounce, feature upsert, inference, sync, history, WebSocket) |
| **Model Explainability** | `backend/model_explainability_service.py` | Lines 58–152 (directional z-score contribution), 153–182 (payload format) |
| **Behavior Event Service** | `backend/behavior_event_service.py` | Lines 13–36 (supported events), 89–116 (build event), 119–149 (log event) |
| **Identity Service** | `backend/identity_service.py` | Lines 12–108 (anonymous resolution, profile merge, rescore customer) |
| **Admin Intelligence** | `backend/admin_intelligence_service.py` | Lines 54–136 (overview metrics), 703–731 (lead distribution) |
| **Legacy Prediction Service** | `backend/prediction_service.py` | Lines 17–46 (legacy artifacts, KMeans clustering, segment mapping) |
| **Flask Application Gateway** | `backend/app.py` | Lines 535–555 (`/predict`), 780–820 (`/track`), 1006–1030 (event profile update), 1075–1102 (`/api/session/event`), 1228–1275 (`/api/leads/score`, `/api/customers/<id>/score`), 1378–1405 (`/api/admin/leads`) |
| **Pipeline & ML Tests** | `backend/tests/test_ecommerce_ml_pipeline.py` | Lines 12–120 (dataset integrity, artifact loading, probability invariants) |
| **Inference Tests** | `backend/tests/test_ecommerce_lead_inference.py` | Lines 53–294 (column order, validation rejection, auth isolation, immutability) |
| **Lead State Tests** | `backend/tests/test_customer_lead_state.py` | Lines 75–200 (indexes, qualification transitions, idempotency) |

---

## 3. Data Provenance and Label Definition

### 3.1 Provenance Trace
- **File**: `data/ml/ecommerce_customer_behavior.csv` (6,000 samples, 25 columns).
- **Generator**: `scripts/generate_ecommerce_dataset.py`, executed via `generate_ecommerce_dataset(num_samples=6000, seed=42)`.
- **Nature of Observations**: Completely synthetic. Customer IDs (`cust_0001` through `cust_6000`), engagement statistics, product actions, cart values, and order histories are drawn from parametric probability distributions (negative binomial, Poisson, gamma, exponential, and uniform).

### 3.2 Target Label Definition
The target variable is `converted_in_window` $\in \{0, 1\}$. It is defined in `scripts/generate_ecommerce_dataset.py` (lines 73–88) using the following parametric logistic log-odds formulation:

$$\text{noise} \sim \mathcal{N}(\mu = 0.0, \sigma = 0.6)$$

$$\begin{aligned}
\text{log\_odds} = &-3.5 \\
&+ 1.15 \times \text{checkout\_attempts} \\
&+ 0.006 \times \text{cart\_value} \\
&+ 0.30 \times \text{high\_intent\_page\_visits} \\
&+ 0.10 \times \text{product\_interactions} \\
&+ 0.18 \times \text{wishlist\_item\_count} \\
&- 0.045 \times \text{days\_since\_last\_activity} \\
&+ 0.50 \times \text{orders\_count} \\
&+ \text{noise}
\end{aligned}$$

$$\text{conversion\_prob} = \frac{1}{1 + e^{-\text{log\_odds}}}$$

$$\text{converted\_in\_window} = \begin{cases} 1 & \text{if } \text{conversion\_prob} \ge 0.50 \\ 0 & \text{if } \text{conversion\_prob} < 0.50 \end{cases}$$

### 3.3 What Reported Accuracy and AUC Actually Establish
- In `scripts/train_ecommerce_model.py` and `model/ecommerce_model_metadata.json`:
  - **Baseline Logistic Regression**: Test ROC-AUC = 0.9764, Test PR-AUC = 0.9685.
  - **Primary XGBoost Classifier**: Test ROC-AUC = 0.9680, Test PR-AUC = 0.9575, Test Precision = 0.8848, Test Recall = 0.8654, Test F1 = 0.8750, Precision@Top-10% = 1.000.
- **Critical Assessment**:
  - These metrics **do not establish real-world predictive validity**.
  - Because the target label is an algebraic combination of 7 input features with a small additive Gaussian disturbance ($\sigma=0.6$), a linear model (Logistic Regression) or gradient-boosted decision tree (XGBoost) easily recovers the generative hyperplane.
  - The metrics prove **internal computational consistency and model trainability on synthetic rules**, but provide zero evidence of how the model will perform on real human visitors with complex intent, browsing interruptions, seasonal demand, price sensitivity, or marketing attribution noise.

---

## 4. Target Leakage, Circularity, and Validation Findings

### 4.1 Feature Leakage & Formula Circularity
- **Circularity**: The 7 features directly driving the log-odds formula (`checkout_attempts`, `cart_value`, `high_intent_page_visits`, `product_interactions`, `wishlist_item_count`, `days_since_last_activity`, `orders_count`) are provided directly to the model as input features.
- Furthermore, 3 of the 4 derived features (`checkout_to_cart_ratio`, `high_intent_ratio`, `product_interaction_density`) encode these exact variables in their numerators.
- **Evaluation of Existing Leakage Checks**:
  - In `scripts/validate_ecommerce_dataset.py` (lines 56–66), feature-target correlations are checked to ensure no single feature has $|r| \ge 0.95$. The maximum correlation found is `checkout_attempts` ($r \approx 0.66$).
  - While this satisfies simple bivariate leakage constraints, it fails to account for multivariate circularity: the combination of inputs deterministically synthesizes the output label.

### 4.2 Dataset Integrity & Partitions
- **Duplicates**: Zero duplicate customer IDs (`df['customer_id'].duplicated().sum() == 0`).
- **Missing Values**: Zero null or NaN values in the generated CSV.
- **Value Bounds**: Zero negative values in numeric counts and currency fields.
- **Partition Contamination**:
  - In `scripts/train_ecommerce_model.py` (lines 62–67), the dataset was split into Train (70% = 4,200), Validation (15% = 900), and Test (15% = 900) using stratified sampling on `y` with fixed seeds (`random_state=42`).
  - No customer ID overlap exists between splits.
  - `StandardScaler` was fitted strictly on `X_train` (`scaler.fit_transform(X_train)`) and then applied to `X_val` and `X_test` via `scaler.transform()`, avoiding standard scaler data leakage.
  - However, because all samples are generated from the same parameter distribution without temporal or customer-cohort separation, validation and test splits suffer from synthetic distribution homogeneity.

---

## 5. Training and Inference Consistency Findings

### 5.1 Artifact Identity and Mapping
The system maintains two distinct models in `model/`:
1. **Legacy Demo Model**: `model/xgb_model.pkl` (11 features), `model/scaler.pkl`, `model/kmeans_model.pkl`, `model/segment_map.pkl`.
2. **Active E-Commerce Lead Model**: `model/ecommerce_xgb_model.pkl` (23 features), `model/ecommerce_scaler.pkl`, `model/ecommerce_feature_columns.pkl`, `model/ecommerce_model_metadata.json`.

The active e-commerce pipeline exclusively references the dedicated artifacts via `backend/ecommerce_model_adapter.py`.

### 5.2 Feature Name, Order, and Type Alignment
Training (`scripts/train_ecommerce_model.py:53`) and inference (`backend/ecommerce_model_adapter.py:42, 143`) were compared across all 23 features:

| Index | Feature Name | Generator / Training Type | Inference Adapter Handling | Match? |
| :---: | :--- | :--- | :--- | :---: |
| 1 | `sessions_count` | `int` | `float(val)` | YES |
| 2 | `total_events` | `int` | `float(val)` | YES |
| 3 | `total_time_spent` | `float` | `float(val)` | YES |
| 4 | `average_session_duration` | `float` | `float(val)` | YES |
| 5 | `page_views_count` | `int` | `float(val)` | YES |
| 6 | `days_since_last_activity` | `float` | `float(val)` (defaults to 0.0 if None) | YES |
| 7 | `products_viewed` | `int` | `float(val)` | YES |
| 8 | `unique_products_viewed` | `int` | `float(val)` | YES |
| 9 | `product_interactions` | `int` | `float(val)` | YES |
| 10 | `search_count` | `int` | `float(val)` | YES |
| 11 | `form_submit_count` | `int` | `float(val)` | YES |
| 12 | `high_intent_page_visits` | `int` | `float(val)` | YES |
| 13 | `cart_item_count` | `int` | `float(val)` | YES |
| 14 | `cart_value` | `float` | `float(val)` | YES |
| 15 | `wishlist_item_count` | `int` | `float(val)` | YES |
| 16 | `checkout_attempts` | `int` | `float(val)` | YES |
| 17 | `orders_count` | `int` | `float(val)` | YES |
| 18 | `total_order_value` | `float` | `float(val)` | YES |
| 19 | `average_order_value` | `float` | `float(val)` | YES |
| 20 | `cart_to_session_ratio` | `float` (derived) | `compute_derived_features()` | YES |
| 21 | `checkout_to_cart_ratio` | `float` (derived) | `compute_derived_features()` | YES |
| 22 | `high_intent_ratio` | `float` (derived) | `compute_derived_features()` | YES |
| 23 | `product_interaction_density` | `float` (derived) | `compute_derived_features()` | YES |

- **Scaler Transformation**: Both training and inference use `StandardScaler.transform()`.
- **Array Dimensions & Names**: In `ecommerce_model_adapter.py:170`, `X_raw = pd.DataFrame([vector], columns=feature_cols)` preserves exact feature column names before scaling, eliminating scikit-learn warnings.
- **Missing-Value Rejection**: In `ecommerce_model_adapter.py:126–162`, missing required base features, non-numeric values, boolean types, and `NaN`/`Inf` floats raise explicit `ValueError` exceptions. Nullable `days_since_last_activity` is safely defaulted to `0.0` if `None`.

---

## 6. Feature Engineering and Telemetry Pipeline Findings

### 6.1 End-to-End Event Ingestion & Feature Aggregation
The feature aggregation flow operates as follows:
```
Browser / Client Event
        │
        ▼ (POST /api/session/event)
log_behavior_event() (behavior_event_service.py)
        │
        ▼
update_profile_from_event() (app.py:1006)
        │
        ▼ (if user_id present)
rescore_customer() (lead_scoring_engine.py:25)
        │
        ▼ (debounced 1.0s window)
upsert_customer_features() (customer_feature_service.py:390)
        │
        ▼
aggregate_customer_features() (customer_feature_service.py:79)
        │
        ▼
predict_customer_features() (ecommerce_model_adapter.py:109)
        │
        ▼
sync_customer_lead_state() (customer_lead_state_service.py:66)
        │
        ▼ (if newly qualified: Hot >= 0.70)
marketing_automation_service.py & SocketIO emit
```

### 6.2 Verification of Phase 2 Telemetry Integration
The four telemetry events added in Phase 2 were traced through `customer_feature_service.py`:
1. `product_view`:
   - Increments `products_viewed` (`len([e for e in events if e.get("event_type") == "product_view"])`, line 221).
   - Contributes to `unique_products_viewed` via product ID extraction (line 228).
   - Increments `product_interactions` (line 230).
   - Increments `total_events` (line 216).
2. `product_click`:
   - Included in `product_interaction_types = {"product_view", "product_click", "add_to_cart", "wishlist_add"}` (line 230).
   - Increments `total_events` (line 216).
3. `checkout_start`:
   - Directly populates `checkout_attempts` (`sum(1 for e in events if e.get("event_type") == "checkout_start")`, line 242).
   - Updates `last_checkout_action_at` timestamp (lines 339–346).
   - Increments `total_events` (line 216).
4. `remove_from_cart`:
   - Included in `cart_events` for `last_cart_action_at` recency tracking (line 323).
   - Increments `total_events` (line 216).

All Phase 2 telemetry events actively contribute to the intended canonical customer features.

### 6.3 Anonymous-to-Registered Identity Merging
- In `backend/identity_service.py:resolve_anonymous_identity()`:
  - Links all anonymous sessions and events to the registered `user_id`.
  - Appends anonymous IDs to `user_profiles.anonymous_ids`.
  - Merges cart items and wishlist items.
  - Deletes orphaned anonymous records in `customer_features` (`customer_features_collection.delete_many({"customer_id": anonymous_id})`, line 91).
  - Triggers `rescore_customer(user_id, db)` (line 96).
  - In `customer_feature_service.py:122–165`, both `canonical_id` and all associated `anonymous_ids` are queried across `sessions`, `events`, `cart`, `wishlist`, and `orders`.
  - Merging is complete and prevents stale feature records or fragmented identity state.

### 6.4 Zero Denominators and Arithmetic Safety
All ratios in `customer_feature_service.py` and `ecommerce_model_adapter.py` implement defensive division:
- `average_session_duration = (total_time_spent / sessions_count) if sessions_count > 0 else 0.0`
- `average_order_value = (total_order_value / orders_count) if orders_count > 0 else 0.0`
- `cart_to_session_ratio = round(cart_items / sessions, 3) if sessions > 0 else 0.0`
- `checkout_to_cart_ratio = round(checkout_attempts / max(cart_items, 1.0), 3)`
- `high_intent_ratio = round(high_intent / max(page_views, 1.0), 3)`
- `product_interaction_density = round(product_interactions / sessions, 3) if sessions > 0 else 0.0`

No unhandled `ZeroDivisionError` risks exist in feature computation.

---

## 7. Scoring, Segmentation, and Calibration Findings

### 7.1 Score Persistence and Pipeline Synchronization
- Model output: `lead_probability = float(model.predict_proba(X_scaled)[0][1])` $\in [0.0, 1.0]$.
- Transformed integer score: `lead_score = int(round(lead_probability * 100))` $\in [0, 100]$.
- Segments:
  - `Hot`: `prob >= 0.70`
  - `Warm`: `0.35 <= prob < 0.70`
  - `Cold`: `prob < 0.35`
- Qualification rule: `qualification_status = "qualified" if prob >= 0.70 else "not_qualified"` (`customer_lead_state_service.py:103`).
- Single source of truth: `customer_lead_state` collection stores one canonical document per customer with `lead_probability`, `lead_score`, `lead_segment`, `qualification_status`, `qualification_transition`, and history timestamps.

### 7.2 Calibration Status
- **Empirical Status**: **Uncalibrated synthetic**.
- In `model/ecommerce_model_metadata.json:4`:
  ```json
  "calibration_status": "uncalibrated_synthetic"
  ```
- The scores do not represent calibrated probabilities that a customer will convert in a real-world e-commerce store. They represent relative rankings against the synthetic generator formula.
- **Evidence**: No Platt scaling, isotonic regression, or empirical calibration on real conversion data has been performed.

### 7.3 Discrepancies and Confirmed Defects

#### Confirmed Defect 1: Admin Intelligence Overview Zero-Count Filter
- **Location**: `backend/admin_intelligence_service.py`, lines 96–98:
  ```python
  total_qualified = lead_state_col.count_documents({"qualification_status": "qualified"})
  hot_leads = lead_state_col.count_documents({"qualification_status": "qualified", "lead_segment": "Hot"})
  warm_leads = lead_state_col.count_documents({"qualification_status": "qualified", "lead_segment": "Warm"})
  cold_leads = lead_state_col.count_documents({"qualification_status": "qualified", "lead_segment": "Cold"})
  ```
- **Mechanism**:
  - `qualification_status` is `"qualified"` strictly when `lead_probability >= 0.70`.
  - The definition of `Hot` is `lead_probability >= 0.70`.
  - Therefore, every document with `lead_segment: "Warm"` has `qualification_status: "not_qualified"`.
  - Every document with `lead_segment: "Cold"` has `qualification_status: "not_qualified"`.
- **Result**:
  - `warm_leads` always evaluates to `0`.
  - `cold_leads` always evaluates to `0`.
  - The admin overview payload returns `"leads": {"total_qualified": N, "hot": N, "warm": 0, "cold": 0}`.
  - This contradicts `get_lead_distribution()` (lines 713–715), which counts all customers by segment regardless of qualification.

#### Confirmed Defect 2: Model Explainability Direction Sign Inversion
- **Location**: `backend/model_explainability_service.py`, lines 139–140:
  ```python
  # Contribution = importance * z_score direction
  # For "days_since_last_activity", higher value = negative for lead score
  contribution = importance * z_score
  ```
- **Mechanism**:
  - XGBoost feature importance is non-negative ($\ge 0$).
  - For an inactive customer with 40 days of inactivity (sample mean is $\approx 9.88$, scale is $\approx 9.70$), the z-score is positive ($z \approx +3.1$).
  - In `generate_ecommerce_dataset.py:81`, the formula specifies `- 0.045 * days_since_last_activity` (negative effect on conversion).
  - However, line 140 computes `contribution = importance * z_score` without negating the sign.
- **Result**:
  - `contribution` is positive ($> 0$), and line 150 assigns `"direction": "positive"`.
  - In the admin dashboard, high inactivity is displayed as a *positive contributor* driving qualification.

---

## 8. Categorized Findings

### Critical Findings

#### [C-1] Admin Overview Segment Discrepancy (Confirmed Defect)
- **Path**: `backend/admin_intelligence_service.py:96-98`
- **Issue**: `warm_leads` and `cold_leads` queries include `"qualification_status": "qualified"`, resulting in permanent `0` values in the admin overview API.
- **Impact**: Administrative dashboard displays broken lead distribution figures, misrepresenting active customer intelligence.

#### [C-2] Explainability Inactivity Sign Inversion (Confirmed Defect)
- **Path**: `backend/model_explainability_service.py:139-150`
- **Issue**: Direction calculation fails to invert sign for negative coefficients (`days_since_last_activity`), marking prolonged inactivity as a positive qualification driver.
- **Impact**: Explanations presented to sales reps and administrators recommend action based on reversed logic.

---

### High Findings

#### [H-1] Synthetic Label Circularity and False Confidence in Model Metrics (Risk)
- **Path**: `scripts/generate_ecommerce_dataset.py:73-88`, `scripts/train_ecommerce_model.py:115-135`
- **Issue**: Target label is a deterministic function of 7 training features with slight Gaussian noise. High ROC-AUC (0.968) and PR-AUC (0.958) do not measure real-world performance.
- **Impact**: Stakeholders may believe the model is production-ready for real-world traffic when it is only fitted to an artificial formula.

#### [H-2] Dual Architecture Divergence Between Legacy and Active Models (Risk)
- **Path**: `backend/app.py:535-555`, `backend/app.py:780-820`, `backend/app.py:1378-1405`, `backend/prediction_service.py:17-46`
- **Issue**: `/predict`, `/track`, and `/api/admin/leads` operate on legacy 11-feature artifacts and the `leads` collection, while the event-driven system operates on the 23-feature model and `customer_lead_state`.
- **Impact**: Confusing dual state stores, legacy endpoint deprecation ambiguity, and fragmented lead exports.

---

### Medium Findings

#### [M-1] Retraining Script Erases Safety Metadata Disclosures (Risk)
- **Path**: `scripts/train_ecommerce_model.py:155-195`
- **Issue**: Running the training script regenerates `ecommerce_model_metadata.json` without `"calibration_status": "uncalibrated_synthetic"` or threshold selection rationale.
- **Impact**: Critical safety invariants and audit metadata are lost upon model retraining.

#### [M-2] Out-of-Distribution Vulnerability for Zero-Session Customers (Risk)
- **Path**: `scripts/generate_ecommerce_dataset.py:20`, `backend/ecommerce_model_adapter.py:170-175`
- **Issue**: Synthetic generator strictly generates `sessions_count >= 1`. A newly registered customer with 0 sessions receives a z-score of $-1.43$, an unrepresented region in training.
- **Impact**: Cold-start leads could produce unpredictable probability spikes.

#### [M-3] Documentation vs. Implementation Inconsistencies (Contradiction)
- **Path**: `README.md:18`, `docs/ml.md:13`, `backend/ecommerce_model_adapter.py:178`
- **Issue**: `README.md` documents 11 features; `docs/ml.md` states Warm is $0.40 - 0.70$ and Cold $< 0.40$; implementation uses 23 features with Warm at $0.35 - 0.70$ and Cold $< 0.35$.
- **Impact**: Contradictory operator expectations and test confusion.

---

### Low Findings

#### [L-1] Scikit-Learn Pickle Deserialization Version Warning (Minor)
- **Path**: `model/ecommerce_scaler.pkl`
- **Issue**: Saved with scikit-learn 1.9.1, emitting `InconsistentVersionWarning` when loaded with version 1.9.0 in current venv.
- **Impact**: Cosmetic warning log on first model import.

---

## 9. Specific Remediation Recommendations (Ordered by Impact)

1. **Remedy C-1 (Admin Overview Segment Counts)**:
   - In `backend/admin_intelligence_service.py:96-98`, decouple segment counts from qualification status:
     ```python
     hot_leads = lead_state_col.count_documents({"lead_segment": "Hot"})
     warm_leads = lead_state_col.count_documents({"lead_segment": "Warm"})
     cold_leads = lead_state_col.count_documents({"lead_segment": "Cold"})
     ```
   - This aligns `get_intelligence_overview()` with `get_lead_distribution()` and correctly displays customer counts across all three segments.

2. **Remedy C-2 (Explainability Inactivity Sign Correction)**:
   - In `backend/model_explainability_service.py:138-140`, explicitly handle directional signs for negative features:
     ```python
     NEGATIVE_IMPACT_FEATURES = {"days_since_last_activity"}
     direction_sign = -1.0 if col in NEGATIVE_IMPACT_FEATURES else 1.0
     contribution = importance * z_score * direction_sign
     ```
   - Ensure `direction` is `"positive"` only when the feature actually increases qualification likelihood.

3. **Remedy H-1 & M-1 (Model Calibration & Metadata Transparency)**:
   - Update `scripts/train_ecommerce_model.py` to preserve `"calibration_status": "uncalibrated_synthetic"`, model purpose disclosures, and calibration disclaimers whenever artifacts are saved.
   - Maintain the threshold disclaimer in `ecommerce_model_adapter.py` returning `"uncalibrated_synthetic"` status to API consumers.

4. **Remedy H-2 (Consolidate Admin Lead Queries to Canonical Store)**:
   - In `backend/app.py:1378-1405` and `backend/app.py:1565-1590`, transition admin lead listing and export endpoints to read from `customer_lead_state` (with customer profile enrichment) rather than the legacy `leads` collection.
   - Mark legacy routes (`/predict`, `/track`) with explicit deprecation notices while preserving backward compatibility.

5. **Remedy M-2 (Cold-Start & Zero-Session Defensive Feature Clipping)**:
   - In `ecommerce_model_adapter.py:compute_derived_features()` and vector construction, ensure that when `sessions_count == 0`, `cart_to_session_ratio` and `product_interaction_density` are safely clamped and do not project extreme negative z-scores.

6. **Remedy M-3 (Documentation Synchronization)**:
   - Update `README.md` and `docs/ml.md` to document the authoritative 23-feature schema, exact threshold boundaries ($0.70$ / $0.35$), and uncalibrated synthetic status.

---

## 10. Verification Plan for Phase 3B

When Phase 3B is authorized, all remediations will be verified with targeted unit and integration tests:

| Test Target | Proposed Test File | Verification Objective |
| :--- | :--- | :--- |
| **Admin Overview Counts** | `backend/tests/test_phase3_data_ml_remediation.py` | Create Warm, Cold, and Hot lead state records; verify `get_intelligence_overview()["leads"]` returns non-zero counts matching actual document totals. |
| **Explainability Sign Inversion** | `backend/tests/test_phase3_data_ml_remediation.py` | Pass a customer with 60 days of inactivity; verify `explain_lead_score()` marks `days_since_last_activity` with `direction: "negative"` and contribution $< 0$. |
| **Metadata Preservation** | `backend/tests/test_phase3_data_ml_remediation.py` | Verify `ecommerce_model_metadata.json` retains `calibration_status: "uncalibrated_synthetic"` and recommended thresholds. |
| **Zero-Session Invariant** | `backend/tests/test_phase3_data_ml_remediation.py` | Score a customer with `sessions_count = 0`; verify prediction succeeds without errors and produces valid score $\in [0, 100]$ and Cold/Warm segment. |
| **Regression Suite** | Full test runner (`run_tests.py`) | Execute all 700+ tests across the entire test suite; confirm zero failures, zero regressions, and full test isolation. |

---

## 11. Safety Invariants Confirmation

During the Phase 3A read-only audit:
- **No application code, models, or datasets were modified.**
- **No external network or communication services were contacted.**
- **Local MongoDB Atlas isolation and dry-run safety defaults were maintained.**
- **Git working tree state was preserved intact.**

**Audit Status**: Complete. Awaiting user review and authorization before beginning Phase 3B.
