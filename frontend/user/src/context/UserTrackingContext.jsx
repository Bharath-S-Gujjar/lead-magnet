import React, { createContext, useContext, useState, useEffect } from 'react';

const UserTrackingContext = createContext();

export const UserTrackingProvider = ({ children }) => {
  const [telemetry, setTelemetry] = useState(() => {
    const saved = localStorage.getItem('leadmagnet_user_telemetry');
    return saved ? JSON.parse(saved) : {
      sessionStart: new Date().toISOString(),
      productsViewed: [],
      categoryHistory: {},
      brandHistory: {},
      searchQueries: [],
      timeSpentMap: {},
      cartEvents: [],
      wishlistEvents: [],
      purchases: []
    };
  });

  useEffect(() => {
    localStorage.setItem('leadmagnet_user_telemetry', JSON.stringify(telemetry));
  }, [telemetry]);

  const trackProductView = (product) => {
    if (!product) return;
    setTelemetry(prev => {
      const categoryCount = (prev.categoryHistory[product.category] || 0) + 1;
      const brandCount = (prev.brandHistory[product.brand] || 0) + 1;

      return {
        ...prev,
        productsViewed: [
          { id: product.id, name: product.name, timestamp: new Date().toISOString() },
          ...prev.productsViewed.filter(p => p.id !== product.id).slice(0, 20)
        ],
        categoryHistory: { ...prev.categoryHistory, [product.category]: categoryCount },
        brandHistory: { ...prev.brandHistory, [product.brand]: brandCount }
      };
    });
  };

  const trackProductTimeSpent = (productId, seconds) => {
    setTelemetry(prev => ({
      ...prev,
      timeSpentMap: {
        ...prev.timeSpentMap,
        [productId]: (prev.timeSpentMap[productId] || 0) + seconds
      }
    }));
  };

  const trackSearch = (query) => {
    if (!query || query.trim() === '') return;
    setTelemetry(prev => ({
      ...prev,
      searchQueries: [query.trim(), ...prev.searchQueries.filter(q => q !== query.trim()).slice(0, 15)]
    }));
  };

  const trackCartAction = (product, action) => {
    setTelemetry(prev => ({
      ...prev,
      cartEvents: [
        { product: product.name, action, timestamp: new Date().toISOString() },
        ...prev.cartEvents.slice(0, 15)
      ]
    }));
  };

  const trackWishlistAction = (product, action) => {
    setTelemetry(prev => ({
      ...prev,
      wishlistEvents: [
        { product: product.name, action, timestamp: new Date().toISOString() },
        ...prev.wishlistEvents.slice(0, 15)
      ]
    }));
  };

  const trackPurchase = (order) => {
    setTelemetry(prev => ({
      ...prev,
      purchases: [order, ...prev.purchases]
    }));
  };

  return (
    <UserTrackingContext.Provider value={{
      telemetry,
      trackProductView,
      trackProductTimeSpent,
      trackSearch,
      trackCartAction,
      trackWishlistAction,
      trackPurchase
    }}>
      {children}
    </UserTrackingContext.Provider>
  );
};

export const useUserTracking = () => useContext(UserTrackingContext);
