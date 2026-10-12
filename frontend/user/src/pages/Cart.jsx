import React, { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useCart } from '../context/CartContext';
import { useAuth } from '../context/AuthContext';
import { createOrder, getCustomerSession, trackCustomerEvent } from '../services/api';
import { getOptimizedImageUrl } from '../utils/imageOptimizer';

export const Cart = () => {
  const {
    cart,
    removeFromCart,
    updateQuantity,
    clearCart,
    removeOrderedItems,
    subtotal: cartSubtotal,
    discountAmount: cartDiscount,
    deliveryFee: cartDeliveryFee,
    totalPrice: cartTotalPrice
  } = useCart();
  const { customer: authCustomer } = useAuth();
  const customer = authCustomer || getCustomerSession();

  const navigate = useNavigate();
  const [selectedIds, setSelectedIds] = useState(() => new Set(cart.map((i) => `${i.id}-${i.selectedSize}-${i.selectedColor}`)));
  const [couponCode, setCouponCode] = useState('');
  const [couponApplied, setCouponApplied] = useState(false);
  const [orderPlaced, setOrderPlaced] = useState(false);
  const [checkoutError, setCheckoutError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    trackCustomerEvent('page_view', { page: '/cart' });
  }, []);

  // Sync selectedIds if new items are added to cart
  useEffect(() => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      cart.forEach(item => {
        const key = `${item.id}-${item.selectedSize}-${item.selectedColor}`;
        if (!prev.has(key) && prev.size === 0) {
          next.add(key);
        }
      });
      return next.size > 0 ? next : new Set(cart.map(i => `${i.id}-${i.selectedSize}-${i.selectedColor}`));
    });
  }, [cart.length]);

  const toggleSelectItem = (key) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (selectedIds.size === cart.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(cart.map(i => `${i.id}-${i.selectedSize}-${i.selectedColor}`)));
    }
  };

  const selectedItems = cart.filter(item => selectedIds.has(`${item.id}-${item.selectedSize}-${item.selectedColor}`));
  const subtotal = selectedItems.reduce((sum, item) => sum + (item.price * item.quantity), 0);
  const originalSubtotal = selectedItems.reduce((sum, item) => sum + ((item.originalPrice || item.price) * item.quantity), 0);
  const discountAmount = originalSubtotal - subtotal;
  const deliveryFee = subtotal > 100 || selectedItems.length === 0 ? 0 : 15;
  const totalPrice = subtotal + deliveryFee;

  const handleApplyCoupon = (e) => {
    e.preventDefault();
    if (couponCode.toUpperCase() === 'LEAD40') {
      setCouponApplied(true);
    }
  };

  const handleCheckout = async () => {
    if (isSubmitting) return;
    setCheckoutError('');

    if (selectedItems.length === 0) {
      setCheckoutError('Please select at least one item to proceed with checkout.');
      return;
    }

    if (!customer?.email) {
      setCheckoutError('Please log in before placing an order.');
      navigate('/login');
      return;
    }

    setIsSubmitting(true);
    const customerSession = getCustomerSession();

    try {
      await createOrder({
        session_id: customerSession?.session_id,
        items: selectedItems.map(item => ({
          product_id: item.id,
          quantity: item.quantity,
          price: item.price,
          name: item.name,
          category: item.category,
          brand: item.brand,
          image: item.image,
        })),
      });

      // Remove only the items that were ordered; preserve unselected cart items
      if (removeOrderedItems) {
        removeOrderedItems(selectedItems.map(i => i.id));
      } else {
        selectedItems.forEach(i => removeFromCart(i.id, i.selectedSize, i.selectedColor));
      }

      setOrderPlaced(true);
      navigate('/orders');
    } catch (error) {
      // Failed checkout preserves cart state without discarding items
      setCheckoutError(error.message || 'Failed to place order. Your cart items are preserved.');
    } finally {
      setIsSubmitting(false);
    }
  };

  if (orderPlaced) {
    return (
      <div className="product-card" style={{ padding: '48px 24px', textAlign: 'center', maxWidth: '540px', margin: '40px auto' }}>
        <h3 style={{ fontSize: '1.4rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '8px' }}>
          Clothing Order Confirmed
        </h3>
        <p style={{ color: 'var(--text-secondary)', marginBottom: '20px', fontSize: '0.9rem' }}>
          Thank you for shopping at Lead Magnet. Your clothing items are being prepared for delivery.
        </p>
        <button onClick={() => navigate('/orders')} className="btn btn-primary">
          View My Orders
        </button>
      </div>
    );
  }

  if (cart.length === 0) {
    return (
      <div className="product-card" style={{ padding: '48px 24px', textAlign: 'center', maxWidth: '540px', margin: '40px auto' }}>
        <h3 style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '8px' }}>
          Your Cart is Empty
        </h3>
        <p style={{ color: 'var(--text-secondary)', marginBottom: '20px', fontSize: '0.9rem' }}>
          Looks like you have not added any clothing items to your shopping cart yet.
        </p>
        <Link to="/" className="btn btn-primary">
          Explore Clothing Collection
        </Link>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2 style={{ fontSize: '1.4rem', fontWeight: 700, color: 'var(--text-primary)' }}>
          Shopping Cart ({cart.length} items)
        </h2>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <button onClick={toggleSelectAll} className="btn btn-ghost" style={{ fontSize: '0.82rem' }}>
            {selectedIds.size === cart.length ? 'Deselect All' : 'Select All'}
          </button>
          <button onClick={clearCart} className="btn btn-ghost" style={{ fontSize: '0.82rem', color: 'var(--color-tertiary, #CC5500)' }}>
            Clear All
          </button>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 360px', gap: '24px', alignItems: 'start' }}>
        {/* Left Side: Cart Item List */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          {cart.map((item, idx) => {
            const itemKey = `${item.id}-${item.selectedSize}-${item.selectedColor}`;
            const isSelected = selectedIds.has(itemKey);
            return (
            <div
              key={`${item.id}-${item.selectedSize}-${item.selectedColor}-${idx}`}
              className="product-card"
              style={{
                padding: '16px',
                display: 'flex',
                alignItems: 'center',
                gap: '16px',
                borderLeft: isSelected ? '3px solid var(--color-primary, #9CAF88)' : '3px solid transparent'
              }}
            >
              {/* Checkbox for Selective Checkout */}
              <input
                type="checkbox"
                checked={isSelected}
                onChange={() => toggleSelectItem(itemKey)}
                style={{ width: '18px', height: '18px', cursor: 'pointer', accentColor: 'var(--color-primary, #9CAF88)' }}
                title="Select item for checkout"
                aria-label={`Select ${item.name}`}
              />

              {/* Product Image */}
              <img
                src={getOptimizedImageUrl(item.image, 200, 70)}
                alt={item.name}
                loading="lazy"
                decoding="async"
                style={{ width: '80px', height: '95px', borderRadius: 'var(--radius-sm, 4px)', objectFit: 'cover' }}
              />

              {/* Product Info */}
              <div style={{ flex: 1 }}>
                <span style={{ fontSize: '0.72rem', fontWeight: 700, color: 'var(--color-primary-dark, #6f805e)', textTransform: 'uppercase' }}>
                  {item.brand}
                </span>
                <h4 style={{ fontWeight: 600, fontSize: '0.95rem', color: 'var(--text-primary)', margin: '2px 0 4px' }}>
                  {item.name}
                </h4>
                <div style={{ display: 'flex', gap: '8px', fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                  <span>Size: <strong>{item.selectedSize}</strong></span>
                  <span>-</span>
                  <span>Color: <strong>{item.selectedColor}</strong></span>
                </div>
              </div>

              {/* Quantity Controls */}
              <div style={{
                display: 'flex',
                alignItems: 'center',
                border: '1px solid var(--panel-border)',
                borderRadius: 'var(--radius-sm, 4px)',
                background: 'var(--panel-solid)'
              }}>
                <button
                  onClick={() => updateQuantity(item.id, item.selectedSize, item.selectedColor, -1)}
                  style={{ width: '28px', height: '32px', border: 'none', background: 'transparent', cursor: 'pointer', fontWeight: 700 }}
                >
                  -
                </button>
                <span style={{ width: '28px', textAlign: 'center', fontWeight: 600, fontSize: '0.85rem' }}>
                  {item.quantity}
                </span>
                <button
                  onClick={() => updateQuantity(item.id, item.selectedSize, item.selectedColor, 1)}
                  style={{ width: '28px', height: '32px', border: 'none', background: 'transparent', cursor: 'pointer', fontWeight: 700 }}
                >
                  +
                </button>
              </div>

              {/* Item Price Total */}
              <div style={{ textAlign: 'right', minWidth: '80px' }}>
                <div style={{ fontWeight: 700, fontSize: '1rem', color: 'var(--text-primary)' }}>
                  ₹{(item.price * item.quantity).toLocaleString('en-IN')}
                </div>
                {item.originalPrice && (
                  <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', textDecoration: 'line-through' }}>
                    ₹{(item.originalPrice * item.quantity).toLocaleString('en-IN')}
                  </div>
                )}
              </div>

              {/* Remove Button */}
              <button
                onClick={() => removeFromCart(item.id, item.selectedSize, item.selectedColor)}
                className="btn btn-ghost"
                style={{ padding: '6px 8px', color: 'var(--text-muted)' }}
                title="Remove item"
                aria-label="Remove item"
              >
                ✕
              </button>
            </div>
            );
          })}
        </div>

        {/* Right Side: Order Summary */}
        <div className="product-card" style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <h3 style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--text-primary)' }}>Order Summary</h3>

          {/* Coupon Code Input */}
          <form onSubmit={handleApplyCoupon} style={{ display: 'flex', gap: '6px' }}>
            <input
              type="text"
              placeholder="Coupon (e.g. LEAD40)"
              value={couponCode}
              onChange={(e) => setCouponCode(e.target.value)}
              style={{
                flex: 1,
                padding: '8px 10px',
                borderRadius: 'var(--radius-sm, 4px)',
                border: '1px solid var(--panel-border)',
                background: 'var(--panel-solid)',
                fontSize: '0.82rem',
                outline: 'none'
              }}
            />
            <button type="submit" className="btn btn-secondary" style={{ padding: '8px 12px', fontSize: '0.82rem' }}>
              Apply
            </button>
          </form>

          {couponApplied && (
            <div style={{ fontSize: '0.78rem', color: 'var(--color-primary-dark, #6f805e)', fontWeight: 600 }}>
              Coupon LEAD40 Applied (Extra 10% Off)
            </div>
          )}

          {checkoutError ? <div className="error-text">{checkoutError}</div> : null}

          {/* Price Calculations */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span>Subtotal</span>
              <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>₹{subtotal.toLocaleString('en-IN')}</span>
            </div>

            {discountAmount > 0 && (
              <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--color-tertiary, #CC5500)' }}>
                <span>Discount Savings</span>
                <span style={{ fontWeight: 700 }}>-₹{discountAmount.toLocaleString('en-IN')}</span>
              </div>
            )}

            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span>Estimated Delivery</span>
              <span style={{ fontWeight: 700, color: deliveryFee === 0 ? 'var(--color-primary-dark, #6f805e)' : 'var(--text-primary)' }}>
                {deliveryFee === 0 ? 'FREE' : `₹${deliveryFee.toLocaleString('en-IN')}`}
              </span>
            </div>

            <div style={{
              display: 'flex',
              justifyContent: 'space-between',
              paddingTop: '10px',
              borderTop: '1px solid var(--panel-border)',
              fontSize: '1.15rem',
              fontWeight: 700,
              color: 'var(--text-primary)'
            }}>
              <span>Grand Total</span>
              <span style={{ color: 'var(--color-tertiary, #CC5500)' }}>
                ₹{Math.round(couponApplied ? totalPrice * 0.9 : totalPrice).toLocaleString('en-IN')}
              </span>
            </div>
          </div>

          <button
            onClick={handleCheckout}
            disabled={isSubmitting || selectedItems.length === 0}
            className="btn btn-primary"
            style={{
              width: '100%',
              padding: '12px',
              fontSize: '0.92rem',
              opacity: (isSubmitting || selectedItems.length === 0) ? 0.6 : 1,
              cursor: (isSubmitting || selectedItems.length === 0) ? 'not-allowed' : 'pointer'
            }}
          >
            {isSubmitting
              ? 'Placing Order...'
              : selectedItems.length === 0
              ? 'Select Items to Checkout'
              : `Proceed to Checkout (${selectedItems.length})`}
          </button>
        </div>
      </div>
    </div>
  );
};

export default Cart;
