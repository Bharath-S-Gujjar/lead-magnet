import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Trash2, ShoppingBag, ArrowLeft, ShieldCheck, Tag, Check } from 'lucide-react';
import { useCart } from '../context/CartContext';
import confetti from 'canvas-confetti';

export const Cart = () => {
  const { 
    cart, 
    removeFromCart, 
    updateQuantity, 
    clearCart, 
    subtotal, 
    originalSubtotal, 
    discountAmount, 
    deliveryFee, 
    totalPrice 
  } = useCart();
  
  const navigate = useNavigate();
  const [couponCode, setCouponCode] = useState('');
  const [couponApplied, setCouponApplied] = useState(false);
  const [orderPlaced, setOrderPlaced] = useState(false);

  const handleApplyCoupon = (e) => {
    e.preventDefault();
    if (couponCode.toUpperCase() === 'LEAD40') {
      setCouponApplied(true);
    }
  };

  const handleCheckout = () => {
    confetti({
      particleCount: 100,
      spread: 70,
      origin: { y: 0.6 }
    });
    setOrderPlaced(true);
    setTimeout(() => {
      clearCart();
    }, 1500);
  };

  if (orderPlaced) {
    return (
      <div className="glass-card" style={{ padding: '60px', textAlign: 'center', maxWidth: '600px', margin: '40px auto' }}>
        <div style={{
          width: '64px',
          height: '64px',
          borderRadius: '50%',
          background: 'rgba(16, 185, 129, 0.15)',
          color: '#10b981',
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          marginBottom: '20px'
        }}>
          <Check size={36} strokeWidth={3} />
        </div>
        <h3 className="heading-xl" style={{ color: 'var(--text-primary)', marginBottom: '10px' }}>
          Clothing Order Confirmed!
        </h3>
        <p className="text-subtle" style={{ marginBottom: '24px' }}>
          Thank you for shopping at Lead Magnet. Your clothing items are being packed for express delivery!
        </p>
        <button onClick={() => navigate('/orders')} className="btn btn-primary">
          View My Orders
        </button>
      </div>
    );
  }

  if (cart.length === 0) {
    return (
      <div className="glass-card" style={{ padding: '60px 24px', textAlign: 'center', maxWidth: '600px', margin: '40px auto' }}>
        <ShoppingBag size={54} style={{ color: 'var(--text-muted)', marginBottom: '16px' }} />
        <h3 className="heading-lg" style={{ color: 'var(--text-primary)', marginBottom: '8px' }}>Your Cart is Empty</h3>
        <p className="text-subtle" style={{ marginBottom: '24px' }}>Looks like you haven't added any clothing items to your shopping cart yet.</p>
        <Link to="/" className="btn btn-primary">
          <ArrowLeft size={16} /> Explore Clothing Collection
        </Link>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2 className="heading-xl" style={{ color: 'var(--text-primary)' }}>
          Shopping Cart ({cart.length} items)
        </h2>
        <button onClick={clearCart} className="btn btn-ghost" style={{ fontSize: '0.82rem', color: 'var(--accent-rose)' }}>
          Clear All
        </button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 380px', gap: '32px', alignItems: 'start' }}>
        {/* Left Side: Cart Item List */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {cart.map((item, idx) => (
            <div 
              key={`${item.id}-${item.selectedSize}-${item.selectedColor}-${idx}`}
              className="glass-card"
              style={{ padding: '20px', display: 'flex', alignItems: 'center', gap: '20px' }}
            >
              {/* Product Image */}
              <img 
                src={item.image} 
                alt={item.name} 
                style={{ width: '90px', height: '105px', borderRadius: 'var(--radius-md)', objectFit: 'cover' }}
              />

              {/* Product Info */}
              <div style={{ flex: 1 }}>
                <span style={{ fontSize: '0.75rem', fontWeight: 800, color: 'var(--accent-indigo)', textTransform: 'uppercase' }}>
                  {item.brand}
                </span>
                <h4 style={{ fontWeight: 700, fontSize: '1rem', color: 'var(--text-primary)', margin: '2px 0 6px' }}>
                  {item.name}
                </h4>
                <div style={{ display: 'flex', gap: '8px', fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                  <span>Size: <strong>{item.selectedSize}</strong></span>
                  <span>•</span>
                  <span>Color: <strong>{item.selectedColor}</strong></span>
                </div>
              </div>

              {/* Quantity Controls */}
              <div style={{
                display: 'flex',
                alignItems: 'center',
                border: '1px solid var(--panel-border)',
                borderRadius: 'var(--radius-md)',
                background: 'var(--panel-solid)'
              }}>
                <button 
                  onClick={() => updateQuantity(item.id, item.selectedSize, item.selectedColor, -1)}
                  style={{ width: '32px', height: '36px', border: 'none', background: 'transparent', cursor: 'pointer', fontWeight: 800 }}
                >
                  -
                </button>
                <span style={{ width: '32px', textAlign: 'center', fontWeight: 800, fontSize: '0.85rem' }}>
                  {item.quantity}
                </span>
                <button 
                  onClick={() => updateQuantity(item.id, item.selectedSize, item.selectedColor, 1)}
                  style={{ width: '32px', height: '36px', border: 'none', background: 'transparent', cursor: 'pointer', fontWeight: 800 }}
                >
                  +
                </button>
              </div>

              {/* Item Price Total */}
              <div style={{ textAlign: 'right', minWidth: '90px' }}>
                <div style={{ fontFamily: 'var(--font-heading)', fontWeight: 800, fontSize: '1.1rem', color: 'var(--text-primary)' }}>
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
                style={{ padding: '8px', color: 'var(--text-muted)' }}
                title="Remove item"
              >
                <Trash2 size={18} />
              </button>
            </div>
          ))}
        </div>

        {/* Right Side: Order Summary */}
        <div className="glass-card" style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <h3 className="heading-md" style={{ color: 'var(--text-primary)' }}>Order Summary</h3>

          {/* Coupon Code Input */}
          <form onSubmit={handleApplyCoupon} style={{ display: 'flex', gap: '8px' }}>
            <input 
              type="text" 
              placeholder="Coupon Code (e.g. LEAD40)" 
              value={couponCode} 
              onChange={(e) => setCouponCode(e.target.value)}
              style={{
                flex: 1,
                padding: '9px 12px',
                borderRadius: 'var(--radius-md)',
                border: '1px solid var(--panel-border)',
                background: 'var(--panel-solid)',
                fontSize: '0.82rem',
                outline: 'none'
              }}
            />
            <button type="submit" className="btn btn-secondary" style={{ padding: '9px 14px', fontSize: '0.82rem' }}>
              Apply
            </button>
          </form>

          {couponApplied && (
            <div style={{ fontSize: '0.78rem', color: 'var(--accent-emerald)', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '4px' }}>
              <Tag size={13} /> Coupon LEAD40 Applied (Extra 10% Off)
            </div>
          )}

          {/* Price Calculations */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', fontSize: '0.88rem', color: 'var(--text-secondary)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span>Subtotal</span>
              <span style={{ fontWeight: 700, color: 'var(--text-primary)' }}>₹{subtotal.toLocaleString('en-IN')}</span>
            </div>

            {discountAmount > 0 && (
              <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--accent-emerald)' }}>
                <span>Discount Savings</span>
                <span style={{ fontWeight: 700 }}>-₹{discountAmount.toLocaleString('en-IN')}</span>
              </div>
            )}

            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span>Estimated Delivery</span>
              <span style={{ fontWeight: 700, color: deliveryFee === 0 ? 'var(--accent-emerald)' : 'var(--text-primary)' }}>
                {deliveryFee === 0 ? 'FREE' : `₹${deliveryFee.toLocaleString('en-IN')}`}
              </span>
            </div>

            <div style={{
              display: 'flex',
              justify: 'space-between',
              paddingTop: '12px',
              borderTop: '1px solid var(--panel-border)',
              fontSize: '1.15rem',
              fontWeight: 800,
              color: 'var(--text-primary)'
            }}>
              <span>Grand Total</span>
              <span style={{ color: 'var(--accent-indigo)' }}>
                ₹{Math.round(couponApplied ? totalPrice * 0.9 : totalPrice).toLocaleString('en-IN')}
              </span>
            </div>
          </div>

          <button 
            onClick={handleCheckout}
            className="btn btn-primary" 
            style={{ width: '100%', padding: '14px', fontSize: '1rem' }}
          >
            <ShieldCheck size={18} /> Proceed to Secure Checkout
          </button>
        </div>
      </div>
    </div>
  );
};
