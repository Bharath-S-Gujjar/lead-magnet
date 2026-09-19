import React, { useState, useEffect } from 'react';
import { HashRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { AdminAuthProvider, useAdminAuth } from './context/AdminAuthContext';
import { ThemeProvider } from './context/ThemeContext';
import { AdminLogin } from './pages/AdminLogin';
import { Topbar } from './components/layout/Topbar';
import { AdminNotificationsList } from './components/layout/AdminNotificationsList';
import { LeadAnalyticsSummary } from './components/analytics/LeadAnalyticsSummary';
import { GenderDistribution } from './components/analytics/GenderDistribution';
import { MarketingActivityFeed } from './components/analytics/MarketingActivityFeed';
import { CustomerTable } from './components/customers/CustomerTable';
import { CustomerDetailDrawer } from './components/customers/CustomerDetailDrawer';
import { getAdminIntelligenceLeads } from './services/api';
import { AlertCircle } from 'lucide-react';

function ProtectedAdminDashboard() {
  const { admin, isAdminAuthenticated } = useAdminAuth();
  const [leadsData, setLeadsData] = useState(null);
  const [selectedCustomerId, setSelectedCustomerId] = useState(null);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');

  // Filtering & Pagination State
  const [qualificationFilter, setQualificationFilter] = useState('qualified');
  const [segmentFilter, setSegmentFilter] = useState('all');
  const [sortBy, setSortBy] = useState('lead_score');
  const [sortOrder, setSortOrder] = useState('desc');
  const [page, setPage] = useState(1);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');

  const loadLeads = async () => {
    if (!isAdminAuthenticated) return;
    setIsLoading(true);
    setError('');
    try {
      const data = await getAdminIntelligenceLeads({
        token: admin?.token,
        qualification_status: qualificationFilter,
        segment: segmentFilter,
        sort_by: sortBy,
        sort_order: sortOrder,
        page,
        limit: 25
      });
      setLeadsData(data);
    } catch (err) {
      if (err.status === 401) {
        setError('Session expired. Please log in again.');
      } else if (err.status === 403) {
        setError('You are not authorized to access admin intelligence.');
      } else {
        setError(err.message || 'Unable to load customer directory.');
      }
      setLeadsData(null);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadLeads();
  }, [isAdminAuthenticated, admin?.token, qualificationFilter, segmentFilter, sortBy, sortOrder, page]);

  if (!isAdminAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  const handleSelectCustomer = (customerId) => {
    setSelectedCustomerId(customerId);
    setIsDrawerOpen(true);
  };

  const handleClearSearch = () => {
    setSearchQuery('');
  };

  return (
    <div className="app-layout">
      {/* 1. TOP HEADER */}
      <Topbar 
        searchQuery={searchQuery}
        setSearchQuery={setSearchQuery}
      />

      {/* MAIN CONTENT BODY */}
      <main className="content-body">
        {/* Global Error Banner */}
        {error && (
          <div className="glass-card" style={{ padding: '16px 24px', marginBottom: '20px', color: 'var(--accent-rose)', display: 'flex', alignItems: 'center', gap: '10px' }} role="alert">
            <AlertCircle size={18} />
            <span>{error}</span>
          </div>
        )}

        {/* 2. ADMIN NOTIFICATIONS */}
        <AdminNotificationsList />

        {/* 3. MAIN ANALYTICS CARDS */}
        <LeadAnalyticsSummary onRefresh={loadLeads} />

        {/* 4. CUSTOMER LEAD DISTRIBUTION */}
        <GenderDistribution />

        {/* 5. MARKETING AUTOMATION ACTIVITY FEED */}
        <MarketingActivityFeed />

        {/* 6. CUSTOMER INTELLIGENCE DIRECTORY */}
        <CustomerTable 
          leadsData={leadsData}
          isLoading={isLoading}
          onSelectCustomer={handleSelectCustomer}
          qualificationFilter={qualificationFilter}
          setQualificationFilter={setQualificationFilter}
          segmentFilter={segmentFilter}
          setSegmentFilter={setSegmentFilter}
          sortBy={sortBy}
          setSortBy={setSortBy}
          sortOrder={sortOrder}
          setSortOrder={setSortOrder}
          page={page}
          setPage={setPage}
          searchQuery={searchQuery}
          onClearSearch={handleClearSearch}
        />
      </main>

      {/* SLIDE-OUT CUSTOMER DETAIL DRAWER */}
      <CustomerDetailDrawer 
        customerId={selectedCustomerId}
        isOpen={isDrawerOpen}
        onClose={() => {
          setIsDrawerOpen(false);
          setSelectedCustomerId(null);
        }}
      />
    </div>
  );
}

export function App() {
  return (
    <ThemeProvider>
      <AdminAuthProvider>
        <Router>
          <Routes>
            <Route path="/login" element={<AdminLogin />} />
            <Route path="/" element={<ProtectedAdminDashboard />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Router>
      </AdminAuthProvider>
    </ThemeProvider>
  );
}
