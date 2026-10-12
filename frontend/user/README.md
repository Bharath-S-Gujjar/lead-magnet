# Lead Magnet — User Portal (Customer Storefront)

The User Portal is the customer-facing e-commerce storefront for Lead Magnet. Customers browse a 120,466-product clothing catalog, manage their cart and wishlist, place orders, and manage their account. All customer interactions are silently captured as behavioral telemetry that feeds the ML lead-scoring pipeline in the backend.

---

## Tech Stack

| Tool | Version |
|:--|:--|
| React | 18.3 |
| Vite | 6.x |
| React Router DOM | 6.28 |
| Recharts | 3.x |
| Lucide React | 0.469 |
| Canvas Confetti | 1.9 |

**Dev server port:** `3001`

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

All commands run from the `frontend/user/` directory:

```bash
cd frontend/user
npm install
```

---

## Available Scripts

| Script | Command | Description |
|:--|:--|:--|
| Development | `npm run dev` | Starts Vite dev server at `http://localhost:3001` with HMR |
| Production build | `npm run build` | Builds to `dist/` for deployment |
| Preview build | `npm run preview` | Serves the `dist/` folder locally for build verification |

---

## API Configuration

### Development (local)

No configuration is needed for local development. When no `VITE_API_BASE_URL` is set, the app defaults to `http://127.0.0.1:5000`.

The backend must be running before the frontend will work. Start it with:
```powershell
venv\Scripts\python backend/local_test_launcher.py --serve --port 5000
```

### Production Build

Set `VITE_API_BASE_URL` to the deployed backend URL **before** running `npm run build`. This can be done via:

1. CI/CD environment variable (recommended)
2. Deployment dashboard (Vercel, Render, etc.)
3. A `.env.production.local` file that is **not committed**

```
VITE_API_BASE_URL=https://your-deployed-backend.onrender.com
```

> ⚠️ The build **will fail at startup** if `VITE_API_BASE_URL` is missing, empty, contains `localhost`, or contains `example.com` in a production build. This is intentional fail-closed behavior to prevent broken deployments.

The committed `frontend/user/.env.production` file intentionally has this variable commented out — set it in your CI/CD pipeline or deployment environment, not in the file.

---

## Running Against the Isolated Local Backend

1. Start MongoDB Community on `127.0.0.1:27017`.
2. Start the backend in isolated mode:
   ```powershell
   venv\Scripts\python backend/local_test_launcher.py --serve --port 5000
   ```
3. Start the user portal:
   ```bash
   cd frontend/user
   npm run dev
   ```
4. Open `http://localhost:3001` in your browser.

The frontend automatically connects to `http://127.0.0.1:5000` in development mode.

---

## Application Structure

```
frontend/user/
├── src/
│   ├── App.jsx                    # Root router and layout
│   ├── main.jsx                   # Application entry point
│   ├── components/
│   │   ├── Navbar.jsx             # Top navigation bar, auth state, cart counter
│   │   ├── HeroBanner.jsx         # Promotional banner slider
│   │   ├── ProductGrid.jsx        # Product cards grid
│   │   ├── ProductCard.jsx        # Individual product card
│   │   ├── FilterPanel.jsx        # Category, gender, price filters
│   │   └── CategorySection.jsx    # Category filter pills
│   ├── context/
│   │   ├── AuthContext.jsx        # JWT login state, register/login/logout
│   │   ├── CartContext.jsx        # Cart state (add, update, remove, clear)
│   │   ├── WishlistContext.jsx    # Wishlist state (add, remove)
│   │   ├── UserTrackingContext.jsx # Behavioral telemetry hook
│   │   └── ThemeContext.jsx       # Light/Dark theme toggle
│   ├── pages/
│   │   ├── Login.jsx / Signup.jsx # Authentication screens
│   │   ├── ProductDetails.jsx     # Product detail view
│   │   ├── Cart.jsx               # Cart and checkout flow
│   │   ├── Wishlist.jsx           # Saved items
│   │   ├── Orders.jsx             # Order history
│   │   ├── Profile.jsx / Account.jsx # Account settings
│   │   └── UserDashboard.jsx      # User home dashboard
│   ├── services/
│   │   └── api.js                 # All backend API calls
│   ├── hooks/
│   │   └── useTracking.js         # Behavioral event hooks
│   └── styles/
│       └── main.css               # Global CSS design system
├── index.html
├── vite.config.js                 # Port 3001, React plugin
└── package.json
```

---

## Implemented User Workflows

1. **Registration and login** — JWT-based, anonymous session merged on login.
2. **Product browsing** — paginated catalog, filter by gender/category, search.
3. **Product detail** — brand, price, discount, rating, add-to-cart, wishlist toggle.
4. **Cart management** — add, update quantity, remove items, running total.
5. **Wishlist** — add and remove products.
6. **Checkout and orders** — COD order creation via `POST /api/orders`, order history view.
7. **Behavioral telemetry** — every page view, cart add, and search is sent to the backend automatically via `UserTrackingContext`.

---

## Verifying a Successful Build

```bash
cd frontend/user
npm run build
```

A successful build outputs:
```
dist/index.html
dist/assets/index-<hash>.js
dist/assets/index-<hash>.css
```

Preview the built app locally:
```bash
npm run preview
```

> **Note:** Previewing the production build locally will fail on API calls if the backend is not running, which is expected behavior.

---

## Troubleshooting

| Symptom | Cause | Fix |
|:--|:--|:--|
| `Failed to fetch` on any API call | Backend not running or wrong port | Start backend on port 5000 |
| CORS error in browser console | Backend CORS origins misconfigured | Ensure `http://localhost:3001` is in `FRONTEND_URL` or default origins |
| Product grid shows 0 items | `leadmagnet_test` not seeded | Run `seed_clothing_products.py` with test env vars |
| Production build throws `VITE_API_BASE_URL` error | Variable not set | Set `VITE_API_BASE_URL` to a real deployed URL before building |
| `npm install` fails | Node version too old | Upgrade to Node.js 18+ |
