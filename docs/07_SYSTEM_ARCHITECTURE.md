# Lead Magnet - System Architecture

> This document describes the overall architecture of the Lead Magnet platform, including the interaction between the frontend, backend, database, and machine learning components.

---

# System Overview

Lead Magnet is an AI-powered Customer Intelligence Platform designed using a modular architecture.

The platform consists of:

- User Portal
- Admin Portal
- Flask Backend
- MongoDB Atlas
- Machine Learning Pipeline

The backend acts as the central hub for all business logic.

---

# High-Level Architecture

```
                    +----------------------+
                    |    User Portal       |
                    |     React + Vite     |
                    +----------+-----------+
                               |
                               |
                         REST APIs
                               |
                               v
+-------------------------------------------------------+
|                  Flask Backend                         |
|-------------------------------------------------------|
| Authentication                                        |
| Product APIs                                          |
| Session Tracking                                      |
| Event Tracking                                        |
| Identity Resolution                                   |
| Lead Processing                                       |
| Admin APIs                                            |
| JWT Middleware                                        |
+----------------------+--------------------------------+
                       |
          +------------+------------+
          |                         |
          v                         v
+---------------------+   +--------------------------+
|   MongoDB Atlas     |   | Machine Learning Engine  |
|---------------------|   |--------------------------|
| users               |   | Feature Aggregation      |
| products            |   | Model Adapter            |
| sessions            |   | Scaler                  |
| events              |   | XGBoost                 |
| leads               |   | KMeans                  |
+---------------------+   +--------------------------+
                       |
                       |
                       v
              +----------------------+
              |   Admin Dashboard    |
              |     React + Vite     |
              +----------------------+
```

---

# Current Backend Architecture (V1)

```
Client Request

↓

Flask Route

↓

Service Layer

↓

MongoDB / ML Pipeline

↓

JSON Response
```

Business logic is implemented inside services.

Routes remain lightweight.

---

# Machine Learning Pipeline

```
Session End

↓

Lead Processing Service

↓

Feature Aggregation

↓

Model Adapter

↓

Scaler

↓

XGBoost Model

↓

Probability Score

↓

KMeans

↓

Lead Segment

↓

Action Recommendation

↓

Lead Document Stored
```

The prediction pipeline executes automatically when a browsing session ends.

---

# Authentication Flow

```
Signup/Login

↓

JWT Generated

↓

Frontend Stores JWT

↓

Admin Request

↓

Authorization Header

↓

JWT Middleware

↓

Protected Route
```

Only administrator routes require JWT validation.

---

# Anonymous Visitor Flow

```
Website Visit

↓

anonymous_id Generated

↓

Session Created

↓

Events Recorded

↓

Visitor Browses

↓

Signup/Login

↓

Identity Resolution

↓

user_id Linked

↓

Previous Behaviour Preserved
```

This ensures anonymous browsing history is retained after account creation.

---

# Session Tracking Flow

```
Website Opens

↓

POST /api/session/start

↓

session_id

↓

User Interaction

↓

POST /api/session/event

↓

MongoDB Events

↓

Website Exit

↓

POST /api/session/end

↓

Lead Processing
```

---

# Lead Processing Flow

```
Session

↓

Events

↓

Feature Aggregation

↓

Behavior Features

↓

Model Adapter

↓

166 Model Features

↓

Scaler

↓

XGBoost

↓

KMeans

↓

Hot / Warm / Cold

↓

Lead Saved
```

---

# Admin Dashboard Flow

```
Admin Login

↓

JWT

↓

Dashboard APIs

↓

Lead Collection

↓

Analytics

↓

Dashboard UI
```

The dashboard reads processed lead data rather than executing machine learning during requests.

---

# Version 2 Architecture

Version 2 expands the backend into a complete Customer Intelligence Platform.

```
Anonymous Visitor

↓

Identity Resolution

↓

Sessions

↓

Events

↓

Cart

↓

Wishlist

↓

Orders

↓

Customer Profile Service

↓

+-------------------------+
|                         |
| Lead Scoring            |
| Recommendation Engine   |
| Marketing Automation    |
+-------------------------+

↓

Customer Intelligence Dashboard
```

The Feature Store becomes the shared source of behavioural information for all intelligent modules.

---

# Planned Service Architecture

```
Flask Routes

↓

Services

├── identity_service.py
├── feature_aggregation.py
├── model_adapter.py
├── prediction_service.py
├── lead_processing_service.py
├── recommendation_service.py
├── marketing_service.py
├── notification_service.py
├── cart_service.py
├── wishlist_service.py
├── order_service.py

↓

MongoDB
```

Every service owns exactly one responsibility.

---

# Database Interaction

```
Frontend

↓

Flask

↓

Services

↓

MongoDB Collections

↓

JSON Response
```

The frontend never communicates directly with MongoDB.

---

# Future Recommendation Architecture

```
Customer Profile

↓

Recommendation Engine

↓

Product Ranking

↓

Recommended Products

↓

User Homepage
```

Recommendations will use:

- browsing behaviour
- purchase history
- wishlist
- category affinity
- popularity fallback

---

# Future Marketing Automation

```
Customer Profile

↓

Marketing Rules

↓

Campaign Trigger

↓

Notification Service

↓

Email

SMS

WhatsApp

↓

Campaign Logs
```

Marketing execution remains independent of the lead scoring pipeline.

---

# Design Principles

The architecture follows these principles:

- Modular design
- Single responsibility
- Service-oriented backend
- Thin Flask routes
- Reusable business logic
- Backward compatibility
- Extensible Version 2 architecture
- AI modules remain independent

---

# Benefits of the Architecture

- Easy to maintain
- Easy to extend
- Reusable services
- Clean separation of concerns
- Suitable for real-time analytics
- Supports future personalization features
- Supports future marketing automation
- Production-ready modular structure

---

# Architecture Status

| Component | Status |
|-----------|--------|
| User Portal | ✅ |
| Admin Portal | ✅ |
| Flask Backend | ✅ |
| MongoDB Atlas | ✅ |
| Authentication | ✅ |
| Product APIs | ✅ |
| Session Tracking | ✅ |
| Event Tracking | ✅ |
| Lead Processing | ✅ |
| Machine Learning Pipeline | ✅ |
| Identity Resolution | ✅ |
| Recommendation Engine | 🚧 Planned |
| Customer Profile Service | 🚧 Planned |
| Marketing Automation | 🚧 Planned |
| Notification Service | 🚧 Planned |

---

End of System Architecture.