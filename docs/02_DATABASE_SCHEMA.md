# Lead Magnet - Database Schema

> This document defines the complete MongoDB database design for the Lead Magnet platform.
>
> It includes both implemented collections (V1) and planned collections (V2).

---

# Database

Database Name:

```
leadmagnet
```

Database Engine:

```
MongoDB Atlas
```

---

# Collection Overview

## Version 1 Collections

- users
- products
- sessions
- events
- leads

---

## Version 2 Collections

- cart
- wishlist
- orders
- user_profiles
- campaigns
- campaign_logs

---

# Collection Relationships

```
users
   │
   ├──────────────┐
   │              │
   ▼              ▼
sessions      user_profiles
   │
   ▼
events
   │
   ▼
leads

users
 ├────────► cart
 ├────────► wishlist
 └────────► orders

products
 ├────────► cart
 ├────────► wishlist
 └────────► orders
```

---

# users

Purpose:

Stores registered customers.

Fields

| Field | Type | Description |
|---------|------|-------------|
| _id | ObjectId | MongoDB ID |
| email | String | User email |
| password | String | Bcrypt hash |
| role | String | user / admin |
| anonymous_id | String | Previous anonymous visitor id |
| created_at | Date | Account creation |
| updated_at | Date | Last update |

Indexes

- unique(email)

Status

✅ Implemented

---

# products

Purpose

Stores products displayed inside the e-commerce website.

Fields

| Field | Type |
|---------|------|
| _id | ObjectId |
| name | String |
| description | String |
| price | Number |
| category | String |
| gender | String |
| brand | String |
| images | Array |
| sizes | Array |
| colors | Array |
| stock | Number |
| created_at | Date |

Future Fields

- tags
- popularity_score
- recommendation_weight

Status

✅ Implemented
(Needs enrichment)

---

# sessions

Purpose

Represents one browsing session.

Fields

| Field | Type |
|---------|------|
| _id | ObjectId |
| visitor_id | String |
| anonymous_id | String |
| user_id | ObjectId |
| started_at | Date |
| last_active_at | Date |
| ended_at | Date |
| total_time_seconds | Number |
| page_views | Number |
| landing_page | String |
| referrer | String |
| utm_source | String |
| utm_medium | String |
| utm_campaign | String |
| status | String |

Status values

- active
- ended

Indexes

- visitor_id
- user_id

Status

✅ Implemented
(V2 fields partially planned)

---

# events

Purpose

Immutable history of user behaviour.

Fields

| Field | Type |
|---------|------|
| _id | ObjectId |
| session_id | ObjectId |
| visitor_id | String |
| user_id | ObjectId |
| event_type | String |
| page | String |
| timestamp | Date |
| metadata | Object |

Current Event Types

- page_view
- click
- scroll
- form_open

Future Event Types

- product_view
- add_to_cart
- remove_from_cart
- wishlist_add
- wishlist_remove
- search
- checkout_start
- purchase
- recommendation_click

Metadata Examples

```
{
  "product_id": "...",
  "category": "Shoes",
  "scroll_depth": 80,
  "cta_name": "Buy Now"
}
```

Indexes

- session_id
- timestamp

Status

✅ Implemented

---

# leads

Purpose

Stores ML prediction results.

Fields

| Field | Type |
|---------|------|
| _id | ObjectId |
| session_id | ObjectId |
| visitor_id | String |
| user_id | ObjectId |
| score | Number |
| segment | String |
| next_action | String |
| status | String |
| prediction_time | Date |
| feature_snapshot | Object |
| source_summary | Object |

Segments

- Hot
- Warm
- Cold

Lead Status

- New
- Contacted
- Qualified
- Converted
- Lost

Indexes

- prediction_time
- segment
- status

Status

✅ Implemented

---

# cart

Purpose

Persistent shopping cart.

Fields

| Field | Type |
|---------|------|
| _id | ObjectId |
| user_id | ObjectId |
| product_id | ObjectId |
| quantity | Number |
| added_at | Date |

Status

🚧 Planned (V2)

---

# wishlist

Purpose

Persistent wishlist.

Fields

| Field | Type |
|---------|------|
| _id | ObjectId |
| user_id | ObjectId |
| product_id | ObjectId |
| created_at | Date |

Status

🚧 Planned (V2)

---

# orders

Purpose

Stores completed purchases.

Fields

| Field | Type |
|---------|------|
| _id | ObjectId |
| user_id | ObjectId |
| products | Array |
| total_amount | Number |
| payment_status | String |
| order_status | String |
| ordered_at | Date |

Future

Will contribute to

- Recommendation Engine
- Lead Score
- Customer Intelligence

Status

🚧 Planned (V2)

---

# user_profiles

Purpose

Central Feature Store.

This collection becomes the heart of Version 2.

Every module reads from here.

Sources

- Sessions
- Events
- Cart
- Wishlist
- Orders

Fields

| Field | Type |
|---------|------|
| _id | ObjectId |
| user_id | ObjectId |
| visitor_id | String |
| engagement_score | Number |
| favorite_category | String |
| favorite_brand | String |
| average_order_value | Number |
| total_orders | Number |
| total_sessions | Number |
| total_page_views | Number |
| wishlist_count | Number |
| cart_count | Number |
| last_active | Date |
| lead_score | Number |

Status

🚧 Planned (Core V2)

---

# campaigns

Purpose

Marketing campaign definitions.

Fields

| Field | Type |
|---------|------|
| _id | ObjectId |
| campaign_name | String |
| trigger_type | String |
| channel | String |
| template | String |
| active | Boolean |

Status

🚧 Planned

---

# campaign_logs

Purpose

History of automated campaigns.

Fields

| Field | Type |
|---------|------|
| _id | ObjectId |
| campaign_id | ObjectId |
| user_id | ObjectId |
| channel | String |
| status | String |
| sent_at | Date |

Status

🚧 Planned

---

# Database Design Principles

The database follows these principles.

- Every collection has one responsibility.
- Events are immutable.
- Sessions summarize browsing.
- User Profiles aggregate behaviour.
- Leads store prediction results only.
- Products remain independent.
- Business logic never depends on duplicated data.
- Customer behaviour is preserved before and after login.

---

# Current Database Status

| Collection | Status |
|------------|--------|
| users | ✅ |
| products | ✅ |
| sessions | ✅ |
| events | ✅ |
| leads | ✅ |
| cart | 🚧 |
| wishlist | 🚧 |
| orders | 🚧 |
| user_profiles | 🚧 |
| campaigns | 🚧 |
| campaign_logs | 🚧 |

---

End of Database Schema.