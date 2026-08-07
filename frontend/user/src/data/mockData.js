// Minimal Clothing Brand Customer Intelligence Mock Dataset

export const CLOTHING_KPIS = {
  totalCustomers: 2500,
  totalLeads: 985,
  totalCustomersText: "2,500",
  leadConversionPct: "39.4%",
  leadDetailsText: "985 Leads out of 2,500 Customers",
  customerDistribution: {
    men: 1000,
    women: 1200,
    kids: 300,
    menPct: "40%",
    womenPct: "48%",
    kidsPct: "12%"
  },
  activeToday: 142
};

export const CLOTHING_GENDER_CHART = [
  { name: "Women", value: 1200, pct: "48%", color: "#ec4899" },
  { name: "Men", value: 1000, pct: "40%", color: "#3b82f6" },
  { name: "Kids", value: 300, pct: "12%", color: "#f59e0b" },
];

export const CLOTHING_CUSTOMERS = [
  {
    id: "LM-CLO-8901",
    name: "Rahul Sharma",
    avatar: "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=150&auto=format&fit=crop&q=80",
    gender: "Male",
    age: 27,
    orders: 8,
    cartItemsCount: 3,
    likedItemsCount: 5,
    timeSpent: "42 mins",
    timeSpentMinutes: 42,
    psychographic: "Streetwear Enthusiast",

    // Time Spent Sessions (for detail page bar chart)
    sessions: [
      { date: "Aug 01", minutes: 14, pagesVisited: 6, outcome: "Viewed Men's T-Shirts" },
      { date: "Aug 02", minutes: 22, pagesVisited: 9, outcome: "Liked Oversized Hoodie" },
      { date: "Aug 03", minutes: 18, pagesVisited: 7, outcome: "Viewed Cargo Pants" },
      { date: "Aug 04", minutes: 30, pagesVisited: 12, outcome: "Added Denim Jacket to Cart" },
      { date: "Aug 05 Today", minutes: 42, pagesVisited: 16, outcome: "Cart Saved - Sneakers & Jacket" },
    ],

    // Interest History Timeline
    interestHistory: [
      { date: "Aug 05", time: "10:15 AM", category: "Men's Clothing", event: "Viewed Men's T-Shirts" },
      { date: "Aug 05", time: "10:22 AM", category: "Outerwear", event: "Liked Oversized Hoodie" },
      { date: "Aug 05", time: "10:35 AM", category: "Denim & Jackets", event: "Added Denim Jacket to Cart" },
      { date: "Aug 05", time: "10:48 AM", category: "Footwear", event: "Viewed Sneakers" },
      { date: "Aug 05", time: "10:55 AM", category: "Bottomwear", event: "Liked Cargo Pants" },
      { date: "Aug 05", time: "11:10 AM", category: "Formalwear", event: "Purchased Formal Shirt" },
    ],

    // Cart Items (Strictly Clothing)
    cartItems: [
      { id: "c1", name: "Vintage Oversized Denim Jacket", size: "L", color: "Washed Denim", price: 2499, qty: 1, category: "Men", image: "https://images.unsplash.com/photo-1543076447-215ad9ba6923?w=150&auto=format&fit=crop&q=80" },
      { id: "c2", name: "Heavyweight Cotton Oversized Hoodie", size: "L", color: "Charcoal Black", price: 1899, qty: 1, category: "Men", image: "https://images.unsplash.com/photo-1556905055-8f358a7a47b2?w=150&auto=format&fit=crop&q=80" },
      { id: "c3", name: "Retro High-Top Canvas Sneakers", size: "10", color: "Off-White", price: 2999, qty: 1, category: "Men", image: "https://images.unsplash.com/photo-1549298916-b41d501d3772?w=150&auto=format&fit=crop&q=80" },
    ],

    // Liked Items / Wishlist
    likedItems: [
      { id: "l1", name: "Relaxed Fit Utility Cargo Pants", category: "Men", dateLiked: "Today 10:55 AM", image: "https://images.unsplash.com/photo-1624378439575-d8705ad7ae80?w=150&auto=format&fit=crop&q=80" },
      { id: "l2", name: "Slim Fit Oxford Formal Shirt", category: "Men", dateLiked: "Aug 04, 2:10 PM", image: "https://images.unsplash.com/photo-1602810318383-e386cc2a3ccf?w=150&auto=format&fit=crop&q=80" },
      { id: "l3", name: "Graphic Streetwear Crew T-Shirt", category: "Men", dateLiked: "Aug 03, 6:40 PM", image: "https://images.unsplash.com/photo-1521572267360-ee0c2909d518?w=150&auto=format&fit=crop&q=80" },
    ],

    // Customer Interest Summary
    interestSummary: "Rahul frequently browses Men's Casual & Streetwear collections, spends a long time comparing Denim Jackets and Oversized Hoodies, and repeatedly adds Sneakers to his cart without completing checkout.",

    // Automated Read-Only Communication
    sentEmail: {
      subject: "Complete Your Casual Look",
      body: "Hi Rahul,\n\nThe Denim Jacket and Oversized Hoodie you liked are still available in your size (L). Complete your purchase today and enjoy an exclusive 10% privilege discount.\n\nWarm regards,\nLead Magnet Team",
      status: "Sent"
    },
    sentSms: {
      text: "Hi Rahul, your favorite Denim Jacket is waiting for you. Complete your order today: https://lmag.net/c/8901",
      status: "Delivered"
    }
  },

  {
    id: "LM-CLO-8902",
    name: "Priya Patel",
    avatar: "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=150&auto=format&fit=crop&q=80",
    gender: "Female",
    age: 25,
    orders: 12,
    cartItemsCount: 2,
    likedItemsCount: 8,
    timeSpent: "38 mins",
    timeSpentMinutes: 38,
    psychographic: "Minimalist Luxe",

    sessions: [
      { date: "Aug 01", minutes: 12, pagesVisited: 5, outcome: "Viewed Linen Tops" },
      { date: "Aug 02", minutes: 18, pagesVisited: 8, outcome: "Liked Silk Slip Dress" },
      { date: "Aug 03", minutes: 25, pagesVisited: 11, outcome: "Viewed Wool Tailored Blazer" },
      { date: "Aug 04", minutes: 30, pagesVisited: 14, outcome: "Added Linen Blazer to Cart" },
      { date: "Aug 05 Today", minutes: 38, pagesVisited: 18, outcome: "Cart Saved - Silk Dress & Blazer" },
    ],

    interestHistory: [
      { date: "Aug 05", time: "11:00 AM", category: "Women's Tops", event: "Viewed Linen Button-Down Shirt" },
      { date: "Aug 05", time: "11:15 AM", category: "Dresses", event: "Liked Silk Satin Slip Dress" },
      { date: "Aug 05", time: "11:30 AM", category: "Outerwear", event: "Added Linen Tailored Blazer to Cart" },
      { date: "Aug 05", time: "11:45 AM", category: "Knitwear", event: "Viewed Cashmere Crew Sweater" },
    ],

    cartItems: [
      { id: "c4", name: "Oversized Tailored Linen Blazer", size: "M", color: "Cream Beige", price: 145.00, qty: 1, category: "Women", image: "https://images.unsplash.com/photo-1591047139829-d91aecb6caea?w=150&auto=format&fit=crop&q=80" },
      { id: "c5", name: "Silk Satin Midi Slip Dress", size: "S", color: "Champagne", price: 115.00, qty: 1, category: "Women", image: "https://images.unsplash.com/photo-1572804013309-59a88b7e92f1?w=150&auto=format&fit=crop&q=80" },
    ],

    likedItems: [
      { id: "l4", name: "Cashmere Soft Crew Neck Sweater", category: "Women", dateLiked: "Today 11:45 AM", image: "https://images.unsplash.com/photo-1576995853123-5a10305d93c0?w=150&auto=format&fit=crop&q=80" },
      { id: "l5", name: "High-Waisted Tailored Linen Trousers", category: "Women", dateLiked: "Aug 04, 4:20 PM", image: "https://images.unsplash.com/photo-1594633312681-425c7b97ccd1?w=150&auto=format&fit=crop&q=80" },
    ],

    interestSummary: "Priya shows high affinity for Women's Minimalist Luxe collection. She spends significant time reading fabric details on Tailored Linen Blazers and Silk Slip Dresses.",

    sentEmail: {
      subject: "Your Elegant Linen Look is Reserved",
      body: "Hi Priya,\n\nThe Oversized Tailored Linen Blazer and Silk Slip Dress you selected are waiting in your cart. Complete your order today to enjoy complimentary express delivery.\n\nBest,\nLead Magnet Luxe Desk",
      status: "Sent"
    },
    sentSms: {
      text: "Hi Priya, your Linen Blazer & Silk Slip Dress are ready for express delivery: https://lmag.net/c/8902",
      status: "Delivered"
    }
  },

  {
    id: "LM-CLO-8903",
    name: "Marcus Vance",
    avatar: "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=150&auto=format&fit=crop&q=80",
    gender: "Male",
    age: 31,
    orders: 15,
    cartItemsCount: 4,
    likedItemsCount: 6,
    timeSpent: "50 mins",
    timeSpentMinutes: 50,
    psychographic: "Activewear Lover",

    sessions: [
      { date: "Aug 01", minutes: 20, pagesVisited: 8, outcome: "Viewed Gym Wear" },
      { date: "Aug 02", minutes: 28, pagesVisited: 11, outcome: "Liked Compression Shorts" },
      { date: "Aug 03", minutes: 35, pagesVisited: 14, outcome: "Purchased Running Shorts" },
      { date: "Aug 04", minutes: 42, pagesVisited: 16, outcome: "Viewed Carbon Running Shoes" },
      { date: "Aug 05 Today", minutes: 50, pagesVisited: 20, outcome: "Cart Saved - Activewear Set" },
    ],

    interestHistory: [
      { date: "Aug 05", time: "1:15 PM", category: "Footwear", event: "Viewed Pro Carbon Running Shoes" },
      { date: "Aug 05", time: "1:30 PM", category: "Men's Active", event: "Liked Seamless Gym Tank" },
      { date: "Aug 05", time: "1:45 PM", category: "Men's Active", event: "Added Performance Training Hoodie to Cart" },
    ],

    cartItems: [
      { id: "c6", name: "Pro Carbon Cushion Running Shoes", size: "11", color: "Neon Red", price: 180.00, qty: 1, category: "Men", image: "https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=150&auto=format&fit=crop&q=80" },
      { id: "c7", name: "Performance Active Training Hoodie", size: "XL", color: "Slate Grey", price: 75.00, qty: 1, category: "Men", image: "https://images.unsplash.com/photo-1556905055-8f358a7a47b2?w=150&auto=format&fit=crop&q=80" },
    ],

    likedItems: [
      { id: "l6", name: "Seamless Breathable Gym Shorts", category: "Men", dateLiked: "Today 1:30 PM", image: "https://images.unsplash.com/photo-1517838277536-f5f99be501cd?w=150&auto=format&fit=crop&q=80" },
    ],

    interestSummary: "Marcus focuses primarily on athletic performance wear and high-cushion running shoes, spending over 50 minutes comparing breathable gear.",

    sentEmail: {
      subject: "Ready for Race Day, Marcus?",
      body: "Hi Marcus,\n\nYour Pro Carbon Running Shoes & Performance Hoodie are ready. Complete checkout today to lock in your fitness reward.\n\nLead Magnet Athletics",
      status: "Sent"
    },
    sentSms: {
      text: "Hi Marcus, get your Pro Carbon Running Shoes ready for race day: https://lmag.net/c/8903",
      status: "Delivered"
    }
  },

  {
    id: "LM-CLO-8904",
    name: "Ananya Sharma",
    avatar: "https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=150&auto=format&fit=crop&q=80",
    gender: "Female",
    age: 23,
    orders: 6,
    cartItemsCount: 1,
    likedItemsCount: 10,
    timeSpent: "29 mins",
    timeSpentMinutes: 29,
    psychographic: "Trend Follower",

    sessions: [
      { date: "Aug 01", minutes: 15, pagesVisited: 6, outcome: "Viewed Floral Midi Dress" },
      { date: "Aug 03", minutes: 22, pagesVisited: 9, outcome: "Liked Cropped Cardigan" },
      { date: "Aug 05 Today", minutes: 29, pagesVisited: 12, outcome: "Added Floral Wrap Dress to Cart" },
    ],

    interestHistory: [
      { date: "Aug 05", time: "2:05 PM", category: "Dresses", event: "Viewed Floral Print Wrap Midi Dress" },
      { date: "Aug 05", time: "2:20 PM", category: "Women's Tops", event: "Liked Cropped Knit Cardigan" },
    ],

    cartItems: [
      { id: "c8", name: "Floral Print Summer Wrap Midi Dress", size: "S", color: "Rose Floral", price: 95.00, qty: 1, category: "Women", image: "https://images.unsplash.com/photo-1572804013309-59a88b7e92f1?w=150&auto=format&fit=crop&q=80" },
    ],

    likedItems: [
      { id: "l7", name: "Soft Pastel Cropped Knit Cardigan", category: "Women", dateLiked: "Today 2:20 PM", image: "https://images.unsplash.com/photo-1583743814966-8936f5b7be1a?w=150&auto=format&fit=crop&q=80" },
    ],

    interestSummary: "Ananya follows summer dress trends on TikTok, heavily liking pastel knitwear and floral wrap dresses.",

    sentEmail: {
      subject: "Ananya, your Floral Wrap Dress is waiting!",
      body: "Hi Ananya,\n\nComplete your order for the Floral Print Wrap Midi Dress today and enjoy free shipping.\n\nLead Magnet Fashion Desk",
      status: "Sent"
    },
    sentSms: {
      text: "Hi Ananya, get your Floral Wrap Dress with free express shipping: https://lmag.net/c/8904",
      status: "Delivered"
    }
  },

  {
    id: "LM-CLO-8905",
    name: "Kabir Mehta",
    avatar: "https://images.unsplash.com/photo-1522075469751-3a6694fb2f61?w=150&auto=format&fit=crop&q=80",
    gender: "Male",
    age: 29,
    orders: 14,
    cartItemsCount: 2,
    likedItemsCount: 4,
    timeSpent: "33 mins",
    timeSpentMinutes: 33,
    psychographic: "Vintage Casual",

    sessions: [
      { date: "Aug 02", minutes: 16, pagesVisited: 7, outcome: "Viewed Vintage Denim Jeans" },
      { date: "Aug 04", minutes: 24, pagesVisited: 10, outcome: "Liked Corduroy Overshirt" },
      { date: "Aug 05 Today", minutes: 33, pagesVisited: 13, outcome: "Added Corduroy Shirt to Cart" },
    ],

    interestHistory: [
      { date: "Aug 05", time: "3:10 PM", category: "Men's Outerwear", event: "Viewed Vintage Wash Corduroy Jacket" },
      { date: "Aug 05", time: "3:25 PM", category: "Bottomwear", event: "Liked Straight Fit Vintage Jeans" },
    ],

    cartItems: [
      { id: "c9", name: "Vintage Wash Corduroy Button Overshirt", size: "L", color: "Tobacco Brown", price: 90.00, qty: 1, category: "Men", image: "https://images.unsplash.com/photo-1576995853123-5a10305d93c0?w=150&auto=format&fit=crop&q=80" },
    ],

    likedItems: [
      { id: "l8", name: "Straight Leg Washed Vintage Jeans", category: "Men", dateLiked: "Today 3:25 PM", image: "https://images.unsplash.com/photo-1541099649105-f69ad21f3246?w=150&auto=format&fit=crop&q=80" },
    ],

    interestSummary: "Kabir is drawn to vintage corduroy textures, earth-tone overshirts, and washed denim casuals.",

    sentEmail: {
      subject: "Complete Your Corduroy Look, Kabir",
      body: "Hi Kabir,\n\nYour Vintage Wash Corduroy Overshirt is waiting in your cart. Grab it today before stock runs out.\n\nLead Magnet",
      status: "Sent"
    },
    sentSms: {
      text: "Hi Kabir, complete your vintage corduroy overshirt order: https://lmag.net/c/8905",
      status: "Delivered"
    }
  }
];
