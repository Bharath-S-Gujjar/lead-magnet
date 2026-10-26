import React, { createContext, useContext, useState, useEffect, useRef } from 'react';
import { trackCustomerEvent } from '../services/api';

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

  const lastTrackedSearchRef = useRef('');

  useEffect(() => {
    localStorage.setItem('leadmagnet_user_telemetry', JSON.stringify(telemetry));
  }, [telemetry]);

  const trackProductView = (product) => {
    if (!product) return;
    const prodId = product.id || product._id || product.product_id;
    const prodTitle = product.title || product.name || 'Product';
    setTelemetry(prev => {
      const categoryCount = (prev.categoryHistory[product.category] || 0) + 1;
      const brandCount = (prev.brandHistory[product.brand] || 0) + 1;

      return {
        ...prev,
        productsViewed: [
          { id: prodId, name: prodTitle, timestamp: new Date().toISOString() },
          ...prev.productsViewed.filter(p => p.id !== prodId).slice(0, 20)
        ],
        categoryHistory: { ...prev.categoryHistory, [product.category]: categoryCount },
        brandHistory: { ...prev.brandHistory, [product.brand]: brandCount }
      };
    });

    trackCustomerEvent('product_view', {
      page: `/product/${prodId}`,
      entity: {
        type: 'product',
        id: prodId,
        name: prodTitle,
        title: prodTitle,
        price: product.price,
        category: product.category,
        brand: product.brand,
      },
    }).catch(() => {});
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
    const cleanQuery = query.trim();
    setTelemetry(prev => ({
      ...prev,
      searchQueries: [cleanQuery, ...prev.searchQueries.filter(q => q !== cleanQuery).slice(0, 15)]
    }));

    if (lastTrackedSearchRef.current !== cleanQuery) {
      lastTrackedSearchRef.current = cleanQuery;
      trackCustomerEvent('search', {
        metadata: { query: cleanQuery }
      }).catch(() => {});
    }
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
