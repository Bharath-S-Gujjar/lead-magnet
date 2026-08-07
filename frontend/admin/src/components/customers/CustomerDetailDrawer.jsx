import React from 'react';
import { 
  X, 
  Clock, 
  ShoppingBag, 
  Heart, 
  Mail, 
  MessageSquare, 
  User, 
  Calendar,
  CheckCircle2,
  TrendingUp,
  Shirt
} from 'lucide-react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Cell } from 'recharts';

export const CustomerDetailDrawer = ({ customer, isOpen, onClose }) => {
  if (!customer) return null;

  // Session math for Time Spent analysis
  const sessions = Array.isArray(customer.sessions) ? customer.sessions : [];
  const interestHistory = Array.isArray(customer.interestHistory) ? customer.interestHistory : [];
  const cartItems = Array.isArray(customer.cartItems) ? customer.cartItems : [];
  const likedItems = Array.isArray(customer.likedItems) ? customer.likedItems : [];

  const sessionMinutes = sessions.map(s => s.minutes || 0);
  const avgTime = sessionMinutes.length > 0 ? (sessionMinutes.reduce((a, b) => a + b, 0) / sessionMinutes.length).toFixed(1) : '0.0';
  const longestVisit = sessionMinutes.length > 0 ? Math.max(...sessionMinutes) : 0;
  const shortestVisit = sessionMinutes.length > 0 ? Math.min(...sessionMinutes) : 0;

  const CustomSessionTooltip = ({ active, payload }) => {
    if (active && payload && payload.length) {
      const item = payload[0].payload;
      return (
        <div style={{
          background: 'var(--panel-solid)',
          border: '1px solid var(--panel-border)',
          padding: '12px 16px',
          borderRadius: 'var(--radius-md)',
          boxShadow: 'var(--panel-shadow)',
          fontSize: '0.82rem',
          color: 'var(--text-primary)',
          maxWidth: '260px'
        }}>
          <div style={{ fontWeight: 800, color: 'var(--accent-indigo)', marginBottom: '4px' }}>{item.date}</div>
          <div><strong>Minutes Spent:</strong> {item.minutes} mins</div>
          <div><strong>Pages Visited:</strong> {item.pagesVisited} pages</div>
          <div style={{ marginTop: '4px', color: 'var(--accent-emerald)', fontWeight: 700 }}>
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
        className={`drawer-overlay ${isOpen ? 'open' : ''}`}
        onClick={onClose}
      />

      {/* Slide-out Drawer Panel */}
      <div className={`drawer-panel ${isOpen ? 'open' : ''}`}>
        {/* Top Header */}
        <div style={{
          padding: '24px 32px',
          borderBottom: '1px solid var(--panel-border)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          background: 'var(--panel-bg)'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
            <img 
              src={customer.avatar || `https://api.dicebear.com/7.x/avataaars/svg?seed=${encodeURIComponent(customer.name || 'user')}`} 
              alt={customer.name}
              style={{ width: '60px', height: '60px', borderRadius: '50%', objectFit: 'cover', border: '3px solid var(--accent-indigo)' }}
            />
            <div>
              <h2 className="heading-lg" style={{ color: 'var(--text-primary)' }}>{customer.name}</h2>
              <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', display: 'flex', gap: '12px', marginTop: '2px', flexWrap: 'wrap' }}>
                <span>ID: {customer.id || 'N/A'}</span>
                <span>•</span>
                <span>{customer.gender || 'User'}, {customer.age ? `${customer.age} yrs` : ''}</span>
                {customer.psychographic && (
                  <>
                    <span>•</span>
                    <span className="badge badge-indigo">{customer.psychographic}</span>
                  </>
                )}
              </div>
            </div>
          </div>

          <button 
            onClick={onClose}
            className="btn btn-ghost"
            style={{ padding: '8px', borderRadius: '50%' }}
          >
            <X size={22} />
          </button>
        </div>

        {/* Scrollable Content */}
        <div style={{ padding: '32px', display: 'flex', flexDirection: 'column', gap: '32px', overflowY: 'auto' }}>
          
          {/* SECTION 1: Customer Overview Cards */}
          <div className="grid-4" style={{ gap: '16px' }}>
            <div style={{ background: 'var(--table-header-bg)', border: '1px solid var(--panel-border)', padding: '16px', borderRadius: 'var(--radius-md)', textAlign: 'center' }}>
              <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)' }}>Customer ID</div>
              <div style={{ fontSize: '1rem', fontWeight: 800, color: 'var(--accent-indigo)', marginTop: '4px' }}>{customer.id || 'N/A'}</div>
            </div>

            <div style={{ background: 'var(--table-header-bg)', border: '1px solid var(--panel-border)', padding: '16px', borderRadius: 'var(--radius-md)', textAlign: 'center' }}>
              <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)' }}>Gender & Age</div>
              <div style={{ fontSize: '1rem', fontWeight: 800, color: 'var(--text-primary)', marginTop: '4px' }}>{customer.gender || 'User'}{customer.age ? `, ${customer.age}` : ''}</div>
            </div>

            <div style={{ background: 'var(--table-header-bg)', border: '1px solid var(--panel-border)', padding: '16px', borderRadius: 'var(--radius-md)', textAlign: 'center' }}>
              <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)' }}>Psychographic</div>
              <div style={{ fontSize: '0.95rem', fontWeight: 800, color: 'var(--accent-emerald)', marginTop: '4px' }}>{customer.psychographic || 'N/A'}</div>
            </div>

            <div style={{ background: 'var(--table-header-bg)', border: '1px solid var(--panel-border)', padding: '16px', borderRadius: 'var(--radius-md)', textAlign: 'center' }}>
              <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--text-muted)' }}>Total Orders</div>
              <div style={{ fontSize: '1rem', fontWeight: 800, color: 'var(--text-primary)', marginTop: '4px' }}>{customer.orders || 0} Orders</div>
            </div>
          </div>

          {/* SECTION 2: Time Spent Analysis Graph */}
          <div className="glass-card" style={{ padding: '24px' }}>
            <div style={{ marginBottom: '20px' }}>
              <h3 className="heading-md" style={{ color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Clock size={18} style={{ color: 'var(--accent-indigo)' }} />
                <span>Time Spent Analysis</span>
              </h3>
              <p className="text-subtle">Browsing session duration & engagement history</p>
            </div>

            {/* Session Bar Chart */}
            <div style={{ height: '220px', width: '100%' }}>
              {sessions.length === 0 ? (
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                  No browsing session records available.
                </div>
              ) : (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={sessions} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="rgba(148, 163, 184, 0.15)" />
                    <XAxis dataKey="date" tick={{ fontSize: 12, fill: 'var(--text-muted)' }} axisLine={false} tickLine={false} />
                    <YAxis tick={{ fontSize: 12, fill: 'var(--text-muted)' }} axisLine={false} tickLine={false} unit="m" />
                    <Tooltip content={<CustomSessionTooltip />} />
                    <Bar dataKey="minutes" radius={[6, 6, 0, 0]} animationDuration={1000}>
                      {sessions.map((entry, index) => (
                        <Cell 
                          key={`cell-${index}`} 
                          fill={index === sessions.length - 1 ? 'var(--accent-indigo)' : '#94a3b8'} 
                        />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              )}
            </div>

            {/* Summary Row Below Graph */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '16px', marginTop: '20px', borderTop: '1px solid var(--panel-border)', paddingTop: '16px', textAlign: 'center' }}>
              <div>
                <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', fontWeight: 600 }}>Average Time</div>
                <div style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--text-primary)' }}>{avgTime} mins</div>
              </div>
              <div>
                <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', fontWeight: 600 }}>Longest Visit</div>
                <div style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--accent-indigo)' }}>{longestVisit} mins</div>
              </div>
              <div>
                <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', fontWeight: 600 }}>Shortest Visit</div>
                <div style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--text-secondary)' }}>{shortestVisit} mins</div>
              </div>
            </div>
          </div>

          {/* SECTION 3: Interest History */}
          <div className="glass-card" style={{ padding: '24px' }}>
            <div style={{ marginBottom: '16px' }}>
              <h3 className="heading-md" style={{ color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <TrendingUp size={18} style={{ color: 'var(--accent-indigo)' }} />
                <span>Interest History Timeline</span>
              </h3>
              <p className="text-subtle">Sequential timeline of clothing product interactions</p>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {interestHistory.length === 0 ? (
                <div style={{ padding: '16px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                  No interest history logged yet.
                </div>
              ) : (
                interestHistory.map((item, idx) => (
                  <div 
                    key={idx}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '12px 16px',
                      borderRadius: 'var(--radius-md)',
                      background: 'var(--table-header-bg)',
                      border: '1px solid var(--panel-border)'
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                      <div style={{ width: '32px', height: '32px', borderRadius: '50%', background: 'rgba(79, 70, 229, 0.1)', color: 'var(--accent-indigo)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <Shirt size={16} />
                      </div>
                      <div>
                        <div style={{ fontWeight: 700, fontSize: '0.9rem', color: 'var(--text-primary)' }}>{item.event}</div>
                        <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Category: {item.category}</div>
                      </div>
                    </div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 600 }}>
                      {item.date}, {item.time}
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* SECTION 4: Cart Section */}
          <div className="glass-card" style={{ padding: '24px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <h3 className="heading-md" style={{ color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <ShoppingBag size={18} style={{ color: 'var(--accent-indigo)' }} />
                <span>Shopping Cart Items</span>
              </h3>
              <span className="badge badge-indigo">{cartItems.length} Products</span>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              {cartItems.length === 0 ? (
                <div style={{ padding: '16px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                  No cart items found for this customer.
                </div>
              ) : (
                cartItems.map(item => (
                  <div key={item.id} style={{ display: 'flex', alignItems: 'center', gap: '16px', padding: '14px', borderRadius: 'var(--radius-md)', background: 'var(--panel-solid)', border: '1px solid var(--panel-border)' }}>
                    <img src={item.image} alt={item.name} style={{ width: '56px', height: '56px', borderRadius: '8px', objectFit: 'cover' }} />
                    <div style={{ flex: 1 }}>
                      <div style={{ fontWeight: 700, fontSize: '0.9rem', color: 'var(--text-primary)' }}>{item.name}</div>
                      <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', display: 'flex', gap: '12px', marginTop: '4px' }}>
                        <span><strong>Size:</strong> {item.size}</span>
                        <span><strong>Color:</strong> {item.color}</span>
                        <span><strong>Category:</strong> {item.category}</span>
                      </div>
                    </div>
                    <div style={{ textAlign: 'right' }}>
                      <div style={{ fontWeight: 800, fontSize: '1rem', color: 'var(--text-primary)' }}>₹{item.price.toLocaleString('en-IN')}</div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Qty: {item.qty}</div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* SECTION 5: Likes / Wishlist Section */}
          <div className="glass-card" style={{ padding: '24px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <h3 className="heading-md" style={{ color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Heart size={18} style={{ color: 'var(--accent-rose)' }} />
                <span>Liked Products & Wishlist</span>
              </h3>
              <span className="badge badge-rose">{likedItems.length} Liked</span>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {likedItems.length === 0 ? (
                <div style={{ padding: '16px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                  No liked products or wishlist items.
                </div>
              ) : (
                likedItems.map(item => (
                  <div key={item.id} style={{ display: 'flex', alignItems: 'center', gap: '14px', padding: '12px 14px', borderRadius: 'var(--radius-md)', background: 'var(--panel-solid)', border: '1px solid var(--panel-border)' }}>
                    <img src={item.image} alt={item.name} style={{ width: '48px', height: '48px', borderRadius: '8px', objectFit: 'cover' }} />
                    <div style={{ flex: 1 }}>
                      <div style={{ fontWeight: 700, fontSize: '0.88rem', color: 'var(--text-primary)' }}>{item.name}</div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Category: {item.category}</div>
                    </div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                      Liked: {item.dateLiked}
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* SECTION 6: Customer Interest Summary */}
          {customer.interestSummary && (
            <div className="glass-card" style={{ padding: '24px', background: 'rgba(79, 70, 229, 0.04)', border: '1px solid rgba(79, 70, 229, 0.2)' }}>
              <h3 className="heading-md" style={{ color: 'var(--accent-indigo)', marginBottom: '8px' }}>
                Customer Interest Summary
              </h3>
              <p style={{ fontSize: '0.9rem', color: 'var(--text-primary)', lineHeight: 1.6 }}>
                "{customer.interestSummary}"
              </p>
            </div>
          )}

          {/* SECTION 7: Automated Communication (READ-ONLY) */}
          {(customer.sentEmail || customer.sentSms) && (
            <div className="glass-card" style={{ padding: '24px' }}>
              <h3 className="heading-md" style={{ color: 'var(--text-primary)', marginBottom: '16px' }}>
                Automated Communications (Read-Only Log)
              </h3>

              <div className="grid-2" style={{ gap: '20px' }}>
                {/* Sent Email Card */}
                {customer.sentEmail && (
                  <div style={{ background: 'var(--table-header-bg)', border: '1px solid var(--panel-border)', padding: '18px', borderRadius: 'var(--radius-lg)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                      <div style={{ fontWeight: 700, fontSize: '0.9rem', color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <Mail size={16} style={{ color: 'var(--accent-indigo)' }} />
                        <span>Email Sent</span>
                      </div>
                      <span className="badge badge-emerald">
                        <CheckCircle2 size={12} /> {customer.sentEmail.status || 'Sent'}
                      </span>
                    </div>

                    <div style={{ marginBottom: '8px' }}>
                      <div style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-muted)' }}>Subject</div>
                      <div style={{ fontWeight: 700, fontSize: '0.85rem', color: 'var(--text-primary)' }}>{customer.sentEmail.subject}</div>
                    </div>

                    <div>
                      <div style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-muted)' }}>Body</div>
                      <div style={{ background: 'var(--panel-solid)', padding: '12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--panel-border)', fontSize: '0.8rem', color: 'var(--text-secondary)', whiteSpace: 'pre-wrap' }}>
                        {customer.sentEmail.body}
                      </div>
                    </div>
                  </div>
                )}

                {/* Sent SMS Card */}
                {customer.sentSms && (
                  <div style={{ background: 'var(--table-header-bg)', border: '1px solid var(--panel-border)', padding: '18px', borderRadius: 'var(--radius-lg)' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                      <div style={{ fontWeight: 700, fontSize: '0.9rem', color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <MessageSquare size={16} style={{ color: 'var(--accent-emerald)' }} />
                        <span>SMS Sent</span>
                      </div>
                      <span className="badge badge-emerald">
                        <CheckCircle2 size={12} /> {customer.sentSms.status || 'Delivered'}
                      </span>
                    </div>

                    <div>
                      <div style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-muted)' }}>Message Content</div>
                      <div style={{ background: 'var(--panel-solid)', padding: '12px', borderRadius: 'var(--radius-sm)', border: '1px solid var(--panel-border)', fontSize: '0.82rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
                        {customer.sentSms.text}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  );
};
