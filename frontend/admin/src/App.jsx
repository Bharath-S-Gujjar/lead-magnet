import React, { useState, useEffect } from 'react';
import { HashRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { AdminAuthProvider, useAdminAuth } from './context/AdminAuthContext';
import { ThemeProvider } from './context/ThemeContext';
import { AdminLogin } from './pages/AdminLogin';
import { Topbar } from './components/layout/Topbar';
import { LeadAnalyticsSummary } from './components/analytics/LeadAnalyticsSummary';
import { GenderDistribution } from './components/analytics/GenderDistribution';
import { MarketingActivityFeed } from './components/analytics/MarketingActivityFeed';
import { FunnelAnalytics } from './components/analytics/FunnelAnalytics';
import { RFMDistribution } from './components/analytics/RFMDistribution';
import { RevenueAttribution } from './components/analytics/RevenueAttribution';
import { LiveActivityFeed } from './components/analytics/LiveActivityFeed';
import { WhatIfSimulator } from './components/analytics/WhatIfSimulator';
import { CustomerTable } from './components/customers/CustomerTable';
import { CustomerDetailDrawer } from './components/customers/CustomerDetailDrawer';
import { getAdminIntelligenceLeads } from './services/api';
import { AlertCircle, BarChart3, Sliders, Zap, Layers } from 'lucide-react';

function ProtectedAdminDashboard() {
  const { admin, isAdminAuthenticated } = useAdminAuth();
  const [leadsData, setLeadsData] = useState(null);
  const [selectedCustomerId, setSelectedCustomerId] = useState(null);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [activeTab, setActiveTab] = useState('overview'); // 'overview', 'funnel_rfm', 'revenue', 'simulator'

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
        onSelectCustomer={handleSelectCustomer}
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

        {/* 2. MAIN ANALYTICS CARDS */}
        <LeadAnalyticsSummary onRefresh={loadLeads} />

        {/* PHASE 17A: NAVIGATION TABS FOR DEEP INTELLIGENCE */}
        <div style={{
          display: 'flex',
          gap: '12px',
          margin: '24px 0 16px 0',
          borderBottom: '1px solid var(--panel-border)',
          paddingBottom: '12px',
          overflowX: 'auto'
        }}>
          <button
            onClick={() => setActiveTab('overview')}
            className={`btn ${activeTab === 'overview' ? 'btn-primary' : 'btn-ghost'}`}
            style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.88rem' }}
          >
            <Layers size={16} />
            <span>Overview & Directory</span>
          </button>

          <button
            onClick={() => setActiveTab('funnel_rfm')}
            className={`btn ${activeTab === 'funnel_rfm' ? 'btn-primary' : 'btn-ghost'}`}
            style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.88rem' }}
          >
            <BarChart3 size={16} />
            <span>Funnel & RFM Intelligence</span>
          </button>

          <button
            onClick={() => setActiveTab('revenue')}
            className={`btn ${activeTab === 'revenue' ? 'btn-primary' : 'btn-ghost'}`}
            style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.88rem' }}
          >
            <Zap size={16} />
            <span>Revenue & Live Feed</span>
          </button>

          <button
            onClick={() => setActiveTab('simulator')}
            className={`btn ${activeTab === 'simulator' ? 'btn-primary' : 'btn-ghost'}`}
            style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.88rem' }}
          >
            <Sliders size={16} />
            <span>What-If Simulator</span>
          </button>
        </div>

        {/* TAB 1: OVERVIEW & DIRECTORY */}
        {activeTab === 'overview' && (
          <>
            {/* CUSTOMER LEAD DISTRIBUTION */}
            <GenderDistribution />

            {/* MARKETING AUTOMATION ACTIVITY FEED */}
            <MarketingActivityFeed />

            {/* CUSTOMER INTELLIGENCE DIRECTORY */}
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
          </>
        )}

        {/* TAB 2: FUNNEL & RFM INTELLIGENCE */}
        {activeTab === 'funnel_rfm' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
            <FunnelAnalytics />
            <RFMDistribution />
          </div>
        )}

        {/* TAB 3: REVENUE & LIVE FEED */}
        {activeTab === 'revenue' && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px' }}>
            <RevenueAttribution />
            <LiveActivityFeed />
          </div>
        )}

        {/* TAB 4: WHAT-IF SIMULATOR */}
        {activeTab === 'simulator' && (
          <div>
            <WhatIfSimulator />
          </div>
        )}

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
