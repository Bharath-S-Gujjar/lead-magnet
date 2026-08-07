# Lead Magnet - Master Context

> This document is the single source of truth for the Lead Magnet project.
>
> Every developer, teammate, or AI assistant must read this document before making architectural or implementation changes.

---

# Project Overview

Lead Magnet is an AI-powered Customer Intelligence Platform that combines an e-commerce website with machine learning to understand customer behavior, identify potential leads, personalize shopping experiences, and automate marketing actions.

Unlike a traditional online shopping website, Lead Magnet continuously observes customer interactions, builds behavioral profiles, predicts customer intent, and assists administrators in making data-driven business decisions.

The long-term vision is to transform anonymous website visitors into identified customers while continuously improving engagement through recommendations and automated marketing.

---

# Project Objectives

The project has the following primary objectives:

- Build a modern e-commerce platform.
- Track customer behavior in real time.
- Predict customer conversion probability using Machine Learning.
- Generate Hot, Warm, and Cold lead classifications.
- Personalize product recommendations.
- Build customer profiles from browsing behavior.
- Automate marketing campaigns.
- Provide an analytics dashboard for administrators.

---

# Technology Stack

## Backend

- Python
- Flask
- Flask-SocketIO
- PyMongo
- JWT Authentication
- APScheduler (Planned)

## Frontend

- React
- Vite
- React Router
- Context API

Two separate applications exist:

- User Portal
- Admin Portal

## Database

MongoDB Atlas

## Machine Learning

- Scikit-Learn
- XGBoost
- KMeans
- Joblib

---

# Project Architecture

The system consists of several independent modules.

```
User Portal
        │
        ▼
Flask Backend
        │
        ▼
MongoDB
        │
        ▼
Machine Learning
        │
        ▼
Admin Dashboard
```

Every module has a single responsibility.

Business logic should never be duplicated.

---

# Current Project Status

The project is divided into two versions.

---

# Version 1 (Completed)

Version 1 establishes the complete backend foundation.

Implemented:

- JWT Authentication
- Admin Authentication
- Product APIs
- Session Tracking
- Event Tracking
- Session Closing
- Feature Aggregation
- Model Adapter
- Prediction Service
- Lead Processing
- Lead Dashboard APIs
- JWT Middleware
- MongoDB Integration
- Machine Learning Pipeline

The backend is considered stable.

---

# Version 2 (In Progress)

Version 2 transforms Lead Magnet into a complete Customer Intelligence Platform.

Major additions:

- Identity Resolution
- Customer Profile Service
- Recommendation Engine
- Marketing Automation
- Customer Intelligence Dashboard
- Notification System

---

# Completed Modules

## Authentication

Implemented.

Features:

- Customer Signup
- Customer Login
- Admin Login
- JWT Authentication
- Role-Based Authorization

---

## Product Module

Implemented.

Features:

- Product Listing
- Product Details
- MongoDB Integration

---

## Session Tracking

Implemented.

Features:

- Session Start
- Event Tracking
- Session End
- Session Duration
- Page View Tracking

---

## Machine Learning Pipeline

Implemented.

Pipeline:

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

Lead Score

↓

Next Action
```

---

## Admin Dashboard

Implemented.

Features:

- Lead Listing
- Lead Details
- Dashboard KPIs
- Lead Status Updates

---

# V2 Architecture

Lead Magnet V2 introduces a modular customer intelligence platform.

Architecture:

```
Anonymous Visitor
        │
        ▼
Identity Resolution
        │
        ▼
Behavior Tracking
        │
        ▼
Feature Store
        │
 ┌──────┼─────────┐
 ▼      ▼         ▼
Lead  Recommendation Marketing
Score     Engine      Engine
        │
        ▼
Notification Service
        │
        ▼
Admin Dashboard
```

---

# Guiding Principles

The project follows these architectural principles.

## 1. Single Responsibility

Each module should perform one responsibility only.

Example:

Prediction Service should only predict.

Recommendation Engine should only recommend.

---

## 2. Service Layer

Business logic belongs inside services.

Flask routes should remain thin.

---

## 3. No Duplicate Logic

Every algorithm should exist only once.

If multiple modules require it, create a shared service.

---

## 4. Evolution, Not Rewrite

Version 2 extends Version 1.

Working modules must not be rewritten unless absolutely necessary.

---

## 5. AI Independence

Project knowledge must live inside documentation.

The project should never depend on AI conversation history.

---

# Identity Model

The project supports anonymous visitors.

Flow:

```
Anonymous Visitor

↓

anonymous_id

↓

Browsing

↓

Cart

↓

Wishlist

↓

Signup/Login

↓

user_id

↓

Customer Profile
```

Behavior before signup must never be lost.

---

# Long-Term Vision

Lead Magnet aims to become a complete AI-driven customer intelligence platform capable of:

- Understanding visitor behavior
- Predicting customer intent
- Recommending products
- Personalizing shopping
- Automating marketing
- Assisting administrators
- Improving conversion rates

---

# Development Rules

Every contributor must follow these rules.

- Never rewrite stable modules.
- Extend existing architecture.
- Keep services modular.
- Write reusable code.
- Prefer composition over duplication.
- Every new module must include tests.
- Keep documentation updated.
- Preserve API compatibility whenever possible.

---

# Current Development Phase

Current Phase:

Version 2

Current Module:

Identity Resolution

Next Planned Module:

Persistent Cart, Wishlist, and Orders

After that:

- Feature Store
- Recommendation Engine
- Lead Scoring Refactor
- Marketing Automation
- Customer Intelligence Dashboard

---

End of Master Context.