# Lead Magnet — Backend

The Flask/SocketIO backend is the central hub for the Lead Magnet platform. It exposes a REST API and WebSocket channel consumed by both the User Portal and Admin Portal, runs the XGBoost lead-scoring pipeline, and drives the marketing automation engine.

---

## Responsibilities

| Area | Modules |
|:--|:--|
| HTTP REST API + JWT auth | `app.py`, `auth_middleware.py` |
| Real-time event streaming | `app.py` (Flask-SocketIO) |
| Behavioral telemetry ingestion | `behavior_event_service.py` |
| Customer feature aggregation | `customer_feature_service.py` |
| ML lead scoring | `ecommerce_model_adapter.py`, `lead_scoring_engine.py` |
| ML explainability | `model_explainability_service.py` |
| Marketing automation | `marketing_automation_service.py`, `opportunity_engine.py` |
| Channel selection + consent | `channel_selector_service.py` |
| Communication dispatch | `communication_provider.py` |
| Admin intelligence | `admin_intelligence_service.py` |
| Analytics (RFM, funnel, revenue) | `rfm_service.py`, `funnel_analytics_service.py`, `revenue_attribution_service.py` |
| What-If simulator | `whatif_simulator_service.py` |
| Background scheduler | `scheduler_service.py` |

---

## Python Version

Python **3.10 or later** is required. The project uses `match`/`case` and other 3.10+ syntax in some utilities.

```bash
python --version   # must be 3.10+
```

---

## Virtual Environment Setup

### Windows (PowerShell)
```powershell
python -m venv venv
venv\Scripts\activate
```

### macOS / Linux
```bash
python3 -m venv venv
source venv/bin/activate
```

---

## Dependency Installation

From the **project root** (not the `backend/` directory):
```bash
pip install -r backend/requirements.txt
```

Key dependencies installed:
- `Flask` 3, `Flask-SocketIO` 5, `Flask-Cors` 6
- `PyMongo` 4, `python-dotenv`, `certifi`
- `PyJWT`, `bcrypt`
- `xgboost`, `scikit-learn`, `numpy`, `pandas`, `joblib`
- `gunicorn`, `eventlet`
- `pytest`

---

## Environment Variables

The backend reads environment variables from `backend/.env` (never committed). A template with all required keys and safe placeholder values is provided at:
- **`backend/.env.local.example`** — minimal local development settings
- **`.env.example`** (root) — complete template with all production variables

Copy one of these templates and fill in your values:
```bash
# Windows
copy .env.example backend\.env

# macOS / Linux
cp .env.example backend/.env
```

### Required Variables

| Variable | Example value | Notes |
|:--|:--|:--|
| `MONGO_URI` | `mongodb+srv://user:pass@cluster.mongodb.net/` | Atlas SRV URI for production |
| `MONGO_DB_NAME` | `leadmagnet` | Production database name |
| `JWT_SECRET` | `<random-64-char-string>` | Must be strong and unique |
| `ADMIN_USERNAME` | `admin` | Admin portal login username |
| `ADMIN_PASSWORD` | `<strong-password>` | Admin portal login password |
| `FRONTEND_URL` | `https://app.example.com,https://admin.example.com` | CORS allowed origins (comma-separated) |
| `COMMUNICATION_PROVIDER` | `dry_run` | `dry_run` \| `gmail` \| `whatsapp` |
| `ALLOW_REAL_DISPATCH` | `false` | Must be `false` unless doing a controlled live test |
| `ENABLE_SCHEDULER` | `false` | Set `true` only in production single-process mode |

> **Never commit `backend/.env` to version control.** The `.gitignore` blocks it. Do not print credentials in documentation or logs.

---

## Local-Only Development Database

For local demos and testing, the backend connects to **MongoDB Community running on `127.0.0.1:27017`** in an isolated database named **`leadmagnet_test`**.

The production `backend/.env` is **never loaded** in this mode. The `local_test_launcher.py` injects safe overrides before any application module is imported.

**Start MongoDB Community first:**
```bash
mongod   # or start via Services if installed as a Windows service
```

**Verify isolation is active:**
```powershell
venv\Scripts\python backend/local_test_launcher.py --check-isolation
```

Expected output:
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

---

## Startup

### Local demo (safe, isolated mode) — RECOMMENDED
```powershell
venv\Scripts\python backend/local_test_launcher.py --serve --port 5000
```

### Production (requires properly configured `backend/.env`)
```bash
gunicorn -k eventlet -w 1 -b 0.0.0.0:5000 backend.app:app
```

> **Do not run `python backend/app.py` directly for local demos.** Without `TESTING=1` set first, `app.py` loads `backend/.env` which may contain Atlas credentials. Use `local_test_launcher.py --serve` instead.

---

## Health Check

After startup, verify the backend is running and connected to the database:

```bash
curl http://127.0.0.1:5000/api/health
```

Expected response:
```json
{"mongo": true, "success": true}
```

If `"mongo": false`, check that MongoDB is running and `MONGO_URI` is set correctly.

---

## Seeding the Product Catalog (first-time local setup)

The `leadmagnet_test` database starts empty. Seed it with product data once:

```powershell
$env:TESTING="1"
$env:MONGO_URI="mongodb://127.0.0.1:27017"
$env:MONGO_DB_NAME="leadmagnet_test"
venv\Scripts\python backend/seed_clothing_products.py
```

Expected: `Inserted N product records into leadmagnet_test.myntra_products`

---

## Running Tests

```powershell
# From project root — uses pytest.ini which sets testpaths = backend/tests
venv\Scripts\python -m pytest backend/tests/ -q --tb=short
```

**Current result:** `678 passed` in ~75 seconds.

The test suite runs entirely against the isolated local database (`leadmagnet_test`). Tests that require a live database use the `local_test_launcher.py` isolation helper via `backend/tests/_isolation.py`.

```powershell
# Run only a specific test file
venv\Scripts\python -m pytest backend/tests/test_marketing_automation_service.py -v
```

---

## Model and Dataset Locations

| Path | Contents |
|:--|:--|
| `model/ecommerce_xgb_model.pkl` | Trained XGBoost classifier |
| `model/ecommerce_scaler.pkl` | StandardScaler fitted on training features |
| `model/ecommerce_feature_columns.pkl` | Feature column names in the correct order |
| `model/ecommerce_model_metadata.json` | Accuracy, ROC-AUC, training date |
| `model/kmeans_model.pkl` | KMeans cluster model (legacy segment mapping) |
| `model/xgb_model.pkl` | Legacy XGBoost model (used by some test paths) |
| `data/ml/ecommerce_customer_behavior.csv` | Training dataset for the ML model |
| `data/catalog/cleaned_clothing_catalog.csv` | Cleaned Myntra clothing product catalog |
| `data/raw/Leads.csv` | Raw leads dataset |
| `notebooks/01_cleaning.ipynb` | Data cleaning and EDA notebook |
| `scripts/train_ecommerce_model.py` | Training script |

> Do not modify, delete, or replace model files without retraining and updating `ecommerce_model_metadata.json`.

---

## Communication Providers and Marketing Safety

### Dry-run mode (default for all local and test usage)
`COMMUNICATION_PROVIDER=dry_run` — all messages are logged to `marketing_communications` with `provider: "dry_run"`. Zero outbound network calls are made. This is the default when the variable is unset.

### Live providers (production only)
- `gmail` — Gmail SMTP via port 587 TLS. Requires `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL`.
- `whatsapp` — Meta Cloud API v18+. Requires `WHATSAPP_API_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, and pre-approved message templates.

### Safety guards enforced at all times
- `ALLOW_REAL_DISPATCH=false` blocks live dispatch at the function level, independent of the provider.
- Idempotency keys in `marketing_automation_events` prevent duplicate sends.
- 72-hour cooldown (`MARKETING_COOLDOWN_HOURS=72`) prevents over-messaging.
- WhatsApp messages are never sent to customers who have not opted in (`whatsapp_opt_in=true` required).

### Scheduler
`ENABLE_SCHEDULER=false` (default). Set to `true` in a production single-process deployment to enable background opportunity pipeline scanning and price-drop detection. In multi-worker Gunicorn deployments, run `python backend/scheduler_service.py` as a separate process instead.

---

## API Reference

The full API specification is at [`docs/api.md`](../docs/api.md). Key endpoint groups:

| Prefix | Responsibility |
|:--|:--|
| `GET /api/health` | Database connectivity check |
| `POST /api/auth/register`, `/api/auth/login` | Customer authentication |
| `GET /api/products` | Paginated product catalog |
| `GET/POST /api/cart/*` | Cart management |
| `GET/POST /api/wishlist/*` | Wishlist management |
| `POST /api/orders` | Order creation |
| `POST /api/session/start`, `/event`, `/end` | Behavioral telemetry |
| `GET /api/admin/intelligence/*` | Admin analytics and customer intelligence |
| `GET /api/admin/analytics/*` | Funnel, RFM, revenue attribution |
| `POST /api/admin/simulate/lead-score` | What-If simulator |
| `POST /api/webhooks/whatsapp` | WhatsApp webhook receiver |

---

## Troubleshooting

| Symptom | Cause | Fix |
|:--|:--|:--|
| `ISOLATION CHECK FAILED` | MongoDB not running | Start `mongod` on port 27017 |
| `678 passed` → `0 passed` | `TESTING` env var pollution | Ensure no `TESTING=0` override in your shell |
| `DuplicateKeyError` on seeding | Catalog already seeded | Safe to ignore — existing records are preserved |
| `401 Unauthorized` on admin routes | Expired or missing JWT | Log in again via `POST /api/admin/login` |
| `RuntimeError: MONGO_URI contains Atlas pattern` | Atlas URI was set while `LOCAL_ONLY_TESTING=1` | Use `mongodb://127.0.0.1:27017` for local mode |
| `503 Service Unavailable` on API calls | MongoDB unavailable | Check `mongod` is running; check `MONGO_URI` |

---

## Security Notes

- **Never run with production `backend/.env` for demos.** Use `local_test_launcher.py --serve`.
- **JWT_SECRET** must be a random, unique string of at least 32 characters. Never use defaults from examples.
- **ADMIN_PASSWORD** must be changed from the local demo default before any real deployment.
- **Wildcard CORS (`"*"`)** is rejected at startup in production (`FLASK_ENV=production`) — configure real frontend origins in `FRONTEND_URL`.
- All passwords are hashed with **bcrypt** before storage.
- TLS certificate verification uses `certifi` CA bundle; `tlsAllowInvalidCertificates` is not available.
