import React from 'react';
import { Target, Flame, Clock, Mail, ChevronLeft, ChevronRight, SearchX, RotateCcw, ArrowUpDown } from 'lucide-react';

export const CustomerTable = ({
  leadsData,
  isLoading,
  onSelectCustomer,
  qualificationFilter,
  setQualificationFilter,
  segmentFilter,
  setSegmentFilter,
  sortBy,
  setSortBy,
  sortOrder,
  setSortOrder,
  page,
  setPage,
  searchQuery,
  onClearSearch,
}) => {
  const items = leadsData?.items || [];
  const total = leadsData?.total || 0;
  const pages = leadsData?.pages || 0;

  // Filter items by searchQuery if provided locally
  const filteredItems = items.filter(item => {
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    return (
      (item.name && item.name.toLowerCase().includes(q)) ||
      (item.email && item.email.toLowerCase().includes(q)) ||
      (item.lead_segment && item.lead_segment.toLowerCase().includes(q))
    );
  });

  const getSegmentBadge = (segment) => {
    if (segment === 'Hot') return <span className="badge badge-rose" style={{ padding: '4px 10px', fontSize: '0.8rem', display: 'inline-flex', alignItems: 'center', gap: '4px' }}><Flame size={13} /> Hot</span>;
    if (segment === 'Warm') return <span className="badge badge-indigo" style={{ padding: '4px 10px', fontSize: '0.8rem' }}>Warm</span>;
    return <span className="badge badge-subtle" style={{ padding: '4px 10px', fontSize: '0.8rem' }}>Cold</span>;
  };

  const getQualificationBadge = (status) => {
    if (status === 'qualified') return <span className="badge badge-emerald">Qualified</span>;
    return <span className="badge badge-subtle">Not Qualified</span>;
  };

  return (
    <section className="glass-card" style={{ padding: '32px', transition: 'all 0.3s ease' }}>
      {/* Header & Controls Bar */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px', flexWrap: 'wrap', gap: '16px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <h3 className="heading-lg" style={{ color: 'var(--text-primary)' }}>
              Customer Intelligence Directory
            </h3>
            <span className="badge badge-indigo">
              {total} Customer{total === 1 ? '' : 's'}
            </span>
          </div>
          <p className="text-subtle">
            Customer-level lead directory. Click any customer row to open full behavioral deep-dive & audit drawer.
          </p>
        </div>

        {/* Filter & Sort Controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
          {/* Qualification Status Filter */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-secondary)' }}>Status:</span>
            <select
              value={qualificationFilter}
              onChange={(e) => {
                setQualificationFilter(e.target.value);
                setPage(1);
              }}
              className="select-input"
              style={{
                background: 'var(--panel-solid)',
                border: '1px solid var(--panel-border)',
                borderRadius: 'var(--radius-md)',
                padding: '8px 12px',
                fontSize: '0.85rem',
                fontWeight: 600,
                color: 'var(--text-primary)',
                outline: 'none',
                cursor: 'pointer'
              }}
            >
              <option value="qualified">Qualified Only</option>
              <option value="not_qualified">Not Qualified Only</option>
              <option value="all">All Statuses</option>
            </select>
          </div>

          {/* Segment Filter */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-secondary)' }}>Segment:</span>
            <select
              value={segmentFilter}
              onChange={(e) => {
                setSegmentFilter(e.target.value);
                setPage(1);
              }}
              style={{
                background: 'var(--panel-solid)',
                border: '1px solid var(--panel-border)',
                borderRadius: 'var(--radius-md)',
                padding: '8px 12px',
                fontSize: '0.85rem',
                fontWeight: 600,
                color: 'var(--text-primary)',
                outline: 'none',
                cursor: 'pointer'
              }}
            >
              <option value="all">All Segments</option>
              <option value="Hot">Hot Leads</option>
              <option value="Warm">Warm Leads</option>
              <option value="Cold">Cold Leads</option>
            </select>
          </div>

          {/* Sort By Field */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-secondary)' }}>Sort:</span>
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value)}
              style={{
                background: 'var(--panel-solid)',
                border: '1px solid var(--panel-border)',
                borderRadius: 'var(--radius-md)',
                padding: '8px 12px',
                fontSize: '0.85rem',
                fontWeight: 600,
                color: 'var(--text-primary)',
                outline: 'none',
                cursor: 'pointer'
              }}
            >
              <option value="lead_score">Lead Score</option>
              <option value="lead_probability">Lead Probability</option>
              <option value="last_scored_at">Last Scored</option>
              <option value="first_qualified_at">First Qualified</option>
            </select>
          </div>

          {/* Sort Order Button */}
          <button
            onClick={() => setSortOrder(sortOrder === 'desc' ? 'asc' : 'desc')}
            className="btn btn-ghost"
            title={`Sort Order: ${sortOrder.toUpperCase()}`}
            style={{ padding: '8px 12px', fontSize: '0.82rem', display: 'flex', alignItems: 'center', gap: '4px' }}
          >
            <ArrowUpDown size={14} />
            <span>{sortOrder.toUpperCase()}</span>
          </button>
        </div>
      </div>

      {/* Table Content or Loading State */}
      {isLoading ? (
        <div style={{ padding: '48px 24px', textAlign: 'center', color: 'var(--text-muted)' }}>
          Loading customer intelligence directory...
        </div>
      ) : filteredItems.length === 0 ? (
        <div style={{
          padding: '48px 24px',
          textAlign: 'center',
          background: 'var(--table-header-bg)',
          borderRadius: 'var(--radius-lg)',
          border: '1px dashed var(--panel-border)'
        }}>
          <SearchX size={40} style={{ color: 'var(--text-muted)', marginBottom: '12px' }} />
          <h4 className="heading-md" style={{ color: 'var(--text-primary)', marginBottom: '6px' }}>
            {searchQuery ? 'No matching customer found' : 'No qualified leads yet'}
          </h4>
          <p style={{ fontSize: '0.875rem', color: 'var(--text-subtle)', marginBottom: '18px' }}>
            {searchQuery
              ? `No customer in the current view matches "${searchQuery}".`
              : 'As customers interact with the store and meet qualification thresholds, their profiles will appear here.'}
          </p>
          {searchQuery && (
            <button
              onClick={onClearSearch}
              className="btn btn-primary"
              style={{ padding: '8px 18px', fontSize: '0.85rem' }}
            >
              <RotateCcw size={14} /> Clear Search
            </button>
          )}
        </div>
      ) : (
        <>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'separate', borderSpacing: '0 8px', textAlign: 'left', fontSize: '0.9rem' }}>
              <thead>
                <tr style={{ background: 'var(--table-header-bg)', color: 'var(--text-secondary)' }}>
                  <th style={{ padding: '16px 20px', borderRadius: 'var(--radius-md) 0 0 var(--radius-md)', fontWeight: 700 }}>Customer</th>
                  <th style={{ padding: '16px 16px', fontWeight: 700, textAlign: 'center' }}>Lead Score</th>
                  <th style={{ padding: '16px 16px', fontWeight: 700, textAlign: 'center' }}>Segment</th>
                  <th style={{ padding: '16px 16px', fontWeight: 700, textAlign: 'center' }}>Status</th>
                  <th style={{ padding: '16px 16px', fontWeight: 700 }}>Last Scored</th>
                  <th style={{ padding: '16px 20px', borderRadius: '0 var(--radius-md) var(--radius-md) 0', fontWeight: 700 }}>Last Communication</th>
                </tr>
              </thead>
              <tbody>
                {filteredItems.map(item => (
                  <tr
                    key={item.customer_id}
                    onClick={() => onSelectCustomer(item.customer_id)}
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
                    {/* Customer Info */}
                    <td style={{ padding: '16px 20px', borderRadius: 'var(--radius-md) 0 0 var(--radius-md)' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                        <div style={{
                          width: '40px',
                          height: '40px',
                          borderRadius: '50%',
                          background: 'linear-gradient(135deg, var(--accent-indigo), #8b5cf6)',
                          color: '#ffffff',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          fontWeight: 700,
                          fontSize: '0.95rem'
                        }}>
                          {(item.name || 'C').charAt(0).toUpperCase()}
                        </div>
                        <div>
                          <div style={{ fontWeight: 700, color: 'var(--text-primary)', fontSize: '0.95rem' }}>{item.name}</div>
                          <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>{item.email || 'No email registered'}</div>
                        </div>
                      </div>
                    </td>

                    {/* Lead Score & Prob */}
                    <td style={{ padding: '16px 16px', textAlign: 'center' }}>
                      <div style={{ display: 'inline-flex', flexDirection: 'column', alignItems: 'center' }}>
                        <span style={{ fontFamily: 'var(--font-heading)', fontSize: '1.2rem', fontWeight: 800, color: 'var(--accent-indigo)' }}>
                          {item.lead_score !== null && item.lead_score !== undefined ? item.lead_score : 'N/A'}
                        </span>
                        <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                          {item.lead_probability !== null && item.lead_probability !== undefined ? `${(item.lead_probability * 100).toFixed(1)}%` : ''}
                        </span>
                      </div>
                    </td>

                    {/* Segment */}
                    <td style={{ padding: '16px 16px', textAlign: 'center' }}>
                      {getSegmentBadge(item.lead_segment)}
                    </td>

                    {/* Qualification Status */}
                    <td style={{ padding: '16px 16px', textAlign: 'center' }}>
                      {getQualificationBadge(item.qualification_status)}
                    </td>

                    {/* Last Scored */}
                    <td style={{ padding: '16px 16px', color: 'var(--text-secondary)' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.82rem' }}>
                        <Clock size={14} style={{ color: 'var(--text-muted)' }} />
                        <span>{item.last_scored_at ? new Date(item.last_scored_at).toLocaleDateString() : 'N/A'}</span>
                      </div>
                    </td>

                    {/* Last Communication */}
                    <td style={{ padding: '16px 20px', borderRadius: '0 var(--radius-md) var(--radius-md) 0' }}>
                      {item.communication_status ? (
                        <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                          <span style={{ fontWeight: 600, textTransform: 'capitalize' }}>{item.communication_status.last_channel}:</span>{' '}
                          <span className={`badge ${item.communication_status.last_status === 'sent' ? 'badge-emerald' : 'badge-subtle'}`} style={{ padding: '2px 8px', fontSize: '0.75rem' }}>
                            {item.communication_status.last_status}
                          </span>
                        </div>
                      ) : (
                        <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>None attempted</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination Controls */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '20px', paddingTop: '16px', borderTop: '1px solid var(--panel-border)' }}>
            <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
              Showing Page <strong>{page}</strong> of <strong>{pages || 1}</strong> ({total} total records)
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <button
                onClick={() => setPage(page - 1)}
                disabled={page <= 1}
                className="btn btn-ghost"
                style={{ padding: '8px 14px', fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: '4px' }}
              >
                <ChevronLeft size={16} /> Previous
              </button>
              <button
                onClick={() => setPage(page + 1)}
                disabled={page >= pages}
                className="btn btn-ghost"
                style={{ padding: '8px 14px', fontSize: '0.85rem', display: 'flex', alignItems: 'center', gap: '4px' }}
              >
                Next <ChevronRight size={16} />
              </button>
            </div>
          </div>
        </>
      )}
    </section>
  );
};
