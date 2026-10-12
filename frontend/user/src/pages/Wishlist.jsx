import React from 'react';
import { Link } from 'react-router-dom';
import { useWishlist } from '../context/WishlistContext';
import { useCart } from '../context/CartContext';
import { WishlistHeartButton } from '../components/WishlistHeartButton';
import { getOptimizedImageUrl } from '../utils/imageOptimizer';

export const Wishlist = () => {
  const { wishlist, removeFromWishlist } = useWishlist();
  const { addToCart } = useCart();

  const handleMoveToCart = (product) => {
    addToCart(product);
    removeFromWishlist(product.id || product._id);
  };

  if (wishlist.length === 0) {
    return (
      <div className="product-card" style={{ padding: '48px 24px', textAlign: 'center', maxWidth: '540px', margin: '40px auto' }}>
        <h3 style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '8px' }}>
          Your Wishlist is Empty
        </h3>
        <p style={{ color: 'var(--text-secondary)', marginBottom: '20px', fontSize: '0.9rem' }}>
          Save your favorite clothing items here for quick access later.
        </p>
        <Link to="/" className="btn btn-primary">
          Explore Clothing Store
        </Link>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2 style={{ fontSize: '1.4rem', fontWeight: 700, color: 'var(--text-primary)' }}>
          My Saved Wishlist ({wishlist.length} items)
        </h2>
      </div>

      <div className="grid-4" style={{ gap: '20px' }}>
        {wishlist.map(product => (
          <div key={product.id || product._id} className="product-card" style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '12px', position: 'relative' }}>
            <div style={{ position: 'relative', width: '100%', height: '220px', borderRadius: 'var(--radius-sm, 4px)', overflow: 'hidden' }}>
              <img
                src={getOptimizedImageUrl(product.image, 400, 75)}
                alt={product.name}
                loading="lazy"
                decoding="async"
                style={{ width: '100%', height: '100%', objectFit: 'cover' }}
              />
              <div
                style={{
                  position: 'absolute',
                  top: '8px',
                  right: '8px',
                  zIndex: 10,
                  background: 'transparent',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                <WishlistHeartButton
                  isLiked={true}
                  onToggle={() => removeFromWishlist(product.id || product._id)}
                  size={36}
                  heartColor="var(--color-tertiary, #CC5500)"
                />
              </div>
            </div>

            <div>
              <span style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--color-primary-dark, #6f805e)', textTransform: 'uppercase' }}>
                {product.brand}
              </span>
              <h4 style={{ fontWeight: 600, fontSize: '0.92rem', color: 'var(--text-primary)', margin: '2px 0 6px' }}>
                {product.name}
              </h4>
              <div style={{ fontWeight: 700, fontSize: '1.1rem', color: 'var(--text-primary)' }}>
                ₹{Number(product.price || 0).toLocaleString('en-IN')}
              </div>
            </div>

            <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
              <button
                onClick={() => handleMoveToCart(product)}
                className="btn btn-primary"
                style={{ flex: 1, padding: '8px 12px', fontSize: '0.82rem' }}
              >
                Move to Cart
              </button>

              <button
                onClick={() => removeFromWishlist(product.id || product._id)}
                className="btn btn-secondary"
                style={{ padding: '8px 10px', color: 'var(--color-tertiary, #CC5500)' }}
                title="Remove"
                aria-label="Remove"
              >
                ✕
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default Wishlist;
