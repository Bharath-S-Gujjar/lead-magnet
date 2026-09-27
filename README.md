# Lead Magnet — AI-Powered Customer Intelligence & E-Commerce Platform

> **Lead Magnet** is an enterprise-grade AI customer intelligence platform combining an active e-commerce shopping experience with real-time visitor behavioral telemetry, machine learning conversion scoring (XGBoost), rule-based marketing automation, and an administrative intelligence dashboard.

---

## 🌟 Key Capabilities

1. **Authoritative 120,466 Product Clothing Catalog**:
   - Multi-gender clothing catalog (Women: 56.5%, Men: 42.7%, Kids: 0.8%) ingested from comprehensive sales datasets.
   - Clean INR pricing, percentage discounts, normalized ratings, and deterministic internal identifiers (`product_id`).
   - Zero fabricated stock, images, SKU, or synthetic reviews.
2. **Real-Time Behavioral Telemetry**:
   - Captures anonymous and identified customer events: page visits, dwell duration, search queries, product views, wishlist additions, cart updates, and checkout progression.
3. **Machine Learning Purchase Prediction**:
   - 11-feature behavioral vector fed into a tuned **XGBoost Classifier** ($\ge 92.8\%$ validation accuracy, $0.965$ ROC-AUC).
   - Real-time conversion score ($\in [0.0, 1.0]$) classifying customers dynamically into **Cold**, **Warm**, and **Hot** lead segments.
   - Transparent feature-contribution explainability identifying positive and negative conversion drivers.
4. **Autonomous Marketing Engine**:
   - Triggers targeted interventions based on behavioral state changes: cart abandonment re-engagement, high-intent browsing incentives, and post-purchase follow-ups.
5. **Executive Admin Intelligence Dashboard**:
   - **Overview & Customer Directory**: Searchable, filterable customer intelligence directory with live drill-down drawer.
   - **Conversion Funnel & RFM Analytics**: Visualized drop-off analytics and Recency-Frequency-Monetary customer value segmentation.
   - **Revenue Attribution & Live Feed**: Touchpoint revenue attribution alongside live real-time WebSocket event feeds.
   - **What-If Scenario Simulator**: Interactive forecasting tool allowing administrators to simulate behavioral shifts and project conversion outcomes.

---

## 🏗️ System Architecture

```
+-------------------------------------------------------------------------------+
|                                FRONTEND LAYER                                 |
|   +------------------------------------+   +------------------------------+   |
|   |   User Portal (React + Vite)       |   |  Admin Portal (React + Vite) |   |
|   |   - Modern E-Commerce Storefront   |   |  - Live Behavioral Feeds     |   |
|   |   - Real-time Telemetry Hook       |   |  - Funnel & RFM Analytics    |   |
|   |   - Cart, Wishlist, Orders         |   |  - What-If Simulator & Leads |   |
|   +-----------------+------------------+   +--------------+---------------+   |
+---------------------|-------------------------------------|-------------------+
                      | HTTP / REST                         | HTTP / WebSocket
                      v                                     v
+-------------------------------------------------------------------------------+
|                            BACKEND APPLICATION LAYER                          |
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
|   | - Customer Feature Aggregator     |   | - 11-feature behavioral vector|   |
|   +-------------------+---------------+   +-----------+-------------------+   |
|                       |                               |                       |
|   +-------------------v---------------+   +-----------v-------------------+   |
|   | Marketing Automation Service      |   | Admin Intelligence Services   |   |
|   +-------------------+---------------+   +-----------+-------------------+   |
+-----------------------|-------------------------------|-----------------------+
                        | PyMongo (TLS / certifi)
                        v
+-------------------------------------------------------------------------------+
|                            DATA STORAGE LAYER                                 |
|   MongoDB Atlas Database: `leadmagnet`                                        |
|   - products (120,466 validated catalog records)                              |
|   - user_profiles, sessions, events, orders, cart, wishlist                   |
|   - customer_features, customer_lead_state, lead_score_history                |
|   - marketing_automation_events, marketing_communications, admin_notifications|
+-------------------------------------------------------------------------------+
```

---

## 🛠️ Technology Stack

| Tier | Technologies |
| :--- | :--- |
| **Backend API & Real-Time** | Python 3.10+, Flask, Flask-SocketIO, PyMongo, Eventlet, Gunicorn, JWT |
| **Machine Learning** | XGBoost, Scikit-Learn, NumPy, Pandas |
| **Frontend Applications** | React 18, Vite, React Router, Recharts, Lucide React |
| **Database** | MongoDB Atlas (M0 / Dedicated Cluster) |
| **Testing** | Pytest (200 test cases, 100% passing) |

---

## 🚀 Quickstart & Demo Guide

### 1. Prerequisites
- Python 3.10+ & Node.js 18+
- MongoDB Atlas cluster URI configured in `backend/.env`

### 2. Backend Setup
```bash
# Activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r backend/requirements.txt

# Run backend test suite (200 tests)
pytest backend/tests/ -v

# Start the Flask API server
cd backend
python app.py
```
*Backend runs on `http://127.0.0.1:5000`.*

### 3. Frontend Portals

#### Customer Storefront (User Portal)
```bash
cd frontend/user
npm install
npm run dev
```
*Accessible at `http://localhost:5173`.*

#### Admin Intelligence Dashboard (Admin Portal)
```bash
cd frontend/admin
npm install
npm run dev
```
*Accessible at `http://localhost:5174`.*

---

## 📚 Documentation Index

For in-depth architectural and operational specifications, consult:

- **[System Architecture](docs/architecture.md)** — Architectural blueprint, customer identity lifecycle, and state machine.
- **[Local Setup & Running Guide](docs/setup.md)** — Step-by-step developer and presentation environment configuration.
- **[API Specification](docs/api.md)** — Endpoints, payloads, and response contracts for all services.
- **[Machine Learning Documentation](docs/ml.md)** — XGBoost model architecture, 11-feature pipeline, and evaluation metrics.
- **[Deployment Guide](docs/deployment.md)** — Production topology, Render/Vercel settings, and environment variables.
- **[Clothing Catalog Cleaning Report](docs/clothing_catalog_cleaning_report.md)** — Data cleaning, normalization, and deduplication methodology.
- **[Atlas Catalog Replacement Report](docs/atlas_product_catalog_replacement.md)** — Non-destructive migration of the 120,466 products into MongoDB Atlas.