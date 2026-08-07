# Lead Magnet - Project Roadmap

> This document tracks the evolution of Lead Magnet from the initial proof-of-concept to the final AI-powered Customer Intelligence Platform.
>
> It serves as the official development roadmap for the project.

---

# Project Timeline

```
Version 1
↓

Stable AI Lead Scoring Backend

↓

Version 2

↓

Customer Intelligence Platform

↓

Future Production Version
```

---

# Version 1

## Goal

Build a complete AI-powered Lead Scoring backend capable of:

- Tracking user behaviour
- Predicting lead quality
- Providing an admin dashboard
- Securing APIs
- Integrating with MongoDB

---

# Version 1 Completed Modules

---

## Module 1

### Authentication

Status

✅ Completed

Features

- User Signup
- User Login
- Admin Login
- JWT Authentication
- Password Hashing
- Role-Based Authorization

---

## Module 2

### Product Module

Status

✅ Completed

Features

- Product Listing
- Product Details
- MongoDB Integration

---

## Module 3

### Session Tracking

Status

✅ Completed

Features

- Session Start
- Session Event
- Session End
- Session Duration
- Visitor Tracking

---

## Module 4

### AI Prediction Pipeline

Status

✅ Completed

Components

- Feature Aggregation
- Model Adapter
- Prediction Service
- Action Recommendation

Pipeline

```
Events
↓

Feature Aggregation
↓

Model Adapter
↓

Scaler
↓

XGBoost
↓

KMeans
↓

Prediction
```

---

## Module 5

### Lead Processing

Status

✅ Completed

Features

- Session Processing
- Lead Creation
- MongoDB Persistence
- Prediction Storage

---

## Module 6

### Admin Dashboard

Status

✅ Completed

Features

- Dashboard Summary
- Lead Listing
- Lead Details
- Lead Status Update

---

## Module 7

### Security

Status

✅ Completed

Features

- JWT Middleware
- Admin Route Protection
- Authorization Decorators

---

# Version 1 Summary

Status

✅ Stable

Backend

Completed

Frontend

Not Integrated

Deployment

Pending

---

# Why Version 2 Exists

During frontend analysis, it became clear that the project had grown beyond simple lead scoring.

The frontend already included:

- Cart
- Wishlist
- Orders
- Profile
- Customer Analytics

These features should contribute to customer intelligence rather than existing independently.

The project therefore evolved into an AI-powered Customer Intelligence Platform.

---

# Version 2 Goals

Version 2 extends Version 1 without rewriting stable modules.

Primary goals

- Preserve Version 1 backend
- Introduce customer profiling
- Support anonymous visitors
- Personalize product recommendations
- Automate marketing
- Expand customer analytics

---

# Version 2 Roadmap

---

## Module V2.1

### Identity Resolution

Status

✅ Completed

Purpose

Support anonymous visitors before login.

Features

- anonymous_id generation
- Identity merge after signup/login
- Session linking
- Event linking
- Lead linking

---

## Module V2.2

### Persistent Shopping

Status

🚧 Planned

Collections

- cart
- wishlist
- orders

Purpose

Persist shopping behaviour inside MongoDB.

These collections become behavioural inputs for AI modules.

---

## Module V2.3

### Behavior Tracking Upgrade

Status

🚧 Planned

Purpose

Expand event vocabulary.

New event types

- product_view
- add_to_cart
- remove_from_cart
- wishlist_add
- wishlist_remove
- search
- checkout_start
- purchase
- recommendation_click

---

## Module V2.4

### Feature Store

Status

🚧 Planned

Purpose

Create a unified behavioural profile.

Inputs

- Sessions
- Events
- Cart
- Wishlist
- Orders

Outputs

- Customer Profile
- Behaviour Metrics
- Category Affinity
- Brand Affinity
- Engagement Score

---

## Module V2.5

### Recommendation Engine

Status

🚧 Planned

Purpose

Generate personalized product recommendations.

Recommendation Strategy

- Content-based recommendation
- Category affinity
- Brand affinity
- Purchase history
- Wishlist
- Popularity fallback

---

## Module V2.6

### Lead Scoring Refactor

Status

🚧 Planned

Purpose

Reuse the Feature Store instead of private aggregation.

The XGBoost model remains unchanged.

Only the input source changes.

---

## Module V2.7

### Marketing Automation

Status

🚧 Planned

Purpose

Automatically engage customers.

Example Triggers

- Abandoned Cart
- Wishlist Reminder
- Returning Customer
- High Lead Score
- Dormant Customer

Delivery Channels

- Email
- SMS
- WhatsApp
- Push Notification (Future)

---

## Module V2.8

### Customer Intelligence Dashboard

Status

🚧 Planned

Purpose

Expand administrator analytics.

Future KPIs

- Customer Lifetime Value
- Repeat Customers
- Wishlist Trends
- Cart Abandonment
- Product Affinity
- Campaign Performance
- Recommendation Performance

---

# Frontend Integration Roadmap

---

## Phase 1

Status

🚧 Planned

Integrations

- User Signup
- User Login
- Admin Login

---

## Phase 2

Status

🚧 Planned

Integrations

- Products
- Product Details

---

## Phase 3

Status

🚧 Planned

Integrations

- Session Tracking
- Event Tracking

---

## Phase 4

Status

🚧 Planned

Integrations

- Dashboard
- Leads
- Lead Details

---

## Phase 5

Status

🚧 Planned

Integrations

- Cart
- Wishlist
- Orders

---

## Phase 6

Status

🚧 Planned

Integrations

- Recommendation Engine
- Marketing Automation

---

# Deployment Roadmap

---

## Backend

- Flask
- Gunicorn
- Render

---

## Frontend

- React
- Vercel

---

## Database

- MongoDB Atlas

---

## Environment Variables

- MONGO_URI
- JWT_SECRET
- ADMIN_USERNAME
- ADMIN_PASSWORD

---

# Long-Term Vision

Lead Magnet aims to become a complete AI-powered Customer Intelligence Platform capable of:

- Anonymous Visitor Tracking
- Customer Profiling
- Behaviour Analysis
- AI Lead Prediction
- Product Recommendation
- Marketing Automation
- Customer Analytics
- Personalized Shopping Experience

---

# Current Progress

| Module | Status |
|---------|--------|
| Authentication | ✅ |
| Products | ✅ |
| Sessions | ✅ |
| Events | ✅ |
| AI Pipeline | ✅ |
| Lead Processing | ✅ |
| Dashboard | ✅ |
| Security | ✅ |
| Identity Resolution | ✅ |
| Cart Persistence | 🚧 |
| Wishlist Persistence | 🚧 |
| Orders | 🚧 |
| Feature Store | 🚧 |
| Recommendation Engine | 🚧 |
| Marketing Automation | 🚧 |
| Customer Intelligence | 🚧 |
| Frontend Integration | 🚧 |
| Deployment | 🚧 |

---

# Development Philosophy

Lead Magnet follows an incremental development strategy.

- Never rewrite stable modules.
- Extend Version 1.
- Keep every module independent.
- Maintain backward compatibility.
- Prefer modular services over large controllers.
- Document every architectural decision.

---

End of Project Roadmap.