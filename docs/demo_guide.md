# Lead Magnet — Demo Guide

> **Purpose:** Step-by-step instructions for running a complete, professional local demonstration of the Lead Magnet platform. Verified against the Task 23 local acceptance test results.
>
> **Safety note:** This guide uses the isolated local test launcher. Zero external API calls are made. Zero real communications are sent. No production data is touched.

---

## Prerequisites

| Requirement | Version | Check |
|:--|:--|:--|
| Python | 3.10+ | `python --version` |
| Node.js | 18+ | `node --version` |
| MongoDB Community | 6.x+ running on `127.0.0.1:27017` | `mongod --version` |
| Virtual environment | `.venv` or `venv` at project root | `venv\Scripts\activate` |

> **MongoDB must be running locally before starting the backend.** Start it with `mongod` if it is not already running as a service.

---

## Part 1: Environment Setup

All commands are run from the **project root** (`d:\lead-magnet` or equivalent).

### 1.1 Activate Virtual Environment

```powershell
# Windows (PowerShell)
venv\Scripts\activate
```

### 1.2 Verify Safety Preflight

Before starting any services, confirm the isolation guard is active and local MongoDB is reachable:

```powershell
venv\Scripts\python backend/local_test_launcher.py --check-isolation
```

**Expected output:**
```
======================================================================
LEAD MAGNET: LOCAL TEST LAUNCHER ISOLATION STATUS
======================================================================
  Isolation Guard:          ACTIVE (TESTING=1, LOCAL_ONLY_TESTING=1)
  Target Database Host:     127.0.0.1:27017 (Loopback Verified)
  Target Database Name:     leadmagnet_test (Isolated Test DB)
  Remote Atlas Status:      ZERO REMOTE NODES (Atlas Completely Disconnected)
  Communication Provider:   dry_run (Dry-Run Enforced)
  Real Dispatch Switch:     false (Blocked)
  Scheduler State:          false (Disabled)
----------------------------------------------------------------------
VERDICT: LOCAL TEST ENVIRONMENT FULLY ISOLATED & SAFE
======================================================================
```

If this fails, check that MongoDB is running on port 27017.

### 1.3 Seed the Product Catalog (first-time only)

The product catalog needs to be loaded into the local isolated database once:

```powershell
$env:TESTING="1"
$env:LOCAL_ONLY_TESTING="1"
$env:MONGO_URI="mongodb://127.0.0.1:27017"
$env:MONGO_DB_NAME="leadmagnet_test"
venv\Scripts\python backend/seed_clothing_products.py
```

Expected: `Inserted N product records into leadmagnet_test.myntra_products`

> If you see `DuplicateKeyError`, the catalog is already seeded — safe to continue.

---

## Part 2: Starting All Services

Open **three separate terminal windows** (or tabs).

### Terminal 1 — Backend API (Isolated Mode)

```powershell
venv\Scripts\python backend/local_test_launcher.py --serve --port 5000
```

**Expected startup output:**
```
[ISOLATED SERVER] Connected to verified local DB: leadmagnet_test @ ('127.0.0.1', 27017)
[ISOLATED SERVER] Starting server on port 5000...
Successfully connected to MongoDB (Standard).
 * Running on http://127.0.0.1:5000
```

**Verify:** Open `http://127.0.0.1:5000/api/health` — should return:
```json
{"mongo": true, "success": true}
```

### Terminal 2 — User Portal (Customer Storefront)

```powershell
cd frontend\user
npm install   # first time only
npm run dev
```

**Expected:** Vite dev server starts at `http://localhost:3001`

### Terminal 3 — Admin Portal (Intelligence Dashboard)

```powershell
cd frontend\admin
npm install   # first time only
npm run dev
```

**Expected:** Vite dev server starts at `http://localhost:3000`

---

## Part 3: Demo Sequence

### Step 1 — Customer Registration and Product Browsing

1. Open **`http://localhost:3001`** in a browser.
2. The homepage loads with the full clothing catalog (120,466 products, paginated).
3. Click **Register** / **Sign Up**. Fill in name, email, password.
   - Example: `demo_visitor@example.com`
4. After registration, observe:
   - JWT token stored in browser.
   - Welcome/registration communication recorded as `dry_run` in backend logs.
5. Browse the product catalog. Click any product card to view the detail page.
   - Observe product name, brand, price in INR, discount percentage, ratings.

**What this demonstrates:**
- Anonymous session creation → identity resolution on signup.
- Behavioral telemetry: `page_view` and `session/start` events logged.
- Registration communication trigger (dry-run).

---

### Step 2 — Cart and Wishlist Interaction

1. From any product detail page, click **Add to Cart**.
2. Open the cart drawer (top-right icon). Adjust quantity to 2 or 3.
   - Observe price recalculation in real time.
3. Click **Add to Wishlist** on a different product.
4. Check the wishlist icon to confirm persistence.

**What this demonstrates:**
- Cart and wishlist services functioning.
- Behavioral signals (`cart_add`, `wishlist_add`) feeding the ML feature vector.

---

### Step 3 — ML Lead Scoring (Observed via Admin Portal)

1. Open **`http://localhost:3000`** in another browser tab.
2. Log in as admin: username `admin`, password `admin12345`.
3. Go to **Customer Directory** (default landing after login).
4. Find the registered demo customer in the table.
5. Observe the **Lead Score** column (0–100) and **Segment** (Cold/Warm/Hot).
6. Click the customer row to open the **360° Customer Intelligence Drawer**.
   - View: Lead Score, Segment, Qualification Status.
   - View: **Feature Contribution Breakdown** (positive/negative ML drivers).
   - View: **Behavioral Timeline** (events, cart adds, score changes).

**What this demonstrates:**
- Real-time ML scoring: XGBoost inference on the 11-feature behavioral vector.
- Explainability: which behaviors are driving the conversion probability.
- Admin intelligence drawer with complete customer 360° view.

---

### Step 4 — Checkout and Order Confirmation

1. Switch back to the User Portal (`localhost:3001`).
2. From the cart drawer, click **Proceed to Checkout**.
3. Choose **Cash on Delivery** (safe local payment method).
4. Complete the order.

**What this demonstrates:**
- Order creation via `POST /api/orders`.
- Post-purchase marketing automation: `trigger_order_confirmation_communication()` fires.
- Communication logged in `marketing_communications` as `dry_run`.

---

### Step 5 — Marketing Automation Feed (Admin Portal)

1. In the Admin Portal, navigate to the **Live Activity Feed** or **Marketing** tab.
2. Observe the list of recent marketing communications:
   - Channel: `email` or `whatsapp`
   - Status: `sent` (dry-run)
   - Provider: `dry_run`
   - Template used (e.g., cart abandonment, order confirmation).

**What this demonstrates:**
- End-to-end marketing automation pipeline.
- Idempotency: duplicate sends are prevented by `idempotency_key`.
- Cooldown enforcement: same customer won't receive repeated messages within 72h.
- Dry-run provider: zero real communications dispatched.

---

### Step 6 — Admin Analytics Dashboards

Navigate through the Admin Portal tabs to demonstrate:

| Tab | What It Shows |
|:--|:--|
| **Overview** | Total leads, qualified count, conversion rate, revenue attribution |
| **Funnel Analytics** | Conversion funnel stages: Sessions → Cart → Checkout → Order |
| **RFM Segmentation** | Recency-Frequency-Monetary customer value distribution |
| **What-If Simulator** | Adjust behavioral sliders and see projected lead score change |
| **Revenue Attribution** | Marketing touchpoints mapped to converted revenue |

---

## Part 4: Test Suite Verification

To demonstrate the automated test coverage:

```powershell
venv\Scripts\python -m pytest backend/tests/ -v --tb=short
```

**Expected result:** `678 passed` in approximately 70–90 seconds.

To run a quick smoke-test only:

```powershell
venv\Scripts\python -m pytest backend/tests/ -q --tb=no
```

---

## Part 5: Cleanup After Demo

After the demonstration, remove all synthetic data created during the session:

### Option A — Full Isolated Database Drop (Recommended)

```powershell
$env:TESTING="1"
$env:MONGO_URI="mongodb://127.0.0.1:27017"
venv\Scripts\python -c "
from pymongo import MongoClient
c = MongoClient('mongodb://127.0.0.1:27017')
c.drop_database('leadmagnet_test')
print('leadmagnet_test dropped.')
"
```

### Option B — Targeted User Cleanup

If you want to preserve the product catalog but remove the demo user:

```powershell
$env:TESTING="1"
$env:MONGO_URI="mongodb://127.0.0.1:27017"
$env:MONGO_DB_NAME="leadmagnet_test"
venv\Scripts\python -c "
from pymongo import MongoClient
c = MongoClient('mongodb://127.0.0.1:27017')
db = c['leadmagnet_test']
email = 'demo_visitor@example.com'
for col in ['user_profiles','sessions','events','cart','wishlist','orders','customer_features','customer_lead_state','marketing_communications','marketing_automation_events']:
    db[col].delete_many({'email': email})
print('Demo user data removed.')
"
```

---

## Quick Reference — Ports and URLs

| Service | URL | Notes |
|:--|:--|:--|
| Backend API | `http://127.0.0.1:5000` | Health: `/api/health` |
| Backend Health | `http://127.0.0.1:5000/api/health` | Returns `{"mongo":true,"success":true}` |
| User Portal | `http://localhost:3001` | Customer storefront |
| Admin Portal | `http://localhost:3000` | Admin dashboard |
| Admin Login | `http://localhost:3000/login` | Credentials: `admin` / `admin12345` |

## Quick Reference — Key Admin Credentials

| Credential | Value |
|:--|:--|
| Admin username | `admin` |
| Admin password | `admin12345` |

> These are the default local demo credentials. They must be changed before any production deployment.

---

## Troubleshooting

| Symptom | Likely Cause | Resolution |
|:--|:--|:--|
| Isolation check fails with "MongoClient ping failed" | MongoDB not running | Run `mongod` or start MongoDB service |
| Frontend shows "Failed to fetch" or CORS error | Backend not started | Start backend first, confirm port 5000 |
| Product catalog shows 0 items | `leadmagnet_test` not seeded | Run `seed_clothing_products.py` |
| Admin login fails | Wrong credentials | Use `admin` / `admin12345` |
| Tests fail | Environment pollution | Ensure `TESTING=1` is not set in shell before running `pytest` without the launcher |

---

*Document generated as part of Task 24 — Lead Magnet Final Audit and Demo Preparation.*
