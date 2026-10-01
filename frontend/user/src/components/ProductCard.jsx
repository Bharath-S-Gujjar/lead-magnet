import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Heart, ShoppingBag, Star, Shirt, Sparkles } from 'lucide-react';
import { useCart } from '../context/CartContext';
import { useWishlist } from '../context/WishlistContext';

export const ProductCard = ({ product }) => {
  const navigate = useNavigate();
  const { addToCart } = useCart();
  const { toggleWishlist, isInWishlist } = useWishlist();
  const [imgFailed, setImgFailed] = useState(false);

  const isLiked = isInWishlist(product.id);

  const handleCardClick = (e) => {
    // Avoid triggering card navigation when clicking buttons
    if (e.target.closest('button')) return;
    navigate(`/product/${product.id}`);
  };

  const hasRealImage = product.image && !product.image.includes('placeholder.com') && !imgFailed;

  // Curated gradient pairs based on gender and category
  const getFallbackGradient = () => {
    const g = (product.gender || '').toLowerCase();
    if (g === 'women') return 'linear-gradient(135deg, #fce7f3 0%, #ede9fe 100%)';
    if (g === 'kids') return 'linear-gradient(135deg, #fef3c7 0%, #e0e7ff 100%)';
    return 'linear-gradient(135deg, #e0e7ff 0%, #f1f5f9 100%)';
  };

  return (
    <div 
      className="glass-card" 
      onClick={handleCardClick}
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        overflow: 'hidden',
        cursor: 'pointer',
        position: 'relative'
      }}
    >
      {/* Product Image Box */}
      <div style={{ position: 'relative', width: '100%', paddingTop: '110%', overflow: 'hidden', background: getFallbackGradient() }}>
        {hasRealImage ? (
          <img 
            src={product.image} 
            alt={product.name} 
            onError={() => setImgFailed(true)}
            style={{
              position: 'absolute',
              inset: 0,
              width: '100%',
              height: '100%',
              objectFit: 'cover',
              transition: 'transform 0.4s ease'
            }}
            onMouseEnter={(e) => e.currentTarget.style.transform = 'scale(1.06)'}
            onMouseLeave={(e) => e.currentTarget.style.transform = 'scale(1.0)'}
          />
        ) : (
          <div style={{
            position: 'absolute',
            inset: 0,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '16px',
            textAlign: 'center',
          }}>
            <div style={{
              width: '54px',
              height: '54px',
              borderRadius: '50%',
              background: 'rgba(255, 255, 255, 0.85)',
              backdropFilter: 'blur(8px)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: 'var(--accent-indigo)',
              boxShadow: '0 4px 14px rgba(79, 70, 229, 0.15)',
              marginBottom: '10px'
            }}>
              <Shirt size={28} />
            </div>
            <span style={{ fontSize: '0.75rem', fontWeight: 800, color: 'var(--accent-indigo)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              {product.brand}
            </span>
            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', fontWeight: 600, marginTop: '2px' }}>
              {product.category}
            </span>
          </div>
        )}

        {/* Discount Badge */}
        {product.discount > 0 && (
          <div style={{
            position: 'absolute',
            top: '12px',
            left: '12px',
            background: 'var(--accent-rose)',
            color: 'white',
            fontWeight: 800,
            fontSize: '0.75rem',
            padding: '3px 9px',
            borderRadius: 'var(--radius-full)',
            boxShadow: '0 2px 8px rgba(244, 63, 94, 0.4)'
          }}>
            {product.discount}% OFF
          </div>
        )}

        {/* Wishlist Heart Toggle Button */}
        <button
          onClick={(e) => {
            e.stopPropagation();
            toggleWishlist(product);
          }}
          style={{
            position: 'absolute',
            top: '12px',
            right: '12px',
            width: '36px',
            height: '36px',
            borderRadius: '50%',
            background: 'rgba(255, 255, 255, 0.85)',
            backdropFilter: 'blur(8px)',
            border: 'none',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            cursor: 'pointer',
            boxShadow: '0 4px 12px rgba(0,0,0,0.1)',
            transition: 'transform 0.2s ease'
          }}
          title={isLiked ? "Remove from Wishlist" : "Add to Wishlist"}
        >
          <Heart size={18} fill={isLiked ? '#f43f5e' : 'none'} color={isLiked ? '#f43f5e' : '#64748b'} />
        </button>
      </div>

      {/* Product Content Body */}
      <div style={{ padding: '18px', display: 'flex', flexDirection: 'column', flex: 1, justifyContent: 'space-between' }}>
        <div>
          {/* Brand & Rating Row */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
            <span style={{ fontSize: '0.78rem', fontWeight: 800, color: 'var(--accent-indigo)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
              {product.brand}
            </span>
            <div style={{ display: 'flex', alignItems: 'center', gap: '3px', fontSize: '0.8rem', fontWeight: 700, color: 'var(--accent-amber)' }}>
              <Star size={13} fill="#f59e0b" />
              <span>{product.rating}</span>
            </div>
          </div>

          {/* Product Name */}
          <h4 style={{ fontSize: '0.98rem', fontWeight: 700, color: 'var(--text-primary)', lineHeight: 1.3, marginBottom: '8px', minHeight: '2.6em' }}>
            {product.name}
          </h4>

          {/* Gender & Category Tags */}
          <div style={{ display: 'flex', gap: '6px', marginBottom: '12px', flexWrap: 'wrap' }}>
            <span className="badge badge-indigo">{product.gender}</span>
            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', fontWeight: 600, background: 'rgba(148, 163, 184, 0.1)', padding: '2px 8px', borderRadius: 'var(--radius-full)' }}>
              {product.category}
            </span>
          </div>
        </div>

        <div>
          {/* Price Row */}
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', marginBottom: '14px' }}>
            <span style={{ fontFamily: 'var(--font-heading)', fontSize: '1.25rem', fontWeight: 800, color: 'var(--text-primary)' }}>
              ₹{product.price.toLocaleString('en-IN')}
            </span>
            {product.originalPrice && (
              <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)', textDecoration: 'line-through' }}>
                ₹{product.originalPrice.toLocaleString('en-IN')}
              </span>
            )}
          </div>

          {/* Add to Cart Button */}
          <button
            onClick={(e) => {
              e.stopPropagation();
              addToCart(product);
            }}
            className="btn btn-primary"
            style={{ width: '100%', padding: '10px', fontSize: '0.85rem' }}
          >
            <ShoppingBag size={16} /> Add to Cart
          </button>
        </div>
      </div>
    </div>
  );
};
