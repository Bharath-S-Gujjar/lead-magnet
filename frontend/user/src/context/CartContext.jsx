import React, { createContext, useContext, useState, useEffect } from 'react';
import confetti from 'canvas-confetti';
import { addToCartApi, clearCartApi, fetchCart, getAnonymousId, getCustomerSession, removeFromCartApi, trackCustomerEvent, updateCartApi } from '../services/api';
import { useAuth } from './AuthContext';

const CartContext = createContext();

export const CartProvider = ({ children }) => {
  const { customer: authCustomer } = useAuth();
  const customer = authCustomer || getCustomerSession();
  const userId = customer?.user_id || null;
  const anonymousId = userId ? null : getAnonymousId();
  const identityKey = userId || anonymousId;
  const [cart, setCart] = useState(() => {
    const saved = localStorage.getItem('leadmagnet_user_cart');
    return saved ? JSON.parse(saved) : [];
  });

  useEffect(() => {
    localStorage.setItem('leadmagnet_user_cart', JSON.stringify(cart));
  }, [cart]);

  useEffect(() => {
    let active = true;
    const localCart = cart;

    const loadPersistedCart = async () => {
      try {
        const persistedCart = await fetchCart(userId, anonymousId);
        if (!active) return;

        if (persistedCart.length > 0 || userId) {
          setCart(persistedCart.map((item) => ({
            id: item.product_id,
            name: item.name,
            price: item.price,
            image: item.image,
            category: item.category,
            brand: item.brand,
            quantity: item.quantity,
            selectedSize: item.selectedSize || 'M',
            selectedColor: item.selectedColor || 'Standard',
          })));
          return;
        }

        if (localCart.length === 0) return;

        for (const item of localCart) {
          await addToCartApi(item.id, item.quantity, null, anonymousId, customer?.session_id);
        }
      } catch (error) {
        // Keep the local cart available when persistence is temporarily unavailable.
      }
    };

    loadPersistedCart();
    return () => {
      active = false;
    };
  }, [identityKey]);

  const restorePersistedCart = async () => {
    try {
      const persistedCart = await fetchCart(userId, anonymousId);
      setCart(persistedCart.map((item) => ({
        id: item.product_id,
        name: item.name,
        price: item.price,
        image: item.image,
        category: item.category,
        brand: item.brand,
        quantity: item.quantity,
        selectedSize: item.selectedSize || 'M',
        selectedColor: item.selectedColor || 'Standard',
      })));
    } catch (error) {
      // Preserve the optimistic local state when the backend is unavailable.
    }
  };

  const addToCart = (product, selectedSize, selectedColor, quantity = 1) => {
    const size = selectedSize || (product.sizes ? product.sizes[0] : 'M');
    const color = selectedColor || (product.colors ? product.colors[0] : 'Standard');

    setCart(prev => {
      const existingIndex = prev.findIndex(
        item => item.id === product.id && item.selectedSize === size && item.selectedColor === color
      );

      if (existingIndex > -1) {
        const updated = [...prev];
        updated[existingIndex].quantity += quantity;
        return updated;
      } else {
        return [...prev, { ...product, selectedSize: size, selectedColor: color, quantity }];
      }
    });

    addToCartApi(product.id, quantity, userId, anonymousId, customer?.session_id)
      .catch(restorePersistedCart);

    trackCustomerEvent('add_to_cart', {
      entity: {
        type: 'product',
        id: product.id,
        name: product.name,
        category: product.category,
        brand: product.brand,
        price: product.price,
      },
      metadata: { quantity, size, color },
    });

    confetti({
      particleCount: 40,
      spread: 60,
      origin: { y: 0.7 }
    });
  };

  const removeFromCart = (id, selectedSize, selectedColor) => {
    setCart(prev => prev.filter(
      item => !(item.id === id && item.selectedSize === selectedSize && item.selectedColor === selectedColor)
    ));
    removeFromCartApi(id, userId, anonymousId, customer?.session_id)
      .catch(restorePersistedCart);
  };

  const updateQuantity = (id, selectedSize, selectedColor, delta) => {
    const item = cart.find((entry) => (
      entry.id === id && entry.selectedSize === selectedSize && entry.selectedColor === selectedColor
    ));
    const nextQuantity = item ? item.quantity + delta : 0;
    setCart(prev => prev.map(item => {
      if (item.id === id && item.selectedSize === selectedSize && item.selectedColor === selectedColor) {
        const newQty = item.quantity + delta;
        return newQty > 0 ? { ...item, quantity: newQty } : item;
      }
      return item;
    }));
    if (nextQuantity > 0) {
      updateCartApi(id, nextQuantity, userId, anonymousId)
        .catch(restorePersistedCart);
    }
  };

  const clearCart = () => {
    setCart([]);
    clearCartApi(userId, anonymousId).catch(restorePersistedCart);
  };

  const totalItems = cart.reduce((sum, item) => sum + item.quantity, 0);
  const subtotal = cart.reduce((sum, item) => sum + (item.price * item.quantity), 0);
  const originalSubtotal = cart.reduce((sum, item) => sum + ((item.originalPrice || item.price) * item.quantity), 0);
  const discountAmount = originalSubtotal - subtotal;
  const deliveryFee = subtotal > 100 || cart.length === 0 ? 0 : 15;
  const totalPrice = subtotal + deliveryFee;

  return (
    <CartContext.Provider value={{
      cart,
      addToCart,
      removeFromCart,
      updateQuantity,
      clearCart,
      totalItems,
      subtotal,
      originalSubtotal,
      discountAmount,
      deliveryFee,
      totalPrice
    }}>
      {children}
    </CartContext.Provider>
  );
};

export const useCart = () => useContext(CartContext);
