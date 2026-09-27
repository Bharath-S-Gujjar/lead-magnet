# Lead Magnet — Local Development & Setup Guide

This guide describes how to configure, set up, and run the complete Lead Magnet platform locally for development, testing, and demonstration.

---

## 1. System Requirements

- **Python**: 3.10+ (Python 3.11 / 3.12 / 3.14 compatible)
- **Node.js**: v18.0+ (with `npm`)
- **Database**: MongoDB Atlas cluster or local MongoDB instance (v6.0+)
- **Git**: Installed and available in terminal

---

## 2. Repository Structure

```text
lead-magnet/
├── backend/                  # Flask REST API, WebSocket server, ML inference services
│   ├── tests/                # Comprehensive test suite (200 test cases)
│   ├── app.py                # Main Flask application entrypoint
│   └── requirements.txt      # Python dependencies
├── frontend/
│   ├── admin/                # React/Vite Admin Intelligence Portal
│   └── user/                 # React/Vite Customer E-Commerce Store
├── data/                     # Catalog datasets, raw, cleaned, and ML feature sets
│   ├── catalog/              # Authoritative 120,466 Myntra clothing catalog
│   └── ml/                   # ML training datasets
├── docs/                     # Authoritative system documentation
├── model/                    # Serialized ML models (XGBoost, Scalers, Metadata)
└── scripts/                  # Reproducible data pipelines & ML training scripts
```

---

## 3. Backend Setup

### 3.1 Virtual Environment
From the repository root:
```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
```

### 3.2 Install Dependencies
```bash
pip install -r backend/requirements.txt
```

### 3.3 Environment Variables
Configure `backend/.env` (using `backend/.env.example` as reference):
```env
PORT=5000
FLASK_ENV=development
MONGO_URI=mongodb+srv://<username>:<password>@<cluster>.mongodb.net/?retryWrites=true&w=majority
MONGO_DB_NAME=leadmagnet
JWT_SECRET=your_jwt_secret_key_here
CLIENT_URL=http://localhost:5173
ADMIN_URL=http://localhost:5174
```

### 3.4 Verify Connection & Run Tests
```bash
# Run isolated test suite
pytest backend/tests/ -v
```

### 3.5 Start the Backend Server
```bash
# From backend directory
cd backend
python app.py
```
Backend starts on `http://127.0.0.1:5000`.

---

## 4. Frontend Setup

### 4.1 Admin Intelligence Portal
```bash
cd frontend/admin
npm install
npm run dev
```
Access at `http://localhost:5174` (or port indicated by Vite).

### 4.2 Customer Store (User Portal)
```bash
cd frontend/user
npm install
npm run dev
```
Access at `http://localhost:5173`.

---

## 5. Catalog Ingestion & ML Pipeline (Reproducibility)

To rebuild the clothing catalog or retrain the machine learning model from source:

- **Build Cleaned Catalog**:
  ```bash
  python scripts/build_catalog.py
  ```
- **Train E-Commerce Lead Model**:
  ```bash
  python scripts/train_ecommerce_model.py
  ```
- **Validate Feature Store**:
  ```bash
  python scripts/validate_ecommerce_dataset.py
  ```
