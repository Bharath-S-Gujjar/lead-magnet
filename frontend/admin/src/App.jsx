import React, { useState } from 'react';
import { HashRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { AdminAuthProvider, useAdminAuth } from './context/AdminAuthContext';
import { ThemeProvider } from './context/ThemeContext';
import { AdminLogin } from './pages/AdminLogin';
import { Topbar } from './components/layout/Topbar';
import { LeadAnalyticsSummary } from './components/analytics/LeadAnalyticsSummary';
import { GenderDistribution } from './components/analytics/GenderDistribution';
import { CustomerTable } from './components/customers/CustomerTable';
import { CustomerDetailDrawer } from './components/customers/CustomerDetailDrawer';
import { CLOTHING_CUSTOMERS } from './data/mockData';

function ProtectedAdminDashboard() {
  const { isAdminAuthenticated } = useAdminAuth();
  const [customers, setCustomers] = useState(CLOTHING_CUSTOMERS);
  const [selectedCustomer, setSelectedCustomer] = useState(null);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [sortOption, setSortOption] = useState('default');

  if (!isAdminAuthenticated) {
    return <Navigate to="/login" replace />;
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
      {/* 1. TOP HEADER */}
      <Topbar 
        searchQuery={searchQuery}
        setSearchQuery={setSearchQuery}
      />

      {/* MAIN CONTENT BODY */}
      <main className="content-body">
        {/* 2. MAIN ANALYTICS CARDS */}
        <LeadAnalyticsSummary />

        {/* 3. CUSTOMER DISTRIBUTION */}
        <GenderDistribution />

        {/* 4. CUSTOMER LIST */}
        <CustomerTable 
          customers={customers}
          onSelectCustomer={handleSelectCustomer}
          sortOption={sortOption}
          setSortOption={setSortOption}
          searchQuery={searchQuery}
          onClearSearch={handleClearSearch}
        />
      </main>

      {/* SLIDE-OUT CUSTOMER DETAIL DRAWER */}
      <CustomerDetailDrawer 
        customer={selectedCustomer}
        isOpen={isDrawerOpen}
        onClose={() => setIsDrawerOpen(false)}
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
