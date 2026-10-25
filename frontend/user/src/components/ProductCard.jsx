import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useCart } from '../context/CartContext';
import { useWishlist } from '../context/WishlistContext';
import { AddToCartButton } from './AddToCartButton';
import { WishlistHeartButton } from './WishlistHeartButton';
import { getOptimizedImageUrl } from '../utils/imageOptimizer';
import { trackCustomerEvent } from '../services/api';

export const ProductCard = ({ product }) => {
  const navigate = useNavigate();
  const { addToCart } = useCart();
  const { toggleWishlist, isInWishlist } = useWishlist();
  const [imgFailed, setImgFailed] = useState(false);
  const [addedAnim, setAddedAnim] = useState(false);

  const isLiked = isInWishlist(product.id || product._id);

  const prodImage = product.primary_image || product.image;
  const prodTitle = product.title || product.name || 'Clothing Item';

  const handleCardClick = (e) => {
    if (e.target.closest('button')) return;
    trackCustomerEvent('product_click', {
      page: window.location.hash.replace('#', '') || '/',
      entity: {
        id: product.id || product._id,
        title: prodTitle,
        category: product.category,
        brand: product.brand,
        price: product.price,
      },
    });
    navigate(`/product/${product.id || product._id}`);
  };

  const handleAddToCart = (e) => {
    e.stopPropagation();
    addToCart(product);
    setAddedAnim(true);
    setTimeout(() => setAddedAnim(false), 1200);
  };

  const discountVal = product.discount_percent || product.discount || 0;
  const hasRealImage = prodImage && !prodImage.includes('placeholder.com') && !imgFailed;

  return (
    <div
      className="product-card"
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
      <div style={{ position: 'relative', width: '100%', paddingTop: '110%', overflow: 'hidden', background: 'var(--table-header-bg, #ecefe9)' }}>
        {hasRealImage ? (
          <img
            src={getOptimizedImageUrl(prodImage, 500, 75)}
            alt={prodTitle}
            loading="lazy"
            decoding="async"
            onError={() => setImgFailed(true)}
            style={{
              position: 'absolute',
              inset: 0,
              width: '100%',
              height: '100%',
              objectFit: 'cover'
            }}
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
            <span style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--color-primary, #9CAF88)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
              {product.brand}
            </span>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 600, marginTop: '4px' }}>
              {product.category}
            </span>
          </div>
        )}

        {/* Wishlist Heart Toggle Button */}
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
          onClick={(e) => e.stopPropagation()}
        >
          <WishlistHeartButton
            isLiked={isLiked}
            onToggle={() => toggleWishlist(product)}
            size={36}
            heartColor="var(--color-tertiary, #CC5500)"
          />
        </div>
      </div>

      {/* Product Content Body */}
      <div style={{ padding: '16px', display: 'flex', flexDirection: 'column', flex: 1, justifyContent: 'space-between', gap: '12px' }}>
        <div>
          {/* Brand & Rating Row */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
            <span style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--color-primary-dark, #6f805e)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
              {product.brand}
            </span>
            <div style={{ display: 'flex', alignItems: 'center', gap: '3px', fontSize: '0.78rem', fontWeight: 700, color: 'var(--text-secondary)' }}>
              <span style={{ color: 'var(--color-tertiary, #CC5500)', fontSize: '0.88rem' }}>★</span>
              <span>{product.rating}</span>
            </div>
          </div>

          {/* Product Name */}
          <h4 style={{ fontSize: '0.92rem', fontWeight: 600, color: 'var(--text-primary)', lineHeight: 1.3, marginBottom: '8px', minHeight: '2.5em' }}>
            {prodTitle}
          </h4>

          {/* Gender & Category Tags */}
          <div style={{ display: 'flex', gap: '6px', marginBottom: '8px', flexWrap: 'wrap' }}>
            <span className="badge badge-primary">{product.gender}</span>
            <span className="badge">{product.category}</span>
          </div>
        </div>

        <div>
          {/* Discount Offer Tag (Above Price in Description) */}
          {discountVal > 0 && (
            <div style={{ marginBottom: '6px' }}>
              <span style={{
                display: 'inline-flex',
                alignItems: 'center',
                fontSize: '0.68rem',
                fontWeight: 700,
                color: 'var(--color-tertiary, #CC5500)',
                background: 'var(--color-tertiary-light, rgba(204, 85, 0, 0.12))',
                padding: '2px 6px',
                borderRadius: '3px',
                border: '1px solid rgba(204, 85, 0, 0.22)',
                letterSpacing: '0.03em',
                textTransform: 'uppercase',
                lineHeight: 1.2
              }}>
                Save {discountVal}%
              </span>
            </div>
          )}

          {/* Price Row */}
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', marginBottom: '12px' }}>
            <span style={{ fontSize: '1.15rem', fontWeight: 700, color: 'var(--text-primary)' }}>
              ₹{Number(product.price || 0).toLocaleString('en-IN')}
            </span>
            {product.originalPrice && (
              <span style={{ fontSize: '0.82rem', color: 'var(--text-muted)', textDecoration: 'line-through' }}>
                ₹{Number(product.originalPrice).toLocaleString('en-IN')}
              </span>
            )}
          </div>

          {/* Add to Cart Animated Button */}
          <AddToCartButton
            onClick={handleAddToCart}
            isAdded={addedAnim}
          />
        </div>
      </div>
    </div>
  );
};

export default ProductCard;
