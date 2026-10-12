# Lead Magnet — Architecture and Data Flow Reference

> **Scope:** Authoritative technical reference for the Lead Magnet platform as of Task 24 (October 2026). All diagrams are derived from direct inspection of `backend/app.py`, service modules, and verified against the Task 23 local acceptance test results (678/678 tests passing).

---

## 1. System Overview

Lead Magnet is a full-stack AI-powered Customer Intelligence Platform consisting of three independently-deployable tiers:

| Tier | Technology | Role |
|:--|:--|:--|
| **User Portal** | React 18 + Vite | Customer-facing e-commerce storefront |
| **Admin Portal** | React 18 + Vite | Internal intelligence & analytics dashboard |
| **Backend API** | Flask + Flask-SocketIO | REST API, WebSocket relay, ML inference, automation |
| **Database** | MongoDB (Atlas in production / `127.0.0.1:27017` for local demo) | Persistent document store for all collections |
| **ML Engine** | XGBoost + Scikit-Learn (offline-trained, serialized) | Real-time lead scoring inference |

---

## 2. High-Level System Architecture

```mermaid
graph TB
    UP["User Portal<br/>(React + Vite, :3001)"]
    AP["Admin Portal<br/>(React + Vite, :3000)"]

    subgraph Backend ["Flask Backend (:5000)"]
        direction TB
        FA["Flask App - app.py<br/>REST Routes + JWT Auth"]
        SIO["Flask-SocketIO<br/>Real-time Event Relay"]
        ML["ML Inference Layer<br/>XGBoost + Scaler"]
        BES["Behavior Event Service"]
        MAS["Marketing Automation Service"]
        AIS["Admin Intelligence Service"]
        CFS["Customer Feature Store"]
        CLS["Customer Lead State Service"]
        CP["Communication Provider<br/>Dry-Run or WhatsApp or Email"]
    end

    subgraph DB ["MongoDB"]
        CORE["Core Collections<br/>user_profiles, sessions, events<br/>cart, wishlist, orders"]
        ML_COL["ML Collections<br/>customer_features<br/>customer_lead_state<br/>lead_score_history"]
        MKTG["Marketing Collections<br/>marketing_automation_events<br/>marketing_communications<br/>admin_notifications"]
        PROD["Product Collection<br/>myntra_products 120466 docs"]
    end

    UP -- "HTTP REST + WebSocket" --> FA
    AP -- "HTTP REST + WebSocket" --> FA
    FA --> SIO
    FA --> BES
    FA --> ML
    FA --> MAS
    FA --> AIS
    BES --> CFS
    CFS --> CLS
    CLS --> ML
    ML --> CLS
    MAS --> CP
    FA --- CORE
    FA --- ML_COL
    FA --- MKTG
    FA --- PROD
    SIO --> AP
```

---

## 3. Request Lifecycle — End-to-End Sequence

```mermaid
sequenceDiagram
    participant Browser as User Browser
    participant UP as User Portal React
    participant API as Flask Backend
    participant DB as MongoDB
    participant ML as XGBoost Engine
    participant MAS as Marketing Automation

    Browser->>UP: Opens storefront
    UP->>API: POST /api/session/start
    API->>DB: Insert sessions document
    API-->>UP: session_id, visitor_id

    Browser->>UP: Views product
    UP->>API: POST /api/session/event product_view
    API->>DB: Insert events document

    Browser->>UP: Adds to cart
    UP->>API: POST /api/cart/add
    API->>DB: Upsert cart document
    API->>ML: aggregate_customer_features()
    ML->>DB: Read events, cart, wishlist, orders
    ML-->>API: 11-feature behavioral vector
    API->>ML: XGBoost.predict_proba()
    ML-->>API: conversion_probability 0.0 to 1.0
    API->>DB: Upsert customer_lead_state score+segment
    API->>MAS: create_automation_event_for_qualification()
    MAS->>DB: Check cooldown marketing_communications
    MAS->>DB: Write marketing_automation_events idempotency_key
    MAS-->>API: Opportunity created

    Browser->>UP: Checkout
    UP->>API: POST /api/orders
    API->>DB: Insert orders document
    API->>MAS: trigger_order_confirmation_communication()
    MAS-->>API: Dry-run or real dispatch logged
```

---

## 4. ML Lead Scoring Pipeline

```mermaid
flowchart LR
    A["Customer Action<br/>page view / cart add / checkout"]
    B["aggregate_customer_features()<br/>customer_feature_service.py"]
    C["11-Feature Behavioral Vector<br/>session_count, cart_add_count,<br/>order_count, total_spent ..."]
    D["ecommerce_model_adapter.py<br/>predict_customer_features()"]
    E["StandardScaler<br/>model/scaler.pkl"]
    F["XGBoostClassifier<br/>model/lead_model.pkl<br/>92.8% validation accuracy<br/>ROC-AUC 0.965"]
    G["conversion_probability 0.0 to 1.0"]
    H{"Segment<br/>Classification"}
    I["Hot Lead score >= 70"]
    J["Warm Lead score >= 40"]
    K["Cold Lead score < 40"]
    L["customer_lead_state upsert<br/>+ lead_score_history append"]
    M["model_explainability_service<br/>Feature Contribution Breakdown"]

    A --> B --> C --> D --> E --> F --> G --> H
    H --> I --> L
    H --> J --> L
    H --> K --> L
    G --> M
```

### 11 Behavioral Features Fed to XGBoost

| # | Feature | Source |
|:--|:--|:--|
| 1 | `session_count` | sessions collection |
| 2 | `page_view_count` | events collection |
| 3 | `cart_add_count` | cart collection |
| 4 | `wishlist_add_count` | wishlist collection |
| 5 | `order_count` | orders collection |
| 6 | `total_spent` | orders collection |
| 7 | `avg_order_value` | computed from orders |
| 8 | `days_since_last_active` | user_profiles |
| 9 | `engagement_score` | computed composite |
| 10 | `search_count` | events collection |
| 11 | `checkout_attempt_count` | events collection |

---

## 5. Marketing Automation Pipeline

```mermaid
flowchart TD
    A["Customer Lead State Change<br/>score threshold crossed"]
    B["create_automation_event_for_qualification()<br/>marketing_automation_service.py"]
    C{"Cooldown Check<br/>default 72h"}
    N1["BLOCKED — within cooldown"]
    D["Write idempotency_key<br/>to marketing_automation_events"]
    E["channel_selector_service.py<br/>Choose email / whatsapp / both"]
    F{"Consent and<br/>Opt-out Check"}
    N2["BLOCKED — no consent"]
    G["Build message template<br/>cart abandon / browse-incentive<br/>post-purchase / registration"]
    H["CommunicationProvider.send()"]
    I["DryRunProvider<br/>local / test — no network calls"]
    J["WhatsAppProvider<br/>Meta Cloud API"]
    K["EmailProvider<br/>Gmail SMTP"]
    L["Write marketing_communications<br/>status, provider, sent_at"]
    M["Emit admin_notifications<br/>via SocketIO"]

    A --> B --> C
    C -- "Within cooldown" --> N1
    C -- "Cooldown elapsed" --> D --> E --> F
    F -- "No consent or opted out" --> N2
    F -- "Consented" --> G --> H
    H --> I --> L --> M
    H --> J --> L --> M
    H --> K --> L --> M
```

### Communication Trigger Events

| Trigger Function | Fired When |
|:--|:--|
| `trigger_registration_communication()` | User completes signup |
| `trigger_cart_abandonment_communication()` | Cart add + no checkout within threshold |
| `trigger_wishlist_reminder_communication()` | Wishlist items not purchased |
| `trigger_order_confirmation_communication()` | Successful order placed |
| `create_automation_event_for_qualification()` | Lead score crosses Hot/Warm threshold |

---

## 6. Identity Resolution Flow

```mermaid
flowchart LR
    A["Anonymous Visit<br/>no account"]
    B["generate_anonymous_id()<br/>identity_service.py"]
    C["session started with visitor_id"]
    D["Events logged under visitor_id"]
    E["User Registers / Logs In"]
    F["resolve_anonymous_identity()<br/>identity_service.py"]
    G["visitor_id -> user_id link stored"]
    H["All prior events backfilled<br/>to authenticated user_id"]
    I["Unified 360 degree Profile Available"]

    A --> B --> C --> D --> E --> F --> G --> H --> I
```

---

## 7. Admin Portal Real-Time Data Flow

```mermaid
flowchart LR
    subgraph AdminPortal["Admin Portal React"]
        OV["Overview & Metrics"]
        CL["Customer Directory"]
        FF["Funnel Analytics"]
        RF["RFM Segmentation"]
        RA["Revenue Attribution"]
        WI["What-If Simulator"]
        LF["Live Activity Feed WebSocket"]
    end

    subgraph Backend["Flask Backend"]
        AIS["admin_intelligence_service.py"]
        RFM["rfm_service.py"]
        FUN["funnel_analytics_service.py"]
        WIF["whatif_simulator_service.py"]
        REV["revenue_attribution_service.py"]
        SIO_E["SocketIO Event Emitter"]
    end

    OV -- "GET /api/admin/intelligence/overview" --> AIS
    CL -- "GET /api/admin/intelligence/leads" --> AIS
    FF -- "GET /api/admin/analytics/funnel" --> FUN
    RF -- "GET /api/admin/analytics/rfm" --> RFM
    RA -- "GET /api/admin/analytics/revenue-attribution" --> REV
    WI -- "POST /api/admin/simulate/lead-score" --> WIF
    LF -- "WebSocket marketing_event" --> SIO_E
```

---

## 8. Database Collections Reference

| Collection | Purpose | Key Indexes |
|:--|:--|:--|
| `user_profiles` | Authenticated customer profiles, consent flags | `email (unique)` |
| `sessions` | Anonymous and authenticated browsing sessions | `visitor_id`, `user_id` |
| `events` | Granular behavioral events (page_view, cart_add…) | `session_id`, `user_id` |
| `cart` | Current cart state per user | `user_id (unique)` |
| `wishlist` | Saved wishlist items per user | `user_id` |
| `orders` | Completed and pending orders | `user_id`, `created_at` |
| `myntra_products` | 120,466 clothing product catalog | `product_id (unique)`, `category`, `brand`, `gender` |
| `customer_features` | Aggregated 11-feature behavioral vector | `user_id (unique)` |
| `customer_lead_state` | Current ML score, segment, qualification status | `user_id (unique)` |
| `lead_score_history` | Timestamped score change log per customer | `user_id`, `computed_at` |
| `marketing_automation_events` | Automation triggers with idempotency keys | `idempotency_key (unique)` |
| `marketing_communications` | All sent (or dry-run) communications | `user_id`, `sent_at` |
| `admin_notifications` | Admin-facing alerts and opportunity cards | `created_at` |
| `campaigns` | Configured marketing campaigns | — |

---

## 9. Application Startup Sequence

```mermaid
sequenceDiagram
    participant Launcher as local_test_launcher.py
    participant App as app.py
    participant DB as MongoDB

    Launcher->>Launcher: configure_local_test_environment()<br/>Injects TESTING=1, MONGO_URI=loopback,<br/>COMMUNICATION_PROVIDER=dry_run
    Launcher->>Launcher: assert_local_only_safety() -- fail closed on any remote URI
    Launcher->>DB: verify_database_connection() -- ping 127.0.0.1:27017
    DB-->>Launcher: OK
    Launcher->>App: import app, socketio, initialize_database
    App->>App: create_mongo_client() -- reads MONGO_URI from os.environ
    App->>DB: MongoClient.admin.command ping
    App->>App: bind_collections() -- bind all 14 named collections
    App->>App: ensure_indexes() -- idempotent index creation
    App->>App: ENABLE_SCHEDULER check -- skip if false
    App-->>Launcher: Flask app ready
    Launcher->>App: socketio.run app port 5000
```

---

## 10. Communication Provider Architecture

```mermaid
classDiagram
    class CommunicationProvider {
        send_whatsapp(phone, template, params) dict
        send_email(to, subject, body) dict
    }
    class DryRunCommunicationProvider {
        send_whatsapp() dict : logs only zero network calls
        send_email() dict : logs only zero network calls
    }
    class WhatsAppCommunicationProvider {
        send_whatsapp() dict : Meta Cloud API v21.0
        PHONE_NUMBER_ID, ACCESS_TOKEN from env
    }
    class GmailCommunicationProvider {
        send_email() dict : Gmail SMTP port 587 TLS
        GMAIL_USER, GMAIL_APP_PASSWORD from env
    }
    CommunicationProvider <|-- DryRunCommunicationProvider
    CommunicationProvider <|-- WhatsAppCommunicationProvider
    CommunicationProvider <|-- GmailCommunicationProvider
```

**Provider Selection** (`get_communication_provider()`):

| `COMMUNICATION_PROVIDER` value | Provider Selected |
|:--|:--|
| `dry_run` (default / unset) | `DryRunCommunicationProvider` — safe for all local/test use |
| `whatsapp` | `WhatsAppCommunicationProvider` — requires Meta API keys |
| `gmail` | `GmailCommunicationProvider` — requires Gmail credentials |

---

## 11. Safety and Isolation Architecture

The local test launcher enforces strict runtime isolation before any application module is imported:

```mermaid
flowchart TD
    A["local_test_launcher.py --serve"]
    B["assert_local_only_safety()<br/>TESTING=1 required<br/>MONGO_URI must be loopback<br/>MONGO_DB_NAME must contain test<br/>COMMUNICATION_PROVIDER must be dry_run<br/>ALLOW_REAL_DISPATCH must not be true<br/>ENABLE_SCHEDULER must not be true"]
    C{"All checks pass?"}
    D["RuntimeError -- fail closed<br/>App never starts"]
    E["verify_database_connection()<br/>Ping 127.0.0.1:27017<br/>Confirm host is loopback<br/>Confirm port is 27017"]
    F{"Node is loopback?"}
    G["RuntimeError -- fail closed"]
    H["App imported and started safely"]

    A --> B --> C
    C -- "No" --> D
    C -- "Yes" --> E --> F
    F -- "No" --> G
    F -- "Yes" --> H
```

**Safety Invariants Enforced at Runtime:**
- `backend/.env` is never loaded when `TESTING=1` is set before `app.py` is imported.
- `DryRunCommunicationProvider` records all communications without any outbound network calls.
- Idempotency keys in `marketing_automation_events` prevent duplicate communications even during retries.
- `ALLOW_REAL_DISPATCH=false` is enforced at the `marketing_automation_service` dispatch layer.
- 678/678 backend tests pass under this isolation model (verified Task 22, Task 23).

---

*Document generated as part of Task 24 — Lead Magnet Final Audit and Demo Preparation.*
