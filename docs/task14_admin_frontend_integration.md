# Task 14 — Admin Frontend Intelligence Integration Documentation

## 1. Overview & Architecture
Task 14 connects `frontend/admin` to the Task 13 backend intelligence APIs (`/api/admin/intelligence/*` and `/api/analytics/overview`). All mock/static KPI values (`CLOTHING_KPIS`, sample arrays, fake lead scores) have been completely removed. The backend MongoDB database is now the single source of truth.

```
Admin React Application (`frontend/admin`)
           ↓
Centralized API Client (`frontend/admin/src/services/api.js`)
           ↓
JWT-Authenticated HTTP Requests (`Authorization: Bearer <token>`)
           ↓
Flask Admin Intelligence Routes (`backend/app.py`)
           ↓
Canonical MongoDB Database (`leadmagnet`)
```

---

## 2. Frontend API Service Layer (`api.js`)
Created [`frontend/admin/src/services/api.js`](file:///d:/lead-magnet/frontend/admin/src/services/api.js) to encapsulate all admin API communications:
- `getAdminIntelligenceOverview(token)`: Fetches real-time aggregate KPIs.
- `getAdminIntelligenceLeads({ token, qualification_status, segment, sort_by, sort_order, page, limit })`: Fetches customer-level directory rows with server pagination, sorting, and filtering.
- `getAdminCustomerIntelligence(customerId, token)`: Fetches customer deep-dive profile (profile, behavior, lead state, orders, marketing dispatches).
- `getAdminLeadDistribution(token)`: Fetches lead segment (`Hot`/`Warm`/`Cold`) and qualification status distribution.
- `getAdminRecentLeads({ token, page, limit })`: Fetches feed of newly qualified leads.
- `getAdminMarketingActivity({ token, page, limit })`: Fetches recent marketing automation events and channel dispatches (`sent`, `failed`, `skipped`).
- `getAdminNotifications({ token, read, page, limit })`: Fetches administrative notification logs.

---

## 3. Connected Dashboard Components

### 3.1 Live KPI Analytics Summary (`LeadAnalyticsSummary.jsx`)
- **Data Source**: `getAdminIntelligenceOverview(token)`
- **Displayed Metrics**:
  - Total Customers (Active Today, New Today)
  - Qualified Leads (Newly Qualified Today)
  - Hot Leads (Warm Leads, Cold Leads breakdown)
  - Communications Sent (Automation Events, Failed, Skipped breakdown)
- **Empty State Policy**: Displays `"Unavailable"` if a backend metric is null or missing. Zero fabricated percentages or fake numbers.
- **Manual Refresh**: Included a manual refresh trigger to re-fetch metrics on demand.

### 3.2 Lead Distribution (`GenderDistribution.jsx`)
- **Data Source**: `getAdminLeadDistribution(token)`
- **Visual Display**: Recharts Doughnut chart rendering real customer segment breakdown (`Hot`, `Warm`, `Cold`) alongside progress bars and qualified vs. total customer ratios.

### 3.3 Customer Intelligence Directory Table (`CustomerTable.jsx`)
- **Data Source**: `getAdminIntelligenceLeads(params)`
- **Structure**: Enforces **ONE ROW = ONE CUSTOMER**.
- **Interactive Controls**:
  - **Qualification Filter**: `Qualified Only` (default), `Not Qualified Only`, `All Statuses`.
  - **Segment Filter**: `All Segments` (default), `Hot Leads`, `Warm Leads`, `Cold Leads`.
  - **Sort By**: `Lead Score` (default), `Lead Probability`, `Last Scored`, `First Qualified`.
  - **Sort Order**: `DESC` (default) / `ASC`.
  - **Pagination**: Server-side Previous / Next buttons, Page X of Y indicator, total record count.
- **Columns**: Customer Name/Email, Lead Score & Probability, Segment Badge, Qualification Badge, Last Scored Date, Last Communication Dispatch metadata.

### 3.4 Customer Detail Drawer (`CustomerDetailDrawer.jsx`)
- **Data Source**: On row click, fetches `getAdminCustomerIntelligence(customerId, token)`.
- **Sections**:
  1. **Canonical Customer Profile**: Name, email, phone, role, created_at, last_active_at.
  2. **Lead State & Qualification Metrics**: Lead score, probability, segment, qualification status, model version, timestamps.
  3. **Behavioral Feature Aggregations**: Sessions count, total events, total time spent, page views, products viewed, cart value, wishlist items, checkout attempts, orders count.
  4. **Order History**: Order IDs, item count, total amounts, status badges.
  5. **Marketing Dispatches & Automation Events**: Dispatched channels (`email`, `sms`, `whatsapp`), status (`sent`, `failed`, `skipped`), timestamps.
- **Security**: Strips sensitive credentials (`password`, `password_hash`, `jwt`, `tokens`, `secrets`).

### 3.5 Marketing Automation Activity Feed (`MarketingActivityFeed.jsx`)
- **Data Source**: `getAdminMarketingActivity(params)`
- **Display**: Lists recent automated dispatches with channel icons, recipient details, status badges, and dispatch timestamps.

### 3.6 Internal Admin Notifications (`AdminNotificationsList.jsx`)
- **Data Source**: `getAdminNotifications(params)`
- **Display**: Renders real administrative event notifications (`lead_qualified`, `communication_sent`).

---

## 4. Authentication, Error & State Handling
- **JWT Authorization**: All requests pass `Authorization: Bearer <admin.token>`.
- **401 Unauthorized**: Clears stale session state and displays clear re-login messaging.
- **403 Forbidden**: Displays authorization warning alert ("You are not authorized to view admin intelligence").
- **404 / 400**: Customer detail drawer handles non-existent or invalid customer IDs gracefully.
- **Loading & Empty States**: Integrated skeleton text, loading indicators, and informative empty-state banners ("No qualified leads yet", "No marketing activity recorded yet").

---

## 5. Verification & Build Results
- **Frontend Production Build**: `npm run build` executed in `frontend/admin` with **0 errors**.
- **User Portal Build**: `npm run build` executed in `frontend/user` with **0 errors**.
- **Backend Regression Test Suite**: `pytest backend/tests -q` executed with **175 passed, 0 failed**.
- **No Mock Data Remaining**: Searched `frontend/admin/src` for static constants; confirmed all active UI data is live API-driven.
