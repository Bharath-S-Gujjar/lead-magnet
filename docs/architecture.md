# Lead Magnet — System Architecture & Design Specification

---

## 1. System Overview

**Lead Magnet** is an AI-driven Customer Intelligence and E-Commerce Platform. It bridges an active e-commerce retail storefront with real-time visitor event telemetry, machine learning conversion scoring, rule-based marketing automation, and an administrative intelligence dashboard.

```
+-------------------------------------------------------------------------------+
|                                FRONTEND LAYER                                 |
|                                                                               |
|   +------------------------------------+   +------------------------------+   |
|   |   User Portal (React + Vite)       |   |  Admin Portal (React + Vite) |   |
|   |   - E-commerce Storefront          |   |  - Live Behavioral Feeds     |   |
|   |   - Behavioral Telemetry Hook      |   |  - Funnel & RFM Analytics    |   |
|   |   - Real-time Wishlist/Cart/Orders |   |  - What-If Simulator & Leads |   |
|   +-----------------+------------------+   +--------------+---------------+   |
+---------------------|-------------------------------------|-------------------+
                      | HTTP / REST                         | HTTP / WebSocket
                      v                                     v
+-------------------------------------------------------------------------------+
|                            BACKEND APPLICATION LAYER                          |
|                                                                               |
|   +-----------------------------------------------------------------------+   |
|   |   Flask Application Core (app.py)                                     |   |
|   |   - REST API Endpoints (/api/products, /api/auth, /api/admin)         |   |
|   |   - Flask-SocketIO Event Dispatcher (Real-time admin streaming)       |   |
|   |   - JWT Authentication & Role-Based Access Control                    |   |
|   +-------------------+-------------------------------+-------------------+   |
|                       |                               |                       |
|   +-------------------v---------------+   +-----------v-------------------+   |
|   | Behavioral Event & Session Engine |   | Machine Learning Inference    |   |
|   | - Session lifecycle tracking      |   | - XGBoost Lead Scorer         |   |
|   | - Event telemetry & aggregation   |   | - 11-feature behavioral vector|   |
|   | - Customer Profile State Machine  |   | - Real-time conversion score  |   |
|   +-------------------+---------------+   +-----------+-------------------+   |
|                       |                               |                       |
|   +-------------------v---------------+   +-----------v-------------------+   |
|   | Marketing Automation Service      |   | Admin Intelligence Services   |   |
|   | - Cart abandonment triggers       |   | - RFM Segmentation            |   |
|   | - High-intent browse triggers     |   | - Revenue attribution         |   |
|   | - Mock communication dispatch     |   | - What-if simulation engine   |   |
|   +-------------------+---------------+   +-----------+-------------------+   |
+-----------------------|-------------------------------|-----------------------+
                        |                               |
                        +---------------+---------------+
                                        | PyMongo (TLS / certifi)
                                        v
+-------------------------------------------------------------------------------+
|                            DATA STORAGE LAYER                                 |
|                                                                               |
|   MongoDB Atlas Database: `leadmagnet`                                        |
|   - products (120,466 catalog documents with unique product_id)               |
|   - user_profiles (canonical customer identity & credentials)                 |
|   - sessions & events (behavioral activity log)                               |
|   - orders & cart & wishlist (transactional state)                            |
|   - customer_features (aggregated behavioral feature store)                   |
|   - customer_lead_state & lead_score_history (ML scoring & audit trail)       |
|   - marketing_automation_events & marketing_communications                    |
|   - admin_notifications                                                       |
+-------------------------------------------------------------------------------+
```

---

## 2. Core Architectural Pillars

### 2.1 Unified Customer Identity Lifecycle
1. **Anonymous Visitors**:
   - Every visitor receives a persistent `visitor_id` (UUID generated in the browser and stored in localStorage).
   - Telemetry tracks anonymous page views, searches, product detail views, and cart actions.
2. **Identity Resolution**:
   - Upon signup or login, the user's `visitor_id` is linked to their canonical `user_profiles` document.
   - Historical sessions, events, cart items, and wishlist items are preserved and attributed to the authenticated customer ID.

### 2.2 Customer Feature Store & State Machine
The `customer_features` collection aggregates real-time signals from raw events into an analytical profile:
- `total_time_seconds`: Total browsing duration
- `page_views` & `total_visits`: Engagement depth
- `cart_adds`, `wishlist_adds`: Purchase intent signals
- `checkout_starts`, `orders_placed`: Transactional progression
- `high_intent_page_visits`: Visits to checkout, pricing, or promotion surfaces

The `customer_lead_state` collection tracks the customer's conversion classification:
- **Cold** (`score < 0.40`): Low engagement / exploratory browsing.
- **Warm** (`0.40 <= score < 0.70`): Active consideration / multiple product views.
- **Hot** (`score >= 0.70`): High intent / cart adds / checkout progress.

### 2.3 Machine Learning Pipeline
- **Model**: Trained XGBoost Classifier (`model/ecommerce_xgb_model.pkl`) with standard scaler (`model/ecommerce_scaler.pkl`).
- **Feature Vector (11 features)**:
  `total_time_seconds`, `page_views`, `total_visits`, `page_views_per_visit`, `event_count`, `cart_adds`, `wishlist_adds`, `checkout_starts`, `high_intent_page_visits`, `avg_time_per_page`, `event_velocity`.
- **Dynamic Rescoring**: Triggered asynchronously whenever a significant customer action occurs (e.g. `add_to_cart`, `checkout_start`, session end).

### 2.4 Marketing Automation Engine
Watches customer state transitions and schedules automated actions:
- **Abandoned Cart**: Dispatched when items remain in cart without checkout for $>15$ minutes.
- **High-Intent Browse**: Dispatched when a customer enters the "Hot" segment without completing checkout.
- **Post-Purchase Re-Engagement**: Dispatched to re-engage converted customers.

### 2.5 Admin Intelligence Dashboard
Provides full executive observability into store performance:
- **Overview & Directory**: Searchable, filterable customer lead table with slide-out customer profile drawer.
- **Funnel & RFM Analytics**: Visualized conversion stages and Recency-Frequency-Monetary customer segments.
- **Revenue Attribution**: Attributed revenue across marketing touchpoints.
- **Live Activity Feed**: Real-time event notifications via WebSockets.
- **What-If Simulator**: Interactive scenario testing to forecast conversion changes under varying customer behavior inputs.

---

## 3. Product Catalog Design
- **Total Records**: **120,466 products**
- **Demographics**: Women (56.5%), Men (42.7%), Kids (0.8%)
- **Data Integrity**: Zero fabricated stock, images, SKU, or reviews. Clean INR pricing and validated discount percentages.
- **Indexes**: `product_id` (unique), `category`, `gender`, `brand`, `name`, `price`.
