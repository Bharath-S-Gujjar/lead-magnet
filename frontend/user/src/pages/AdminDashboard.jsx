import React, { useState } from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { AdminTopbar } from '../components/admin/AdminTopbar';
import { LeadAnalyticsSummary } from '../components/admin/LeadAnalyticsSummary';
import { GenderDistribution } from '../components/admin/GenderDistribution';
import { CustomerTable } from '../components/admin/CustomerTable';
import { CustomerDetailDrawer } from '../components/admin/CustomerDetailDrawer';
import { CLOTHING_CUSTOMERS } from '../data/mockData';
import '../styles/admin.css';

export function AdminDashboard() {
  const { isAdminAuthenticated } = useAuth();
  
  const [customers, setCustomers] = useState(CLOTHING_CUSTOMERS);
  const [selectedCustomer, setSelectedCustomer] = useState(null);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [sortOption, setSortOption] = useState('default');

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
      {/* 1. TOP HEADER */}
      <AdminTopbar 
        searchQuery={searchQuery}
        setSearchQuery={setSearchQuery}
      />

      {/* MAIN CONTENT BODY */}
      <main className="content-body">
        {/* 2. MAIN ANALYTICS CARDS (INCLUDES NEW PREDICTED FUTURE LEADS CARD) */}
        <LeadAnalyticsSummary />

        {/* 3. CUSTOMER DISTRIBUTION (DOUGHNUT + LEETCODE PROGRESS BARS) */}
        <GenderDistribution />

        {/* 4. CUSTOMER LIST (FOCUSED SEARCH MODE + DYNAMIC 3-COLUMN METRIC SIMPLIFICATION) */}
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

export default AdminDashboard;
