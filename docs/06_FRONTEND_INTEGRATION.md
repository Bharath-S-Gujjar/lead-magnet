# Lead Magnet - Frontend Integration Guide

> This document explains how the User Portal and Admin Portal communicate with the Flask backend.

It serves as the integration guide for frontend developers.

---

# Project Structure

The frontend consists of two independent React applications.

```
frontend/

├── user/
│
└── admin/
```

Both applications communicate with the same Flask backend.

---

# Architecture

```
                 React User Portal
                       │
                       │ HTTP
                       ▼
                Flask Backend
                       ▲
                       │ HTTP
                 React Admin Portal
```

MongoDB and Machine Learning remain completely hidden from the frontend.

The frontend must never communicate directly with MongoDB.

---

# Backend Base URL

Development

```
http://localhost:5000
```

Future Production

```
(To be configured after deployment)
```

Store this URL inside an API configuration file rather than hardcoding it throughout components.

---

# User Portal Integration

The user portal is responsible for customer interactions.

Major responsibilities

- Authentication
- Browsing products
- Product details
- Cart
- Wishlist
- Orders
- Session tracking
- Behaviour tracking

---

# User Authentication Flow

## Signup

```
React

↓

POST /api/auth/signup

↓

JWT not required

↓

Backend creates account

↓

Return success
```

Request

```json
{
  "email": "user@example.com",
  "password": "password123",
  "anonymous_id": "anon_xxxxx"
}
```

---

## Login

```
React

↓

POST /api/auth/login

↓

Receive JWT

↓

Store JWT

↓

Authenticated User
```

Store

- JWT
- user_id
- role

Do not store passwords.

---

# Anonymous Visitor Flow

When the website loads

```
Homepage

↓

POST /api/session/start

↓

anonymous_id

↓

session_id
```

Store

- session_id
- anonymous_id

These values are reused during the browsing session.

If the visitor later signs up,

send the anonymous_id.

The backend automatically links previous behaviour.

---

# Behaviour Tracking

User interactions should generate events.

Examples

```
Home Viewed

↓

page_view
```

```
Product Viewed

↓

product_view
```

```
Product Added

↓

add_to_cart
```

```
Wishlist

↓

wishlist_add
```

```
Checkout Started

↓

checkout_start
```

```
Purchase

↓

purchase
```

Each event should call

```
POST /api/session/event
```

---

# Session End

When the visitor leaves the website

```
Browser Close

↓

POST /api/session/end
```

The backend will

- end the session
- process behaviour
- generate lead score
- save lead

The frontend does not perform prediction.

---

# Product Integration

Homepage

↓

GET /api/products

Product Details

↓

GET /api/products/{id}

The frontend should treat MongoDB "_id" as the product identifier.

---

# Cart

Current Status

🚧 Planned

Future APIs

```
GET /api/cart

POST /api/cart

PUT /api/cart/{id}

DELETE /api/cart/{id}
```

---

# Wishlist

Current Status

🚧 Planned

Future APIs

```
GET /api/wishlist

POST /api/wishlist

DELETE /api/wishlist/{id}
```

---

# Orders

Current Status

🚧 Planned

Future APIs

```
GET /api/orders

POST /api/orders
```

---

# Recommendation Engine

Future endpoint

```
GET /api/recommendations
```

The frontend simply displays recommended products.

All recommendation logic remains inside the backend.

---

# Admin Portal Integration

The admin application is independent from the user application.

---

# Admin Authentication

```
Admin Login

↓

POST /api/auth/admin/login

↓

Receive JWT

↓

Store JWT

↓

Dashboard Access
```

JWT must be included with every admin request.

```
Authorization: Bearer <token>
```

---

# Dashboard

```
GET /api/admin/dashboard
```

Returns

- Total Leads
- Hot Leads
- Warm Leads
- Cold Leads
- Average Score

---

# Lead Table

```
GET /api/admin/leads
```

Display

- Lead ID
- Visitor ID
- Score
- Segment
- Status
- Prediction Time

---

# Lead Details

```
GET /api/admin/leads/{id}
```

Displays

- Feature Snapshot
- Source Summary
- Prediction
- Behaviour Summary

---

# Lead Status

```
PUT /api/admin/leads/{id}/status
```

Allowed

- New
- Contacted
- Qualified
- Converted
- Lost

---

# State Management

Current frontend uses React Context.

Recommended responsibilities

```
AuthContext

↓

Authentication
```

```
UserTrackingContext

↓

Session

↓

Events
```

```
CartContext

↓

Cart State
```

```
WishlistContext

↓

Wishlist
```

Business logic should remain inside the backend.

---

# API Layer

Every frontend application should use a centralized API layer.

Example

```
src/

services/

api.js

authService.js

productService.js

trackingService.js

adminService.js
```

Components should never call fetch() directly.

---

# Error Handling

Handle

- Loading state
- Empty state
- Network errors
- Unauthorized (401)
- Forbidden (403)
- Not Found (404)

Never expose backend errors directly to users.

---

# Future Integrations

Version 2 introduces additional frontend features.

These include

- Personalized Recommendations
- Marketing Notifications
- Customer Profile
- Purchase History
- Behaviour Insights
- Recommendation Explanations

The frontend should remain presentation-focused.

All AI, recommendation, lead scoring, and customer intelligence logic belongs inside the backend.

---

# Integration Principles

- Backend owns business logic.
- Frontend owns presentation.
- JWT secures admin routes.
- Anonymous behaviour is preserved before login.
- APIs must remain backward compatible.
- New frontend features should consume existing backend services whenever possible.

---

End of Frontend Integration Guide.