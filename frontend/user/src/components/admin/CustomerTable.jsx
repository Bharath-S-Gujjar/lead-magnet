import React from 'react';

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
    <section style={{ padding: '24px', background: 'var(--panel-solid)', border: '1px solid var(--panel-border)', borderRadius: '4px' }}>
      {/* Table Header & Single Sorting Dropdown */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px', flexWrap: 'wrap', gap: '16px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <h3 className="heading-lg" style={{ color: 'var(--text-primary)' }}>
              {isFocusedMode ? 'Focused Customer View' : 'Customer Intelligence Directory'}
            </h3>
            {isFocusedMode && (
              <span className="badge badge-primary">
                {filtered.length} Result{filtered.length === 1 ? '' : 's'}
              </span>
            )}
          </div>
          <p className="text-subtle">
            {isFocusedMode
              ? `Filtered view for "${searchQuery}". Click row to inspect detailed customer behavior.`
              : 'Click any customer row to view detailed clothing cart, wishlist, and behavioral analysis.'}
          </p>
        </div>

        {/* Sorting Dropdown */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-secondary)' }}>Sort:</span>
          <select
            value={sortOption}
            onChange={(e) => setSortOption(e.target.value)}
            style={{
              background: 'var(--bg-app)',
              border: '1px solid var(--panel-border)',
              borderRadius: '4px',
              padding: '8px 14px',
              fontSize: '0.85rem',
              fontWeight: 600,
              color: 'var(--text-primary)',
              outline: 'none',
              cursor: 'pointer'
            }}
          >
            <option value="default">Default View (All Columns)</option>
            <option value="time-spent">Time Spent</option>
            <option value="orders">Number of Orders</option>
            <option value="cart-items">Cart Items</option>
            <option value="likes">Likes</option>
            <option value="psychographic">Psychographic</option>
          </select>
        </div>
      </div>

      {/* Empty State */}
      {sorted.length === 0 ? (
        <div style={{
          padding: '40px 20px',
          textAlign: 'center',
          background: 'var(--bg-app)',
          borderRadius: '4px',
          border: '1px dashed var(--panel-border)'
        }}>
          <h4 className="heading-md" style={{ color: 'var(--text-primary)', marginBottom: '6px' }}>No customers match your query.</h4>
          <p style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', marginBottom: '16px' }}>
            We could not find any customer matching "{searchQuery}".
          </p>
          <button
            onClick={onClearSearch}
            className="btn btn-primary"
            style={{ padding: '8px 18px', fontSize: '0.85rem', borderRadius: '4px' }}
          >
            Clear Search
          </button>
        </div>
      ) : (
        /* Table Container */
        <div style={{ overflowX: 'auto', maxHeight: '480px', overflowY: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'separate', borderSpacing: '0 6px', textAlign: 'left', fontSize: '0.875rem' }}>
            <thead>
              <tr style={{ background: 'var(--table-header-bg)', color: 'var(--text-secondary)' }}>
                <th style={{ padding: '12px 16px', fontWeight: 700 }}>Customer Name</th>
                <th style={{ padding: '12px 14px', fontWeight: 700 }}>Gender</th>

                {isDefaultView ? (
                  <>
                    <th style={{ padding: '12px 14px', fontWeight: 700, textAlign: 'center' }}>Orders</th>
                    <th style={{ padding: '12px 14px', fontWeight: 700, textAlign: 'center' }}>Cart</th>
                    <th style={{ padding: '12px 14px', fontWeight: 700, textAlign: 'center' }}>Likes</th>
                    <th style={{ padding: '12px 14px', fontWeight: 700 }}>Time Spent</th>
                    <th style={{ padding: '12px 16px', fontWeight: 700 }}>Psychographic</th>
                  </>
                ) : (
                  <th style={{ padding: '12px 16px', fontWeight: 700, color: 'var(--brand-tertiary)' }}>
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
                    border: '1px solid var(--panel-border)',
                    cursor: 'pointer'
                  }}
                >
                  <td style={{ padding: '14px 16px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                      <img
                        src={cust.avatar}
                        alt={cust.name}
                        loading="lazy"
                        decoding="async"
                        style={{ width: '36px', height: '36px', borderRadius: '4px', objectFit: 'cover' }}
                      />
                      <div>
                        <div style={{ fontWeight: 700, color: 'var(--text-primary)', fontSize: '0.9rem' }}>{cust.name}</div>
                        <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>{cust.gender || 'Unknown'}{cust.age && cust.age !== '-' ? `, ${cust.age} yrs` : ''}</div>
                      </div>
                    </div>
                  </td>

                  <td style={{ padding: '14px', color: 'var(--text-secondary)', fontWeight: 600 }}>
                    {cust.gender || 'Unknown'}
                  </td>

                  {isDefaultView ? (
                    <>
                      <td style={{ padding: '14px', textAlign: 'center', fontWeight: 700, color: 'var(--text-primary)' }}>
                        {cust.order_count ?? cust.orders ?? 0}
                      </td>

                      <td style={{ padding: '14px', textAlign: 'center', fontWeight: 700, color: 'var(--brand-primary)' }}>
                        {cust.cartItemsCount}
                      </td>

                      <td style={{ padding: '14px', textAlign: 'center', fontWeight: 700, color: 'var(--brand-tertiary)' }}>
                        {cust.likedItemsCount}
                      </td>

                      <td style={{ padding: '14px', color: 'var(--text-secondary)', fontWeight: 600 }}>
                        {cust.timeSpent}
                      </td>

                      <td style={{ padding: '14px 16px' }}>
                        <span className="badge badge-primary">
                          {cust.psychographic}
                        </span>
                      </td>
                    </>
                  ) : (
                    <td style={{ padding: '14px 16px' }}>
                      {sortOption === 'time-spent' && (
                        <div style={{ fontWeight: 700, color: 'var(--brand-primary)' }}>
                          {cust.timeSpent}
                        </div>
                      )}
                      {sortOption === 'orders' && (
                        <div style={{ fontWeight: 800, color: 'var(--text-primary)' }}>
                          {cust.order_count ?? cust.orders ?? 0} Orders
                        </div>
                      )}
                      {sortOption === 'cart-items' && (
                        <div style={{ fontWeight: 700, color: 'var(--brand-primary)' }}>
                          {cust.cartItemsCount} Cart Items
                        </div>
                      )}
                      {sortOption === 'likes' && (
                        <div style={{ fontWeight: 700, color: 'var(--brand-tertiary)' }}>
                          {cust.likedItemsCount} Liked Items
                        </div>
                      )}
                      {sortOption === 'psychographic' && (
                        <span className="badge badge-primary">
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
