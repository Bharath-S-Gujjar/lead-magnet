import React, { useEffect, useMemo, useState } from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { AdminTopbar } from '../components/admin/AdminTopbar';
import { LeadAnalyticsSummary } from '../components/admin/LeadAnalyticsSummary';
import { GenderDistribution } from '../components/admin/GenderDistribution';
import { CustomerTable } from '../components/admin/CustomerTable';
import { CustomerDetailDrawer } from '../components/admin/CustomerDetailDrawer';
import { LeadsTable } from '../components/admin/LeadsTable';
import {
  fetchAnalyticsEvents,
  fetchAnalyticsOverview,
  fetchLeads,
  fetchProfiles,
  fetchSessions,
  fetchAllOrders,
  fetchAdminNotifications,
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
      gender: profile.gender || '',
      age: profile.age != null ? profile.age : '-',
      orders: profile.order_count ?? 0,
      order_count: profile.order_count ?? 0,
      total_spent: profile.total_spent ?? 0,
      last_order_at: profile.last_order_at || null,
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
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '16px' }}>
        {[1, 2, 3, 4].map((i) => (
          <div key={i} style={{ padding: '24px', background: 'var(--panel-solid)', border: '1px solid var(--panel-border)', borderRadius: 'var(--radius-md, 6px)' }}>
            <div className="skeleton-loader" style={{ height: '14px', width: '60%', marginBottom: '12px', borderRadius: '3px' }} />
            <div className="skeleton-loader" style={{ height: '28px', width: '40%', marginBottom: '8px', borderRadius: '4px' }} />
            <div className="skeleton-loader" style={{ height: '12px', width: '80%', borderRadius: '3px' }} />
          </div>
        ))}
      </div>
      <div style={{ padding: '24px', background: 'var(--panel-solid)', border: '1px solid var(--panel-border)', borderRadius: 'var(--radius-md, 6px)' }}>
        <div className="skeleton-loader" style={{ height: '20px', width: '30%', marginBottom: '16px', borderRadius: '4px' }} />
        <div className="skeleton-loader" style={{ height: '180px', width: '100%', borderRadius: '4px' }} />
      </div>
    </div>
  );
}

function RecentOrders({ orders }) {
  if (!orders || orders.length === 0) {
    return (
      <div style={{ padding: '24px', background: 'var(--panel-solid)', border: '1px solid var(--panel-border)', borderRadius: '4px' }}>
        <h3 className="heading-lg" style={{ color: 'var(--text-primary)', marginBottom: '4px' }}>Recent Orders</h3>
        <p className="text-subtle" style={{ marginBottom: '16px' }}>Live orders from orders collection</p>
        <div style={{
          padding: '24px',
          textAlign: 'center',
          background: 'var(--bg-app)',
          borderRadius: '4px',
          border: '1px dashed var(--panel-border)',
          color: 'var(--text-muted)',
        }}>
          <div style={{ fontSize: '0.88rem' }}>No orders placed yet.</div>
        </div>
      </div>
    );
  }

  const recent = orders.slice(0, 10);

  return (
    <div style={{ padding: '24px', background: 'var(--panel-solid)', border: '1px solid var(--panel-border)', borderRadius: '4px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
        <div>
          <h3 className="heading-lg" style={{ color: 'var(--text-primary)' }}>Recent Orders</h3>
          <p className="text-subtle">Live store orders: {orders.length} total</p>
        </div>
        <span className="badge badge-primary" style={{ fontSize: '0.8rem', padding: '4px 12px' }}>
          {orders.length} Total
        </span>
      </div>

      <div style={{ overflowX: 'auto', maxHeight: '440px', overflowY: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'separate', borderSpacing: '0 6px', fontSize: '0.875rem' }}>
          <thead>
            <tr style={{ background: 'var(--table-header-bg)', color: 'var(--text-secondary)' }}>
              <th style={{ padding: '12px 16px', fontWeight: 700, textAlign: 'left' }}>Order ID</th>
              <th style={{ padding: '12px 14px', fontWeight: 700, textAlign: 'left' }}>Customer</th>
              <th style={{ padding: '12px 14px', fontWeight: 700, textAlign: 'center' }}>Items</th>
              <th style={{ padding: '12px 14px', fontWeight: 700, textAlign: 'right' }}>Total</th>
              <th style={{ padding: '12px 14px', fontWeight: 700, textAlign: 'center' }}>Status</th>
              <th style={{ padding: '12px 16px', fontWeight: 700, textAlign: 'left' }}>Date</th>
            </tr>
          </thead>
          <tbody>
            {recent.map((order) => (
              <tr
                key={order._id}
                style={{
                  background: 'var(--panel-solid)',
                  border: '1px solid var(--panel-border)',
                }}
              >
                <td style={{ padding: '12px 16px', fontFamily: 'monospace', fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                  #{String(order._id).slice(-8).toUpperCase()}
                </td>
                <td style={{ padding: '12px 14px' }}>
                  <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{order.customer_email || 'Shopper'}</span>
                </td>
                <td style={{ padding: '12px 14px', textAlign: 'center' }}>
                  <span style={{ color: 'var(--brand-primary)', fontWeight: 700 }}>
                    {Array.isArray(order.items) ? order.items.length : 0}
                  </span>
                </td>
                <td style={{ padding: '12px 14px', textAlign: 'right', fontWeight: 700, color: 'var(--text-primary)' }}>
                  ₹{(order.total_amount || 0).toLocaleString('en-IN')}
                </td>
                <td style={{ padding: '12px 14px', textAlign: 'center' }}>
                  <span className="badge badge-primary" style={{ fontSize: '0.75rem', textTransform: 'capitalize' }}>
                    {order.status || 'placed'}
                  </span>
                </td>
                <td style={{ padding: '12px 16px', color: 'var(--text-muted)', fontSize: '0.82rem' }}>
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
  const [rawLeads, setRawLeads] = useState([]);
  const [orders, setOrders] = useState([]);
  const [notifications, setNotifications] = useState([]);
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

    const loadAll = () => {
      Promise.all([
        fetchAnalyticsOverview(),
        fetchAnalyticsEvents(),
        fetchLeads(),
        fetchSessions(),
        fetchProfiles(),
        fetchAllOrders(),
        fetchAdminNotifications(),
      ])
        .then(([overviewResponse, eventResponse, leadsResponse, sessionsResponse, profilesResponse, ordersResponse, notifData]) => {
          if (!isMounted) return;
          const overviewData = overviewResponse.data;
          const eventData = eventResponse.data;
          const leads = leadsResponse.data;
          const sessions = sessionsResponse.data;
          const profiles = profilesResponse.data;
          const allOrders = ordersResponse.data;
          setOverview(overviewData);
          setEventAnalytics(eventData);
          setCustomers(buildCustomers(profiles || [], sessions || [], leads || []));
          setRawLeads(leads || []);
          setOrders(allOrders || []);
          setNotifications(notifData || []);
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
    };

    loadAll();

    // 15-second live refresh polling for analytics overview
    const interval = setInterval(() => {
      fetchAnalyticsOverview()
        .then((res) => {
          if (isMounted && res?.data) {
            setOverview(res.data);
          }
        })
        .catch(() => {});
    }, 15000);

    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, [isAdminAuthenticated]);

  const dashboardKpis = useMemo(() => ({
    totalCustomers: overview?.total_customers || 0,
    totalLeads: overview?.total_leads || 0,
    activeToday: overview?.active_customers_today ?? overview?.active_customers ?? overview?.active_sessions ?? 0,
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
    <div className="app-layout" style={{ position: 'relative', width: '100%' }}>
      <AdminTopbar
        searchQuery={searchQuery}
        setSearchQuery={setSearchQuery}
        notifications={notifications}
      />

      <main className="content-body" style={{ position: 'relative', zIndex: 1 }}>
        {isLoading ? (
          <LoadingSkeleton />
        ) : (
          <>
            <LeadAnalyticsSummary kpis={dashboardKpis} />

            <GenderDistribution eventAnalytics={eventAnalytics} overview={overview} customers={customers} />

            {loadError ? (
              <div style={{ padding: '16px 20px', color: 'var(--brand-tertiary)', border: '1px solid var(--panel-border)', borderRadius: '4px', background: 'var(--panel-solid)' }}>
                Failed to load dashboard data: {loadError}
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

            <LeadsTable
              leads={rawLeads}
              onSelectLead={handleSelectCustomer}
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
