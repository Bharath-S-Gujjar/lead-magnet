# Lead Magnet — API Reference Specification

Base URL: `http://localhost:5000` (Local) / Configured deployment host

All requests and responses use `application/json` unless otherwise specified. Authenticated endpoints require an `Authorization: Bearer <token>` header.

---

## 1. Authentication Endpoints

### 1.1 Customer Registration
- **`POST /api/auth/register`**
- **Payload**:
  ```json
  {
    "email": "customer@example.com",
    "password": "SecurePassword123",
    "full_name": "Jane Doe",
    "visitor_id": "optional-uuid"
  }
  ```
- **Response `201`**:
  ```json
  {
    "success": true,
    "token": "<JWT_TOKEN>",
    "user": { "id": "...", "email": "customer@example.com", "role": "user" }
  }
  ```

### 1.2 Customer Login
- **`POST /api/auth/login`**
- **Payload**: `{ "email": "customer@example.com", "password": "SecurePassword123", "visitor_id": "..." }`
- **Response `200`**: `{ "success": true, "token": "<JWT_TOKEN>", "user": { ... } }`

### 1.3 Administrator Login
- **`POST /api/admin/login`**
- **Payload**: `{ "email": "admin@example.com", "password": "AdminPassword123" }`
- **Response `200`**: `{ "success": true, "token": "<JWT_TOKEN>", "admin": { ... } }`

---

## 2. Product Catalog Endpoints

### 2.1 List / Search Products
- **`GET /api/products`**
- **Query Parameters**:
  - `category` *(optional)*: Filter by clothing category (e.g., `T-Shirts`, `Jeans`)
  - `gender` *(optional)*: Filter by `Men`, `Women`, or `Kids`
  - `brand` *(optional)*: Filter by manufacturer brand
  - `search` *(optional)*: Keyword search query
  - `page`, `limit` *(optional)*: Pagination controls
- **Response `200`**:
  ```json
  {
    "success": true,
    "data": [
      {
        "_id": "6a778eab...",
        "product_id": "prod_c877ae3c24fe331f",
        "name": "Boys Straight Fit Jeans",
        "brand": "HERE&NOW",
        "gender": "Kids",
        "category": "Jeans",
        "price": 839.0,
        "price_inr": 839.0,
        "discount": 65.0,
        "discount_percent": 65.0,
        "rating": 4.1,
        "verified_buyers": 240
      }
    ]
  }
  ```

### 2.2 Get Product By ID
- **`GET /api/products/<product_id>`**
- **Response `200`**: Single product object.

---

## 3. Behavioral Telemetry & Session Endpoints

### 3.1 Start Session
- **`POST /api/session/start`**
- **Payload**:
  ```json
  {
    "visitor_id": "anon-uuid-1234",
    "landing_page": "/",
    "user_agent": "Mozilla/5.0...",
    "user_id": null
  }
  ```
- **Response `201`**: `{ "success": true, "session_id": "..." }`

### 3.2 Track Behavioral Event
- **`POST /api/events/track`**
- **Payload**:
  ```json
  {
    "session_id": "...",
    "visitor_id": "...",
    "event_type": "view_product",
    "event_category": "e-commerce",
    "page": "/product/prod_c877ae3c24fe331f",
    "metadata": { "product_id": "prod_c877ae3c24fe331f", "price": 839.0 }
  }
  ```

### 3.3 Session Heartbeat
- **`POST /api/session/heartbeat`**
- **Payload**: `{ "session_id": "...", "duration_increment_seconds": 15 }`

---

## 4. Shopping Cart & Wishlist

### 4.1 Get Cart
- **`GET /api/cart`** (Header or `visitor_id` query param)
- **Response `200`**: List of cart items with populated product metadata.

### 4.2 Add to Cart
- **`POST /api/cart/add`**
- **Payload**: `{ "product_id": "...", "quantity": 1 }`

### 4.3 Wishlist Operations
- **`GET /api/wishlist`**
- **`POST /api/wishlist/toggle`**: `{ "product_id": "..." }`

---

## 5. Orders & Checkout

### 5.1 Place Order
- **`POST /api/orders`** *(Authenticated)*
- **Payload**:
  ```json
  {
    "items": [{ "product_id": "...", "quantity": 2, "price": 839.0 }],
    "shipping_address": { ... },
    "payment_method": "card"
  }
  ```
- **Response `201`**: Order confirmation object with order ID.

---

## 6. Admin Intelligence Endpoints *(Admin Auth Required)*

- **`GET /api/admin/intelligence/leads`**: Search, sort, and paginate through customer profiles with ML lead scores, qualification status, and RFM scores.
- **`GET /api/admin/intelligence/customer/<customer_id>`**: Detailed analytical profile of a customer, including behavioral feature vector, score history, and recommended next actions.
- **`GET /api/admin/intelligence/funnel`**: Multi-stage funnel conversion metrics (Visitors -> Product Views -> Cart Adds -> Checkout Starts -> Converted).
- **`GET /api/admin/intelligence/rfm`**: RFM matrix breakdown across segments (Champions, Loyal Customers, At Risk, Lost).
- **`GET /api/admin/intelligence/revenue-attribution`**: Revenue breakdown attributed to marketing campaigns and direct organic interactions.
- **`POST /api/admin/intelligence/what-if`**: Simulator computing predicted lead score changes given synthetic shifts in customer behavioral inputs.
- **`GET /api/admin/intelligence/notifications`**: Live feed of marketing automation events and high-priority lead triggers.
