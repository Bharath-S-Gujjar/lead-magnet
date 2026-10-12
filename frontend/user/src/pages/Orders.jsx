import React, { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useCart } from '../context/CartContext';
import { useAuth } from '../context/AuthContext';
import { fetchCustomerOrders, getCustomerSession, trackCustomerEvent } from '../services/api';
import { getOptimizedImageUrl } from '../utils/imageOptimizer';

export const Orders = () => {
  const navigate = useNavigate();
  const { addToCart } = useCart();
  const { customer: authCustomer } = useAuth();
  const customer = authCustomer || getCustomerSession();
  const [orders, setOrders] = useState([]);

  useEffect(() => {
    trackCustomerEvent('page_view', { page: '/orders' });
    const email = customer?.email || getCustomerSession()?.email;
    fetchCustomerOrders(email)
      .then(setOrders)
      .catch(() => setOrders([]));
  }, [customer?.email]);

  const handleBuyAgain = (product) => {
    if (product) {
      addToCart(product);
      navigate('/cart');
    }
  };

  if (!orders || orders.length === 0) {
    return (
      <div className="product-card" style={{ padding: '48px 24px', textAlign: 'center', maxWidth: '540px', margin: '40px auto' }}>
        <h3 style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '8px' }}>
          Your Orders List is Empty
        </h3>
        <p style={{ color: 'var(--text-secondary)', marginBottom: '20px', fontSize: '0.9rem' }}>
          Looks like you have not placed any clothing orders yet.
        </p>
        <Link to="/" className="btn btn-primary">
          Explore Clothing Collection
        </Link>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <div>
        <h2 style={{ fontSize: '1.4rem', fontWeight: 700, color: 'var(--text-primary)' }}>
          My Clothing Orders & Purchases
        </h2>
        <p style={{ color: 'var(--text-secondary)', fontSize: '0.88rem', marginTop: '4px' }}>
          Review your order history, track shipments, and reorder items.
        </p>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
        {orders.map(order => {
          const firstItem = order.items?.[0];
          const totalQuantity = order.items?.reduce((sum, item) => sum + (item.quantity || 1), 0) || 1;

          return (
            <div key={order._id} className="product-card" style={{ padding: '18px', display: 'flex', alignItems: 'center', gap: '20px' }}>
              {firstItem?.image && (
                <img
                  src={getOptimizedImageUrl(firstItem.image, 200, 70)}
                  alt={firstItem.name || 'Order Item'}
                  loading="lazy"
                  decoding="async"
                  style={{ width: '80px', height: '95px', borderRadius: 'var(--radius-sm, 4px)', objectFit: 'cover' }}
                />
              )}

              <div style={{ flex: 1 }}>
                <div style={{ display: 'flex', gap: '10px', alignItems: 'center', marginBottom: '4px' }}>
                  <span className="badge badge-primary">
                    {order._id}
                  </span>
                  <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                    Ordered on {new Date(order.created_at).toLocaleDateString('en-IN')}
                  </span>
                </div>

                <h4 style={{ fontWeight: 600, fontSize: '0.98rem', color: 'var(--text-primary)', marginBottom: '4px' }}>
                  {firstItem?.name || 'Clothing Item'}
                </h4>
                <span style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
                  Brand: <strong>{firstItem?.brand || 'Lead Magnet'}</strong> - Qty: {totalQuantity}
                </span>
              </div>

              <div style={{ textAlign: 'right' }}>
                <div style={{ marginBottom: '6px' }}>
                  <span style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '4px',
                    fontSize: '0.72rem',
                    fontWeight: 700,
                    textTransform: 'uppercase',
                    letterSpacing: '0.04em',
                    padding: '2px 8px',
                    borderRadius: '4px',
                    background: (order.status === 'delivered')
                      ? 'var(--color-primary-light, rgba(156, 175, 136, 0.15))'
                      : (order.status === 'shipped')
                      ? 'var(--color-secondary-light, rgba(167, 167, 167, 0.18))'
                      : 'var(--color-tertiary-light, rgba(204, 85, 0, 0.12))',
                    color: (order.status === 'delivered')
                      ? 'var(--color-primary-dark, #6f805e)'
                      : (order.status === 'shipped')
                      ? 'var(--text-primary)'
                      : 'var(--color-tertiary, #CC5500)',
                    border: `1px solid ${(order.status === 'delivered') ? 'var(--color-primary, #9CAF88)' : (order.status === 'shipped') ? 'var(--color-secondary, #A7A7A7)' : 'rgba(204, 85, 0, 0.3)'}`
                  }}>
                    ● {order.status || 'placed'}
                  </span>
                </div>
                <div style={{ fontWeight: 700, fontSize: '1.15rem', color: 'var(--text-primary)' }}>
                  ₹{(order.total_amount || 0).toLocaleString('en-IN')}
                </div>
              </div>

              <div>
                <button
                  onClick={() => handleBuyAgain(firstItem)}
                  className="btn btn-secondary"
                  style={{ padding: '8px 16px', fontSize: '0.82rem' }}
                >
                  Buy Again
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default Orders;
