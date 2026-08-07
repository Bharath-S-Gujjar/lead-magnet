import React from 'react';
import { Link } from 'react-router-dom';
import { Heart, ShoppingBag, Trash2, ArrowLeft } from 'lucide-react';
import { useWishlist } from '../context/WishlistContext';
import { useCart } from '../context/CartContext';

export const Wishlist = () => {
  const { wishlist, removeFromWishlist } = useWishlist();
  const { addToCart } = useCart();

  const handleMoveToCart = (product) => {
    addToCart(product);
    removeFromWishlist(product.id);
  };

  if (wishlist.length === 0) {
    return (
      <div className="glass-card" style={{ padding: '60px 24px', textAlign: 'center', maxWidth: '600px', margin: '40px auto' }}>
        <Heart size={54} style={{ color: 'var(--text-muted)', marginBottom: '16px' }} />
        <h3 className="heading-lg" style={{ color: 'var(--text-primary)', marginBottom: '8px' }}>Your Wishlist is Empty</h3>
        <p className="text-subtle" style={{ marginBottom: '24px' }}>Save your favorite clothing items here for quick access later.</p>
        <Link to="/" className="btn btn-primary">
          <ArrowLeft size={16} /> Explore Clothing Store
        </Link>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2 className="heading-xl" style={{ color: 'var(--text-primary)' }}>
          My Saved Wishlist ({wishlist.length} items)
        </h2>
      </div>

      <div className="grid-4" style={{ gap: '24px' }}>
        {wishlist.map(product => (
          <div key={product.id} className="glass-card" style={{ padding: '18px', display: 'flex', flexDirection: 'column', gap: '14px' }}>
            <img 
              src={product.image} 
              alt={product.name} 
              style={{ width: '100%', height: '240px', borderRadius: 'var(--radius-md)', objectFit: 'cover' }}
            />

            <div>
              <span style={{ fontSize: '0.75rem', fontWeight: 800, color: 'var(--accent-indigo)', textTransform: 'uppercase' }}>
                {product.brand}
              </span>
              <h4 style={{ fontWeight: 700, fontSize: '0.95rem', color: 'var(--text-primary)', margin: '2px 0 6px' }}>
                {product.name}
              </h4>
              <div style={{ fontFamily: 'var(--font-heading)', fontWeight: 800, fontSize: '1.1rem', color: 'var(--text-primary)' }}>
                ₹{product.price.toLocaleString('en-IN')}
              </div>
            </div>

            <div style={{ display: 'flex', gap: '8px' }}>
              <button 
                onClick={() => handleMoveToCart(product)}
                className="btn btn-primary"
                style={{ flex: 1, padding: '9px', fontSize: '0.82rem' }}
              >
                <ShoppingBag size={15} /> Move to Cart
              </button>

              <button 
                onClick={() => removeFromWishlist(product.id)}
                className="btn btn-secondary"
                style={{ padding: '9px', color: 'var(--accent-rose)' }}
                title="Remove"
              >
                <Trash2 size={16} />
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
