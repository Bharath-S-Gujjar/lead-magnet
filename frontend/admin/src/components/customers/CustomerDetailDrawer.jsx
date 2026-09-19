import React, { useState, useEffect } from 'react';
import { useAdminAuth } from '../../context/AdminAuthContext';
import { getAdminCustomerIntelligence } from '../../services/api';
import {
  X,
  User,
  Activity,
  Target,
  ShoppingBag,
  Mail,
  Send,
  MessageSquare,
  Clock,
  Flame,
  CheckCircle2,
  AlertCircle,
  PackageCheck
} from 'lucide-react';

export const CustomerDetailDrawer = ({ customerId, isOpen, onClose }) => {
  const { admin } = useAdminAuth();
  const [detail, setDetail] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!isOpen || !customerId) {
      setDetail(null);
      setError('');
      return;
    }

    let isMounted = true;
    async function loadDetail() {
      setIsLoading(true);
      setError('');
      try {
        const data = await getAdminCustomerIntelligence(customerId, admin?.token);
        if (isMounted) setDetail(data);
      } catch (err) {
        if (isMounted) {
          setError(err.message || 'Unable to load customer intelligence detail.');
          setDetail(null);
        }
      } finally {
        if (isMounted) setIsLoading(false);
      }
    }

    loadDetail();
    return () => { isMounted = false; };
  }, [isOpen, customerId, admin?.token]);

  if (!isOpen) return null;

  const profile = detail?.customer || {};
  const behavior = detail?.behavior || {};
  const lead = detail?.lead || {};
  const orders = detail?.orders || [];
  const autoEvents = detail?.marketing?.automation_events || [];
  const comms = detail?.marketing?.communications || [];

  const getChannelIcon = (ch) => {
    if (ch === 'email') return <Mail size={14} style={{ color: '#3b82f6' }} />;
    if (ch === 'sms') return <Send size={14} style={{ color: '#10b981' }} />;
    if (ch === 'whatsapp') return <MessageSquare size={14} style={{ color: '#25d366' }} />;
    return <Mail size={14} />;
  };

  return (
    <>
      {/* Background Overlay */}
      <div
        className={`drawer-overlay ${isOpen ? 'open' : ''}`}
        onClick={onClose}
      />

      {/* Drawer Panel */}
      <div className={`drawer-panel ${isOpen ? 'open' : ''}`} style={{ maxWidth: '640px', width: '100%', overflowY: 'auto' }}>
        {/* Header */}
        <div style={{
          padding: '24px 32px',
          borderBottom: '1px solid var(--panel-border)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          background: 'var(--panel-bg)',
          sticky: 'top'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
            <div style={{
              width: '56px',
              height: '56px',
              borderRadius: '50%',
              background: 'linear-gradient(135deg, var(--accent-indigo), #8b5cf6)',
              color: '#ffffff',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontWeight: 800,
              fontSize: '1.4rem'
            }}>
              {(profile.full_name || profile.username || 'C').charAt(0).toUpperCase()}
            </div>
            <div>
              <h2 className="heading-lg" style={{ color: 'var(--text-primary)' }}>
                {profile.full_name || profile.username || 'Customer Intelligence Profile'}
              </h2>
              <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', display: 'flex', gap: '10px', marginTop: '2px', flexWrap: 'wrap' }}>
                <span>ID: {customerId}</span>
                <span>•</span>
                <span>{profile.email || 'No email registered'}</span>
              </div>
            </div>
          </div>

          <button onClick={onClose} className="btn btn-ghost" style={{ padding: '8px' }}>
            <X size={20} />
          </button>
        </div>

        {/* Content Body */}
        <div style={{ padding: '32px' }}>
          {isLoading ? (
            <div style={{ padding: '40px 0', textAlign: 'center', color: 'var(--text-muted)' }}>
              Fetching real-time customer intelligence deep-dive...
            </div>
          ) : error ? (
            <div className="glass-card" style={{ padding: '20px', color: 'var(--accent-rose)', display: 'flex', alignItems: 'center', gap: '10px' }}>
              <AlertCircle size={18} />
              <span>{error}</span>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '28px' }}>
              
              {/* SECTION 1: CUSTOMER PROFILE */}
              <div>
                <h3 className="heading-md" style={{ color: 'var(--text-primary)', marginBottom: '14px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <User size={18} style={{ color: 'var(--accent-indigo)' }} />
                  <span>Canonical Customer Profile</span>
                </h3>
                <div style={{
                  background: 'var(--table-header-bg)',
                  border: '1px solid var(--panel-border)',
                  borderRadius: 'var(--radius-md)',
                  padding: '16px 20px',
                  display: 'grid',
                  gridTemplateColumns: '1fr 1fr',
                  gap: '12px',
                  fontSize: '0.88rem'
                }}>
                  <div><span style={{ color: 'var(--text-muted)' }}>Full Name:</span> <strong>{profile.full_name || profile.username || 'N/A'}</strong></div>
                  <div><span style={{ color: 'var(--text-muted)' }}>Email:</span> <strong>{profile.email || 'N/A'}</strong></div>
                  <div><span style={{ color: 'var(--text-muted)' }}>Phone:</span> <strong>{profile.phone || 'N/A'}</strong></div>
                  <div><span style={{ color: 'var(--text-muted)' }}>Role:</span> <strong>{profile.role || 'user'}</strong></div>
                  <div><span style={{ color: 'var(--text-muted)' }}>Created At:</span> <strong>{profile.created_at ? new Date(profile.created_at).toLocaleDateString() : 'N/A'}</strong></div>
                  <div><span style={{ color: 'var(--text-muted)' }}>Last Active:</span> <strong>{profile.last_active_at ? new Date(profile.last_active_at).toLocaleString() : 'N/A'}</strong></div>
                </div>
              </div>

              {/* SECTION 2: LEAD STATE & SCORE */}
              <div>
                <h3 className="heading-md" style={{ color: 'var(--text-primary)', marginBottom: '14px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Target size={18} style={{ color: 'var(--accent-indigo)' }} />
                  <span>Lead State & Qualification Metrics</span>
                </h3>
                <div style={{
                  background: 'var(--panel-solid)',
                  border: '1.5px solid var(--panel-border)',
                  borderRadius: 'var(--radius-md)',
                  padding: '20px',
                  boxShadow: 'var(--panel-shadow)'
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                    <div>
                      <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 700 }}>Lead Score</div>
                      <div style={{ fontFamily: 'var(--font-heading)', fontSize: '2.5rem', fontWeight: 800, color: 'var(--accent-indigo)', lineHeight: 1, marginTop: '4px' }}>
                        {lead.lead_score !== undefined && lead.lead_score !== null ? lead.lead_score : 'N/A'}
                      </div>
                    </div>
                    <div style={{ textAlign: 'right' }}>
                      <div style={{ marginBottom: '4px' }}>
                        <span className={`badge ${lead.qualification_status === 'qualified' ? 'badge-emerald' : 'badge-subtle'}`}>
                          {lead.qualification_status || 'not_qualified'}
                        </span>
                      </div>
                      <div>
                        <span className={`badge ${lead.lead_segment === 'Hot' ? 'badge-rose' : 'badge-indigo'}`}>
                          {lead.lead_segment || 'Cold'} Segment
                        </span>
                      </div>
                    </div>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px', fontSize: '0.82rem', borderTop: '1px solid var(--panel-border)', paddingTop: '12px' }}>
                    <div><span style={{ color: 'var(--text-muted)' }}>Lead Probability:</span> <strong>{lead.lead_probability ? `${(lead.lead_probability * 100).toFixed(2)}%` : 'N/A'}</strong></div>
                    <div><span style={{ color: 'var(--text-muted)' }}>Model Version:</span> <strong>{lead.model_version || 'N/A'}</strong></div>
                    <div><span style={{ color: 'var(--text-muted)' }}>First Qualified:</span> <strong>{lead.first_qualified_at ? new Date(lead.first_qualified_at).toLocaleString() : 'N/A'}</strong></div>
                    <div><span style={{ color: 'var(--text-muted)' }}>Last Scored:</span> <strong>{lead.last_scored_at ? new Date(lead.last_scored_at).toLocaleString() : 'N/A'}</strong></div>
                  </div>
                </div>
              </div>

              {/* SECTION 3: BEHAVIORAL FEATURE STORE */}
              <div>
                <h3 className="heading-md" style={{ color: 'var(--text-primary)', marginBottom: '14px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Activity size={18} style={{ color: 'var(--accent-indigo)' }} />
                  <span>Behavioral Feature Aggregations</span>
                </h3>
                <div style={{
                  background: 'var(--table-header-bg)',
                  border: '1px solid var(--panel-border)',
                  borderRadius: 'var(--radius-md)',
                  padding: '16px 20px',
                  display: 'grid',
                  gridTemplateColumns: '1fr 1fr',
                  gap: '10px',
                  fontSize: '0.85rem'
                }}>
                  <div><span style={{ color: 'var(--text-muted)' }}>Sessions Count:</span> <strong>{behavior.sessions_count || 0}</strong></div>
                  <div><span style={{ color: 'var(--text-muted)' }}>Total Events:</span> <strong>{behavior.total_events || 0}</strong></div>
                  <div><span style={{ color: 'var(--text-muted)' }}>Total Time Spent:</span> <strong>{behavior.total_time_spent ? `${Math.round(behavior.total_time_spent)}s` : '0s'}</strong></div>
                  <div><span style={{ color: 'var(--text-muted)' }}>Page Views Count:</span> <strong>{behavior.page_views_count || 0}</strong></div>
                  <div><span style={{ color: 'var(--text-muted)' }}>Products Viewed:</span> <strong>{behavior.products_viewed || 0}</strong></div>
                  <div><span style={{ color: 'var(--text-muted)' }}>Unique Products Viewed:</span> <strong>{behavior.unique_products_viewed || 0}</strong></div>
                  <div><span style={{ color: 'var(--text-muted)' }}>Product Interactions:</span> <strong>{behavior.product_interactions || 0}</strong></div>
                  <div><span style={{ color: 'var(--text-muted)' }}>Search Count:</span> <strong>{behavior.search_count || 0}</strong></div>
                  <div><span style={{ color: 'var(--text-muted)' }}>High Intent Page Visits:</span> <strong>{behavior.high_intent_page_visits || 0}</strong></div>
                  <div><span style={{ color: 'var(--text-muted)' }}>Cart Items:</span> <strong>{behavior.cart_item_count || 0}</strong></div>
                  <div><span style={{ color: 'var(--text-muted)' }}>Cart Value:</span> <strong>${behavior.cart_value || 0}</strong></div>
                  <div><span style={{ color: 'var(--text-muted)' }}>Wishlist Items:</span> <strong>{behavior.wishlist_item_count || 0}</strong></div>
                  <div><span style={{ color: 'var(--text-muted)' }}>Checkout Attempts:</span> <strong>{behavior.checkout_attempts || 0}</strong></div>
                  <div><span style={{ color: 'var(--text-muted)' }}>Orders Count:</span> <strong>{behavior.orders_count || 0}</strong></div>
                </div>
              </div>

              {/* SECTION 4: RECENT ORDERS */}
              <div>
                <h3 className="heading-md" style={{ color: 'var(--text-primary)', marginBottom: '14px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <ShoppingBag size={18} style={{ color: 'var(--accent-indigo)' }} />
                  <span>Recent Orders ({orders.length})</span>
                </h3>
                {orders.length === 0 ? (
                  <div style={{ padding: '16px', background: 'var(--table-header-bg)', borderRadius: 'var(--radius-md)', fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                    No purchase history recorded yet.
                  </div>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    {orders.map((o, idx) => (
                      <div key={idx} style={{ padding: '12px 16px', background: 'var(--table-header-bg)', borderRadius: 'var(--radius-md)', fontSize: '0.85rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div>
                          <div style={{ fontWeight: 700 }}>Order #{o._id || o.id}</div>
                          <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>{o.items ? `${o.items.length} items` : ''} • {o.created_at ? new Date(o.created_at).toLocaleDateString() : 'N/A'}</div>
                        </div>
                        <div style={{ textAlign: 'right' }}>
                          <div style={{ fontWeight: 800, color: 'var(--accent-emerald)' }}>${o.total_amount || o.total || 0}</div>
                          <span className="badge badge-emerald" style={{ padding: '2px 8px', fontSize: '0.72rem' }}>{o.status || 'placed'}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* SECTION 5: MARKETING DISPATCHES */}
              <div>
                <h3 className="heading-md" style={{ color: 'var(--text-primary)', marginBottom: '14px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <PackageCheck size={18} style={{ color: 'var(--accent-indigo)' }} />
                  <span>Marketing Dispatches & Automation Events</span>
                </h3>
                {comms.length === 0 ? (
                  <div style={{ padding: '16px', background: 'var(--table-header-bg)', borderRadius: 'var(--radius-md)', fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                    No automated communications dispatched yet.
                  </div>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    {comms.map((c, idx) => (
                      <div key={idx} style={{ padding: '12px 16px', background: 'var(--table-header-bg)', borderRadius: 'var(--radius-md)', fontSize: '0.85rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                          {getChannelIcon(c.channel)}
                          <div>
                            <div style={{ fontWeight: 700, textTransform: 'capitalize' }}>{c.channel} Channel</div>
                            <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>Recipient: {c.recipient || 'N/A'}</div>
                          </div>
                        </div>
                        <div style={{ textAlign: 'right' }}>
                          <span className={`badge ${c.status === 'sent' ? 'badge-emerald' : 'badge-subtle'}`} style={{ padding: '2px 8px', fontSize: '0.75rem' }}>
                            {c.status}
                          </span>
                          <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: '2px' }}>
                            {c.sent_at ? new Date(c.sent_at).toLocaleTimeString() : (c.created_at ? new Date(c.created_at).toLocaleTimeString() : '')}
                          </div>
                        </div>
                      </div>
                    ))}
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
