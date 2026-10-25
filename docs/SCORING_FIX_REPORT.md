# Lead Scoring Architecture & Production Fix Report

## 1. Executive Summary

This document describes the resolution of the false-positive lead scoring issue (where brand-new accounts or login-only visits were scored as **75 / Hot / Qualified**) and the stabilization of the lead scoring engine.

The system now runs on a **pure, direct XGBoost Machine Learning pipeline** (`model/ecommerce_xgb_model.pkl`) coupled with:
1. **Frontend `localStorage` user isolation**: Eliminates browser state leakage across anonymous and authenticated sessions.
2. **Authoritative customer lifecycle tracking**: Clear distinction between `prospect`, `converted` (1 order), and `repeat_customer` (2+ orders).
3. **Decay half-lives and background scheduler**: Recency decay that operates automatically via background daemon jobs.
4. **Safe administration and migration CLI**: `scripts/rescore_customers.py` replaces legacy unvalidated scripts.

---

## 2. Root Cause Analysis

Two coupled defects produced the false-positive "75 / Hot / Qualified" score on newly created accounts:

| Defect | Location | Mechanism | Remediation |
|---|---|---|---|
| **Artificial Scoring Floor** | [ecommerce_model_adapter.py](file:///d:/lead-magnet/backend/ecommerce_model_adapter.py) | Hardcoded floor overrides (`if cart_item_count > 0: score = max(score, 75); segment = "Hot"`) artificially forced any cart item into Hot regardless of model prediction. | Removed all artificial floors. The XGBoost model calculates probability directly from feature values. |
| **Frontend Storage Pollution** | [CartContext.jsx](file:///d:/lead-magnet/frontend/user/src/context/CartContext.jsx), [AuthContext.jsx](file:///d:/lead-magnet/frontend/user/src/context/AuthContext.jsx) | Anonymous cart items stored in shared browser `localStorage` were automatically merged into newly created user accounts upon registration. | Carts and wishlists are scoped by user ID (`leadmagnet_user_cart_${userId}`). Storage keys are completely purged on logout. |

---

## 3. Pure XGBoost Scoring Architecture

### 3.1 Model Pipeline
```
Behavior Events (page views, clicks, searches)
Cart & Wishlist DB records
Order history DB records
           │
           ▼
[customer_feature_service.py]  ─── Aggregate into 25 base ecommerce features
           │
           ▼
[ecommerce_model_adapter.py]   ─── Standardize via ecommerce_scaler.pkl
           │
           ▼
[ecommerce_xgb_model.pkl]       ─── Direct ML probability inference P(conversion)
           │
           ▼
Score = round(P * 100)
Segment: Hot (≥70) | Warm (35–69) | Cold (<35)
Intent Override: checkout_start within 24h promotes to Hot
           │
           ▼
[customer_lead_state]           ─── Canonical document in MongoDB
```

### 3.2 Quantitative Scenario Comparison

| Scenario | Model Probability | Lead Score | Lead Segment (Behavior) | Status (Admin Directory) | Lifecycle Status |
|---|---|---|---|---|---|
| **Brand-New Signup (Zero Activity)** | `0.0054` | **1** | **Cold** | `Not Qualified` | `prospect` (provisional) |
| **Browsing Only (3 Page Views, 1 Search)** | `0.0120` | **1** | **Cold** | `Not Qualified` | `prospect` |
| **Active Cart (1 Product Added)** | `0.4820` | **48** | **Warm** | `Not Qualified` | `prospect` |
| **Active Checkout (within 24h)** | `0.5819` | **58 → 70** | **Hot** | **`Qualified Lead`** | `prospect` |
| **Order Placed (Cart 0, Checkout Complete)** | `0.0079` | **1** | **Cold** | **`Converted`** | **`converted`** |
| **Repeat Order Placed (Cart 0)** | `0.0079` | **1** | **Cold** | **`Repeat Customer`** | **`repeat_customer`** |
| **Converted Customer Shopping Again (Cart 1)** | `0.4820` | **48** | **Warm** | **`Converted`** | **`converted`** |

> **Key Rule**: 
> 1. **Segment (Hot, Warm, Cold)** is strictly driven by **active shopping behavior** (cart items, active checkout, browsing). A completed order does NOT artificially keep a customer "Hot" once their cart is empty.
> 2. **Status (Directory)** clearly displays **`Converted`** or **`Repeat Customer`** for converted buyers, and **`Qualified Lead`** or **`Not Qualified`** for unconverted prospects. This eliminates the confusing `[HOT] [NOT QUALIFIED]` contradiction.

---

## 4. Key Files Modified & Created

### Backend Core
- [scoring_constants.py](file:///d:/lead-magnet/backend/scoring_constants.py): Single source of truth for thresholds (`HOT=70`, `WARM=35`) and half-lives (checkout=3d, cart=7d, general=14d).
- [ecommerce_model_adapter.py](file:///d:/lead-magnet/backend/ecommerce_model_adapter.py): Clean XGBoost inference without hardcoded floor boosts; outputs `is_provisional` and `confidence`.
- [customer_lead_state_service.py](file:///d:/lead-magnet/backend/customer_lead_state_service.py): Lifecycle status calculation (`prospect`, `converted`, `repeat_customer`) and single-document sync.
- [lead_scoring_engine.py](file:///d:/lead-magnet/backend/lead_scoring_engine.py): Central rescore orchestrator with debounce guard and live SocketIO admin emission.
- [scheduler_service.py](file:///d:/lead-magnet/backend/scheduler_service.py): Distributed lease-locked background job (`customer_recency_rescore`) applying recency decay.
- [rescore_all.py](file:///d:/lead-magnet/backend/rescore_all.py): Deprecated in favor of the audited CLI.
- [scripts/rescore_customers.py](file:///d:/lead-magnet/scripts/rescore_customers.py): Safe CLI migration tool with dry-run default, host masking, and before/after distribution summaries.
- [app.py](file:///d:/lead-magnet/backend/app.py): Real-time rescore triggers wired to signup, login, cart changes, wishlist changes, and orders.

### Frontend Storage Isolation
- [CartContext.jsx](file:///d:/lead-magnet/frontend/user/src/context/CartContext.jsx): User-scoped storage keys (`leadmagnet_user_cart_${userId}`).
- [WishlistContext.jsx](file:///d:/lead-magnet/frontend/user/src/context/WishlistContext.jsx): User-scoped storage keys (`leadmagnet_user_wishlist_${userId}`).
- [AuthContext.jsx](file:///d:/lead-magnet/frontend/user/src/context/AuthContext.jsx): Clean logout purge of all cart and wishlist storage.

---

## 5. Manual Testing Step-by-Step Guide

Follow these steps to manually test and verify the lead scoring behavior across the User Storefront and Admin Intelligence Dashboard:

### Step 1: Verify Clean State on New User Signup
1. Open the storefront in your browser (`http://localhost:3000` or `http://localhost:5173`).
2. If already logged in, click **Logout**.
3. Register a fresh account via the **Sign Up** modal.
4. **Observe**:
   - Cart badge shows strictly **0 items**.
   - Open MongoDB (`leadmagnet` database) -> check `customer_lead_state` for this user:
     - `lead_score`: **1**
     - `lead_segment`: **"Cold"**
     - `qualification_status`: **"not_qualified"**
     - `lifecycle_status`: **"prospect"**
     - `is_provisional`: **true**
   - Open Admin Dashboard (`http://localhost:5174` or admin port) -> Lead is in the **Cold Leads** section.

### Step 2: Browse Products and Add to Cart
1. In the user storefront, navigate to the product catalog and view 2 products.
2. Click **Add to Cart** on one product.
3. **Observe**:
   - Cart badge shows **1 item**.
   - Check `customer_lead_state` in MongoDB:
     - `lead_score` will increase based on XGBoost prediction (~40–50 range).
     - It will **NOT** jump to 75.
     - `lead_segment`: **"Warm"**
     - `qualification_status`: **"not_qualified"** (Hot is required for qualification).

### Step 3: Initiate Checkout (High Purchase Intent)
1. Navigate to the Cart page and click **Proceed to Checkout**.
2. **Observe**:
   - An event `checkout_start` is logged.
   - Active checkout intent override activates (valid for 24h).
   - Check `customer_lead_state` in MongoDB:
     - `lead_segment`: **"Hot"**
     - `qualification_status`: **"qualified"**
     - `score_reasons`: includes `"active_checkout_intent_override_24h"`
   - Admin Intelligence Dashboard immediately shows this user in **Hot Leads / Qualified Leads**.

### Step 4: Place Order (First Purchase)
1. Complete the checkout form and click **Place Order**.
2. **Observe**:
   - Order confirmation displays with an Order ID.
   - Cart is cleared to 0 items.
   - Check `customer_lead_state` in MongoDB:
     - `lifecycle_status`: **"converted"**
     - `qualification_status`: **"not_qualified"** (Prevents acquisition marketing spam).
   - Admin Dashboard marks the customer under **Converted Customers**.

### Step 5: Place Second Order (Repeat Buyer)
1. Add an item to cart and place another order.
2. **Observe**:
   - Check `customer_lead_state` in MongoDB:
     - `lifecycle_status`: **"repeat_customer"**

---

## 6. Automated Test Suite

All 55 regression tests covering the entire pipeline pass:

```powershell
.\venv\Scripts\python.exe -m pytest `
  backend/tests/test_manual_user_journey_e2e.py `
  backend/tests/test_xgboost_scoring_clean.py `
  backend/tests/test_customer_lead_state.py `
  backend/tests/test_phase2_lifecycle.py `
  backend/tests/test_phase4c_deprecation_and_contract_closure.py
```
