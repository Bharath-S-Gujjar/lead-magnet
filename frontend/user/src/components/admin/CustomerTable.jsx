import React from 'react';
import { Heart, ShoppingBag, Clock, ChevronDown, RotateCcw, SearchX } from 'lucide-react';

export const CustomerTable = ({ 
  customers, 
  onSelectCustomer, 
  sortOption, 
  setSortOption,
  searchQuery,
  onClearSearch
}) => {
  // 1. Filter by search query
  let filtered = customers.filter(cust => {
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    return (
      cust.name.toLowerCase().includes(q) ||
      cust.psychographic.toLowerCase().includes(q) ||
      cust.gender.toLowerCase().includes(q)
    );
  });

  // 2. Auto-Sort Rows in Descending Order based on metric
  const sorted = [...filtered].sort((a, b) => {
    if (sortOption === 'time-spent') return b.timeSpentMinutes - a.timeSpentMinutes;
    if (sortOption === 'orders') return (b.order_count ?? b.orders ?? 0) - (a.order_count ?? a.orders ?? 0);
    if (sortOption === 'cart-items') return b.cartItemsCount - a.cartItemsCount;
    if (sortOption === 'likes') return b.likedItemsCount - a.likedItemsCount;
    if (sortOption === 'psychographic') return a.psychographic.localeCompare(b.psychographic);
    return 0;
  });

  // 3. Determine Columns based on selected Filter
  const isDefaultView = sortOption === 'default' || !sortOption;

  const getMetricHeaderLabel = () => {
    if (sortOption === 'time-spent') return 'Time Spent';
    if (sortOption === 'orders') return 'Orders';
    if (sortOption === 'cart-items') return 'Cart Items';
    if (sortOption === 'likes') return 'Liked Items';
    if (sortOption === 'psychographic') return 'Psychographic';
    return '';
  };

  const isFocusedMode = searchQuery.trim().length > 0;

  return (
    <section className="glass-card" style={{ padding: '32px', transition: 'all 0.3s ease' }}>
      {/* Table Header & Single Sorting Dropdown */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px', flexWrap: 'wrap', gap: '16px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <h3 className="heading-lg" style={{ color: 'var(--text-primary)' }}>
              {isFocusedMode ? 'Focused Customer Mode' : 'Customer Intelligence Directory'}
            </h3>
            {isFocusedMode && (
              <span className="badge badge-emerald">
                {filtered.length} Search Result{filtered.length === 1 ? '' : 's'}
              </span>
            )}
          </div>
          <p className="text-subtle">
            {isFocusedMode 
              ? `Isolated view for "${searchQuery}". Click row to inspect detailed customer behavior.` 
              : 'Click any customer row to view detailed clothing cart, wishlist, and behavioral analysis.'}
          </p>
        </div>

        {/* Single Sorting Dropdown with Highlight */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-secondary)' }}>Sort & View:</span>
          <div style={{ position: 'relative' }}>
            <select
              value={sortOption}
              onChange={(e) => setSortOption(e.target.value)}
              style={{
                appearance: 'none',
                background: !isDefaultView ? 'rgba(79, 70, 229, 0.1)' : 'var(--panel-solid)',
                border: !isDefaultView ? '1.5px solid var(--accent-indigo)' : '1px solid var(--panel-border)',
                borderRadius: 'var(--radius-md)',
                padding: '10px 36px 10px 16px',
                fontSize: '0.875rem',
                fontWeight: 700,
                color: !isDefaultView ? 'var(--accent-indigo)' : 'var(--text-primary)',
                outline: 'none',
                cursor: 'pointer',
                boxShadow: 'var(--panel-shadow)',
                transition: 'all 0.2s ease'
              }}
            >
              <option value="default">Default View (All Columns)</option>
              <option value="time-spent">Time Spent</option>
              <option value="orders">Number of Orders</option>
              <option value="cart-items">Cart Items</option>
              <option value="likes">Likes</option>
              <option value="psychographic">Psychographic</option>
            </select>
            <ChevronDown size={16} style={{ position: 'absolute', right: '12px', top: '50%', transform: 'translateY(-50%)', pointerEvents: 'none', color: !isDefaultView ? 'var(--accent-indigo)' : 'var(--text-muted)' }} />
          </div>
        </div>
      </div>

      {/* Empty State when zero search results match */}
      {sorted.length === 0 ? (
        <div style={{
          padding: '48px 24px',
          textAlign: 'center',
          background: 'var(--table-header-bg)',
          borderRadius: 'var(--radius-lg)',
          border: '1px dashed var(--panel-border)'
        }}>
          <SearchX size={40} style={{ color: 'var(--text-muted)', marginBottom: '12px' }} />
          <h4 className="heading-md" style={{ color: 'var(--text-primary)', marginBottom: '6px' }}>No customer found.</h4>
          <p style={{ fontSize: '0.875rem', color: 'var(--text-subtle)', marginBottom: '18px' }}>
            We couldn't find any customer matching "{searchQuery}".
          </p>
          <button 
            onClick={onClearSearch}
            className="btn btn-primary"
            style={{ padding: '8px 18px', fontSize: '0.85rem' }}
          >
            <RotateCcw size={14} /> Clear Search
          </button>
        </div>
      ) : (
        /* Dynamic Table Container */
        <div style={{ overflowX: 'auto', maxHeight: '480px', overflowY: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'separate', borderSpacing: '0 8px', textAlign: 'left', fontSize: '0.9rem' }}>
            <thead>
              <tr style={{ background: 'var(--table-header-bg)', color: 'var(--text-secondary)' }}>
                <th style={{ padding: '16px 20px', borderRadius: 'var(--radius-md) 0 0 var(--radius-md)', fontWeight: 700 }}>Customer Name</th>
                <th style={{ padding: '16px 16px', fontWeight: 700 }}>Gender</th>

                {/* Render All Columns in Default View */}
                {isDefaultView ? (
                  <>
                    <th style={{ padding: '16px 16px', fontWeight: 700, textAlign: 'center' }}>Orders</th>
                    <th style={{ padding: '16px 16px', fontWeight: 700, textAlign: 'center' }}>Cart Items</th>
                    <th style={{ padding: '16px 16px', fontWeight: 700, textAlign: 'center' }}>Liked Items</th>
                    <th style={{ padding: '16px 16px', fontWeight: 700 }}>Time Spent</th>
                    <th style={{ padding: '16px 20px', borderRadius: '0 var(--radius-md) var(--radius-md) 0', fontWeight: 700 }}>Psychographic</th>
                  </>
                ) : (
                  /* Render ONLY Selected Metric Column in Filter View */
                  <th style={{ padding: '16px 20px', borderRadius: '0 var(--radius-md) var(--radius-md) 0', fontWeight: 700, color: 'var(--accent-indigo)' }}>
                    {getMetricHeaderLabel()}
                  </th>
                )}
              </tr>
            </thead>
            <tbody>
              {sorted.map(cust => (
                <tr 
                  key={cust.id}
                  onClick={() => onSelectCustomer(cust)}
                  style={{
                    background: 'var(--panel-solid)',
                    boxShadow: '0 2px 8px rgba(0,0,0,0.02)',
                    border: '1px solid var(--panel-border)',
                    cursor: 'pointer',
                    transition: 'all 0.18s ease'
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.transform = 'translateY(-1px)';
                    e.currentTarget.style.boxShadow = 'var(--panel-shadow-hover)';
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.transform = 'translateY(0)';
                    e.currentTarget.style.boxShadow = '0 2px 8px rgba(0,0,0,0.02)';
                  }}
                >
                  {/* Column 1: Customer Name */}
                  <td style={{ padding: '18px 20px', borderRadius: 'var(--radius-md) 0 0 var(--radius-md)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
                      <img 
                        src={cust.avatar} 
                        alt={cust.name}
                        style={{ width: '42px', height: '42px', borderRadius: '50%', objectFit: 'cover' }}
                      />
                      <div>
                        <div style={{ fontWeight: 700, color: 'var(--text-primary)', fontSize: '0.95rem' }}>{cust.name}</div>
                        <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{cust.gender || 'Unknown'}{cust.age && cust.age !== '-' ? `, ${cust.age} yrs` : ''}</div>
                      </div>
                    </div>
                  </td>

                  {/* Column 2: Gender */}
                  <td style={{ padding: '18px 16px', color: 'var(--text-secondary)', fontWeight: 600 }}>
                    {cust.gender || 'Unknown'}
                  </td>

                  {/* Render All Columns OR Selected Metric Column */}
                  {isDefaultView ? (
                    <>
                      <td style={{ padding: '18px 16px', textAlign: 'center', fontWeight: 800, color: 'var(--text-primary)', fontSize: '1rem' }}>
                        {cust.order_count ?? cust.orders ?? 0}
                      </td>

                      <td style={{ padding: '18px 16px', textAlign: 'center', fontWeight: 700, color: 'var(--accent-indigo)' }}>
                        <div style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                          <ShoppingBag size={15} />
                          <span>{cust.cartItemsCount}</span>
                        </div>
                      </td>

                      <td style={{ padding: '18px 16px', textAlign: 'center', fontWeight: 700, color: 'var(--accent-rose)' }}>
                        <div style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                          <Heart size={15} />
                          <span>{cust.likedItemsCount}</span>
                        </div>
                      </td>

                      <td style={{ padding: '18px 16px', color: 'var(--text-secondary)' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 600 }}>
                          <Clock size={15} style={{ color: 'var(--accent-indigo)' }} />
                          <span>{cust.timeSpent}</span>
                        </div>
                      </td>

                      <td style={{ padding: '18px 20px', borderRadius: '0 var(--radius-md) var(--radius-md) 0' }}>
                        <span className="badge badge-indigo" style={{ padding: '6px 14px', fontSize: '0.82rem' }}>
                          {cust.psychographic}
                        </span>
                      </td>
                    </>
                  ) : (
                    /* Metric Column Only */
                    <td style={{ padding: '18px 20px', borderRadius: '0 var(--radius-md) var(--radius-md) 0' }}>
                      {sortOption === 'time-spent' && (
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 700, color: 'var(--accent-indigo)', fontSize: '0.95rem' }}>
                          <Clock size={16} />
                          <span>{cust.timeSpent}</span>
                        </div>
                      )}
                      {sortOption === 'orders' && (
                        <div style={{ fontWeight: 800, color: 'var(--text-primary)', fontSize: '1.05rem' }}>
                          {cust.order_count ?? cust.orders ?? 0} Orders
                        </div>
                      )}
                      {sortOption === 'cart-items' && (
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 700, color: 'var(--accent-indigo)', fontSize: '0.95rem' }}>
                          <ShoppingBag size={16} />
                          <span>{cust.cartItemsCount} Cart Items</span>
                        </div>
                      )}
                      {sortOption === 'likes' && (
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 700, color: 'var(--accent-rose)', fontSize: '0.95rem' }}>
                          <Heart size={16} />
                          <span>{cust.likedItemsCount} Liked Items</span>
                        </div>
                      )}
                      {sortOption === 'psychographic' && (
                        <span className="badge badge-indigo" style={{ padding: '6px 14px', fontSize: '0.85rem' }}>
                          {cust.psychographic}
                        </span>
                      )}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
};
