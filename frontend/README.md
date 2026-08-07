# Lead Magnet — E-Commerce & Customer Intelligence Platform 🛍️📊

Welcome to the **Lead Magnet** repository! This monorepo contains the complete frontend architecture for the **Lead Magnet** clothing brand platform, featuring two primary web applications:

1. **User Portal (`/user`)**: A high-conversion, multi-language customer-facing e-commerce clothing store.
2. **Admin Portal (`/admin`)**: A real-time Customer Intelligence & Analytics dashboard for store administrators and growth analysts.

---

## 🏗️ Platform Architecture & Overview

```
                          ┌──────────────────────────────────────┐
                          │         LEAD MAGNET PLATFORM         │
                          └──────────────────┬───────────────────┘
                                             │
               ┌─────────────────────────────┴─────────────────────────────┐
               ▼                                                           ▼
 🛍️ User Store Portal (Port 3001)                           📊 Admin Analytics Portal (Port 3000)
 ├── Multi-Language (English, ಕನ್ನಡ, हिंदी)                 ├── Secured Admin Auth (admin@leadmagnet.com)
 ├── Dynamic Clothing Catalog & Filters                     ├── Real-time Lead KPI Analytics
 ├── Shopping Cart & Wishlist Management                   ├── Demographic Split Breakdown Chart
 ├── Order History Tracking                                ├── Multi-Metric Intelligence Directory Table
 └── Responsive Dark / Light Mode UI                        └── Behavioral Telemetry Detail Drawer
```

---

## 📦 Application Breakdown

| Application | Path | Dev Port | Key Functionality |
| :--- | :--- | :--- | :--- |
| **User E-Commerce Store** | [`/user`](./user) | `http://localhost:3001` | Customer shopping, product filtering, multi-language switching (EN/KN/HI), cart, wishlist, and order tracking. |
| **Admin Customer Intelligence** | [`/admin`](./admin) | `http://localhost:3000` | Store analytics, lead KPI monitoring, demographic split charts, directory sorting, and customer session drawers. |

---

## 🌟 Primary Features

### 🛍️ User Clothing Store (`/user`)
- **🌐 i18n Multi-Language Support**: Instant switching between **English**, **Kannada (ಕನ್ನಡ)**, and **Hindi (हिंदी)**.
- **👕 Clothing Categories**: Filter by *T-Shirts*, *Shirts*, *Jeans*, *Hoodies*, *Jackets*, *Dresses*, *Kurtas*, *Sarees*, *Trousers*, *Kids Wear*.
- **🛒 Persistent Cart & Wishlist**: Real-time item additions, quantity updates, total calculations, and item removals.
- **📦 Order History**: Dedicated orders view designed to match the wishlist layout for tracking past purchases.
- **🌓 Adaptive Theme**: Smooth glassmorphism light and dark theme toggling.

### 📊 Admin Customer Intelligence (`/admin`)
- **🔐 Protected Admin Login**: Authenticate with standard admin credentials (`admin@leadmagnet.com` / `admin123`).
- **📈 KPI Metrics Cards**: Live summary of *Total Customers*, *Total Qualified Leads*, *Predicted Future Leads*, and *Active Customers Today*.
- **📊 Demographic Split Visualizations**: Doughnut charts & progress bars breaking down engagement across *Women*, *Men*, and *Kids*.
- **📋 Customer Intelligence Directory Table**: Multi-metric sorting (*Time Spent*, *Orders*, *Cart Items*, *Likes*, *Psychographic*) and real-time search filtering.
- **🔎 Customer Detail Drawer**: Slide-out panel presenting session duration bar charts, interest history timelines, cart items, wishlist records, and automated SMS/email communication logs.
- **🏬 Back to Store Link**: Quick top bar navigation button for jumping directly to the app store (`http://localhost:3001`).

---

## 📁 Repository Directory Structure

```
lead-magnet frontend/
├── user/                         # User E-Commerce Store Application
│   ├── src/
│   │   ├── components/           # Navbar, CategorySection, ProductGrid, etc.
│   │   ├── context/              # CartContext, WishlistContext, LanguageContext, ThemeContext
│   │   ├── pages/                # Home, ProductDetails, Cart, Wishlist, Orders, Profile
│   │   └── data/                 # Product definitions & mock data
│   ├── package.json
│   └── README.md                 # Detailed User Store Documentation
│
├── admin/                        # Admin Customer Intelligence Portal
│   ├── src/
│   │   ├── components/           # LeadAnalyticsSummary, GenderDistribution, CustomerTable, CustomerDetailDrawer
│   │   ├── context/              # AdminAuthContext, ThemeContext
│   │   ├── pages/                # AdminLogin
│   │   └── data/                 # Admin credentials & telemetry data schema
│   ├── package.json
│   └── README.md                 # Detailed Admin Portal Documentation
│
└── README.md                     # Monorepo Master Documentation (This File)
```

---

## 🚀 Quick Start Guide

### Prerequisites
- **Node.js** (v18.0.0 or higher)
- **npm** (v9.0.0 or higher)

### 1. Running the User E-Commerce Store

```bash
# Navigate to user directory
cd user

# Install dependencies
npm install

# Start User Dev Server (Port 3001)
npm run dev
```
Open **`http://localhost:3001`** in your browser.

---

### 2. Running the Admin Customer Intelligence Portal

Open a new terminal window:

```bash
# Navigate to admin directory
cd admin

# Install dependencies
npm install

# Start Admin Dev Server (Port 3000)
npm run dev
```
Open **`http://localhost:3000`** in your browser.

**Official Admin Logins:**
- **Email**: `admin@leadmagnet.com`
- **Password**: `admin123`

---

## 🏗️ Production Build Instructions

To generate production-ready static assets for deployment:

```bash
# Build User Store
cd user
npm run build

# Build Admin Portal
cd ../admin
npm run build
```

Production builds will be output to `user/dist` and `admin/dist` respectively.

---

## 🔌 Backend Integration

Both applications are configured to receive dynamic REST API payloads from your backend server:

- **Products API**: Feed products into `user/src/data/clothingProducts.js` or directly via your API state context.
- **Telemetry API**: Push live store browsing sessions, cart additions, wishlist likes, and lead events into `admin/src/data/mockData.js` or real-time WebSocket/REST endpoints.

---

## 📄 License & Attribution

This codebase is part of the **Lead Magnet** brand platform architecture.
