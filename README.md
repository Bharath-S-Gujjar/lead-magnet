# Lead Magnet

**An AI-powered Customer Intelligence and Lead-Scoring Platform for E-Commerce.**

Real e-commerce stores lose customers silently — visitors browse, fill carts, and leave without buying. Lead Magnet solves this by combining a full-featured clothing storefront with real-time behavioral analytics, an XGBoost-powered purchase-intent scorer, and a rule-based marketing automation engine that fires targeted, channel-appropriate communications at the right moment.

---

## Features

| Capability | Status |
|:--|:--|
| 120,466-product clothing catalog (Myntra dataset) | ✅ Implemented |
| Customer registration, login, JWT authentication | ✅ Implemented |
| Cart, wishlist, order management | ✅ Implemented |
| Real-time behavioral telemetry (sessions, events) | ✅ Implemented |
| Anonymous visitor identity resolution on signup | ✅ Implemented |
| XGBoost lead scoring — 11-feature behavioral vector | ✅ Implemented |
| Cold / Warm / Hot lead segmentation | ✅ Implemented |
| ML explainability — feature contribution breakdown | ✅ Implemented |
| Marketing automation (cart abandon, post-purchase, browse incentive) | ✅ Implemented |
| Idempotency keys + 72-hour cooldown anti-spam | ✅ Implemented |
| WhatsApp + Email channel selection with consent enforcement | ✅ Implemented |
| Admin intelligence dashboard — customer 360° drawer | ✅ Implemented |
| Funnel analytics, RFM segmentation, revenue attribution | ✅ Implemented |
| What-If scenario simulator | ✅ Implemented |
| Live real-time admin event feed (WebSocket) | ✅ Implemented |
| Runtime database isolation for local testing | ✅ Implemented |
| Dry-run communication provider (no real messages sent) | ✅ Implemented |

---

## Technology Stack

| Tier | Technologies |
|:--|:--|
| **Backend** | Python 3.10+, Flask 3, Flask-SocketIO 5, PyMongo 4, Eventlet, Gunicorn, PyJWT |
| **Machine Learning** | XGBoost, Scikit-Learn, NumPy, Pandas |
| **User Frontend** | React 18, Vite 6, React Router 6, Recharts, Lucide React |
| **Admin Frontend** | React 18, Vite 6, React Router 7, Recharts, Socket.IO Client |
| **Database** | MongoDB Atlas (production) · MongoDB Community (local demo) |
| **Testing** | Pytest (678 tests, 100% passing) |

---

## Architecture Summary

```
User Portal (React, :3001)  ─┐
                              ├── HTTP REST + WebSocket ──► Flask Backend (:5000)
Admin Portal (React, :3000) ─┘                                │
                                                               ├── XGBoost ML Engine
                                                               ├── Marketing Automation
                                                               ├── Admin Intelligence
                                                               └── MongoDB
                                                                   ├── myntra_products (120,466)
                                                                   ├── user_profiles, sessions, events
                                                                   ├── cart, wishlist, orders
                                                                   └── marketing_communications
```

---

## Prerequisites

| Requirement | Version |
|:--|:--|
| Python | 3.10 or later |
| Node.js | 18 or later |
| npm | 9 or later (bundled with Node.js) |
| MongoDB Community | 6.x or later, running on `127.0.0.1:27017` (local demo only) |

---

## Getting the Code

**Clone:**
```bash
git clone https://github.com/Bharath-S-Gujjar/lead-magnet.git
cd lead-magnet
```

**Download ZIP:** Use the *Code → Download ZIP* button on GitHub, extract the archive, and `cd lead-magnet`.

---

## Quick Start (Local Demo)

> Full instructions with troubleshooting are in each component's README.

**1. Backend (Python virtual environment required):**
```bash
# Windows PowerShell
python -m venv venv
venv\Scripts\activate
pip install -r backend/requirements.txt
python backend/local_test_launcher.py --check-isolation   # confirm safety
python backend/local_test_launcher.py --serve --port 5000
```

**2. User Portal:**
```bash
cd frontend/user
npm install
npm run dev          # http://localhost:3001
```

**3. Admin Portal:**
```bash
cd frontend/admin
npm install
npm run dev          # http://localhost:3000
```

Admin login: use the `ADMIN_USERNAME` and `ADMIN_PASSWORD` values from `backend/.env` (defaults for local demo: `admin` / `admin12345`).

> ⚠️ Always start the backend via `local_test_launcher.py --serve`, not `python backend/app.py`, for local demo. The launcher enforces isolated loopback database and dry-run communications.

---

## Testing

```bash
# Backend test suite (678 tests, ~75 seconds)
python -m pytest backend/tests/ -q --tb=short

# Frontend production builds
cd frontend/user  && npm run build
cd frontend/admin && npm run build
```

---

## Documentation

| Document | Location |
|:--|:--|
| **Backend setup, API, isolation, troubleshooting** | [`backend/README.md`](backend/README.md) |
| **User frontend setup and configuration** | [`frontend/user/README.md`](frontend/user/README.md) |
| **Admin frontend setup and configuration** | [`frontend/admin/README.md`](frontend/admin/README.md) |
| **Architecture & data flow (Mermaid diagrams)** | [`docs/architecture_and_data_flow.md`](docs/architecture_and_data_flow.md) |
| **Step-by-step demo guide** | [`docs/demo_guide.md`](docs/demo_guide.md) |
| **Technical design decisions (viva notes)** | [`docs/project_viva_notes.md`](docs/project_viva_notes.md) |
| **ML model documentation** | [`docs/ml.md`](docs/ml.md) |
| **API specification** | [`docs/api.md`](docs/api.md) |
| **Deployment guide** | [`docs/deployment.md`](docs/deployment.md) |
| **Clothing catalog cleaning report** | [`docs/clothing_catalog_cleaning_report.md`](docs/clothing_catalog_cleaning_report.md) |

---

## Current Limitations

| Limitation | Notes |
|:--|:--|
| Live payment gateways not configured | COD path used for local demo; Razorpay/Stripe keys needed for production |
| WhatsApp requires Meta Sandbox allowlist | Test recipients must be pre-registered with Meta Developer dashboard |
| Scheduler is disabled by default | Set `ENABLE_SCHEDULER=true` in production `.env` for background automation |
| Production builds require `VITE_API_BASE_URL` | Set in CI/CD or deployment dashboard; localhost value is rejected at build time |

---

## License

No license file is present in this repository.