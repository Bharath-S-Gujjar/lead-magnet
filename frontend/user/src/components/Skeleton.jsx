import React from 'react';

export const Skeleton = ({ width, height, borderRadius = 'var(--radius-sm, 4px)', className = '', style = {} }) => {
  return (
    <div
      className={`skeleton-loader ${className}`}
      style={{
        width: width || '100%',
        height: height || '20px',
        borderRadius,
        ...style,
      }}
      aria-hidden="true"
    />
  );
};

export const ProductCardSkeleton = () => {
  return (
    <div className="product-card" style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Image Skeleton */}
      <Skeleton height="260px" borderRadius="var(--radius-sm, 4px)" style={{ width: '100%' }} />

      <div style={{ padding: '16px', display: 'flex', flexDirection: 'column', flex: 1, justifyContent: 'space-between', gap: '12px' }}>
        <div>
          {/* Brand & Rating */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
            <Skeleton width="60px" height="14px" />
            <Skeleton width="40px" height="14px" />
          </div>

          {/* Title */}
          <Skeleton width="90%" height="18px" style={{ marginBottom: '6px' }} />
          <Skeleton width="60%" height="18px" style={{ marginBottom: '10px' }} />

          {/* Tags */}
          <div style={{ display: 'flex', gap: '6px' }}>
            <Skeleton width="50px" height="20px" borderRadius="4px" />
            <Skeleton width="65px" height="20px" borderRadius="4px" />
          </div>
        </div>

        <div>
          {/* Price */}
          <Skeleton width="80px" height="24px" style={{ marginBottom: '12px' }} />

          {/* Button */}
          <Skeleton width="100%" height="38px" borderRadius="var(--radius-sm, 4px)" />
        </div>
      </div>
    </div>
  );
};

export const ProductGridSkeleton = ({ count = 8 }) => {
  return (
    <div className="grid-4" style={{ rowGap: '24px', columnGap: '20px' }}>
      {Array.from({ length: count }).map((_, idx) => (
        <ProductCardSkeleton key={idx} />
      ))}
    </div>
  );
};

export const ProductDetailsSkeleton = () => {
  return (
    <div className="product-details-shell" style={{ display: 'grid', gridTemplateColumns: '1fr 1.1fr', gap: '32px', padding: '24px 0' }}>
      {/* Gallery Skeleton */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
        <Skeleton height="460px" borderRadius="var(--radius-md, 6px)" style={{ width: '100%' }} />
        <div style={{ display: 'flex', gap: '10px' }}>
          <Skeleton width="80px" height="80px" borderRadius="4px" />
          <Skeleton width="80px" height="80px" borderRadius="4px" />
          <Skeleton width="80px" height="80px" borderRadius="4px" />
        </div>
      </div>

      {/* Info Skeleton */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
        <Skeleton width="100px" height="16px" />
        <Skeleton width="80%" height="32px" />
        <Skeleton width="120px" height="28px" />
        <Skeleton width="100%" height="60px" />

        {/* Sizes */}
        <div style={{ marginTop: '12px' }}>
          <Skeleton width="80px" height="16px" style={{ marginBottom: '8px' }} />
          <div style={{ display: 'flex', gap: '8px' }}>
            <Skeleton width="44px" height="40px" borderRadius="4px" />
            <Skeleton width="44px" height="40px" borderRadius="4px" />
            <Skeleton width="44px" height="40px" borderRadius="4px" />
            <Skeleton width="44px" height="40px" borderRadius="4px" />
          </div>
        </div>

        {/* Action Button */}
        <div style={{ display: 'flex', gap: '12px', marginTop: '16px' }}>
          <Skeleton width="110px" height="44px" borderRadius="4px" />
          <Skeleton width="100%" height="44px" borderRadius="4px" />
        </div>
      </div>
    </div>
  );
};

export default Skeleton;
