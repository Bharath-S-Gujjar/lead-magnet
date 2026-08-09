import React, { createContext, useContext, useState, useEffect } from 'react';
import { trackCustomerEvent } from '../services/api';

const WishlistContext = createContext();

export const WishlistProvider = ({ children }) => {
  const [wishlist, setWishlist] = useState(() => {
    const saved = localStorage.getItem('leadmagnet_user_wishlist');
    return saved ? JSON.parse(saved) : [];
  });

  useEffect(() => {
    localStorage.setItem('leadmagnet_user_wishlist', JSON.stringify(wishlist));
  }, [wishlist]);

  const toggleWishlist = (product) => {
    setWishlist(prev => {
      const exists = prev.some(item => item.id === product.id);
      if (exists) {
        trackCustomerEvent('wishlist_remove', {
          entity: { type: 'product', id: product.id, name: product.name, category: product.category, brand: product.brand },
        });
        return prev.filter(item => item.id !== product.id);
      } else {
        trackCustomerEvent('wishlist_add', {
          entity: { type: 'product', id: product.id, name: product.name, category: product.category, brand: product.brand },
        });
        return [...prev, { ...product, dateLiked: 'Just now' }];
      }
    });
  };

  const isInWishlist = (id) => {
    return wishlist.some(item => item.id === id);
  };

  const removeFromWishlist = (id) => {
    setWishlist(prev => prev.filter(item => item.id !== id));
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
