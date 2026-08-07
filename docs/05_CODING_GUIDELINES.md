# Lead Magnet - Coding Guidelines

> This document defines the engineering standards and development rules for the Lead Magnet project.
>
> Every contributor must follow these guidelines before implementing any new feature.

---

# Philosophy

Lead Magnet follows a modular, scalable, and maintainable architecture.

The project should evolve through small, independent modules rather than large rewrites.

Every new feature should extend the existing architecture without breaking stable functionality.

---

# Core Principles

## 1. Never Rewrite Working Code

If a module is stable and tested, do not rewrite it.

Instead:

- Extend it
- Reuse it
- Wrap it

Only refactor when there is a measurable architectural benefit.

---

## 2. One Responsibility Per Module

Each module must perform only one responsibility.

Examples

Good

```
PredictionService

→ prediction only
```

```
FeatureAggregation

→ feature generation only
```

```
RecommendationService

→ recommendations only
```

Bad

```
PredictionService

↓

Prediction

↓

MongoDB writes

↓

Email sending

↓

Dashboard updates
```

---

## 3. Thin Flask Routes

Routes should only:

- receive requests
- validate input
- call services
- return responses

Business logic must never live inside app.py.

Good

```
Route

↓

Service

↓

Database
```

Bad

```
Route

↓

200 lines of business logic
```

---

## 4. Business Logic Lives in Services

Every complex operation belongs in a dedicated service.

Examples

```
identity_service.py

feature_aggregation.py

model_adapter.py

prediction_service.py

lead_processing_service.py

auth_middleware.py
```

Future services

```
cart_service.py

wishlist_service.py

order_service.py

recommendation_service.py

marketing_service.py

notification_service.py
```

---

## 5. Do Not Duplicate Logic

If logic is needed twice,

move it into a reusable service.

Bad

```
calculateScore()

in 4 files
```

Good

```
prediction_service.py

↓

Used everywhere
```

---

## 6. Keep Collections Independent

Every MongoDB collection has one responsibility.

Examples

```
users

authentication
```

```
events

immutable behaviour history
```

```
user_profiles

aggregated behaviour
```

Never overload one collection with unrelated data.

---

## 7. Events Are Immutable

Events should never be edited.

If behaviour changes,

append a new event.

Never modify history.

---

## 8. Preserve Backward Compatibility

Existing APIs should continue working whenever possible.

Deprecated endpoints should delegate to newer services instead of being removed immediately.

Examples

```
/predict

/track
```

remain functional while newer pipelines evolve.

---

## 9. Use Common Response Format

Every API should return

Success

```json
{
  "success": true,
  "message": "...",
  "data": {}
}
```

Failure

```json
{
  "success": false,
  "message": "...",
  "errors": []
}
```

Do not invent new response formats.

---

## 10. Environment Variables

Never hardcode:

- database URLs
- JWT secrets
- API keys
- passwords
- admin credentials

Always use

```
.env
```

---

## 11. Authentication Rules

Public routes

- Signup
- Login
- Products
- Session APIs

Protected routes

- Admin Dashboard
- Lead Management
- Campaigns

JWT authentication must use:

```
Authorization: Bearer <token>
```

---

## 12. Write Tests

Every new module should include tests.

Examples

```
test_identity_service.py

test_prediction_service.py

test_feature_aggregation.py
```

A feature is not considered complete until basic tests exist.

---

## 13. Documentation First

Before implementing a major module:

- update roadmap
- update database schema
- update API contract

Architecture changes should be documented before they are coded.

---

# Naming Conventions

## Files

Services

```
prediction_service.py

identity_service.py
```

Contexts

```
AuthContext.jsx

CartContext.jsx
```

Components

```
ProductCard.jsx

CustomerTable.jsx
```

---

## Collections

Use plural nouns.

Examples

```
users

products

events

orders
```

---

## Variables

Python

```
snake_case
```

JavaScript

```
camelCase
```

React Components

```
PascalCase
```

---

# Git Workflow

Every logical feature should be committed separately.

Good examples

```
feat: add identity resolution

feat: implement session tracking

fix: correct Mongo URI loading

docs: add API documentation

test: add prediction service tests
```

Avoid giant commits containing unrelated work.

---

# AI Collaboration Rules

When using AI tools (ChatGPT, Claude, Codex, etc.):

- Work on one module at a time.
- Never ask the AI to rewrite the whole project.
- Preserve stable modules.
- Review generated code before merging.
- Keep documentation synchronized with implementation.

The project documentation is the primary source of truth, not chat history.

---

# Performance Guidelines

Prefer:

- reusable services
- indexed MongoDB queries
- pagination for large datasets
- caching where appropriate

Avoid:

- duplicated database queries
- unnecessary model loading
- blocking operations inside request handlers

---

# Error Handling

Every API should:

- validate inputs
- handle invalid ObjectIds
- return meaningful HTTP status codes
- never expose internal stack traces to clients

---

# Future Architecture Rules

Future modules should plug into the existing architecture instead of replacing it.

Preferred flow

```
Frontend

↓

API Route

↓

Service

↓

MongoDB

↓

Response
```

Avoid direct communication between unrelated modules.

Use services as the integration layer.

---

# Definition of Done

A module is considered complete only if:

- Functionality works.
- Tests pass.
- Documentation is updated.
- API contract is updated (if applicable).
- Database schema is updated (if applicable).
- Existing functionality remains unaffected.

---

# Final Rule

The project must evolve incrementally.

Every new feature should improve the architecture without increasing unnecessary complexity.

Maintain readability, modularity, and consistency throughout the codebase.

---

End of Coding Guidelines.