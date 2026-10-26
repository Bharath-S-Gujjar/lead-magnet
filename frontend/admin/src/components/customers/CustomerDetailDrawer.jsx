import React, { useState, useEffect } from 'react';
import { io } from 'socket.io-client';
import { useAdminAuth } from '../../context/AdminAuthContext';
import { getAdminCustomerIntelligence } from '../../services/api';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, LabelList
} from 'recharts';
import {
  X, User, Activity, Target, ShoppingBag, Mail, Send, MessageSquare,
  AlertCircle, PackageCheck, TrendingUp, History, Compass, ShoppingCart, Heart
} from 'lucide-react';

// ─── Helpers ──────────────────────────────────────────────────────────────────

const EVENT_LABEL_MAP = {
  page_view:        'Page View',
  product_view:     'Product View',
  product_click:    'Product Click',
  search:           'Search',
  filter_apply:     'Filter Applied',
  sort_apply:       'Sort Applied',
  add_to_cart:      'Added to Cart',
  remove_from_cart: 'Removed from Cart',
  cart_update:      'Cart Updated',
  cart_clear:       'Cart Cleared',
  add_to_wishlist:  'Wishlist Add',
  wishlist_add:     'Wishlist Add',
  wishlist_remove:  'Wishlist Remove',
  wishlist_clear:   'Wishlist Cleared',
  checkout_start:   'Checkout Start',
  order_placed:     'Order Placed',
  order:            'Order Placed',
  purchase:         'Purchase Completed',
  order_status_update: 'Order Status Update',
  registration:     'Registration',
  signup:           'Registration',
  login:            'Login',
};

function getJourneyLabel(item) {
  if (!item) return 'Activity';
  if (item.type === 'order') {
    const amt = item.total_amount != null ? ` ₹${Number(item.total_amount).toLocaleString('en-IN')}` : '';
    const status = item.status ? ` (${item.status})` : '';
    const itemsCount = item.items && item.items.length ? ` · ${item.items.length} item(s)` : '';
    return `Order Placed${amt}${status}${itemsCount}`;
  }
  if (item.type === 'marketing') {
    return `${(item.channel || 'Email').toUpperCase()} Campaign${item.status ? ` (${item.status})` : ''}${item.template ? ` · ${item.template}` : ''}`;
  }
  // event type
  const evtType = item.event_type || '';
  const label = EVENT_LABEL_MAP[evtType] || evtType.replace(/_/g, ' ');
  const entity = item.entity || {};
  const meta = item.metadata || {};

  if (evtType === 'search') {
    const q = meta.query || entity.query || '';
    return q ? `Search "${q}"` : 'Search';
  }
  if (evtType === 'registration' || evtType === 'signup') {
    return `User Registered${meta.email ? ` (${meta.email})` : ''}`;
  }
  if (evtType === 'login') {
    return `User Login${meta.email ? ` (${meta.email})` : ''}`;
  }
  if (evtType === 'product_view' || evtType === 'product_click') {
    const name = entity.name || entity.title || meta.name || '';
    return name ? `Product View: ${name}` : `Product View · ${item.page || ''}`;
  }
  if (evtType === 'add_to_cart') {
    const name = entity.name || entity.title || meta.name || '';
    const qty = meta.quantity ? ` (Qty: ${meta.quantity})` : '';
    return name ? `Added to Cart: ${name}${qty}` : `Added to Cart${qty}`;
  }
  if (evtType === 'remove_from_cart') {
    if (meta.cleared_all) return 'Cleared Cart';
    const name = entity.name || entity.title || meta.name || '';
    return name ? `Removed from Cart: ${name}` : 'Removed from Cart';
  }
  if (evtType === 'cart_update') {
    const name = entity.name || entity.title || meta.name || '';
    const qty = meta.quantity != null ? ` (Qty: ${meta.quantity})` : '';
    return name ? `Cart Updated: ${name}${qty}` : `Cart Updated${qty}`;
  }
  if (evtType === 'wishlist_add' || evtType === 'add_to_wishlist') {
    const name = entity.name || entity.title || meta.name || '';
    return name ? `Wishlist Add: ${name}` : 'Wishlist Add';
  }
  if (evtType === 'wishlist_remove') {
    if (meta.cleared_all) return 'Cleared Wishlist';
    const name = entity.name || entity.title || meta.name || '';
    return name ? `Wishlist Remove: ${name}` : 'Wishlist Remove';
  }
  if (evtType === 'checkout_start') {
    const count = meta.item_count ? ` (${meta.item_count} items)` : '';
    return `Checkout Started${count}`;
  }
  if (evtType === 'order_status_update') {
    return `Order Status: ${meta.status || 'Updated'}`;
  }

  const page = item.page ? ` · ${item.page}` : '';
  return `${label}${page}`;
}

function getEventColor(item) {
  const colorMap = {
    page_view:        '#6366f1',
    product_view:     '#8b5cf6',
    product_click:    '#a78bfa',
    search:           '#3b82f6',
    filter_apply:     '#60a5fa',
    add_to_cart:      '#f59e0b',
    remove_from_cart: '#ef4444',
    cart_update:      '#f59e0b',
    cart_clear:       '#ef4444',
    wishlist_add:     '#ec4899',
    add_to_wishlist:  '#ec4899',
    wishlist_remove:  '#94a3b8',
    wishlist_clear:   '#94a3b8',
    checkout_start:   '#f97316',
    order_placed:     '#10b981',
    order:            '#10b981',
    purchase:         '#10b981',
    registration:     '#14b8a6',
    signup:           '#14b8a6',
    login:            '#06b6d4',
    order_status_update: '#3b82f6',
    marketing:        '#06b6d4',
  };
  return colorMap[item?.event_type] || colorMap[item?.type] || '#94a3b8';
}

function buildChartData(behaviorSummary, behaviorDistribution) {
  const bs = behaviorSummary || {};
  // Derive directly from canonical behavior summary to ensure 100% consistency with KPI cards
  // and avoid alias double-counting.
  const categories = [
    { name: 'Page Views',    value: Number(bs.page_views_count    ?? 0) },
    { name: 'Product Views', value: Number(bs.product_views_count ?? 0) },
    { name: 'Cart Adds',     value: Number(bs.cart_adds_count     ?? 0) },
    { name: 'Wishlist',      value: Number(bs.wishlist_adds_count ?? 0) },
    { name: 'Orders',        value: Number(bs.orders_count        ?? 0) },
    { name: 'Searches',      value: Number(bs.searches_count      ?? 0) },
  ];

  if (Number(bs.checkout_starts_count ?? 0) > 0) {
    categories.push({ name: 'Checkouts', value: Number(bs.checkout_starts_count) });
  }

  // Filter out non-positive entries
  return categories.filter(item => item.value > 0);
}

// ─── Component ────────────────────────────────────────────────────────────────

export const CustomerDetailDrawer = ({ customerId, isOpen, onClose }) => {
  const { admin } = useAdminAuth();
  const [detail, setDetail] = useState(null);
  const [cachedDetail, setCachedDetail] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const [shouldRender, setShouldRender] = useState(isOpen);
  const [isSlideOpen, setIsSlideOpen] = useState(false);

  // Manage mounting for smooth slide-in / slide-out CSS transitions
  useEffect(() => {
    let timer;
    let animId;
    if (isOpen) {
      setShouldRender(true);
      // Wait a frame after mount to allow DOM insertion before transitioning transform
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

  useEffect(() => {
    if (!isOpen || !customerId) { return; }
    let isMounted = true;
    async function load(showSpinner = true) {
      if (showSpinner) setIsLoading(true);
      setError('');
      try {
        const data = await getAdminCustomerIntelligence(customerId, admin?.token);
        if (isMounted) {
          setDetail(data);
          setCachedDetail(data);
        }
      } catch (err) {
        if (isMounted && showSpinner) {
          setError(err.message || 'Unable to load customer intelligence.');
          setDetail(null);
        }
      } finally {
        if (isMounted && showSpinner) setIsLoading(false);
      }
    }
    load(true);

    // Dynamic background polling every 5 seconds while drawer is open
    const pollInterval = setInterval(() => {
      load(false);
    }, 5000);

    // Socket.io listener for real-time customer activity
    let socket = null;
    try {
      const API_BASE = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:5000').replace(/\/$/, '');
      socket = io(API_BASE, { transports: ['websocket', 'polling'] });
      const handleActivity = (payload) => {
        const payloadCid = payload?.customer_id || payload?.user_id || payload?.anonymous_id;
        if (!payloadCid || String(payloadCid) === String(customerId)) {
          load(false);
        }
      };
      socket.on('customer_activity', handleActivity);
      socket.on('cart_update', handleActivity);
      socket.on('wishlist_update', handleActivity);
      socket.on('order_placed', handleActivity);
      socket.on('order_status_update', handleActivity);
    } catch (e) {
      // Non-blocking socket fallback
    }

    return () => {
      isMounted = false;
      clearInterval(pollInterval);
      if (socket) socket.disconnect();
    };
  }, [isOpen, customerId, admin?.token]);

  if (!shouldRender && !isOpen) return null;

  const currentDetail = detail || cachedDetail;
  const profile = currentDetail?.customer || {};
  const lead = currentDetail?.lead || {};
  const orders = currentDetail?.orders || [];
  const cart = currentDetail?.cart || [];
  const wishlist = currentDetail?.wishlist || [];
  const comms = currentDetail?.marketing?.communications || [];
  const scoreHistory = currentDetail?.score_history || [];
  const rfm = currentDetail?.rfm || {};
  const affinity = currentDetail?.product_affinity || {};
  const explanation = currentDetail?.lead_explanation || {};
  const retention = currentDetail?.retention || {};
  const journey = currentDetail?.journey_timeline || [];

  // Canonical behavior data — from behavior_summary (live events)
  const bs = currentDetail?.behavior_summary || {};
  const bd = currentDetail?.behavior_distribution || {};
  const chartData = buildChartData(bs, bd);

  const totalRevenue = orders.reduce((s, o) => s + (o.total_amount || o.total || 0), 0);
  const hasUnavailablePrice = cart.some(i => i.price == null);
  const cartTotal = cart.reduce((s, i) => s + (i.subtotal != null ? i.subtotal : (i.price != null ? i.price * (i.quantity || 1) : 0)), 0);

  const CHART_COLORS = ['#6366f1','#8b5cf6','#3b82f6','#f59e0b','#f43f5e','#10b981','#06b6d4','#a78bfa'];

  const getChannelIcon = (ch) => {
    if (ch === 'email') return <Mail size={14} style={{ color: '#3b82f6' }} />;
    if (ch === 'sms') return <Send size={14} style={{ color: '#10b981' }} />;
    if (ch === 'whatsapp') return <MessageSquare size={14} style={{ color: '#25d366' }} />;
    return <Mail size={14} />;
  };

  return (
    <>
      <div className={`drawer-overlay ${isSlideOpen ? 'open' : ''}`} onClick={onClose} />

      <div className={`drawer-panel ${isSlideOpen ? 'open' : ''}`}>

        {/* ── Header ── */}
        <div style={{
          padding: '24px 32px', borderBottom: '1px solid var(--panel-border)',
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          background: 'var(--panel-bg)', position: 'sticky', top: 0, zIndex: 10,
          flexShrink: 0
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
            <div style={{
              width: '56px', height: '56px', borderRadius: '50%',
              background: 'linear-gradient(135deg, var(--accent-indigo), #8b5cf6)',
              color: '#ffffff', display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontWeight: 800, fontSize: '1.4rem'
            }}>
              {(profile.full_name || profile.username || 'C').charAt(0).toUpperCase()}
            </div>
            <div>
              <h2 className="heading-lg" style={{ color: 'var(--text-primary)' }}>
                {profile.full_name || profile.username || 'Customer Intelligence Profile'}
              </h2>
              <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', display: 'flex', gap: '10px', marginTop: '2px', flexWrap: 'wrap' }}>
                <span>{profile.email || 'No email'}</span>
                {rfm.rfm_segment && <><span>•</span><span style={{ color: '#8b5cf6', fontWeight: 700 }}>{rfm.rfm_segment}</span></>}
              </div>
            </div>
          </div>
          <button onClick={onClose} className="btn btn-ghost" style={{ padding: '8px' }} aria-label="Close drawer"><X size={20} /></button>
        </div>

        {/* ── Body ── */}
        <div className="drawer-content" style={{ padding: '32px' }}>
          {isLoading ? (
            <div style={{ padding: '60px 0', textAlign: 'center', color: 'var(--text-muted)' }}>
              Fetching Customer 360 intelligence...
            </div>
          ) : error ? (
            <div className="glass-card" style={{ padding: '20px', color: 'var(--accent-rose)', display: 'flex', alignItems: 'center', gap: '10px' }}>
              <AlertCircle size={18} /><span>{error}</span>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '28px' }}>

              {/* ── SECTION 1: Profile ── */}
              <div>
                <h3 className="heading-md" style={{ color: 'var(--text-primary)', marginBottom: '14px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <User size={18} style={{ color: 'var(--accent-indigo)' }} /><span>Canonical Customer 360 Profile</span>
                </h3>
                <div style={{
                  background: 'var(--table-header-bg)', border: '1px solid var(--panel-border)',
                  borderRadius: 'var(--radius-md)', padding: '16px 20px',
                  display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', fontSize: '0.88rem'
                }}>
                  <div><span style={{ color: 'var(--text-muted)' }}>Full Name:</span> <strong>{profile.full_name || profile.username || 'N/A'}</strong></div>
                  <div><span style={{ color: 'var(--text-muted)' }}>Email:</span> <strong>{profile.email || 'N/A'}</strong></div>
                  <div><span style={{ color: 'var(--text-muted)' }}>Phone:</span> <strong>{profile.phone || 'N/A'}</strong></div>
                  <div><span style={{ color: 'var(--text-muted)' }}>Role:</span> <strong>{profile.role || 'user'}</strong></div>
                  <div><span style={{ color: 'var(--text-muted)' }}>RFM Segment:</span> <strong style={{ color: '#8b5cf6' }}>{rfm.rfm_segment || 'N/A'}</strong></div>
                  <div><span style={{ color: 'var(--text-muted)' }}>Churn Risk:</span> <strong style={{ color: (retention.churn_risk_level === 'High' || retention.inactivity_risk === 'high') ? '#f43f5e' : '#10b981' }}>{retention.churn_risk_level || (retention.inactivity_risk ? retention.inactivity_risk.charAt(0).toUpperCase() + retention.inactivity_risk.slice(1) : 'Low')}</strong></div>
                </div>
              </div>

              {/* ── SECTION 2: Lead Score ── */}
              <div>
                <h3 className="heading-md" style={{ color: 'var(--text-primary)', marginBottom: '14px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Target size={18} style={{ color: 'var(--accent-indigo)' }} /><span>Lead Intelligence & Model Explainability</span>
                </h3>
                <div style={{ background: 'var(--panel-solid)', border: '1.5px solid var(--panel-border)', borderRadius: 'var(--radius-md)', padding: '20px', boxShadow: 'var(--panel-shadow)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                    <div>
                      <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 700 }}>Lead Score</div>
                      <div style={{ fontFamily: 'var(--font-heading)', fontSize: '2.5rem', fontWeight: 800, color: 'var(--accent-indigo)', lineHeight: 1, marginTop: '4px' }}>
                        {lead.lead_score !== undefined && lead.lead_score !== null ? lead.lead_score : 'N/A'}
                      </div>
                    </div>
                    <div style={{ textAlign: 'right', display: 'flex', flexDirection: 'column', gap: '6px', alignItems: 'flex-end' }}>
                      <div style={{ display: 'flex', gap: '6px' }}>
                        <span className={`badge ${lead.lead_segment === 'Hot' ? 'badge-rose' : lead.lead_segment === 'Warm' ? 'badge-indigo' : 'badge-subtle'}`}>
                          {lead.lead_segment || 'Cold'} Behavior
                        </span>
                        {lead.qualification_status === 'qualified' ? (
                          <span className="badge badge-emerald" style={{ fontWeight: 700 }}>Qualified Lead</span>
                        ) : (
                          <span className="badge badge-subtle">Unqualified Prospect</span>
                        )}
                      </div>
                      <div>
                        {lead.lifecycle_status === 'repeat_customer' ? (
                          <span className="badge badge-purple" style={{ fontWeight: 700 }}>Repeat Customer</span>
                        ) : lead.lifecycle_status === 'converted' ? (
                          <span className="badge badge-blue" style={{ fontWeight: 700 }}>Converted Customer</span>
                        ) : (
                          <span className="badge badge-subtle" style={{ color: 'var(--text-secondary)' }}>Prospect</span>
                        )}
                      </div>
                    </div>
                  </div>
                  {explanation.top_driving_factors?.length > 0 && (
                    <div style={{ marginTop: '16px', borderTop: '1px solid var(--panel-border)', paddingTop: '14px' }}>
                      <div style={{ fontSize: '0.82rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <TrendingUp size={14} style={{ color: '#6366f1' }} /><span>Key Factors Driving Score</span>
                      </div>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                        {explanation.top_driving_factors.slice(0, 4).map((factor, fIdx) => (
                          <div key={fIdx} style={{ fontSize: '0.8rem', display: 'flex', justifyContent: 'space-between', background: 'var(--table-header-bg)', padding: '6px 10px', borderRadius: '4px' }}>
                            <span style={{ color: 'var(--text-secondary)' }}>{factor.description || factor.label || factor.feature}</span>
                            <span style={{ fontWeight: 700, color: factor.direction === 'positive' ? '#10b981' : '#f43f5e' }}>
                              {factor.direction === 'positive' ? '+' : '-'}{factor.weight != null ? factor.weight : Math.abs(factor.contribution || 0)}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px', fontSize: '0.82rem', borderTop: '1px solid var(--panel-border)', paddingTop: '12px', marginTop: '14px' }}>
                    <div><span style={{ color: 'var(--text-muted)' }}>Lead Probability:</span> <strong>{lead.lead_probability ? `${(lead.lead_probability * 100).toFixed(2)}%` : 'N/A'}</strong></div>
                    <div><span style={{ color: 'var(--text-muted)' }}>Model Version:</span> <strong>{lead.model_version || 'N/A'}</strong></div>
                    <div><span style={{ color: 'var(--text-muted)' }}>First Qualified:</span> <strong>{lead.first_qualified_at ? new Date(lead.first_qualified_at).toLocaleString() : 'N/A'}</strong></div>
                    <div><span style={{ color: 'var(--text-muted)' }}>Last Scored:</span> <strong>{lead.last_scored_at ? new Date(lead.last_scored_at).toLocaleString() : 'N/A'}</strong></div>
                  </div>
                </div>
              </div>

              {/* ── SECTION 3: Product Affinity ── */}
              {affinity.top_categories && (
                <div>
                  <h3 className="heading-md" style={{ color: 'var(--text-primary)', marginBottom: '14px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <ShoppingBag size={18} style={{ color: 'var(--accent-indigo)' }} /><span>Product Affinity & Next Best Action</span>
                  </h3>
                  <div style={{ background: 'var(--table-header-bg)', border: '1px solid var(--panel-border)', borderRadius: 'var(--radius-md)', padding: '16px 20px', fontSize: '0.85rem' }}>
                    <div style={{ marginBottom: '10px' }}>
                      <span style={{ color: 'var(--text-muted)' }}>Top Categories Viewed: </span>
                      <strong>{affinity.top_categories.join(', ') || 'None'}</strong>
                    </div>
                    {affinity.recommended_actions && (
                      <div style={{ background: '#6366f115', borderLeft: '3px solid #6366f1', padding: '10px 14px', borderRadius: '4px' }}>
                        <div style={{ fontWeight: 700, color: '#6366f1', fontSize: '0.8rem' }}>RECOMMENDED ACTION</div>
                        <div style={{ marginTop: '2px', color: 'var(--text-primary)' }}>{affinity.recommended_actions[0]}</div>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* ── SECTION 4: Behaviour Activity Graph ── */}
              {/* Uses behavior_summary (SAME SOURCE as journey timeline) */}
              <div>
                <h3 className="heading-md" style={{ color: 'var(--text-primary)', marginBottom: '14px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Activity size={18} style={{ color: 'var(--accent-indigo)' }} /><span>Behaviour Activity Distribution</span>
                </h3>
                <div style={{ background: 'var(--table-header-bg)', border: '1px solid var(--panel-border)', borderRadius: 'var(--radius-md)', padding: '20px' }}>

                  {/* KPI stat cards — all from behavior_summary (live events) */}
                  <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '18px' }}>
                    {[
                      { label: 'Sessions',    value: bs.sessions_count       ?? 0,  color: '#6366f1' },
                      { label: 'Page Views',  value: bs.page_views_count      ?? 0,  color: '#8b5cf6' },
                      { label: 'Cart Adds',   value: bs.cart_adds_count       ?? 0,  color: '#f59e0b' },
                      { label: 'Wishlist Adds', value: bs.wishlist_adds_count ?? 0,  color: '#f43f5e' },
                      { label: 'Orders',      value: bs.orders_count          ?? orders.length, color: '#10b981' },
                      { label: 'Searches',    value: bs.searches_count        ?? 0,  color: '#3b82f6' },
                    ].map(stat => (
                      <div key={stat.label} style={{
                        flex: '1 1 70px', textAlign: 'center', padding: '10px 6px',
                        background: `${stat.color}12`, borderRadius: 'var(--radius-md)',
                        border: `1px solid ${stat.color}30`
                      }}>
                        <div style={{ fontSize: '1.4rem', fontWeight: 800, color: stat.color, fontFamily: 'var(--font-heading)' }}>
                          {stat.value}
                        </div>
                        <div style={{ fontSize: '0.67rem', color: 'var(--text-muted)', marginTop: '2px' }}>{stat.label}</div>
                      </div>
                    ))}
                  </div>

                  {/* Bar chart from behavior_summary */}
                  {chartData.length > 0 ? (
                    <ResponsiveContainer width="100%" height={210}>
                      <BarChart data={chartData} margin={{ top: 20, right: 15, left: -10, bottom: 25 }}>
                        <XAxis
                          dataKey="name"
                          tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
                          axisLine={{ stroke: 'var(--panel-border)' }}
                          tickLine={false}
                          interval={0}
                          angle={-20}
                          textAnchor="end"
                          height={40}
                        />
                        <YAxis
                          tick={{ fontSize: 10, fill: 'var(--text-muted)' }}
                          axisLine={false}
                          tickLine={false}
                          allowDecimals={false}
                        />
                        <Tooltip
                          contentStyle={{ background: 'var(--panel-solid)', border: '1px solid var(--panel-border)', borderRadius: 8, fontSize: 12 }}
                          labelStyle={{ color: 'var(--text-primary)', fontWeight: 700 }}
                          cursor={{ fill: 'rgba(99,102,241,0.08)' }}
                          formatter={(val) => [`${val} event${val === 1 ? '' : 's'}`, 'Count']}
                        />
                        <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                          <LabelList
                            dataKey="value"
                            position="top"
                            offset={5}
                            style={{ fontSize: 11, fill: 'var(--text-secondary)', fontWeight: 700 }}
                          />
                          {chartData.map((_, idx) => (
                            <Cell key={`c-${idx}`} fill={CHART_COLORS[idx % CHART_COLORS.length]} />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  ) : (
                    <div style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.82rem', padding: '16px 0' }}>
                      No behavior events recorded yet.
                    </div>
                  )}
                </div>
              </div>

              {/* ── SECTION 5: Customer Journey Timeline ── */}
              <div>
                <h3 className="heading-md" style={{ color: 'var(--text-primary)', marginBottom: '14px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Compass size={18} style={{ color: 'var(--accent-indigo)' }} />
                  <span>Customer Journey Timeline ({journey.length} event{journey.length !== 1 ? 's' : ''})</span>
                </h3>
                {journey.length === 0 ? (
                  <div style={{ padding: '16px', background: 'var(--table-header-bg)', borderRadius: 'var(--radius-md)', fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                    No journey events recorded yet.
                  </div>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', borderLeft: '2px solid var(--panel-border)', paddingLeft: '16px', marginLeft: '8px', maxHeight: '340px', overflowY: 'auto' }}>
                    {journey.slice(0, 30).map((item, idx) => {
                      const color = getEventColor(item);
                      const label = getJourneyLabel(item);
                      return (
                        <div key={idx} style={{ fontSize: '0.82rem', position: 'relative' }}>
                          <div style={{
                            position: 'absolute', left: '-21px', top: '6px',
                            width: '9px', height: '9px', borderRadius: '50%', background: color
                          }} />
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '10px' }}>
                            <div style={{ fontWeight: 600, color: 'var(--text-primary)', flex: 1 }}>{label}</div>
                            <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', flexShrink: 0 }}>
                              {item.timestamp ? new Date(item.timestamp).toLocaleString() : ''}
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* ── SECTION 6: Score History ── */}
              {scoreHistory.length > 0 && (
                <div>
                  <h3 className="heading-md" style={{ color: 'var(--text-primary)', marginBottom: '14px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <History size={18} style={{ color: 'var(--accent-indigo)' }} />
                    <span>Lead Score & Qualification History ({scoreHistory.length})</span>
                  </h3>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', maxHeight: '200px', overflowY: 'auto' }}>
                    {scoreHistory.slice(0, 10).map((sh, idx) => (
                      <div key={idx} style={{ padding: '8px 12px', background: 'var(--table-header-bg)', borderRadius: '6px', fontSize: '0.8rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div>
                          <span style={{ fontWeight: 700, color: 'var(--accent-indigo)' }}>Score {sh.lead_score}</span>
                          <span style={{ color: 'var(--text-muted)', marginLeft: '8px' }}>({(sh.lead_probability * 100).toFixed(1)}%)</span>
                          {sh.trigger_event && <span style={{ color: 'var(--text-secondary)', marginLeft: '8px' }}>• {sh.trigger_event}</span>}
                        </div>
                        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                          {sh.created_at ? new Date(sh.created_at).toLocaleString() : ''}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* ── SECTION 7: Recent Orders ── */}
              <div>
                <h3 className="heading-md" style={{ color: 'var(--text-primary)', marginBottom: '14px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <ShoppingBag size={18} style={{ color: 'var(--accent-indigo)' }} />
                  <span>Recent Orders ({orders.length})</span>
                  {orders.length > 0 && (
                    <span style={{ marginLeft: 'auto', fontSize: '0.82rem', color: 'var(--text-muted)' }}>
                      Total: <strong style={{ color: '#10b981' }}>₹{totalRevenue.toLocaleString('en-IN')}</strong>
                    </span>
                  )}
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
                          <div style={{ fontWeight: 700 }}>Order #{String(o._id || o.id).slice(-8)}</div>
                          <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                            {o.items ? `${o.items.length} item${o.items.length !== 1 ? 's' : ''}` : ''} • {o.created_at ? new Date(o.created_at).toLocaleDateString('en-IN') : 'N/A'}
                          </div>
                        </div>
                        <div style={{ textAlign: 'right' }}>
                          <div style={{ fontWeight: 800, color: 'var(--accent-emerald)' }}>
                            ₹{(o.total_amount || o.total || 0).toLocaleString('en-IN')}
                          </div>
                          <span className="badge badge-emerald" style={{ padding: '2px 8px', fontSize: '0.72rem' }}>{o.status || 'placed'}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* ── SECTION 8: Current Cart ── */}
              <div>
                <h3 className="heading-md" style={{ color: 'var(--text-primary)', marginBottom: '14px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <ShoppingCart size={18} style={{ color: 'var(--accent-indigo)' }} />
                  <span>Current Cart ({cart.length} item{cart.length !== 1 ? 's' : ''})</span>
                  {cart.length > 0 && (
                    <span style={{ marginLeft: 'auto', fontSize: '0.82rem', color: 'var(--text-muted)' }}>
                      Total: <strong style={{ color: '#f59e0b' }}>₹{cartTotal.toLocaleString('en-IN')}</strong>
                      {hasUnavailablePrice && <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginLeft: '4px' }}>(partial)</span>}
                    </span>
                  )}
                </h3>
                {cart.length === 0 ? (
                  <div style={{ padding: '16px', background: 'var(--table-header-bg)', borderRadius: 'var(--radius-md)', fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                    No active cart items found.
                    <div style={{ fontSize: '0.75rem', marginTop: '4px', opacity: 0.7 }}>
                      Cart events ({bs.cart_adds_count || 0} add_to_cart recorded) — items may have been purchased or removed.
                    </div>
                  </div>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    {cart.map((item, idx) => (
                      <div key={idx} style={{
                        padding: '12px 16px', background: 'rgba(245, 158, 11, 0.06)',
                        border: '1px solid rgba(245, 158, 11, 0.18)',
                        borderRadius: 'var(--radius-md)', fontSize: '0.85rem',
                        display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '12px'
                      }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flex: 1 }}>
                          {item.image ? (
                            <img src={item.image} alt={item.name} style={{ width: 44, height: 50, objectFit: 'cover', borderRadius: 6 }} />
                          ) : (
                            <div style={{ width: 44, height: 50, background: 'rgba(99,102,241,0.15)', borderRadius: 6, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                              <ShoppingCart size={18} style={{ color: '#6366f1' }} />
                            </div>
                          )}
                          <div>
                            <div style={{ fontWeight: 700, color: item.name === 'Product unavailable' ? 'var(--text-muted)' : 'var(--text-primary)' }}>
                              {item.name || 'Product unavailable'}
                            </div>
                            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                              {item.brand && <span>{item.brand}</span>}
                              {item.category && <span> · {item.category}</span>}
                              {item.gender && <span> · {item.gender}</span>}
                              <span> · Qty: {item.quantity || 1}</span>
                            </div>
                          </div>
                        </div>
                        <div style={{ textAlign: 'right', flexShrink: 0 }}>
                          {item.subtotal != null ? (
                            <div style={{ fontWeight: 800, color: '#f59e0b' }}>
                              ₹{item.subtotal.toLocaleString('en-IN')}
                            </div>
                          ) : (
                            <div style={{ fontWeight: 700, color: 'var(--text-muted)', fontSize: '0.82rem' }}>
                              Subtotal unavailable
                            </div>
                          )}
                          {item.price != null && item.price > 0 ? (
                            <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                              ₹{(item.price).toLocaleString('en-IN')} each
                            </div>
                          ) : (
                            <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', fontStyle: 'italic' }}>
                              Price unavailable
                            </div>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* ── SECTION 9: Current Wishlist ── */}
              <div>
                <h3 className="heading-md" style={{ color: 'var(--text-primary)', marginBottom: '14px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Heart size={18} style={{ color: '#f43f5e' }} />
                  <span>Current Wishlist ({wishlist.length} item{wishlist.length !== 1 ? 's' : ''})</span>
                </h3>
                {wishlist.length === 0 ? (
                  <div style={{ padding: '16px', background: 'var(--table-header-bg)', borderRadius: 'var(--radius-md)', fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                    No active wishlist items found.
                    <div style={{ fontSize: '0.75rem', marginTop: '4px', opacity: 0.7 }}>
                      Wishlist events ({bs.wishlist_adds_count || 0} recorded) — items may have been moved to cart or removed.
                    </div>
                  </div>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    {wishlist.map((item, idx) => (
                      <div key={idx} style={{
                        padding: '12px 16px', background: 'rgba(244, 63, 94, 0.06)',
                        border: '1px solid rgba(244, 63, 94, 0.18)',
                        borderRadius: 'var(--radius-md)', fontSize: '0.85rem',
                        display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '12px'
                      }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flex: 1 }}>
                          {item.image ? (
                            <img src={item.image} alt={item.name} style={{ width: 44, height: 50, objectFit: 'cover', borderRadius: 6 }} />
                          ) : (
                            <div style={{ width: 44, height: 50, background: 'rgba(244,63,94,0.15)', borderRadius: 6, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                              <Heart size={18} style={{ color: '#f43f5e' }} />
                            </div>
                          )}
                          <div>
                            <div style={{ fontWeight: 700, color: item.name === 'Product unavailable' ? 'var(--text-muted)' : 'var(--text-primary)' }}>
                              {item.name || 'Product unavailable'}
                            </div>
                            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                              {item.brand && <span>{item.brand}</span>}
                              {item.category && <span> · {item.category}</span>}
                              {item.gender && <span> · {item.gender}</span>}
                              {item.added_at && <span> · Added {new Date(item.added_at).toLocaleDateString('en-IN')}</span>}
                            </div>
                          </div>
                        </div>
                        <div style={{ textAlign: 'right', flexShrink: 0 }}>
                          {item.price != null && item.price > 0 ? (
                            <div style={{ fontWeight: 800, color: '#f43f5e' }}>
                              ₹{item.price.toLocaleString('en-IN')}
                            </div>
                          ) : (
                            <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', fontStyle: 'italic' }}>
                              Price unavailable
                            </div>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* ── SECTION 10: Marketing Dispatches ── */}
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
