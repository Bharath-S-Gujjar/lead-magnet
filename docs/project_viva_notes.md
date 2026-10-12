# Lead Magnet — Project Viva Notes

> **Purpose:** Technical justification notes for viva/presentation. Covers design decisions, architectural trade-offs, ML pipeline rationale, and security/safety choices. Intended for the project author to explain the "why" behind implementation choices.

---

## 1. Project Overview — The Elevator Pitch

**Lead Magnet** is a full-stack AI-powered Customer Intelligence Platform. It simulates a real e-commerce business where:

1. Customers browse and purchase clothing from a 120,466-product catalog.
2. Every customer interaction (page view, cart add, checkout) is captured as behavioral telemetry.
3. A trained XGBoost model continuously scores each customer's purchase intent (0–100).
4. A rule-based marketing automation engine selects the best communication channel and fires targeted messages at the right moment.
5. An admin intelligence dashboard gives business operators complete visibility into customer conversion, funnel health, RFM segmentation, and revenue attribution.

**The core academic contribution:** Demonstrating how ML-driven behavioral analytics can replace static lead qualification forms, enabling real-time, evidence-based marketing interventions.

---

## 2. Technology Choice Justifications

### Why Flask over Django or FastAPI?

- **Flask** was chosen for its explicit, low-magic design. Routes, middleware, and service boundaries are clearly visible in `app.py`.
- **FastAPI** would be superior for a pure API service but was unnecessary given the Socket.IO real-time requirement, which Flask-SocketIO handles cleanly.
- **Django** was overkill for this service-oriented monolith where we needed full control over the authentication pattern (JWT vs. session cookies).

### Why MongoDB over PostgreSQL?

- Behavioral event data (page views, cart events, session telemetry) is naturally document-shaped. Each event has variable fields depending on event type.
- MongoDB's flexible schema allowed rapid iteration on the customer feature vector without schema migrations.
- The product catalog (120,466 products with heterogeneous clothing attributes) benefits from document storage.
- **Trade-off acknowledged:** MongoDB does not enforce relational integrity. This was mitigated by service-layer validation in `customer_feature_service.py` and idempotency keys in `marketing_automation_events`.

### Why XGBoost for Lead Scoring?

- XGBoost is a gradient-boosted decision tree ensemble, well-suited for tabular behavioral data.
- Achieved **≥92.8% validation accuracy** and **0.965 ROC-AUC** on the 11-feature behavioral vector.
- Unlike neural networks, XGBoost is inherently interpretable. Feature contributions (SHAP-style) are used by `model_explainability_service.py` to show admins which behaviors are driving the score.
- **Model is offline-trained** (stored as `model/lead_model.pkl` + `model/scaler.pkl`). At inference time, only `predict_proba()` is called — no GPU, no cloud endpoint required.

### Why React + Vite (not Next.js)?

- The frontend does not require server-side rendering (SSR) or SEO — this is a demonstration platform with a logged-in admin portal.
- Vite provides the fastest cold-start developer experience and tree-shaking build output.
- The admin portal uses Recharts for analytics visualizations (a React-native charting library with no extra dependencies).

---

## 3. ML Pipeline — Design Decisions

### Feature Engineering

The 11 features were chosen to capture:

| Feature Group | Purpose |
|:--|:--|
| Frequency features (session_count, page_view_count) | How often the customer visits |
| Depth features (cart_add_count, wishlist_add_count) | How deep they engage with products |
| Conversion signals (checkout_attempt_count, order_count) | Direct purchase intent |
| Monetary value (total_spent, avg_order_value) | Customer economic value |
| Recency (days_since_last_active) | Staleness / churn risk |
| Composite (engagement_score) | Weighted combination of above |

These features are entirely **behavioral**, not demographic. This avoids bias from age, gender, or location signals.

### Segment Thresholds

| Segment | Score Range | Rationale |
|:--|:--|:--|
| Hot | ≥ 70 | High purchase intent — immediate intervention warranted |
| Warm | 40–69 | Moderate intent — nurturing campaign appropriate |
| Cold | < 40 | Low intent — no intervention to avoid spam/annoyance |

Thresholds were tuned empirically on the validation set to balance precision (avoid false positives sending to cold leads) vs. recall (capture most genuine warm/hot leads).

### Why Not a Neural Network?

- Neural networks for tabular data rarely outperform XGBoost on datasets of this size (<10M rows).
- XGBoost training was ~3–5 seconds on the dataset. Neural network hyperparameter tuning would require significantly more time.
- Interpretability is critical for marketing automation: operators need to know *why* a customer is scored hot, not just that they are.

---

## 4. Marketing Automation — Design Decisions

### Idempotency

Every automation event carries an `idempotency_key` (a deterministic hash of `user_id + trigger_type + date`). This means:

- If the same trigger fires twice (e.g., due to rapid score oscillation), only one communication is sent.
- Restarts or retries cannot cause duplicate messages.
- This is a production-grade pattern used by payment processors and event-driven systems.

### Cooldown Period (72h)

After a qualification campaign is sent, a 72-hour cooldown prevents sending another campaign to the same customer. This was a deliberate product decision:

- Avoids annoyance and opt-out from over-messaging.
- Respects customer communication preferences.
- Configurable via `MARKETING_COOLDOWN_HOURS` environment variable.

### Channel Selection

`channel_selector_service.py` decides between email and WhatsApp based on:

1. Customer opt-in flags (`whatsapp_opt_in`, `whatsapp_opt_out`).
2. Template availability.
3. Channel policy configuration.

The system never sends WhatsApp messages to customers who have not opted in. Opt-out is respected immediately and permanently.

### Dry-Run Provider

`DryRunCommunicationProvider` is the default in all local and testing contexts. It:

- Logs the message content and recipient.
- Records the communication in `marketing_communications` with `provider: "dry_run"`.
- Makes **zero** outbound network calls.
- Allows full end-to-end pipeline testing without any live API credentials.

This is a standard pattern in communication-heavy systems (analogous to email providers' "sandbox" modes).

---

## 5. Security Architecture

### JWT Authentication

- Admin routes are protected by `@admin_required` middleware (`auth_middleware.py`).
- JWTs are signed with `JWT_SECRET` from environment variables (never hardcoded).
- Token expiry is enforced. Expired tokens are rejected with `401 Unauthorized`.

### CORS Configuration

- The allowed origins list in `app.py` (`DEFAULT_ALLOWED_ORIGINS`) is explicitly enumerated.
- **Wildcard CORS (`"*"`) is rejected in production** — the application raises a `ValueError` on startup if `FRONTEND_URL` is set to `"*"` in a production environment. This prevents a common security misconfiguration.

### Security Headers

`app.after_request` injects:
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: SAMEORIGIN`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `X-XSS-Protection: 1; mode=block`

### Password Hashing

Customer passwords are hashed with `bcrypt` before storage. Bcrypt is an adaptive hashing function designed for passwords — it is intentionally slow to prevent brute-force attacks.

### No Insecure TLS Fallback

The `create_mongo_client()` function was specifically hardened to remove the `tlsAllowInvalidCertificates` fallback that previously existed. Both connection attempts use verified TLS certificates; if both fail, the system fails closed (returns `MONGO_AVAILABLE=False`) rather than silently connecting insecurely.

---

## 6. Runtime Isolation Architecture

This is the most technically sophisticated aspect of the project from a software engineering perspective.

### Problem

The production `backend/.env` contains live MongoDB Atlas credentials and real API keys. Any accidental load of this file during testing could:

1. Connect to the production Atlas database and corrupt real data.
2. Trigger real WhatsApp or email communications to real customers.

### Solution: `local_test_launcher.py`

The launcher enforces isolation **before** importing any application module:

1. Sets `TESTING=1` in `os.environ`.
2. `app.py` checks this flag at import time; if set, skips `load_dotenv()` entirely.
3. Launcher then sets all safe overrides: `MONGO_URI=loopback`, `COMMUNICATION_PROVIDER=dry_run`, etc.
4. `assert_local_only_safety()` validates each variable and raises `RuntimeError` on any unsafe value.
5. `verify_database_connection()` physically pings `127.0.0.1:27017` and checks the resolved node address is loopback.

This pattern ensures the safety is enforced structurally, not by convention. Even if a developer accidentally passes an Atlas URI as a CLI argument, `assert_local_only_safety()` rejects it before `MongoClient` is constructed.

---

## 7. Test Coverage

| Test Area | Test File | Coverage |
|:--|:--|:--|
| Database isolation | `test_runtime_database_isolation.py` | URI safety, loopback enforcement |
| Isolation audit | `test_runtime_isolation_audit.py` | Import-time safety invariants |
| Task 21.7 regression | `test_task21_7_regression.py` | Explicit arg safety, CLI entry point |
| Isolation fixture verification | `test_whatsapp_isolated_fixture_verification.py` | Fixture lifecycle |
| Configuration hardening | `test_whatsapp_configuration_hardening.py` | Atlas URI rejection |
| Marketing automation | `test_marketing_automation_service.py` | Cooldown, idempotency, consent |
| Communication provider | `test_communication_provider.py` | Dry-run, channel selection |
| ML lead scoring | `test_lead_scoring_engine.py` | Feature vector, score output |

**Total: 678 tests, 100% passing** (verified Task 22 and Task 23, October 2026).

---

## 8. Known Limitations and Production Readiness

### Intentional Demo-Mode Limitations (Not Defects)

| Limitation | Impact | Production Resolution |
|:--|:--|:--|
| No live payment gateway | COD-only checkout in demo | Configure Razorpay or Stripe with live keys |
| WhatsApp via Meta Sandbox | Requires pre-registered recipient numbers | Production WhatsApp Business account with approved templates |
| `STORE_URL` = localhost | Email URLs go to localhost | Set `STORE_URL` to public HTTPS domain |
| Admin password `admin12345` | Insecure default for local demo | Change `ADMIN_PASSWORD` env var before deployment |
| Scheduler disabled | No background automated campaigns | Set `ENABLE_SCHEDULER=true` in production env |

### Architecture Scalability Notes

- The current Flask monolith could be decomposed into microservices (ML service, communication service, analytics service) for high-traffic production use.
- The MongoDB Atlas M0 free tier has throughput limits; a dedicated cluster (M10+) would be needed for production load.
- `Flask-SocketIO` with `eventlet` works well for a single-server deployment. For multi-instance deployments, a Redis message broker would be needed for the Socket.IO channel.

---

## 9. Data Source — Myntra Clothing Catalog

The 120,466 product records are sourced from a public Myntra clothing dataset:

- **Gender distribution:** Women 56.5%, Men 42.7%, Kids 0.8%
- **Price range:** INR 149 to INR 19,999
- **Normalization applied:** Ratings normalized to 0.0–5.0, discounts calculated from original and current prices, `product_id` field added as a deterministic unique identifier.
- **No synthetic data:** Zero fabricated stock levels, images, SKUs, or reviews were added. Products that lacked mandatory fields were excluded during cleaning.

The cleaning methodology is documented in detail in [`docs/clothing_catalog_cleaning_report.md`](clothing_catalog_cleaning_report.md).

---

## 10. Key Design Principle — "Fail Closed"

The system is designed to fail closed on any safety-critical decision:

- MongoDB connection failure → `MONGO_AVAILABLE=False`, routes return `503` rather than serving stale data.
- Atlas URI detected in local launcher → `RuntimeError` before any client is constructed.
- Missing WhatsApp consent → communication blocked entirely.
- `ALLOW_REAL_DISPATCH=false` → communication function returns early before any provider is called.
- Wildcard CORS in production → `ValueError` at startup prevents the server from running.

This principle ensures that misconfiguration produces a visible, immediate failure rather than a subtle, hard-to-detect data corruption or privacy breach.

---

*Document generated as part of Task 24 — Lead Magnet Final Audit and Demo Preparation.*
