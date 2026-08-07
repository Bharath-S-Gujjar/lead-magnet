import React, { createContext, useContext, useState, useEffect } from 'react';
import confetti from 'canvas-confetti';

const CartContext = createContext();

export const CartProvider = ({ children }) => {
  const [cart, setCart] = useState(() => {
    const saved = localStorage.getItem('leadmagnet_user_cart');
    return saved ? JSON.parse(saved) : [];
  });

  useEffect(() => {
    localStorage.setItem('leadmagnet_user_cart', JSON.stringify(cart));
  }, [cart]);

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
  };

  const updateQuantity = (id, selectedSize, selectedColor, delta) => {
    setCart(prev => prev.map(item => {
      if (item.id === id && item.selectedSize === selectedSize && item.selectedColor === selectedColor) {
        const newQty = item.quantity + delta;
        return newQty > 0 ? { ...item, quantity: newQty } : item;
      }
      return item;
    }));
  };

  const clearCart = () => {
    setCart([]);
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
