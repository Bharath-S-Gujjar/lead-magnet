import React, { createContext, useContext, useState, useEffect } from 'react';
import { addToWishlistApi, fetchWishlist, getAnonymousId, getCustomerSession, removeFromWishlistApi, trackCustomerEvent } from '../services/api';
import { useAuth } from './AuthContext';

const WishlistContext = createContext();

export const WishlistProvider = ({ children }) => {
  const { customer: authCustomer } = useAuth();
  const customer = authCustomer || getCustomerSession();
  const userId = customer?.user_id || null;
  const anonymousId = userId ? null : getAnonymousId();
  const identityKey = userId || anonymousId;

  const [wishlist, setWishlist] = useState(() => {
    const saved = localStorage.getItem('leadmagnet_user_wishlist');
    return saved ? JSON.parse(saved) : [];
  });

  useEffect(() => {
    localStorage.setItem('leadmagnet_user_wishlist', JSON.stringify(wishlist));
  }, [wishlist]);

  // Sync with backend wishlist
  useEffect(() => {
    let active = true;
    const loadWishlist = async () => {
      try {
        const persisted = await fetchWishlist(userId, anonymousId);
        if (!active) return;
        if (Array.isArray(persisted) && (persisted.length > 0 || userId)) {
          setWishlist(persisted.map(item => ({
            id: item.product_id || item.id,
            name: item.name,
            price: item.price,
            image: item.image,
            category: item.category,
            brand: item.brand,
            rating: item.rating || 4.3,
            discount: item.discount || 0,
            dateLiked: item.created_at ? new Date(item.created_at).toLocaleDateString() : 'Recently'
          })));
        }
      } catch (err) {
        // Fallback to local storage if API is temporarily unavailable
      }
    };
    loadWishlist();
    return () => {
      active = false;
    };
  }, [identityKey]);

  const toggleWishlist = (product) => {
    const prodId = product.id || product._id;
    const exists = wishlist.some(item => item.id === prodId);

    if (exists) {
      setWishlist(prev => prev.filter(item => item.id !== prodId));
      removeFromWishlistApi(prodId, userId, anonymousId, customer?.session_id).catch(() => {});
      trackCustomerEvent('wishlist_remove', {
        entity: { type: 'product', id: prodId, name: product.name, category: product.category, brand: product.brand },
      });
    } else {
      const newItem = { ...product, id: prodId, dateLiked: 'Just now' };
      setWishlist(prev => [...prev, newItem]);
      addToWishlistApi(prodId, userId, anonymousId, customer?.session_id).catch(() => {});
      trackCustomerEvent('wishlist_add', {
        entity: { type: 'product', id: prodId, name: product.name, category: product.category, brand: product.brand },
      });
    }
  };

  const isInWishlist = (id) => {
    return wishlist.some(item => item.id === id);
  };

  const removeFromWishlist = (id) => {
    setWishlist(prev => prev.filter(item => item.id !== id));
    removeFromWishlistApi(id, userId, anonymousId, customer?.session_id).catch(() => {});
    trackCustomerEvent('wishlist_remove', {
      entity: { type: 'product', id },
    });
  };

  return (
    <WishlistContext.Provider value={{
      wishlist,
      toggleWishlist,
      isInWishlist,
      removeFromWishlist,
      totalWishlist: wishlist.length
    }}>
      {children}
    </WishlistContext.Provider>
  );
};

export const useWishlist = () => useContext(WishlistContext);
