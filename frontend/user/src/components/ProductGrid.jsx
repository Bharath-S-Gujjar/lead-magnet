import React from 'react';
import { ProductCard } from './ProductCard';
import { Shirt, RotateCcw, AlertTriangle, Loader2 } from 'lucide-react';

export const ProductGrid = ({ products, loading, error, onRetry, onResetFilters }) => {
  // 1. Loading State
  if (loading) {
    return (
      <div className="glass-card" style={{ padding: '80px 24px', textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
        <Loader2 size={44} className="spin-animation" style={{ color: 'var(--accent-indigo)', marginBottom: '16px', animation: 'spin 1s linear infinite' }} />
        <h4 className="heading-md" style={{ color: 'var(--text-primary)', marginBottom: '6px' }}>Loading Real Catalog...</h4>
        <p className="text-subtle">Fetching authoritative clothing products from MongoDB</p>
      </div>
    );
  }

  // 2. Error State (Never hide errors as empty state!)
  if (error) {
    return (
      <div className="glass-card" style={{ padding: '60px 24px', textAlign: 'center', border: '1px solid rgba(244, 63, 94, 0.3)', background: 'rgba(244, 63, 94, 0.04)' }}>
        <div style={{
          width: '54px',
          height: '54px',
          borderRadius: '50%',
          background: 'rgba(244, 63, 94, 0.15)',
          color: '#f43f5e',
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          marginBottom: '16px'
        }}>
          <AlertTriangle size={28} />
        </div>
        <h4 className="heading-lg" style={{ color: 'var(--text-primary)', marginBottom: '8px' }}>Unable to Load Products</h4>
        <p className="text-subtle" style={{ maxWidth: '500px', margin: '0 auto 20px', color: 'var(--text-secondary)' }}>
          {error}
        </p>
        <div style={{ display: 'flex', gap: '12px', justifyContent: 'center' }}>
          {onRetry && (
            <button onClick={onRetry} className="btn btn-primary">
              <RotateCcw size={16} /> Retry Connection
            </button>
          )}
          {onResetFilters && (
            <button onClick={onResetFilters} className="btn btn-ghost">
              Reset Filters
            </button>
          )}
        </div>
      </div>
    );
  }

  // 3. Empty State (Honest zero state when filters return 0 matches)
  if (!products || products.length === 0) {
    return (
      <div className="glass-card" style={{ padding: '60px 24px', textAlign: 'center' }}>
        <Shirt size={48} style={{ color: 'var(--text-muted)', marginBottom: '16px' }} />
        <h4 className="heading-lg" style={{ color: 'var(--text-primary)', marginBottom: '8px' }}>No products match your filters</h4>
        <p className="text-subtle" style={{ marginBottom: '20px' }}>Try adjusting your category, price range, brand, or search terms.</p>
        {onResetFilters && (
          <button 
            onClick={onResetFilters}
            className="btn btn-primary"
          >
            <RotateCcw size={16} /> Reset All Filters
          </button>
        )}
      </div>
    );
  }

  // 4. Success State (Render real product cards)
  return (
    <div className="grid-4" style={{ rowGap: '28px', columnGap: '24px' }}>
      {products.map(product => (
        <ProductCard key={product.id || product._id} product={product} />
      ))}
    </div>
  );
};
