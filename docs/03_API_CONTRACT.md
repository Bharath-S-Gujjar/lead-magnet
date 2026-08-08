# Lead Magnet - API Contract

> This document defines every public API exposed by the Lead Magnet backend.
>
> All frontend applications, external services, and future modules must follow this contract.

---

# Base URL

Development

```
http://localhost:5000
```

Production

```
(To be updated after deployment)
```

---

# Standard API Response

Every endpoint should return the same response structure.

## Success

```json
{
  "success": true,
  "message": "Operation successful",
  "data": {}
}
```

---

## Error

```json
{
  "success": false,
  "message": "Description of error",
  "errors": []
}
```

---

# Authentication APIs

---

## POST /api/auth/signup

### Purpose

Create a new customer account.

### Request

```json
{
  "email": "user@example.com",
  "password": "password123",
  "anonymous_id": "anon_xxxxx"
}
```

`anonymous_id` is optional and allows previously anonymous behaviour to be linked to the new account.

### Response

```json
{
  "success": true,
  "message": "Account created successfully",
  "data": {
    "user_id": "...",
    "identity_resolution": {
      "sessions": 2,
      "events": 18,
      "leads": 1
    }
  }
}
```

Authentication Required

❌ No

---

## POST /api/auth/login

### Purpose

Authenticate an existing user.

### Request

```json
{
  "email": "user@example.com",
  "password": "password123",
  "anonymous_id": "anon_xxxxx"
}
```

### Response

```json
{
  "success": true,
  "message": "Login successful",
  "data": {
    "token": "<JWT>",
    "user_id": "...",
    "role": "user"
  }
}
```

Authentication Required

❌ No

---

## POST /api/auth/admin/login

### Purpose

Authenticate administrator.

### Request

```json
{
  "username": "admin",
  "password": "password"
}
```

### Response

```json
{
  "success": true,
  "message": "Admin login successful",
  "data": {
    "token": "<JWT>",
    "role": "admin"
  }
}
```

Authentication Required

❌ No

---

# Product APIs

---

## GET /api/products

### Purpose

Fetch all products.

Optional Query Parameters

```
category
```

Example

```
GET /api/products?category=Shoes
```

### Response

```json
{
  "success": true,
  "message": "Products fetched",
  "data": [
    {
      "_id": "...",
      "name": "...",
      "price": 1999
    }
  ]
}
```

Authentication Required

❌ No

---

## GET /api/products/{id}

### Purpose

Fetch a single product.

### Response

```json
{
  "success": true,
  "message": "Product fetched",
  "data": {
    "_id": "...",
    "name": "...",
    "price": 1999
  }
}
```

Authentication Required

❌ No

---

# Session APIs

---

## POST /api/session/start

### Purpose

Create a browsing session.

### Request

```json
{
  "visitor_id": "visitor_001",
  "anonymous_id": "anon_xxxxx"
}
```

Both fields are optional.

If neither is supplied, the backend generates an anonymous identity.

### Response

```json
{
  "success": true,
  "message": "Session started",
  "data": {
    "session_id": "...",
    "visitor_id": "...",
    "anonymous_id": "..."
  }
}
```

Authentication Required

❌ No

---

## POST /api/session/event

### Purpose

Record one behavioural event.

This endpoint is the V2 Rich Behavior Event Bus. It remains backward-compatible
with legacy tracking payloads while accepting richer behavioral context for
future intelligence modules.

### Request

Legacy payloads remain valid:

```json
{
  "session_id": "...",
  "event_type": "page_view",
  "page": "/products",
  "metadata": {
    "scroll_depth": 80
  }
}
```

Rich payloads may include `entity`, `context`, `event_category`,
`event_action`, and `schema_version`:

```json
{
  "session_id": "...",
  "event_type": "product_view",
  "event_category": "product",
  "event_action": "view",
  "page": "/products/64f...",
  "entity": {
    "type": "product",
    "id": "64f...",
    "name": "Running Shoe",
    "category": "Shoes",
    "brand": "Nike",
    "price": 2999
  },
  "metadata": {
    "source": "product_grid",
    "position": 4
  },
  "context": {
    "device_type": "mobile",
    "utm_source": "instagram"
  },
  "schema_version": 2
}
```

Stored event schema:

```json
{
  "_id": "...",
  "session_id": "...",
  "visitor_id": "visitor_001",
  "anonymous_id": "anon_xxxxx",
  "user_id": "...",
  "event_type": "product_view",
  "event_category": "product",
  "event_action": "view",
  "page": "/products/64f...",
  "timestamp": "Date",
  "entity": {},
  "metadata": {},
  "context": {},
  "schema_version": 2
}
```

### Supported Events

- page_view
- click
- scroll
- form_open
- form_submit
- product_view
- product_click
- search
- filter_apply
- sort_apply
- add_to_cart
- remove_from_cart
- wishlist_add
- wishlist_remove
- checkout_start
- purchase
- recommendation_view
- recommendation_click
- banner_view
- banner_click
- lead_capture

Unsupported `event_type` values are rejected with HTTP 400 and message
`Unsupported event_type`.

### Response

```json
{
  "success": true,
  "message": "Event logged",
  "data": {
    "event_id": "..."
  }
}
```

Authentication Required

❌ No

---

## POST /api/session/end

### Purpose

Close a browsing session.

Current behaviour

- marks session as ended
- calculates total duration
- processes lead
- stores prediction

### Request

```json
{
  "session_id": "..."
}
```

### Response

```json
{
  "success": true,
  "message": "Session ended and lead processed",
  "data": {
    "session_id": "...",
    "score": 0.82,
    "segment": "Hot",
    "next_action": "Call now + send email"
  }
}
```

Authentication Required

❌ No

---

# Admin APIs

All Admin APIs require

```
Authorization: Bearer <JWT>
```

---

## GET /api/admin/dashboard

### Purpose

Dashboard summary.

Returns

- Total Leads
- Hot Leads
- Warm Leads
- Cold Leads
- Average Score

Authentication Required

✅ Admin

---

## GET /api/admin/leads

### Purpose

Fetch all processed leads.

Sorted by

```
prediction_time DESC
```

Authentication Required

✅ Admin

---

## GET /api/admin/leads/{id}

### Purpose

Fetch one lead.

Authentication Required

✅ Admin

---

## PUT /api/admin/leads/{id}/status

### Purpose

Update lead status.

Allowed values

- New
- Contacted
- Qualified
- Converted
- Lost

### Request

```json
{
  "status": "Qualified"
}
```

Authentication Required

✅ Admin

---

# Legacy APIs

These APIs are retained for backward compatibility.

---

## POST /predict

Uses the original ML pipeline directly.

Status

⚠ Legacy

---

## POST /track

Uses the original flat lead-scoring flow.

Status

⚠ Legacy

Future

Will eventually delegate to the new modular pipeline.

---

# Future APIs (V2)

The following APIs are planned but not yet implemented.

---

## Cart

```
GET    /api/cart
POST   /api/cart
PUT    /api/cart/{id}
DELETE /api/cart/{id}
```

---

## Wishlist

```
GET    /api/wishlist
POST   /api/wishlist
DELETE /api/wishlist/{id}
```

---

## Orders

```
GET  /api/orders
POST /api/orders
GET  /api/orders/{id}
```

---

## Recommendations

```
GET /api/recommendations
```

Returns personalized products.

---

## Customer Profile

```
GET /api/profile
```

Returns aggregated behavioural profile.

---

## Marketing

```
POST /api/campaigns
GET  /api/campaigns
GET  /api/campaigns/logs
```

---

# Authentication Rules

Public APIs

- Signup
- Login
- Products
- Session APIs

Protected APIs

- Admin Dashboard
- Lead Management
- Campaign Management

JWT must be sent as

```
Authorization: Bearer <token>
```

---

# API Versioning Strategy

Current Version

```
v1
```

Future versions will evolve without breaking existing integrations.

Backward compatibility should be maintained whenever possible.

---

End of API Contract.
