import React from 'react';
import { ProductCard } from './ProductCard';
import { ProductGridSkeleton } from './Skeleton';
import { PurchasedProductRecommendations } from './PurchasedProductRecommendations';

export const ProductGrid = ({ products, loading, error, onRetry, onResetFilters }) => {
  // 1. Skeletal Loading State
  if (loading) {
    return <ProductGridSkeleton count={8} />;
  }

  // 2. Error State
  if (error) {
    return (
      <div className="product-card" style={{ padding: '48px 24px', textAlign: 'center', border: '1px solid var(--color-tertiary, #CC5500)' }}>
        <h4 style={{ fontSize: '1.2rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '8px' }}>
          Unable to Load Products
        </h4>
        <p style={{ maxWidth: '460px', margin: '0 auto 18px', color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
          {error}
        </p>
        <div style={{ display: 'flex', gap: '10px', justifyContent: 'center' }}>
          {onRetry && (
            <button onClick={onRetry} className="btn btn-primary">
              Retry Connection
            </button>
          )}
          {onResetFilters && (
            <button onClick={onResetFilters} className="btn btn-secondary">
              Reset Filters
            </button>
          )}
        </div>
      </div>
    );
  }

  // 3. Empty State
  if (!products || products.length === 0) {
    return (
      <div className="product-card" style={{ padding: '48px 24px', textAlign: 'center' }}>
        <h4 style={{ fontSize: '1.2rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '8px' }}>
          No products match your filters
        </h4>
        <p style={{ marginBottom: '18px', color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
          Try adjusting your category, price range, brand, or search terms.
        </p>
        {onResetFilters && (
          <button 
            onClick={onResetFilters}
            className="btn btn-primary"
          >
            Reset All Filters
          </button>
        )}
      </div>
    );
  }

  // 4. Success State (Render first 2 rows, then post-purchase recommendations, then remaining products)
  const firstTwoRows = products.slice(0, 8);
  const remainingProducts = products.slice(8);

  return (
    <div className="product-catalog-flow">
      {/* First 2 rows of products (4-column grid = 8 items) */}
      <div className="grid-4" style={{ rowGap: '24px', columnGap: '20px' }}>
        {firstTwoRows.map(product => (
          <ProductCard key={product.id || product._id} product={product} />
        ))}
      </div>

      {/* Post-Purchase Recommendations: displayed strictly after 2 rows of products */}
      <PurchasedProductRecommendations />

      {/* Remaining products continuation */}
      {remainingProducts.length > 0 && (
        <div className="grid-4" style={{ rowGap: '24px', columnGap: '20px' }}>
          {remainingProducts.map(product => (
            <ProductCard key={product.id || product._id} product={product} />
          ))}
        </div>
      )}
    </div>
  );
};

export default ProductGrid;
