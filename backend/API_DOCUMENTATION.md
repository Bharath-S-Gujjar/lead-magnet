# Lead Magnet Backend API

Base URL: `http://127.0.0.1:5000` in local development.

Successful API routes generally use `{ "success": true, "message": "...", "data": ... }`. Legacy `/predict` and `/track` return their payloads directly. Error envelopes are not yet fully standardized across the application.

## Health and legacy scoring

| Endpoint | Method | Purpose | Request JSON | Success response | Error responses |
|---|---|---|---|---|---|
| `/` | GET | Health check. | None | `{ "status": "Lead Magnet API is running" }` | No explicit application error handling. |
| `/predict` | POST | Legacy, stateless prediction using the saved model. | Any fields matching the historic model input schema. | `{ "score": 0.82, "segment": "Hot", "reason": "Scored based on submitted lead behavior" }` | No validation or explicit error envelope; malformed/incompatible input can return a server error. |
| `/track` | POST | Legacy prediction, lead insertion, and SocketIO emission. | Historic model input fields; optional `visitor_id`. | `{ "visitor_id": "visitor-1", "score": 0.82, "segment": "Hot", "next_action": "Call now + send email" }` | No validation or explicit error envelope; malformed/incompatible input can return a server error. |

## Authentication

| Endpoint | Method | Purpose | Request JSON | Success response | Error responses |
|---|---|---|---|---|---|
| `/api/auth/signup` | POST | Create a customer account; optionally resolve prior anonymous activity. | `{ "email": "user@example.com", "password": "secret", "anonymous_id": "anon_..." }` | `{ "success": true, "message": "Account created successfully", "data": { "user_id": "<id>", "identity_resolution": { "sessions_merged": 1, "events_merged": 4, "leads_merged": 0 } } }` | `400` `{ "success": false, "message": "Email and password required", "errors": [] }`; `400` `{ "success": false, "message": "User already exists", "errors": [] }` |
| `/api/auth/login` | POST | Authenticate a customer, issue a one-day JWT, and optionally resolve prior anonymous activity. | `{ "email": "user@example.com", "password": "secret", "anonymous_id": "anon_..." }` | `{ "success": true, "message": "Login successful", "data": { "token": "<jwt>", "email": "user@example.com", "role": "user", "user_id": "<id>", "identity_resolution": { "sessions_merged": 1, "events_merged": 4, "leads_merged": 0 } } }` | `401` `{ "success": false, "message": "Invalid credentials", "errors": [] }` |
| `/api/auth/admin/login` | POST | Authenticate the configured admin and issue a one-day JWT. | `{ "username": "admin", "password": "secret" }` | `{ "success": true, "message": "Admin login successful", "data": { "token": "<jwt>", "role": "admin" } }` | `401` `{ "success": false, "message": "Invalid admin credentials", "errors": [] }` |

## Product catalog

| Endpoint | Method | Purpose | Request JSON | Success response | Error responses |
|---|---|---|---|---|---|
| `/api/products` | GET | List products; optionally filter by category. | None. Optional query string: `?category=men`. | `{ "success": true, "message": "Products fetched", "data": [{ "_id": "<id>", "...": "..." }] }` | No explicit application error handling. |
| `/api/products/<product_id>` | GET | Fetch one product. | None | `{ "success": true, "message": "Product fetched", "data": { "_id": "<id>", "...": "..." } }` | `404` `{ "success": false, "message": "Product not found", "errors": [] }`. An invalid ObjectId is not currently handled and can return a server error. |

## Visitor session tracking and lead processing

| Endpoint | Method | Purpose | Request JSON | Success response | Error responses |
|---|---|---|---|---|---|
| `/api/session/start` | POST | Create an active visitor session. If neither ID is supplied, generate an anonymous visitor ID. | `{ "anonymous_id": "anon_..." }` or `{ "visitor_id": "visitor-1" }` | `{ "success": true, "message": "Session started", "data": { "session_id": "<id>", "visitor_id": "anon_...", "anonymous_id": "anon_..." } }` | No explicit application error handling. |
| `/api/session/event` | POST | Store one visitor event and update the session summary. | `{ "session_id": "<id>", "event_type": "page_view", "page": "/pricing", "metadata": { "scroll_depth": 40 } }` | `{ "success": true, "message": "Event logged", "data": {} }` | `400` `{ "success": false, "message": "session_id and event_type required", "errors": [] }`; `404` `{ "success": false, "message": "Session not found", "errors": [] }`. An invalid ObjectId is not currently handled and can return a server error. |
| `/api/session/end` | POST | End a session, aggregate events, score it, and save a lead. | `{ "session_id": "<id>" }` | `{ "success": true, "message": "Session ended and lead processed", "data": { "session_id": "<id>", "total_time_seconds": 123.4, "score": 0.82, "segment": "Hot", "next_action": "Call now + send email" } }` | `400` `{ "success": false, "message": "session_id required", "errors": [] }`; `404` `{ "success": false, "message": "Session not found", "errors": [] }`. Prediction or database failures currently propagate as server errors. |

## Admin dashboard

All admin endpoints require `Authorization: Bearer <jwt>` with a valid, unexpired JWT whose `role` claim is `admin`. Missing or invalid tokens return `401`; authenticated non-admin users return `403`.

| Endpoint | Method | Purpose | Request JSON | Success response | Error responses |
|---|---|---|---|---|---|
| `/api/admin/leads` | GET | Return every lead ordered by newest `prediction_time` first. | None | `{ "success": true, "message": "Leads fetched", "data": [{ "_id": "<id>", "session_id": "<id>", "visitor_id": "visitor-1", "score": 0.82, "segment": "Hot", "next_action": "Call now + send email", "prediction_time": "2026-08-07T10:00:00+00:00", "...": "..." }] }` | `401` missing/invalid token; `403` non-admin token. |
| `/api/admin/leads/<lead_id>` | GET | Return one lead. | None | `{ "success": true, "message": "Lead fetched", "data": { "_id": "<id>", "session_id": "<id>", "visitor_id": "visitor-1", "score": 0.82, "segment": "Hot", "next_action": "Call now + send email", "prediction_time": "..." } }` | `401` missing/invalid token; `403` non-admin token; `404` `{ "success": false, "message": "Lead not found", "errors": [] }` for absent or invalid IDs. |
| `/api/admin/leads/<lead_id>/status` | PUT | Update a lead workflow status. Supported values: `New`, `Contacted`, `Qualified`, `Converted`, `Lost`. | `{ "status": "Qualified" }` | `{ "success": true, "message": "Lead status updated", "data": { "lead_id": "<id>", "status": "Qualified" } }` | `401` missing/invalid token; `403` non-admin token; `400` `{ "success": false, "message": "Invalid lead status", "errors": [] }`; `404` `{ "success": false, "message": "Lead not found", "errors": [] }` |
| `/api/admin/dashboard` | GET | Return lead counts by segment and average score. | None | `{ "success": true, "message": "Dashboard summary fetched", "data": { "total_leads": 10, "hot_leads": 3, "warm_leads": 4, "cold_leads": 3, "average_score": 0.54 } }` | `401` missing/invalid token; `403` non-admin token. |

## Environment variables

| Name | Purpose |
|---|---|
| `MONGO_URI` | MongoDB Atlas connection string. |
| `JWT_SECRET` | HS256 JWT signing secret. |
| `ADMIN_USERNAME` | Configured administrator username. |
| `ADMIN_PASSWORD` | Configured administrator password. |
