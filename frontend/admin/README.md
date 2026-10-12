# Lead Magnet — Admin Intelligence Portal

The Admin Portal is the operational intelligence dashboard for Lead Magnet. It gives business operators a real-time view of customer conversion activity, lead qualification, marketing automation, and revenue analytics. It connects to the same Flask backend as the User Portal and receives live event updates via WebSocket.

---

## Tech Stack

| Tool | Version |
|:--|:--|
| React | 18.3 |
| Vite | 6.x |
| React Router DOM | 7.x |
| Recharts | 2.x |
| Socket.IO Client | 4.8 |
| Lucide React | 0.469 |

**Dev server port:** `3000`

---

## Prerequisites

- **Node.js** 18 or later
- **npm** 9 or later

```bash
node --version   # 18+
npm --version    # 9+
```

---

## Installation

All commands run from the `frontend/admin/` directory:

```bash
cd frontend/admin
npm install
```

---

## Available Scripts

| Script | Command | Description |
|:--|:--|:--|
| Development | `npm run dev` | Starts Vite dev server at `http://localhost:3000` with HMR |
| Production build | `npm run build` | Builds to `dist/` for deployment |
| Preview build | `npm run preview` | Serves the `dist/` folder locally for build verification |

---

## API Configuration

### Development (local)

No configuration is needed. The admin portal defaults to connecting to `http://127.0.0.1:5000` when `VITE_API_BASE_URL` is not set.

Start the backend in isolated mode first:
```powershell
venv\Scripts\python backend/local_test_launcher.py --serve --port 5000
```

### Production Build

Set `VITE_API_BASE_URL` to the deployed backend URL before building:

```
VITE_API_BASE_URL=https://your-deployed-backend.onrender.com
```

Set this via:
- CI/CD environment variable (recommended)
- Deployment platform dashboard (Vercel, Render, etc.)

> ⚠️ The build will fail at startup if `VITE_API_BASE_URL` is missing or contains a localhost/placeholder value in production. This is intentional.

The committed `frontend/admin/.env.production` file has this variable commented out intentionally — configure it in your deployment environment, not in the file.

---

## Authentication

The admin portal uses **JWT-based authentication** against the backend `POST /api/admin/login` endpoint.

**Local demo credentials** are configured via the backend `.env` variables `ADMIN_USERNAME` and `ADMIN_PASSWORD`. The defaults for local demo use are `admin` / `admin12345`, but these should always be confirmed against your local `backend/.env`.

> ⚠️ Do not publish or hardcode default admin credentials in documentation or source code. The old README for this portal contained hardcoded credentials (`admin@leadmagnet.com` / `admin123`) — those are invalid and have been removed.

The backend enforces:
- JWT tokens signed with `JWT_SECRET` from the environment.
- `@admin_required` middleware on all `/api/admin/*` routes.
- Token expiry — expired tokens return `401 Unauthorized`.

---

## Running Against the Isolated Local Backend

1. Confirm MongoDB Community is running on `127.0.0.1:27017`.
2. Start the backend:
   ```powershell
   venv\Scripts\python backend/local_test_launcher.py --serve --port 5000
   ```
3. Start the admin portal:
   ```bash
   cd frontend/admin
   npm run dev
   ```
4. Open `http://localhost:3000` and log in with admin credentials.

---

## Application Structure

```
frontend/admin/
├── src/
│   ├── App.jsx                          # Root router, protected routes
│   ├── main.jsx                         # Application entry point
│   ├── components/
│   │   ├── analytics/
│   │   │   ├── FunnelAnalytics.jsx      # Conversion funnel drop-off chart
│   │   │   ├── RFMDistribution.jsx      # RFM segmentation visualization
│   │   │   ├── RevenueAttribution.jsx   # Marketing touchpoint revenue chart
│   │   │   ├── LiveActivityFeed.jsx     # Real-time WebSocket event feed
│   │   │   ├── MarketingActivityFeed.jsx # Recent communications log
│   │   │   ├── LeadAnalyticsSummary.jsx # Top-level KPI cards
│   │   │   ├── GenderDistribution.jsx   # Demographic breakdown chart
│   │   │   └── WhatIfSimulator.jsx      # Interactive lead score simulator
│   │   ├── customers/
│   │   │   ├── CustomerTable.jsx        # Searchable, sortable customer directory
│   │   │   └── CustomerDetailDrawer.jsx # 360° customer profile slide-out drawer
│   │   └── layout/
│   │       ├── Topbar.jsx               # Navigation header, user info
│   │       ├── NotificationBell.jsx     # Admin notification badge and list
│   │       └── AdminNotificationsList.jsx # Full notification feed
│   ├── context/
│   │   ├── AdminAuthContext.jsx         # JWT login/logout, token persistence
│   │   └── ThemeContext.jsx             # Dark/Light mode toggle
│   ├── pages/
│   │   └── AdminLogin.jsx              # Login form
│   ├── services/
│   │   └── api.js                       # All backend API calls with auth headers
│   └── styles/
│       └── main.css                     # Global admin CSS design system
├── index.html
├── vite.config.js                       # Port 3000, open: true
├── vercel.json                          # Vercel SPA routing config
└── package.json
```

---

## Implemented Dashboard Features

| Feature | API Endpoints Used |
|:--|:--|
| **Overview & KPI Cards** | `GET /api/admin/intelligence/overview` |
| **Customer Directory** | `GET /api/admin/intelligence/leads` |
| **Customer 360° Detail Drawer** | `GET /api/admin/intelligence/customer/:id` |
| **Lead Score Explainability** | `GET /api/admin/intelligence/customer/:id/explain` |
| **Funnel Analytics** | `GET /api/admin/analytics/funnel` |
| **RFM Segmentation** | `GET /api/admin/analytics/rfm` |
| **Revenue Attribution** | `GET /api/admin/analytics/revenue-attribution` |
| **What-If Simulator** | `POST /api/admin/simulate/lead-score` |
| **Live Activity Feed** | WebSocket `marketing_event` channel |
| **Marketing Activity Log** | `GET /api/admin/intelligence/marketing-activity` |
| **Notification Bell** | `GET /api/admin/notifications`, `PATCH /api/admin/notifications/:id/read` |

---

## Verifying a Successful Build

```bash
cd frontend/admin
npm run build
```

A successful build outputs:
```
dist/index.html
dist/assets/index-<hash>.js
dist/assets/index-<hash>.css
```

Preview locally:
```bash
npm run preview
```

The Vercel routing configuration (`vercel.json`) rewrites all paths to `index.html` for client-side routing. For other hosting platforms, configure equivalent SPA fallback routing.

---

## Troubleshooting

| Symptom | Cause | Fix |
|:--|:--|:--|
| Login returns `401 Unauthorized` | Wrong credentials or expired backend session | Confirm `ADMIN_USERNAME`/`ADMIN_PASSWORD` match `backend/.env` |
| Dashboard shows no data | Backend not running or MongoDB unavailable | Start backend with `local_test_launcher.py --serve` |
| CORS error in browser console | Backend CORS origins not including port 3000 | Port 3000 is in the default allowed origins; ensure backend is on port 5000 |
| Live feed shows no events | WebSocket connection failed | Check backend is running; check browser console for WS errors |
| Production build fails with `VITE_API_BASE_URL` error | Variable not set for production build | Set to real deployed backend URL before building |
| Charts show empty state | No customers in database | Register a test customer via the User Portal first |
