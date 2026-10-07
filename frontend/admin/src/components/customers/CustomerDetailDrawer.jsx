import React, { useState, useEffect } from 'react';
import { useAdminAuth } from '../../context/AdminAuthContext';
import { getAdminCustomerIntelligence } from '../../services/api';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell
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
  filter_apply:     'Filter',
  add_to_cart:      'Added to Cart',
  remove_from_cart: 'Removed from Cart',
  add_to_wishlist:  'Wishlist Add',
  wishlist_add:     'Wishlist Add',
  wishlist_remove:  'Wishlist Remove',
  checkout_start:   'Checkout Start',
  order_placed:     'Order Placed',
};

function getJourneyLabel(item) {
  if (!item) return 'Activity';
  if (item.type === 'order') {
    return `Order ₹${(item.total_amount || 0).toLocaleString('en-IN')}`;
  }
  if (item.type === 'marketing') {
    return `${item.channel || 'Email'} Campaign${item.status ? ` (${item.status})` : ''}`;
  }
  // event type
  const evtType = item.event_type || '';
  const label = EVENT_LABEL_MAP[evtType] || evtType.replace(/_/g, ' ');
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
    remove_from_cart: '#94a3b8',
    wishlist_add:     '#f43f5e',
    add_to_wishlist:  '#f43f5e',
    wishlist_remove:  '#94a3b8',
    checkout_start:   '#f97316',
    order_placed:     '#10b981',
    order:            '#10b981',
    marketing:        '#06b6d4',
  };
  return colorMap[item?.event_type] || colorMap[item?.type] || '#94a3b8';
}

function buildChartData(behaviorDistribution) {
  if (!behaviorDistribution || typeof behaviorDistribution !== 'object') return [];
  const labelMap = {
    page_view: 'Page View', product_view: 'Product View', product_click: 'Product Click',
    search: 'Search', filter_apply: 'Filter',
    add_to_cart: 'Cart Add', remove_from_cart: 'Cart Remove',
    wishlist_add: 'Wishlist', add_to_wishlist: 'Wishlist',
    order_placed: 'Order', order: 'Order', checkout_start: 'Checkout',
    marketing: 'Marketing',
  };
  // Merge synonyms
  const merged = {};
  for (const [key, val] of Object.entries(behaviorDistribution)) {
    const label = labelMap[key] || key.replace(/_/g, ' ');
    merged[label] = (merged[label] || 0) + val;
  }
  return Object.entries(merged)
    .filter(([, v]) => v > 0)
    .sort((a, b) => b[1] - a[1])
    .map(([name, value]) => ({ name, value }));
}

// ─── Component ────────────────────────────────────────────────────────────────

export const CustomerDetailDrawer = ({ customerId, isOpen, onClose }) => {
  const { admin } = useAdminAuth();
  const [detail, setDetail] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!isOpen || !customerId) { setDetail(null); setError(''); return; }
    let isMounted = true;
    async function load() {
      setIsLoading(true); setError('');
      try {
        const data = await getAdminCustomerIntelligence(customerId, admin?.token);
        if (isMounted) setDetail(data);
      } catch (err) {
        if (isMounted) { setError(err.message || 'Unable to load customer intelligence.'); setDetail(null); }
      } finally {
        if (isMounted) setIsLoading(false);
      }
    }
    load();
    return () => { isMounted = false; };
  }, [isOpen, customerId, admin?.token]);

  if (!isOpen) return null;

  const profile = detail?.customer || {};
  const lead = detail?.lead || {};
  const orders = detail?.orders || [];
  const cart = detail?.cart || [];
  const wishlist = detail?.wishlist || [];
  const comms = detail?.marketing?.communications || [];
  const scoreHistory = detail?.score_history || [];
  const rfm = detail?.rfm || {};
  const affinity = detail?.product_affinity || {};
  const explanation = detail?.lead_explanation || {};
  const retention = detail?.retention || {};
  const journey = detail?.journey_timeline || [];

  // Canonical behavior data — from behavior_summary (live events)
  const bs = detail?.behavior_summary || {};
  const bd = detail?.behavior_distribution || {};
  const chartData = buildChartData(bd);

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
      <div className={`drawer-overlay ${isOpen ? 'open' : ''}`} onClick={onClose} />

      <div className={`drawer-panel ${isOpen ? 'open' : ''}`} style={{ maxWidth: '760px', width: '100%', overflowY: 'auto' }}>

        {/* ── Header ── */}
        <div style={{
          padding: '24px 32px', borderBottom: '1px solid var(--panel-border)',
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          background: 'var(--panel-bg)', position: 'sticky', top: 0, zIndex: 10
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
          <button onClick={onClose} className="btn btn-ghost" style={{ padding: '8px' }}><X size={20} /></button>
        </div>

        {/* ── Body ── */}
        <div style={{ padding: '32px' }}>
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
                      { label: 'Wishlist',    value: bs.wishlist_adds_count   ?? 0,  color: '#f43f5e' },
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

                  {/* Bar chart from behavior_distribution (same events source) */}
                  {chartData.length > 0 ? (
                    <ResponsiveContainer width="100%" height={150}>
                      <BarChart data={chartData} margin={{ top: 4, right: 0, left: -20, bottom: 0 }}>
                        <XAxis dataKey="name" tick={{ fontSize: 10, fill: 'var(--text-muted)' }} axisLine={false} tickLine={false} />
                        <YAxis tick={{ fontSize: 10, fill: 'var(--text-muted)' }} axisLine={false} tickLine={false} allowDecimals={false} />
                        <Tooltip
                          contentStyle={{ background: 'var(--panel-solid)', border: '1px solid var(--panel-border)', borderRadius: 8, fontSize: 12 }}
                          labelStyle={{ color: 'var(--text-primary)', fontWeight: 700 }}
                          cursor={{ fill: 'rgba(99,102,241,0.08)' }}
                        />
                        <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                          {chartData.map((_, idx) => (
                            <Cell key={`c-${idx}`} fill={CHART_COLORS[idx % CHART_COLORS.length]} />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  ) : (
                    <div style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.82rem', padding: '12px 0' }}>
                      No behavior events recorded yet.
                    </div>
                  )}
                </div>
              </div>

              {/* ── SECTION 5: Customer Journey Timeline ── */}
              {journey.length > 0 && (
                <div>
                  <h3 className="heading-md" style={{ color: 'var(--text-primary)', marginBottom: '14px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <Compass size={18} style={{ color: 'var(--accent-indigo)' }} />
                    <span>Customer Journey Timeline ({journey.length} events)</span>
                  </h3>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', borderLeft: '2px solid var(--panel-border)', paddingLeft: '16px', marginLeft: '8px' }}>
                    {journey.slice(0, 15).map((item, idx) => {
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
                </div>
              )}

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
