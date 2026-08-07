# Lead Magnet — Customer Intelligence & Analytics Admin Portal 📊👔

The administrator portal for **Lead Magnet** brand management. This dashboard empowers store managers and analysts to track customer leads, demographic splits, session behaviors, shopping cart abandonments, and automated communication workflows in real-time.

---

## 🌟 Key Features

- **🔐 Secured Admin Authentication**: Guarded dashboard access. Official credentials:
  - **Admin Email**: `admin@leadmagnet.com`
  - **Admin Password**: `admin123`
- **📈 Real-Time KPI Analytics**: Overview cards summarizing *Total Customers*, *Total Qualified Leads*, *Predicted Future Leads*, and *Active Customers Today*.
- **📊 Demographic Split Visualization**: Interactive LeetCode-style doughnut chart and progress bars breaking down customer engagement by gender (*Women*, *Men*, *Kids*).
- **📋 Customer Intelligence Directory**: Full-featured directory table supporting search query filtering and metric-focused sorting (*Time Spent*, *Number of Orders*, *Cart Items*, *Wishlist Likes*, *Psychographic Segment*).
- **🔎 Slide-out Customer Detail Drawer**: Deep-dive behavioral analysis drawer displaying:
  - Time Spent session bar charts & visit metrics
  - Interest history timeline
  - Active shopping cart contents & prices
  - Liked products & wishlist history
  - Customer interest summaries
  - Read-only automated email & SMS communication logs
- **🏬 Back to Store Link**: Quick navigation button in the top navigation bar linking directly to the main clothing store (`http://localhost:3001`).
- **🌓 Adaptive Light & Dark Theme**: Full glassmorphism design system tailored for data density and visual clarity.

---

## 🛠️ Tech Stack

- **Core Framework**: React 18
- **Build Tool & Dev Server**: Vite (Running on `http://localhost:3000`)
- **Routing**: React Router DOM
- **Data Visualizations**: Recharts (PieChart, BarChart, ResponsiveContainer)
- **Icons**: Lucide React
- **Styling**: Vanilla CSS with HSL design tokens, glassmorphism cards, and responsive panel layouts.

---

## 📁 Project Structure

```
admin/
├── src/
│   ├── components/
│   │   ├── analytics/
│   │   │   ├── LeadAnalyticsSummary.jsx   # Top KPI metrics summary cards
│   │   │   └── GenderDistribution.jsx      # Demographic doughnut chart & progress breakdown
│   │   ├── customers/
│   │   │   ├── CustomerTable.jsx          # Intelligence directory table with sorting & search
│   │   │   └── CustomerDetailDrawer.jsx   # Slide-out customer behavior detail drawer
│   │   └── layout/
│   │       └── Topbar.jsx                 # Navigation header with "Back to Store" & search
│   ├── context/
│   │   ├── AdminAuthContext.jsx           # Admin login session management
│   │   └── ThemeContext.jsx               # Dark/Light mode theme state
│   ├── data/
│   │   ├── adminCredentials.js            # Admin authentication configuration
│   │   └── mockData.js                    # Datasets for backend telemetry mapping
│   ├── pages/
│   │   └── AdminLogin.jsx                 # Administrator authentication view
│   ├── styles/                            # CSS variables & panel design system
│   ├── App.jsx
│   └── main.jsx
├── package.json
└── vite.config.js
```

---

## 🚀 Getting Started

### Prerequisites

Ensure you have **Node.js** (v18 or higher) and **npm** installed on your system.

### Installation

1. Navigate to the `admin` directory:
   ```bash
   cd admin
   ```

2. Install dependencies:
   ```bash
   npm install
   ```

3. Start the development server:
   ```bash
   npm run dev
   ```
   The application will launch locally at `http://localhost:3000`.

4. Access the dashboard using the official admin credentials:
   - **Email**: `admin@leadmagnet.com`
   - **Password**: `admin123`

5. Build for production:
   ```bash
   npm run build
   ```

---

## 🔌 Backend Telemetry & Customer Data Integration

The dashboard UI components are decoupled and built to map directly to real user telemetry and customer lead data fetched from your backend API:

```javascript
// Example customer object structure expected by the Customer Intelligence Directory
{
  id: "LM-CLO-8901",
  name: "Rahul Sharma",
  gender: "Male",
  age: 27,
  orders: 8,
  cartItemsCount: 3,
  likedItemsCount: 5,
  timeSpent: "42 mins",
  psychographic: "Streetwear Enthusiast",
  sessions: [ ... ],
  interestHistory: [ ... ],
  cartItems: [ ... ],
  likedItems: [ ... ],
  sentEmail: { subject: "...", body: "...", status: "Sent" },
  sentSms: { text: "...", status: "Delivered" }
}
```

---

## 📄 License

This project is part of the **Lead Magnet** clothing brand platform suite.
