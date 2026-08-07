# Lead Magnet — Premium Clothing Store Frontend 🛍️👗👕

A modern, high-performance e-commerce frontend web application built for the **Lead Magnet** clothing brand. This portal provides an immersive shopping experience featuring multi-language support, real-time product filtering, wishlist management, cart handling, and order tracking.

---

## 🌟 Key Features

- **🌐 Multi-Language Support**: Seamlessly switch between **English**, **Kannada (ಕನ್ನಡ)**, and **Hindi (हिंदी)** across the entire store UI.
- **🏷️ Dynamic Clothing Catalog**: Browse clothing items organized by categories (*T-Shirts*, *Shirts*, *Jeans*, *Hoodies*, *Jackets*, *Dresses*, *Kurtas*, *Sarees*, *Trousers*, *Kids Wear*).
- **⚡ Backend Product Integration Ready**: Designed to dynamically populate and render products fetched directly from your backend REST API or database.
- **🛒 Shopping Cart & Wishlist**: Real-time persistent state management for saving favorite items and managing cart item quantities.
- **📦 Order History & Tracking**: Dedicated Orders section matching the wishlist design system to review past clothing purchases and delivery statuses.
- **👤 Customer Profile & Settings**: Clean account management view with personal preferences and shipping address settings.
- **🌓 Dark & Light Theme**: Built-in glassmorphism design system supporting smooth toggle between dark mode and light mode.

---

## 🛠️ Tech Stack

- **Core Framework**: React 18
- **Build Tool & Dev Server**: Vite (Running on `http://localhost:3001`)
- **Routing**: React Router DOM
- **Icons**: Lucide React
- **Data Visualizations**: Recharts
- **Celebration Effects**: Canvas Confetti
- **Styling**: Modern Vanilla CSS with HSL design tokens, CSS variables, glassmorphism, and responsive grid layouts.

---

## 📁 Project Structure

```
user/
├── src/
│   ├── components/       # Reusable UI components
│   │   ├── CategorySection.jsx    # Gender & Category filter pills
│   │   ├── Navbar.jsx             # Top navigation bar & language selector
│   │   ├── ProductGrid.jsx        # Product cards grid layout
│   │   └── HeroBanner.jsx         # Promotional banner slider
│   ├── context/          # Application state context providers
│   │   ├── CartContext.jsx        # Cart state manager
│   │   ├── WishlistContext.jsx    # Wishlist state manager
│   │   ├── LanguageContext.jsx    # i18n English/Kannada/Hindi state
│   │   └── ThemeContext.jsx       # Light/Dark mode state
│   ├── pages/            # Application routes & screens
│   │   ├── Home.jsx               # Main store landing page
│   │   ├── ProductDetails.jsx     # Individual product detail page
│   │   ├── Cart.jsx               # Shopping cart & checkout flow
│   │   ├── Wishlist.jsx           # Saved items view
│   │   ├── Orders.jsx             # Customer purchase order history
│   │   ├── Profile.jsx            # Account profile & settings
│   │   └── Login.jsx / Signup.jsx # Authentication screens
│   ├── data/             # Static data & clothing product definitions
│   └── styles/           # CSS design system & global styles
├── package.json
└── vite.config.js
```

---

## 🚀 Getting Started

### Prerequisites

Ensure you have **Node.js** (v18 or higher) and **npm** installed on your system.

### Installation

1. Navigate to the `user` directory:
   ```bash
   cd user
   ```

2. Install dependencies:
   ```bash
   npm install
   ```

3. Start the development server:
   ```bash
   npm run dev
   ```
   The application will launch locally at `http://localhost:3001`.

4. Build for production:
   ```bash
   npm run build
   ```

---

## 🔌 Connecting to Backend API

Products are ready to be fetched dynamically from your backend server. Simply replace or extend `clothingProducts.js` or dispatch an API request in your state context:

```javascript
// Example REST API Fetch Integration
useEffect(() => {
  fetch('https://your-backend-api.com/api/products')
    .then((res) => res.json())
    .then((data) => setProducts(data))
    .catch((err) => console.error(err));
}, []);
```

---

## 📄 License

This project is part of the **Lead Magnet** clothing brand platform suite.
