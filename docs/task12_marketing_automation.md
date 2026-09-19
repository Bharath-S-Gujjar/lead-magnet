# Task 12 — Marketing Automation Engine Foundation

## 1. Overview & Business Goal
The business goal of Lead Magnet is to automatically identify qualified, high-intent e-commerce customers and engage them through marketing channels (Email, SMS, WhatsApp) rather than manually marketing to every user.

Task 12 establishes the event-driven, idempotent marketing automation layer that connects **Customer Lead State** (Task 11) to **Communication Providers**.

```
Customer Behavior (Events / Cart / Orders)
         ↓
Customer Feature Store (`customer_features`)
         ↓
E-Commerce ML Inference (`predict_customer_features`)
         ↓
Customer Lead State (`customer_lead_state`)
         ↓
[Transition: not_qualified → qualified]
         ↓
Marketing Automation Event (`marketing_automation_events`)
         ↓
Channel Eligibility & Policy Evaluation
         ↓
Communication Dispatch (`marketing_communications`)
         ↓
Communication Provider Abstraction (`DryRunCommunicationProvider`)
```

---

## 2. Event-Driven Trigger Policy
Marketing automation is **strictly event-driven** based on lead-state transitions:
- **Primary Trigger**: `not_qualified` → `qualified` (where `is_newly_qualified == True`).
- **Suppressed Triggers**:
  - `qualified` → `qualified` (Repeated scoring of an already-qualified lead does **NOT** trigger duplicate marketing).
  - `not_qualified` → `not_qualified` (Unqualified users produce no automation events).
  - On-demand inference requests (Inference alone does not initiate communication dispatches).

---

## 3. Data Models

### 3.1 Marketing Automation Event (`marketing_automation_events`)
Stores state-transition events generated when a customer becomes newly qualified.
```json
{
  "_id": "ObjectId(...)",
  "customer_id": "ObjectId(...)",
  "event_type": "lead_qualified",
  "lead_state_transition": "not_qualified_to_qualified",
  "lead_score": 85,
  "lead_probability": 0.852,
  "lead_segment": "Hot",
  "model_version": "v2.0_ecommerce_xgb",
  "status": "completed",
  "idempotency_key": "<customer_id>_lead_qualified_<first_qualified_at>",
  "created_at": "2026-09-19T14:00:00.000Z",
  "processed_at": "2026-09-19T14:00:00.100Z"
}
```

### 3.2 Marketing Communication Record (`marketing_communications`)
Records every attempted communication dispatch for auditing and idempotency.
```json
{
  "_id": "ObjectId(...)",
  "customer_id": "ObjectId(...)",
  "automation_event_id": "ObjectId(...)",
  "channel": "email",
  "campaign_type": "lead_qualification",
  "recipient": "customer@example.com",
  "status": "sent",
  "provider": "dry_run",
  "provider_message_id": "dry-run-email-a1b2c3d4e5f6",
  "attempt_count": 1,
  "last_error": null,
  "created_at": "2026-09-19T14:00:00.050Z",
  "sent_at": "2026-09-19T14:00:00.080Z",
  "updated_at": "2026-09-19T14:00:00.080Z"
}
```

### 3.3 Admin Notification Record (`admin_notifications`)
Internal administrative log created whenever a customer becomes newly qualified or an automated message is dispatched.
```json
{
  "_id": "ObjectId(...)",
  "type": "lead_qualified",
  "customer_id": "ObjectId(...)",
  "message": "Customer customer@example.com was newly qualified as a Hot lead (Score: 85).",
  "read": false,
  "created_at": "2026-09-19T14:00:00.060Z"
}
```

---

## 4. Communication Provider Abstraction & Dry-Run Mode

### 4.1 Interface Boundary
The system defines an abstract base provider (`CommunicationProvider` in `backend/communication_provider.py`) with three standard channels:
- `send_email(recipient, subject, body, metadata=None)`
- `send_sms(recipient, body, metadata=None)`
- `send_whatsapp(recipient, body, metadata=None)`

### 4.2 Local Dry-Run Provider (`DryRunCommunicationProvider`)
For local development, automated testing, and CI/CD, the default provider is `DryRunCommunicationProvider`.
- **Zero External Network Calls**: Does not hit any external APIs.
- **Deterministic Response**: Returns structured success metadata with unique dry-run message identifiers (e.g., `dry-run-email-...`, `dry-run-sms-...`, `dry-run-whatsapp-...`).

### 4.3 Production Provider Integration Guide
To connect real providers in future phases:
1. Implement `ProductionCommunicationProvider(CommunicationProvider)` wrapping external APIs (SendGrid / Brevo for Email; Twilio for SMS / WhatsApp).
2. Load credentials exclusively from environment variables (`SENDGRID_API_KEY`, `TWILIO_AUTH_TOKEN`, etc.).
3. Configure `get_communication_provider(name)` factory in `communication_provider.py`.

---

## 5. Channel Eligibility & Default Automation Policy

### 5.1 Eligibility Rules
Determined dynamically from the canonical user profile (`user_profiles` collection):
- **Email**: Eligible if a valid email address containing `@` exists in the customer profile.
- **SMS**: Eligible if a non-empty phone number exists **AND** SMS is explicitly enabled by policy.
- **WhatsApp**: Eligible if a non-empty phone number exists **AND** WhatsApp is explicitly enabled by policy.

### 5.2 Default Channel Policy
```python
DEFAULT_CHANNEL_POLICY = {
    "email": {"enabled": True},
    "sms": {"enabled": False},
    "whatsapp": {"enabled": False}
}
```
*Note: SMS and WhatsApp are disabled by default to prevent unintended dispatches without explicit provider setup.*

---

## 6. Idempotency & Unique Indexes
Idempotency is enforced at both the database level (via MongoDB unique indexes) and application service logic:
1. **`marketing_automation_events` Unique Index**:
   - `idempotency_key`: Unique index on `f"{customer_id}_lead_qualified_{first_qualified_at}"`.
2. **`marketing_communications` Unique Index**:
   - `automation_event_channel_unique`: Compound unique index on `[("automation_event_id", 1), ("channel", 1)]`.
3. **Application Level**:
   - `process_marketing_automation_event` checks if a communication record is already in status `"sent"`. If `"sent"`, re-execution is a safe no-op.

---

## 7. Retry Behavior & Status Lifecycle
- **Status Lifecycles**:
  - **Automation Event**: `pending` → `processing` → `completed` (or `failed`).
  - **Communication Record**: `pending` → `sent` (or `failed`, `skipped`).
- **Failure Tracking**: If a provider call fails, `status` becomes `"failed"`, `last_error` stores the error message, and `attempt_count` increments.
- **Retry Policy**: Retries increment `attempt_count` without creating duplicate communication records. No infinite background loops are executed in Task 12.

---

## 8. Security & Admin API
Diagnostic endpoints are strictly restricted to administrators via `@admin_required`:
- `GET /api/admin/marketing/automation-events`
- `GET /api/admin/marketing/communications`
- `GET /api/admin/notifications`

*Security Rules:*
- Non-admin JWT tokens receive `403 Forbidden`.
- Normal user profiles cannot inspect other users' automation history.
- Credentials and internal secrets are never exposed in API outputs.

---

## 9. Provisional ML Threshold Notice
> [!IMPORTANT]
> The current lead qualification probability threshold (`0.70` / Lead Score `70`) is **provisional**. The underlying XGBoost lead-scoring model was trained on synthetic e-commerce behavioral data (`data/ecommerce_lead_scoring_dataset.csv`). As real customer traffic accumulates, qualification thresholds and model weights should be re-calibrated.
