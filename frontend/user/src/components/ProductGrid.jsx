import React from 'react';
import { ProductCard } from './ProductCard';
import { Shirt, RotateCcw } from 'lucide-react';

export const ProductGrid = ({ products, onResetFilters }) => {
  if (!products || products.length === 0) {
    return (
      <div className="glass-card" style={{ padding: '60px 24px', textAlign: 'center' }}>
        <Shirt size={48} style={{ color: 'var(--text-muted)', marginBottom: '16px' }} />
        <h4 className="heading-lg" style={{ color: 'var(--text-primary)', marginBottom: '8px' }}>No products available</h4>
        <p className="text-subtle" style={{ marginBottom: '20px' }}>Products added from the backend will automatically appear here in this card layout.</p>
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

  return (
    <div className="grid-4" style={{ rowGap: '28px', columnGap: '24px' }}>
      {products.map(product => (
        <ProductCard key={product.id} product={product} />
      ))}
    </div>
  );
};
