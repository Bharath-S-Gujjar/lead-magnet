import React, { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Package, CheckCircle, ShoppingBag, ArrowLeft } from 'lucide-react';
import { useCart } from '../context/CartContext';
import { useAuth } from '../context/AuthContext';
import { fetchCustomerOrders, getCustomerSession, trackCustomerEvent } from '../services/api';

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
      <div className="glass-card" style={{ padding: '60px 24px', textAlign: 'center', maxWidth: '600px', margin: '40px auto' }}>
        <Package size={54} style={{ color: 'var(--text-muted)', marginBottom: '16px' }} />
        <h3 className="heading-lg" style={{ color: 'var(--text-primary)', marginBottom: '8px' }}>Your Orders is Empty</h3>
        <p className="text-subtle" style={{ marginBottom: '24px' }}>Looks like you haven't placed any clothing orders yet.</p>
        <Link to="/" className="btn btn-primary">
          <ArrowLeft size={16} /> Explore Clothing Collection
        </Link>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <div>
        <h2 className="heading-xl" style={{ color: 'var(--text-primary)' }}>
          My Clothing Orders & Purchases
        </h2>
        <p className="text-subtle">Review your order history, track shipments, and easily reorder your favorite clothing items.</p>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
        {orders.map(order => {
          const firstItem = order.items?.[0];
          const totalQuantity = order.items?.reduce((sum, item) => sum + (item.quantity || 1), 0) || 1;

          return (
            <div key={order._id} className="glass-card" style={{ padding: '24px', display: 'flex', alignItems: 'center', gap: '24px' }}>
              {firstItem?.image && (
                <img 
                  src={firstItem.image} 
                  alt={firstItem.name || 'Order Item'} 
                  style={{ width: '90px', height: '110px', borderRadius: 'var(--radius-md)', objectFit: 'cover' }}
                />
              )}

              <div style={{ flex: 1 }}>
                <div style={{ display: 'flex', gap: '12px', alignItems: 'center', marginBottom: '6px' }}>
                  <span className="badge badge-indigo">
                    {order._id}
                  </span>
                  <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                    Ordered on {new Date(order.created_at).toLocaleDateString('en-IN')}
                  </span>
                </div>

                <h4 style={{ fontWeight: 700, fontSize: '1.05rem', color: 'var(--text-primary)', marginBottom: '4px' }}>
                  {firstItem?.name || 'Clothing Item'}
                </h4>
                <span style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
                  Brand: <strong>{firstItem?.brand || 'Lead Magnet'}</strong> • Qty: {totalQuantity}
                </span>
              </div>

              <div style={{ textAlign: 'right' }}>
                <div style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '6px',
                  fontSize: '0.82rem',
                  fontWeight: 700,
                  color: '#10b981',
                  marginBottom: '8px'
                }}>
                  <CheckCircle size={15} /> {order.status || 'placed'}
                </div>
                <div style={{ fontFamily: 'var(--font-heading)', fontWeight: 800, fontSize: '1.2rem', color: 'var(--text-primary)' }}>
                  ₹{(order.total_amount || 0).toLocaleString('en-IN')}
                </div>
              </div>

              {firstItem && (
                <button 
                  onClick={() => handleBuyAgain({ ...firstItem, id: firstItem.product_id })}
                  className="btn btn-primary"
                  style={{ padding: '10px 18px', fontSize: '0.85rem' }}
                >
                  <ShoppingBag size={16} /> Buy Again
                </button>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
