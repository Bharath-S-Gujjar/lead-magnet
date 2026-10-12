import React, { useState, useEffect } from 'react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Cell } from 'recharts';
import { getOptimizedImageUrl } from '../../utils/imageOptimizer';

function formatDate(value) {
  if (!value) return 'No orders';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'No orders';
  return date.toLocaleDateString('en-IN', { month: 'short', day: '2-digit', year: 'numeric' });
}

export const CustomerDetailDrawer = ({ customer: incomingCustomer, isOpen, onClose }) => {
  const [shouldRender, setShouldRender] = useState(isOpen);
  const [isSlideOpen, setIsSlideOpen] = useState(false);
  const [cachedCustomer, setCachedCustomer] = useState(incomingCustomer);

  useEffect(() => {
    if (incomingCustomer) {
      setCachedCustomer(incomingCustomer);
    }
  }, [incomingCustomer]);

  // Manage mounting for smooth slide-in / slide-out CSS transitions
  useEffect(() => {
    let timer;
    let animId;
    if (isOpen) {
      setShouldRender(true);
      animId = requestAnimationFrame(() => {
        animId = requestAnimationFrame(() => {
          setIsSlideOpen(true);
        });
      });
    } else {
      setIsSlideOpen(false);
      timer = setTimeout(() => {
        setShouldRender(false);
      }, 450);
    }
    return () => {
      if (animId) cancelAnimationFrame(animId);
      if (timer) clearTimeout(timer);
    };
  }, [isOpen]);

  // Lock background body scrolling and listen for Escape key while drawer is open
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') onClose?.();
    };
    const originalOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      document.body.style.overflow = originalOverflow;
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen, onClose]);

  const customer = incomingCustomer || cachedCustomer;
  if (!shouldRender && !isOpen) return null;
  if (!customer) return null;

  // Session math for Time Spent analysis
  const sessionMinutes = (customer.sessions || []).map(s => s.minutes || 0);
  const avgTime = sessionMinutes.length ? (sessionMinutes.reduce((a, b) => a + b, 0) / sessionMinutes.length).toFixed(1) : '0.0';
  const longestVisit = sessionMinutes.length ? Math.max(...sessionMinutes) : 0;
  const shortestVisit = sessionMinutes.length ? Math.min(...sessionMinutes) : 0;

  const CustomSessionTooltip = ({ active, payload }) => {
    if (active && payload && payload.length) {
      const item = payload[0].payload;
      return (
        <div style={{
          background: 'var(--panel-solid)',
          border: '1px solid var(--panel-border)',
          padding: '12px 16px',
          borderRadius: '4px',
          fontSize: '0.82rem',
          color: 'var(--text-primary)',
          maxWidth: '260px'
        }}>
          <div style={{ fontWeight: 800, color: 'var(--brand-tertiary)', marginBottom: '4px' }}>{item.date}</div>
          <div><strong>Minutes Spent:</strong> {item.minutes} mins</div>
          <div><strong>Pages Visited:</strong> {item.pagesVisited} pages</div>
          <div style={{ marginTop: '4px', color: 'var(--brand-primary)', fontWeight: 700 }}>
            <strong>Outcome:</strong> {item.outcome}
          </div>
        </div>
      );
    }
    return null;
  };

  return (
    <>
      {/* Background Overlay */}
      <div
        className={`drawer-overlay ${isSlideOpen ? 'open' : ''}`}
        onClick={onClose}
      />

      {/* Slide-out Drawer Panel */}
      <div className={`drawer-panel ${isSlideOpen ? 'open' : ''}`}>
        {/* Top Header */}
        <div style={{
          padding: '20px 28px',
          borderBottom: '1px solid var(--panel-border)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          background: 'var(--panel-solid)',
          flexShrink: 0
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
            <img
              src={customer.avatar}
              alt={customer.name}
              loading="lazy"
              decoding="async"
              style={{ width: '48px', height: '48px', borderRadius: '4px', objectFit: 'cover', border: '1px solid var(--panel-border)' }}
            />
            <div>
              <h2 className="heading-lg" style={{ color: 'var(--text-primary)' }}>{customer.name}</h2>
              <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', display: 'flex', gap: '10px', marginTop: '2px' }}>
                <span>ID: {customer.id}</span>
                <span>•</span>
                <span>{customer.gender}{customer.age && customer.age !== '-' ? `, ${customer.age} yrs` : ''}</span>
                <span>•</span>
                <span className="badge badge-primary">{customer.psychographic}</span>
              </div>
            </div>
          </div>

          <button
            onClick={onClose}
            className="btn btn-secondary"
            style={{ padding: '6px 12px', borderRadius: '4px' }}
            aria-label="Close drawer"
          >
            ✕
          </button>
        </div>

        {/* Scrollable Content */}
        <div className="drawer-content" style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '24px' }}>

          {/* SECTION 1: Customer Profile Header */}
          <div style={{ padding: '20px', background: 'var(--bg-app)', border: '1px solid var(--panel-border)', borderRadius: '4px' }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))', gap: '16px', textAlign: 'center' }}>
              <div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 600 }}>Customer ID</div>
                <div style={{ fontSize: '1rem', fontWeight: 800, color: 'var(--brand-tertiary)', marginTop: '2px' }}>{customer.id}</div>
              </div>
              <div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 600 }}>Gender & Age</div>
                <div style={{ fontSize: '1rem', fontWeight: 800, color: 'var(--text-primary)', marginTop: '2px' }}>
                  {customer.gender}{customer.age && customer.age !== '-' ? `, ${customer.age}` : ''}
                </div>
              </div>
              <div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 600 }}>Total Orders</div>
                <div style={{ fontSize: '1rem', fontWeight: 800, color: 'var(--text-primary)', marginTop: '2px' }}>
                  {customer.order_count ?? customer.orders ?? 0} Orders
                </div>
              </div>
              <div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 600 }}>Total Spent</div>
                <div style={{ fontSize: '1rem', fontWeight: 800, color: 'var(--brand-primary)', marginTop: '2px' }}>
                  ₹{(customer.total_spent || 0).toLocaleString('en-IN')}
                </div>
              </div>
              <div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 600 }}>Last Order Date</div>
                <div style={{ fontSize: '0.95rem', fontWeight: 800, color: 'var(--text-primary)', marginTop: '2px' }}>
                  {formatDate(customer.last_order_at)}
                </div>
              </div>
            </div>
          </div>

          {/* SECTION 2: Time Spent Analysis */}
          <div style={{ padding: '20px', background: 'var(--panel-solid)', border: '1px solid var(--panel-border)', borderRadius: '4px' }}>
            <div style={{ marginBottom: '16px' }}>
              <h3 className="heading-md" style={{ color: 'var(--text-primary)' }}>
                Time Spent Analysis
              </h3>
              <p className="text-subtle">Browsing session duration and engagement history</p>
            </div>

            {/* Session Bar Chart */}
            <div style={{ width: '100%', height: '200px' }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={customer.sessions} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--table-border)" vertical={false} />
                  <XAxis dataKey="date" stroke="var(--text-muted)" fontSize={11} tickLine={false} />
                  <YAxis stroke="var(--text-muted)" fontSize={11} tickLine={false} unit="m" />
                  <Tooltip content={<CustomSessionTooltip />} />
                  <Bar dataKey="minutes" radius={[2, 2, 0, 0]}>
                    {(customer.sessions || []).map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={index === customer.sessions.length - 1 ? '#9CAF88' : '#A7A7A7'} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>

            {/* Summary Row Below Graph */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '16px', marginTop: '16px', borderTop: '1px solid var(--panel-border)', paddingTop: '14px', textAlign: 'center' }}>
              <div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 600 }}>Average Time</div>
                <div style={{ fontSize: '1.1rem', fontWeight: 800, color: 'var(--text-primary)' }}>{avgTime} mins</div>
              </div>
              <div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 600 }}>Longest Visit</div>
                <div style={{ fontSize: '1.1rem', fontWeight: 800, color: 'var(--brand-tertiary)' }}>{longestVisit} mins</div>
              </div>
              <div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 600 }}>Shortest Visit</div>
                <div style={{ fontSize: '1.1rem', fontWeight: 800, color: 'var(--text-secondary)' }}>{shortestVisit} mins</div>
              </div>
            </div>
          </div>

          {/* SECTION 3: Interest History */}
          <div style={{ padding: '20px', background: 'var(--panel-solid)', border: '1px solid var(--panel-border)', borderRadius: '4px' }}>
            <div style={{ marginBottom: '14px' }}>
              <h3 className="heading-md" style={{ color: 'var(--text-primary)' }}>
                Interest History Timeline
              </h3>
              <p className="text-subtle">Sequential timeline of clothing product interactions</p>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {(customer.interestHistory || []).map((item, idx) => (
                <div
                  key={idx}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '10px 14px',
                    borderRadius: '4px',
                    background: 'var(--bg-app)',
                    border: '1px solid var(--panel-border)'
                  }}
                >
                  <div>
                    <div style={{ fontWeight: 700, fontSize: '0.88rem', color: 'var(--text-primary)' }}>{item.event}</div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Category: {item.category}</div>
                  </div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 600 }}>
                    {item.date}, {item.time}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* SECTION 4: Cart Section */}
          <div style={{ padding: '20px', background: 'var(--panel-solid)', border: '1px solid var(--panel-border)', borderRadius: '4px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
              <h3 className="heading-md" style={{ color: 'var(--text-primary)' }}>
                Shopping Cart Items
              </h3>
              <span className="badge badge-primary">{(customer.cartItems || []).length} Products</span>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {(customer.cartItems || []).map(item => (
                <div key={item.id} style={{ display: 'flex', alignItems: 'center', gap: '14px', padding: '12px', borderRadius: '4px', background: 'var(--bg-app)', border: '1px solid var(--panel-border)' }}>
                  <img src={getOptimizedImageUrl(item.image, 100, 75)} alt={item.name} loading="lazy" decoding="async" style={{ width: '48px', height: '48px', borderRadius: '4px', objectFit: 'cover' }} />
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 700, fontSize: '0.88rem', color: 'var(--text-primary)' }}>{item.name}</div>
                    <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', display: 'flex', gap: '10px', marginTop: '2px' }}>
                      <span>Size: {item.size}</span>
                      <span>Color: {item.color}</span>
                      <span>Category: {item.category}</span>
                    </div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontWeight: 800, fontSize: '0.95rem', color: 'var(--text-primary)' }}>₹{typeof item.price === 'number' ? item.price.toLocaleString('en-IN') : item.price}</div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Qty: {item.qty}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* SECTION 5: Likes / Wishlist Section */}
          <div style={{ padding: '20px', background: 'var(--panel-solid)', border: '1px solid var(--panel-border)', borderRadius: '4px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
              <h3 className="heading-md" style={{ color: 'var(--text-primary)' }}>
                Liked Products & Wishlist
              </h3>
              <span className="badge badge-tertiary">{(customer.likedItems || []).length} Liked</span>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {(customer.likedItems || []).map(item => (
                <div key={item.id} style={{ display: 'flex', alignItems: 'center', gap: '12px', padding: '10px 12px', borderRadius: '4px', background: 'var(--bg-app)', border: '1px solid var(--panel-border)' }}>
                  <img src={getOptimizedImageUrl(item.image, 100, 75)} alt={item.name} loading="lazy" decoding="async" style={{ width: '42px', height: '42px', borderRadius: '4px', objectFit: 'cover' }} />
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 700, fontSize: '0.85rem', color: 'var(--text-primary)' }}>{item.name}</div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Category: {item.category}</div>
                  </div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                    Liked: {item.dateLiked}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* SECTION 6: Customer Interest Summary */}
          <div style={{
            padding: '20px',
            background: 'var(--bg-app)',
            border: '1px solid var(--panel-border)',
            borderLeft: '4px solid var(--color-primary, #9CAF88)',
            borderRadius: '4px'
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
              <h3 className="heading-md" style={{ color: 'var(--brand-primary, #9CAF88)', margin: 0 }}>
                Customer Interest Summary
              </h3>
              <span className="badge badge-tertiary" style={{ fontSize: '0.72rem' }}>
                AI Behavior Match
              </span>
            </div>
            <p style={{ fontSize: '0.88rem', color: 'var(--text-primary)', lineHeight: 1.5, marginBottom: '14px' }}>
              "{customer.interestSummary}"
            </p>
            <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
              <button
                type="button"
                onClick={() => {
                  navigator.clipboard.writeText(customer.interestSummary);
                  alert('Customer interest summary copied to clipboard.');
                }}
                className="btn btn-secondary"
                style={{ padding: '0.5em 1.2em', fontSize: '0.75rem', borderRadius: '4px' }}
              >
                Copy Summary
              </button>
              <button
                type="button"
                onClick={() => alert(`Generated personalized discount strategy for ${customer.name}.`)}
                className="btn btn-tertiary"
                style={{ padding: '0.5em 1.2em', fontSize: '0.75rem', borderRadius: '4px' }}
              >
                Auto-Offer Recommendation
              </button>
            </div>
          </div>

          {/* SECTION 7: Automated Communication Log */}
          <div style={{ padding: '20px', background: 'var(--panel-solid)', border: '1px solid var(--panel-border)', borderRadius: '4px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px', flexWrap: 'wrap', gap: '10px' }}>
              <div>
                <h3 className="heading-md" style={{ color: 'var(--text-primary)' }}>
                  Customer Communications
                </h3>
                <p className="text-subtle">Sales emails and SMS communication history for {customer.name}</p>
              </div>

              <div style={{ display: 'flex', gap: '10px' }}>
                <button
                  onClick={() => alert(`Sales email dispatched to registered email: ${customer.name}!`)}
                  className="btn btn-primary"
                  style={{ padding: '8px 14px', fontSize: '0.82rem', borderRadius: '4px' }}
                >
                  Send Sales Email
                </button>
                <button
                  onClick={() => alert(`Promotional SMS dispatched to: ${customer.name}!`)}
                  className="btn btn-secondary"
                  style={{ padding: '8px 14px', fontSize: '0.82rem', borderRadius: '4px' }}
                >
                  Send SMS Coupon
                </button>
              </div>
            </div>

            <div className="grid-2" style={{ gap: '16px' }}>
              {/* Sent Email Card */}
              <div style={{ background: 'var(--bg-app)', border: '1px solid var(--panel-border)', padding: '16px', borderRadius: '4px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                  <div style={{ fontWeight: 700, fontSize: '0.88rem', color: 'var(--text-primary)' }}>
                    Latest Email Communication
                  </div>
                  <span className="badge badge-primary">Delivered</span>
                </div>

                <div style={{ marginBottom: '6px' }}>
                  <div style={{ fontSize: '0.72rem', fontWeight: 700, color: 'var(--text-muted)' }}>To Registered Email</div>
                  <div style={{ fontWeight: 700, fontSize: '0.82rem', color: 'var(--text-primary)' }}>
                    {customer.id.includes('@') ? customer.id : `${customer.name.toLowerCase().replace(/\s+/g, '')}@gmail.com`}
                  </div>
                </div>

                <div style={{ marginBottom: '6px' }}>
                  <div style={{ fontSize: '0.72rem', fontWeight: 700, color: 'var(--text-muted)' }}>Subject</div>
                  <div style={{ fontWeight: 700, fontSize: '0.82rem', color: 'var(--text-primary)' }}>
                    {customer.sentEmail?.subject || `Exclusive 20% OFF Top Clothing Styles for ${customer.name}!`}
                  </div>
                </div>

                <div>
                  <div style={{ fontSize: '0.72rem', fontWeight: 700, color: 'var(--text-muted)' }}>Message Content</div>
                  <div style={{ background: 'var(--panel-solid)', padding: '10px', borderRadius: '4px', border: '1px solid var(--panel-border)', fontSize: '0.78rem', color: 'var(--text-secondary)', whiteSpace: 'pre-wrap', lineHeight: 1.4 }}>
                    {customer.sentEmail?.body || `Hello ${customer.name},\n\nWe noticed you were checking out our latest clothing catalog! Use exclusive discount code MAGNET20 at checkout for 20% OFF.`}
                  </div>
                </div>
              </div>

              {/* Sent SMS Card */}
              <div style={{ background: 'var(--bg-app)', border: '1px solid var(--panel-border)', padding: '16px', borderRadius: '4px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                  <div style={{ fontWeight: 700, fontSize: '0.88rem', color: 'var(--text-primary)' }}>
                    Latest SMS Communication
                  </div>
                  <span className="badge badge-primary">Delivered</span>
                </div>

                <div style={{ marginBottom: '6px' }}>
                  <div style={{ fontSize: '0.72rem', fontWeight: 700, color: 'var(--text-muted)' }}>To Registered Phone Number</div>
                  <div style={{ fontWeight: 700, fontSize: '0.82rem', color: 'var(--text-primary)' }}>
                    +91 98765 43210
                  </div>
                </div>

                <div>
                  <div style={{ fontSize: '0.72rem', fontWeight: 700, color: 'var(--text-muted)' }}>Message Content</div>
                  <div style={{ background: 'var(--panel-solid)', padding: '10px', borderRadius: '4px', border: '1px solid var(--panel-border)', fontSize: '0.78rem', color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                    {customer.sentSms?.text || `Lead Magnet Clothing: Hey ${customer.name}! Complete your order today with code MAGNET20 to get 20% OFF.`}
                  </div>
                </div>
              </div>
            </div>
          </div>

        </div>
      </div>
    </>
  );
};
