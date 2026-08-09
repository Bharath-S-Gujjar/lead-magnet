import React, { useEffect, useMemo, useState } from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { AdminTopbar } from '../components/admin/AdminTopbar';
import { LeadAnalyticsSummary } from '../components/admin/LeadAnalyticsSummary';
import { GenderDistribution } from '../components/admin/GenderDistribution';
import { CustomerTable } from '../components/admin/CustomerTable';
import { CustomerDetailDrawer } from '../components/admin/CustomerDetailDrawer';
import { ShoppingBag, Clock, User, Package } from 'lucide-react';
import {
  fetchAnalyticsEvents,
  fetchAnalyticsOverview,
  fetchLeads,
  fetchProfiles,
  fetchSessions,
  fetchAllOrders,
} from '../services/api';
import '../styles/admin.css';

function formatDate(value) {
  if (!value) return 'Recent';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Recent';
  return date.toLocaleDateString('en-IN', { month: 'short', day: '2-digit' });
}

function formatTime(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' });
}

function topKey(mapValue, fallback = 'General Shopper') {
  if (!mapValue || typeof mapValue !== 'object') return fallback;
  const entries = Object.entries(mapValue);
  if (!entries.length) return fallback;
  return entries.sort((a, b) => b[1] - a[1])[0][0] || fallback;
}

function buildCustomers(profiles, sessions, leads) {
  const sessionsByVisitor = sessions.reduce((acc, session) => {
    const key = session.visitor_id || session.anonymous_id || 'unknown';
    acc[key] = acc[key] || [];
    acc[key].push(session);
    return acc;
  }, {});

  const leadsByVisitor = leads.reduce((acc, lead) => {
    const key = lead.visitor_id || 'unknown';
    acc[key] = acc[key] || [];
    acc[key].push(lead);
    return acc;
  }, {});

  const profileRows = profiles.length ? profiles : Object.keys(sessionsByVisitor).map((visitorId) => ({
    visitor_id: visitorId,
    session_count: sessionsByVisitor[visitorId].length,
    page_view_count: sessionsByVisitor[visitorId].reduce((sum, session) => sum + (session.page_views || 0), 0),
    engagement_score: 0,
  }));

  return profileRows.map((profile, index) => {
    const visitorId = profile.visitor_id || profile.user_id || `visitor-${index + 1}`;
    const visitorSessions = sessionsByVisitor[visitorId] || [];
    const visitorLeads = leadsByVisitor[visitorId] || [];
    const totalSeconds = visitorSessions.reduce((sum, session) => sum + (session.total_time_seconds || 0), 0);
    const totalMinutes = Math.max(0, Math.round(totalSeconds / 60));
    const category = topKey(profile.favorite_categories);
    const latestLead = visitorLeads[0];

    return {
      id: String(visitorId),
      name: String(profile.full_name || profile.email || profile.user_id || visitorId),
      avatar: `https://api.dicebear.com/7.x/avataaars/svg?seed=${encodeURIComponent(String(visitorId))}`,
      gender: profile.gender || 'Unknown',
      age: profile.age || '-',
      orders: 0,
      cartItemsCount: profile.cart_add_count || 0,
      likedItemsCount: profile.wishlist_add_count || 0,
      timeSpent: `${totalMinutes} mins`,
      timeSpentMinutes: totalMinutes,
      psychographic: latestLead?.segment || category || 'General Shopper',
      sessions: (visitorSessions.length ? visitorSessions : [{}]).slice(0, 8).map((session, sessionIndex) => ({
        date: formatDate(session.started_at || session.last_active_at),
        minutes: Math.max(0, Math.round((session.total_time_seconds || 0) / 60)),
        pagesVisited: session.page_views || 0,
        outcome: session.status || `Session ${sessionIndex + 1}`,
      })),
      interestHistory: [
        {
          date: formatDate(profile.last_active_at || profile.updated_at),
          time: formatTime(profile.last_active_at || profile.updated_at),
          category,
          event: `Engagement score ${profile.engagement_score || 0}`,
        },
      ],
      cartItems: [],
      likedItems: [],
      interestSummary: `Real customer profile for ${profile.full_name || profile.email || visitorId}. Favorite category: ${category}. Page views: ${profile.page_view_count || 0}.`,
      sentEmail: {
        subject: 'No automated email sent',
        body: 'No email campaign log exists for this customer yet.',
        status: 'Not Sent',
      },
      sentSms: {
        text: 'No SMS campaign log exists for this customer yet.',
        status: 'Not Sent',
      },
    };
  });
}

function LoadingSkeleton() {
  const pulse = {
    background: 'linear-gradient(90deg, var(--panel-solid) 25%, rgba(255,255,255,0.06) 50%, var(--panel-solid) 75%)',
    backgroundSize: '200% 100%',
    animation: 'skeletonPulse 1.5s ease-in-out infinite',
    borderRadius: '8px',
  };
  return (
    <>
      {/* KPI Cards skeleton */}
      <section>
        <div className="grid-4" style={{ gap: '20px' }}>
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="glass-card" style={{ padding: '24px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '14px' }}>
                <div style={{ ...pulse, height: '14px', width: '60%' }} />
                <div style={{ ...pulse, height: '36px', width: '36px', borderRadius: '10px' }} />
              </div>
              <div style={{ ...pulse, height: '32px', width: '50%', marginBottom: '8px' }} />
              <div style={{ ...pulse, height: '12px', width: '80%' }} />
            </div>
          ))}
        </div>
      </section>

      {/* Chart skeleton */}
      <div className="glass-card" style={{ padding: '24px 28px', marginTop: '20px' }}>
        <div style={{ ...pulse, height: '20px', width: '40%', marginBottom: '8px' }} />
        <div style={{ ...pulse, height: '14px', width: '60%', marginBottom: '24px' }} />
        <div style={{ display: 'flex', gap: '48px' }}>
          <div style={{ ...pulse, height: '220px', width: '220px', borderRadius: '50%' }} />
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {[1, 2, 3].map((i) => (
              <div key={i} style={{ ...pulse, height: '60px', borderRadius: '8px' }} />
            ))}
          </div>
        </div>
      </div>

      {/* Table skeleton */}
      <section className="glass-card" style={{ padding: '32px', marginTop: '20px' }}>
        <div style={{ ...pulse, height: '22px', width: '35%', marginBottom: '8px' }} />
        <div style={{ ...pulse, height: '14px', width: '55%', marginBottom: '24px' }} />
        {[1, 2, 3, 4, 5].map((i) => (
          <div key={i} style={{ ...pulse, height: '62px', marginBottom: '8px', borderRadius: '8px' }} />
        ))}
      </section>
    </>
  );
}

function RecentOrders({ orders }) {
  if (!orders || orders.length === 0) {
    return (
      <div className="glass-card" style={{ padding: '28px 32px' }}>
        <h3 className="heading-lg" style={{ color: 'var(--text-primary)', marginBottom: '6px' }}>Recent Orders</h3>
        <p className="text-subtle" style={{ marginBottom: '20px' }}>Live orders from MongoDB orders collection</p>
        <div style={{
          padding: '32px',
          textAlign: 'center',
          background: 'var(--table-header-bg)',
          borderRadius: 'var(--radius-lg)',
          border: '1px dashed var(--panel-border)',
          color: 'var(--text-muted)',
        }}>
          <Package size={36} style={{ marginBottom: '10px', opacity: 0.5 }} />
          <div style={{ fontSize: '0.9rem' }}>No orders yet. Place an order from the storefront to see data here.</div>
        </div>
      </div>
    );
  }

  const recent = orders.slice(0, 10);

  return (
    <div className="glass-card" style={{ padding: '28px 32px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
        <div>
          <h3 className="heading-lg" style={{ color: 'var(--text-primary)' }}>Recent Orders</h3>
          <p className="text-subtle">Live orders from MongoDB — {orders.length} total order{orders.length !== 1 ? 's' : ''}</p>
        </div>
        <span className="badge badge-emerald" style={{ fontSize: '0.8rem', padding: '6px 14px' }}>
          {orders.length} Total
        </span>
      </div>

      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'separate', borderSpacing: '0 8px', fontSize: '0.875rem' }}>
          <thead>
            <tr style={{ background: 'var(--table-header-bg)', color: 'var(--text-secondary)' }}>
              <th style={{ padding: '14px 18px', borderRadius: 'var(--radius-md) 0 0 var(--radius-md)', fontWeight: 700, textAlign: 'left' }}>Order ID</th>
              <th style={{ padding: '14px 16px', fontWeight: 700, textAlign: 'left' }}>Customer</th>
              <th style={{ padding: '14px 16px', fontWeight: 700, textAlign: 'center' }}>Items</th>
              <th style={{ padding: '14px 16px', fontWeight: 700, textAlign: 'right' }}>Total</th>
              <th style={{ padding: '14px 16px', fontWeight: 700, textAlign: 'center' }}>Status</th>
              <th style={{ padding: '14px 18px', borderRadius: '0 var(--radius-md) var(--radius-md) 0', fontWeight: 700, textAlign: 'left' }}>
                <Clock size={13} style={{ marginRight: '4px', verticalAlign: 'middle' }} />Date
              </th>
            </tr>
          </thead>
          <tbody>
            {recent.map((order) => (
              <tr
                key={order._id}
                style={{
                  background: 'var(--panel-solid)',
                  boxShadow: '0 2px 8px rgba(0,0,0,0.02)',
                  border: '1px solid var(--panel-border)',
                }}
              >
                <td style={{ padding: '14px 18px', borderRadius: 'var(--radius-md) 0 0 var(--radius-md)', fontFamily: 'monospace', fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                  #{String(order._id).slice(-8).toUpperCase()}
                </td>
                <td style={{ padding: '14px 16px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <User size={15} style={{ color: 'var(--accent-indigo)' }} />
                    <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{order.customer_email || '—'}</span>
                  </div>
                </td>
                <td style={{ padding: '14px 16px', textAlign: 'center' }}>
                  <div style={{ display: 'inline-flex', alignItems: 'center', gap: '5px', color: 'var(--accent-indigo)', fontWeight: 700 }}>
                    <ShoppingBag size={14} />
                    {Array.isArray(order.items) ? order.items.length : 0}
                  </div>
                </td>
                <td style={{ padding: '14px 16px', textAlign: 'right', fontWeight: 800, color: 'var(--text-primary)', fontSize: '0.95rem' }}>
                  ₹{(order.total_amount || 0).toLocaleString('en-IN')}
                </td>
                <td style={{ padding: '14px 16px', textAlign: 'center' }}>
                  <span className="badge badge-emerald" style={{ fontSize: '0.75rem', padding: '4px 10px', textTransform: 'capitalize' }}>
                    {order.status || 'placed'}
                  </span>
                </td>
                <td style={{ padding: '14px 18px', borderRadius: '0 var(--radius-md) var(--radius-md) 0', color: 'var(--text-muted)', fontSize: '0.82rem' }}>
                  {formatDate(order.created_at)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function AdminDashboard() {
  const { isAdminAuthenticated } = useAuth();

  const [overview, setOverview] = useState(null);
  const [eventAnalytics, setEventAnalytics] = useState(null);
  const [customers, setCustomers] = useState([]);
  const [orders, setOrders] = useState([]);
  const [loadError, setLoadError] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [selectedCustomer, setSelectedCustomer] = useState(null);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [sortOption, setSortOption] = useState('default');

  useEffect(() => {
    if (!isAdminAuthenticated) return;

    let isMounted = true;
    setIsLoading(true);

    Promise.all([
      fetchAnalyticsOverview(),
      fetchAnalyticsEvents(),
      fetchLeads(),
      fetchSessions(),
      fetchProfiles(),
      fetchAllOrders(),
    ])
      .then(([overviewResponse, eventResponse, leadsResponse, sessionsResponse, profilesResponse, ordersResponse]) => {
        if (!isMounted) return;
        const overviewData = overviewResponse.data;
        const eventData = eventResponse.data;
        const leads = leadsResponse.data;
        const sessions = sessionsResponse.data;
        const profiles = profilesResponse.data;
        const allOrders = ordersResponse.data;
        console.log('ADMIN OVERVIEW', overviewData);
        setOverview(overviewData);
        setEventAnalytics(eventData);
        setCustomers(buildCustomers(profiles || [], sessions || [], leads || []));
        setOrders(allOrders || []);
        setLoadError('');
      })
      .catch((error) => {
        if (!isMounted) return;
        setLoadError(error.message);
        setCustomers([]);
        setOrders([]);
      })
      .finally(() => {
        if (isMounted) setIsLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [isAdminAuthenticated]);

  const dashboardKpis = useMemo(() => ({
    totalCustomers: overview?.total_customers || 0,
    totalLeads: overview?.total_leads || 0,
    activeToday: overview?.active_customers_today || overview?.active_sessions || 0,
    totalSessions: overview?.total_sessions || 0,
    totalEvents: overview?.total_events || 0,
  }), [overview]);

  if (!isAdminAuthenticated) {
    return <Navigate to="/login?mode=admin" replace />;
  }

  const handleSelectCustomer = (customer) => {
    setSelectedCustomer(customer);
    setIsDrawerOpen(true);
  };

  const handleClearSearch = () => {
    setSearchQuery('');
  };

  return (
    <div className="app-layout">
      <AdminTopbar
        searchQuery={searchQuery}
        setSearchQuery={setSearchQuery}
      />

      <main className="content-body">
        {isLoading ? (
          <LoadingSkeleton />
        ) : (
          <>
            <LeadAnalyticsSummary kpis={dashboardKpis} />

            <GenderDistribution eventAnalytics={eventAnalytics} overview={overview} />

            {loadError ? (
              <div className="glass-card" style={{ padding: '18px 24px', color: 'var(--accent-rose)', marginBottom: '20px' }}>
                ⚠ Failed to load dashboard data: {loadError}
              </div>
            ) : null}

            <RecentOrders orders={orders} />

            <CustomerTable
              customers={customers}
              onSelectCustomer={handleSelectCustomer}
              sortOption={sortOption}
              setSortOption={setSortOption}
              searchQuery={searchQuery}
              onClearSearch={handleClearSearch}
            />
          </>
        )}
      </main>

      <CustomerDetailDrawer
        customer={selectedCustomer}
        isOpen={isDrawerOpen}
        onClose={() => setIsDrawerOpen(false)}
      />
    </div>
  );
}

export default AdminDashboard;
