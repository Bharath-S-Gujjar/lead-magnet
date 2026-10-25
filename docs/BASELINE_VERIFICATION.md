# Lead Magnet: Phase 0 Baseline Verification & Audit Validation Report

**Date of Verification:** October 2026  
**Auditor / Verification Lead:** Senior Software Architect, Backend, ML & QA Engineer  
**Workspace Root:** `D:\lead-magnet`  
**Git Branch:** `main`  
**Current Commit:** `e6b661fd` (*"Finalize Lead Magnet frontend and customer intelligence updates"*)  
**Execution Constraints:** Read-only inspection and non-destructive execution (zero application source code mutations, zero database writes to non-test databases, zero external API calls).

---

## 1. Executive Baseline Summary

Phase 0 establishes the empirical baseline of the **Lead Magnet** repository prior to implementing remediation in subsequent phases. Every claim made in the previous technical audit ([`docs/LEAD_MAGNET_TECHNICAL_AUDIT.md`](file:///d:/lead-magnet/docs/LEAD_MAGNET_TECHNICAL_AUDIT.md)) has been systematically cross-referenced against the actual source code, directory structures, function signatures, runtime entry points, and test suites.

### Key Verification Highlights:
1. **Source Code Unmodified in Phase 0**: In compliance with strict Phase 0 instructions, zero application source code, configuration files, model binaries, or persistent database collections have been altered.
2. **Backend Test Suite Status**: **685 tests passed** (0 failures, 0 errors, 397 localhost URL warnings) in **53.71 seconds** running against the isolated local test database (`leadmagnet_test` on `127.0.0.1:27017`).
3. **Frontend Production Builds**:
   - **User Storefront** (`frontend/user`): Built successfully in **3.78 seconds** via Vite v6.4.3.
   - **Admin Portal** (`frontend/admin`): Built successfully in **5.76 seconds** via Vite v6.4.3.
4. **Backend Runtime Health**: Backend server running on port 5000 verified healthy (`GET /api/health` returned `{"mongo": true, "success": true}`).
5. **Critical Discrepancies Discovered in Audit Report**:
   - **Module File Paths**: The audit report cited `backend/services/ecommerce_model_adapter.py`, `backend/services/scoring_service.py`, and `backend/services/reefapi_service.py`. Inspection confirms the directory `backend/services/` **does not exist**. All backend service files reside directly in `backend/` (`backend/ecommerce_model_adapter.py`, `backend/lead_scoring_engine.py`, `backend/reef_api_client.py`, `backend/myntra_catalog_refresh_service.py`).
   - **Test Count**: The audit cited 678 tests; current execution verifies **685 passing tests** across 52 test files.
   - **Feature Count & Threshold Docs Contradiction**: Confirmed that `README.md:18` incorrectly claims an "11-feature behavioral vector" (code uses **23 features** in `backend/ecommerce_model_adapter.py:57-85`), and `docs/ml.md:13` incorrectly claims Cold $< 0.40$ (code executes $< 0.35$ in `backend/ecommerce_model_adapter.py:178-184`).

---

## 2. Git & Working-Tree State

* **Branch:** `main`
* **Head Commit:** `e6b661fd`
* **Working-Tree Status (`git status -s`):**
  ```text
  ?? docs/LEAD_MAGNET_TECHNICAL_AUDIT.md
  ```
  *(Only the technical audit report generated in the previous step is untracked; zero uncommitted modifications exist in application source code).*
* **Active Branches:**
  - `* main`: `e6b661fd`
  - `feature/demo-polish`: `cb9ccade`

---

## 3. Audit Claim Verification Matrix

Every technical claim from `docs/LEAD_MAGNET_TECHNICAL_AUDIT.md` was checked for file existence, exact line ranges, entry-point reachability, and automated test coverage:

| Audit Claim | Cited File & Path | Verified File & Location | Status | Reachability & Entry Point | Test Coverage | Discrepancies & Findings |
|---|---|---|---|---|---|---|
| **E-Commerce ML Model Adapter** | `backend/services/ecommerce_model_adapter.py` | [`backend/ecommerce_model_adapter.py`](file:///d:/lead-magnet/backend/ecommerce_model_adapter.py) | **VERIFIED (Path corrected)** | Called by `lead_scoring_engine.py:17` on user behavioral telemetry | [`backend/tests/test_model_adapter.py`](file:///d:/lead-magnet/backend/tests/test_model_adapter.py), [`test_ecommerce_lead_inference.py`](file:///d:/lead-magnet/backend/tests/test_ecommerce_lead_inference.py) | File is in `backend/`, not `backend/services/`. Implements `predict_customer_features` evaluating 23 features. |
| **Central Lead Scoring Engine** | `backend/services/scoring_service.py` | [`backend/lead_scoring_engine.py`](file:///d:/lead-magnet/backend/lead_scoring_engine.py) | **VERIFIED (File renamed)** | Called by `backend/app.py:76` and behavioral event ingestion routes | [`backend/tests/test_lead_processing_service.py`](file:///d:/lead-magnet/backend/tests/test_lead_processing_service.py) | Actual file is `lead_scoring_engine.py`. Implements 1.0-second debounce and orchestrates scoring -> state sync -> history -> admin WS events. |
| **Qualification & Lead State** | `backend/services/customer_lead_state_service.py` | [`backend/customer_lead_state_service.py`](file:///d:/lead-magnet/backend/customer_lead_state_service.py) | **VERIFIED** | Called by `lead_scoring_engine.py:15` | [`backend/tests/test_customer_lead_state.py`](file:///d:/lead-magnet/backend/tests/test_customer_lead_state.py) | Confirmed `QUALIFICATION_PROBABILITY_THRESHOLD = 0.70`. Triggers `marketing_automation_service` on `is_newly_qualified`. |
| **Catalog Refresh & ReefAPI** | `backend/services/reefapi_service.py` | [`backend/reef_api_client.py`](file:///d:/lead-magnet/backend/reef_api_client.py) & [`backend/myntra_catalog_refresh_service.py`](file:///d:/lead-magnet/backend/myntra_catalog_refresh_service.py) | **VERIFIED (Two files)** | Invoked in background scheduler job `myntra_catalog_refresh_service.run_catalog_refresh_cycle` | [`backend/tests/test_reef_api_client.py`](file:///d:/lead-magnet/backend/tests/test_reef_api_client.py), [`test_myntra_catalog_refresh_service.py`](file:///d:/lead-magnet/backend/tests/test_myntra_catalog_refresh_service.py) | Client logic is in `reef_api_client.py`; refresh scheduling & budget guardrails (5 max calls, 50 reserve) are in `myntra_catalog_refresh_service.py`. |
| **Multi-Channel Provider** | `backend/services/communication_provider.py` | [`backend/communication_provider.py`](file:///d:/lead-magnet/backend/communication_provider.py) | **VERIFIED** | Called by `marketing_automation_service.py:21` | [`backend/tests/test_communication_providers.py`](file:///d:/lead-magnet/backend/tests/test_communication_providers.py), [`test_communication_engine.py`](file:///d:/lead-magnet/backend/tests/test_communication_engine.py) | Implements `GmailSMTPProvider` (TLS port 587) and `WhatsAppBusinessProvider` (Meta Cloud API). Zero SMS. |
| **Distributed Scheduler** | `backend/services/scheduler_service.py` | [`backend/scheduler_service.py`](file:///d:/lead-magnet/backend/scheduler_service.py) | **VERIFIED** | Launched conditionally in `backend/app.py:2910` | [`backend/tests/test_scheduler_lease_hardening.py`](file:///d:/lead-magnet/backend/tests/test_scheduler_lease_hardening.py), [`test_scheduler_production_safety.py`](file:///d:/lead-magnet/backend/tests/test_scheduler_production_safety.py) | Distributed lease locking on `scheduler_locks` collection using atomic `find_one_and_update`. |
| **Dual ML Model Artifacts** | `model/xgb_model.pkl` & `model/ecommerce_xgb_model.pkl` | [`model/`](file:///d:/lead-magnet/model/) | **VERIFIED** | `POST /predict` calls legacy model; all customer intelligence uses active e-commerce model | [`backend/tests/test_predict.py`](file:///d:/lead-magnet/backend/tests/test_predict.py), [`test_ecommerce_ml_pipeline.py`](file:///d:/lead-magnet/backend/tests/test_ecommerce_ml_pipeline.py) | Legacy model: 334 KB (`xgb_model.pkl`); Active model: 257 KB (`ecommerce_xgb_model.pkl`). Evaluates 23 features. |
| **Database Collections** | 22 MongoDB Collections | `backend/app.py:248-264` & service modules | **VERIFIED** | Bound on startup via `bind_collections(mongo_client)` | [`backend/tests/test_db_isolation.py`](file:///d:/lead-magnet/backend/tests/test_db_isolation.py), [`test_runtime_database_isolation.py`](file:///d:/lead-magnet/backend/tests/test_runtime_database_isolation.py) | 22 collections confirmed in active code; `docs/02_DATABASE_SCHEMA.md` is outdated (lists only 11). |

---

## 4. Empirical Baseline Execution Results

### 4.1 Backend Automated Test Suite
* **Execution Command:**
  ```powershell
  & "D:\lead-magnet\venv\Scripts\python.exe" run_tests.py
  ```
* **Execution Environment:** Windows, Python 3.11.9, pytest 9.1.1, pluggy 1.6.0.
* **Test Isolation Invariants:** Guaranteed by `backend/tests/_isolation.py` and `run_tests.py`:
  - `TESTING = "1"`
  - `MONGO_URI = "mongodb://127.0.0.1:27017"`
  - `MONGO_DB_NAME = "leadmagnet_test"`
  - `COMMUNICATION_PROVIDER = "dry_run"`
  - `ENABLE_SCHEDULER = "false"`
* **Outcome:**
  ```text
  ===================== 685 passed, 397 warnings in 53.71s ======================
  ```
* **Status:** **100% PASS (685/685 tests)**.
* **Diagnostics on Warnings:** All 397 warnings are non-fatal runtime `UserWarning` emissions from `backend/marketing_automation_service.py` and `backend/price_drop_opportunity_service.py` alerting that `STORE_URL` resolves to `http://localhost:3001` (intended development behavior).

### 4.2 Frontend Production Builds

#### A. User Storefront (`frontend/user`)
* **Execution Command:**
  ```powershell
  cd D:\lead-magnet\frontend\user
  npm run build
  ```
* **Build Tool:** Vite v6.4.3
* **Outcome:**
  ```text
  vite v6.4.3 building for production...
  transforming...
  ✓ 656 modules transformed.
  rendering chunks...
  computing gzip size...
  dist/index.html                   0.90 kB │ gzip:   0.49 kB
  dist/assets/index-rNqfOe0B.css   25.32 kB │ gzip:   5.37 kB
  dist/assets/index-BPwjuIMz.js   722.66 kB │ gzip: 206.49 kB
  ✓ built in 3.78s
  ```
* **Status:** **PASS** (Zero build errors, bundle emitted in 3.78s).

#### B. Admin Intelligence Portal (`frontend/admin`)
* **Execution Command:**
  ```powershell
  cd D:\lead-magnet\frontend\admin
  npm run build
  ```
* **Build Tool:** Vite v6.4.3
* **Outcome:**
  ```text
  vite v6.4.3 building for production...
  transforming...
  ✓ 2254 modules transformed.
  rendering chunks...
  computing gzip size...
  dist/index.html                   0.93 kB │ gzip:   0.50 kB
  dist/assets/index-Bh_d56LG.css   20.40 kB │ gzip:   4.58 kB
  dist/assets/index-DPtJEzJi.js   753.07 kB │ gzip: 213.05 kB
  ✓ built in 5.76s
  ```
* **Status:** **PASS** (Zero build errors, bundle emitted in 5.76s).

### 4.3 Backend Server Startup & Local Services
* **Active Backend Process:** PID 3404 running `D:\lead-magnet\venv\Scripts\python.exe app.py` on port 5000.
* **Health Check Probe:**
  ```powershell
  Invoke-RestMethod -Uri "http://127.0.0.1:5000/api/health" -Method Get
  ```
* **Response:**
  ```json
  {
    "mongo": true,
    "success": true
  }
  ```
* **Required Local Services:**
  - MongoDB 7.0+ on `127.0.0.1:27017` (Active & verified).
  - Node.js v24.14.1.0 and npm (Installed & verified).
  - Python 3.11.9 in `D:\lead-magnet\venv\` (Active & verified).

---

## 5. Security & Isolation Baseline Findings

1. **Production Fallback Secrets in `backend/app.py`**:
   - `JWT_SECRET`: Evaluates `os.getenv("JWT_SECRET") or "default_jwt_secret_key_for_lead_magnet"` (`app.py:426`). If `FLASK_ENV == "production"`, lines 433-435 raise `ValueError`. In non-production, the default insecure string is permitted.
   - `ADMIN_PASSWORD`: Evaluates `os.getenv("ADMIN_PASSWORD", "admin12345")` (`app.py:430`). Production raises `ValueError` (`app.py:436-437`).
2. **CORS Configuration in `backend/app.py`**:
   - `DEFAULT_ALLOWED_ORIGINS`: Ports 5173, 5174, 3000, 3001 on `localhost` and `127.0.0.1` (`app.py:91-100`).
   - Production validation: Rejects wildcard `*` if `IS_PROD_ENV == True` (`app.py:107-121`).
3. **Communication Provider Default Behavior in `backend/communication_provider.py`**:
   - Lines 560-568 inspect `COMMUNICATION_PROVIDER`. If unset, it checks whether SMTP or WhatsApp credentials exist in the environment. If credentials are present, it auto-promotes to `multi_channel`.
   - **Remediation Requirement for Phase 1**: Live communication must be explicitly opt-in (`COMMUNICATION_PROVIDER=multi_channel` or `ALLOW_REAL_DISPATCH=true`); an unset variable must always fail safe to `dry_run`.
4. **Local Test Launcher Invariants**:
   - [`backend/local_test_launcher.py`](file:///d:/lead-magnet/backend/local_test_launcher.py) verified with `--check-isolation`:
     ```text
     Isolation Guard:          ACTIVE (TESTING=1, LOCAL_ONLY_TESTING=1)
     Target Database Host:     127.0.0.1:27017 (Loopback Verified)
     Target Database Name:     leadmagnet_test (Isolated Test DB)
     Remote Atlas Status:      ZERO REMOTE NODES (Atlas Completely Disconnected)
     Communication Provider:   dry_run (Dry-Run Enforced)
     Real Dispatch Switch:     false (Blocked)
     Scheduler State:          false (Disabled)
     ```

---

## 6. Dependency & Manifest Baseline

1. **Python Dependencies (`backend/requirements.txt`)**:
   - Contains 168 declared packages.
   - Core runtime dependencies verified: `Flask==3.1.3`, `Flask-Cors==6.0.1`, `Flask-SocketIO==5.6.1`, `pymongo==4.18.1`, `xgboost==3.4.1`, `scikit-learn==1.9.1`, `pandas==3.0.6`, `numpy==2.5.3`, `requests==2.34.2`, `PyJWT==2.10.1`, `python-dotenv==1.2.2`, `gunicorn==23.0.0`, `eventlet==0.40.4`.
   - Phantom / Unused dependencies confirmed in manifest: `torch`, `torchvision`, `torchaudio`, `fastapi`, `uvicorn`, `streamlit`, `langchain`, `huggingface_hub`, `google-api-python-client`, `google-auth-oauthlib`. None of these are imported in application code.
2. **Node Dependencies**:
   - User Portal (`frontend/user/package.json`): React 18.3.1, Vite 6.0.7, React Router DOM 6.28.0, Recharts 3.10.1, Lucide React 0.469.0.
   - Admin Portal (`frontend/admin/package.json`): React 18.3.1, Vite 6.0.7, React Router DOM 7.18.2, Recharts 2.15.0, Socket.io-client 4.8.3, Lucide React 0.469.0.

---

## 7. Model & Data Provenance Baseline

1. **Active E-Commerce Model (`v2.0_ecommerce_xgb`)**:
   - Binary: `model/ecommerce_xgb_model.pkl`
   - Scaler: `model/ecommerce_scaler.pkl`
   - Feature Columns: `model/ecommerce_feature_columns.pkl` (23 features)
   - Metadata: `model/ecommerce_model_metadata.json`
   - Training Dataset: `data/ml/ecommerce_customer_behavior.csv` (6,000 samples, 100% synthetic, generated via log-odds formula with Gaussian noise in `scripts/generate_ecommerce_dataset.py`).
   - Synthetic Metrics: Validation ROC-AUC = 0.9573, PR-AUC = 0.9417, Precision@Top-10% = 1.0.
   - **Crucial Engineering Distinction**: These metrics represent benchmark performance on synthetic formulaic distributions; they do **not** demonstrate real-world purchase prediction efficacy on human shoppers.
2. **Catalog Ingestion Provenance**:
   - Source: 3 Excel files in root (`Kids.xlsx`, `WOMEN.xlsx`, `myntra-MEN.xlsx` totalling 567,001 rows).
   - Ingestion Script: `scripts/build_catalog.py` produces `data/catalog/cleaned_clothing_catalog.csv` (120,466 products, SHA-256 deduplicated).
   - Database Collection: Loaded into MongoDB `myntra_products`.

---

## 8. Summary of Baseline Acceptance Criteria

| Check Item | Requirement | Observed Status | Phase 0 Verdict |
|---|---|---|---|
| **Git Working Tree** | No uncommitted source changes | Clean working tree on `main` | **PASSED** |
| **Backend Tests** | Run in isolated local test environment | 685 passed in 53.71s | **PASSED** |
| **User Frontend** | Production build passes | Built in 3.78s via Vite | **PASSED** |
| **Admin Frontend** | Production build passes | Built in 5.76s via Vite | **PASSED** |
| **Backend Startup** | Health endpoint responds | `{"mongo": true, "success": true}` | **PASSED** |
| **Isolation Safeguards** | Zero remote calls / Atlas connections | Enforced by `_isolation.py` & launcher | **PASSED** |
| **Source Integrity** | No application source edits in Phase 0 | 0 source files modified | **PASSED** |

---

**End of Phase 0 Baseline Verification Report.**  
*Execution halted per strict Phase gating rules. Awaiting user authorization to proceed to Phase 1.*
