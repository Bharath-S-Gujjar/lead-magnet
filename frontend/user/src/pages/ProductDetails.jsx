import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useCart } from '../context/CartContext';
import { useWishlist } from '../context/WishlistContext';
import { fetchProductById, fetchProducts, trackCustomerEvent } from '../services/api';
import { ProductCard } from '../components/ProductCard';
import { ProductDetailsSkeleton } from '../components/Skeleton';
import { AddToCartButton } from '../components/AddToCartButton';
import { WishlistHeartButton } from '../components/WishlistHeartButton';
import { getOptimizedImageUrl } from '../utils/imageOptimizer';

function normalizeProduct(product) {
  const primaryImg = product.primary_image || product.image || product.images?.[0] || '';
  const images = (Array.isArray(product.images) && product.images.length > 0)
    ? product.images
    : (primaryImg ? [primaryImg] : []);
  const title = product.title || product.name || '';
  return {
    ...product,
    id: product.product_id || product.id || product._id,
    product_id: product.product_id || product.id || product._id,
    name: title,
    title: title,
    image: primaryImg,
    primary_image: primaryImg,
    images: images,
    rating: product.rating || 4.3,
    discount: product.discount_percent || product.discount || 0,
    originalPrice: product.mrp || product.price_before_discount || null,
    sizes: product.sizes || ['S', 'M', 'L', 'XL'],
    colors: product.colors || ['Classic'],
    fabric: product.fabric || '100% Premium Cotton',
    material: product.material || 'Breathable Fabric',
    fit: product.fit || 'Comfort Regular Fit',
    washInstructions: product.washInstructions || 'Machine wash cold with like colors',
    price: Number(product.price || 0),
    description: product.description || `${title} by ${product.brand || 'Myntra'} - authentic clothing.`
  };
}

export const ProductDetails = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const { addToCart } = useCart();
  const { toggleWishlist, isInWishlist } = useWishlist();

  const [product, setProduct] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [relatedProducts, setRelatedProducts] = useState([]);
  const [imgFailed, setImgFailed] = useState(false);

  const [selectedImage, setSelectedImage] = useState('');
  const [selectedSize, setSelectedSize] = useState('M');
  const [selectedColor, setSelectedColor] = useState('Classic');
  const [quantity, setQuantity] = useState(1);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    setImgFailed(false);

    fetchProductById(id)
      .then((data) => {
        if (!active) return;
        if (data) {
          const norm = normalizeProduct(data);
          setProduct(norm);
          setSelectedImage(norm.image);
          setSelectedSize(norm.sizes[0] || 'M');
          setSelectedColor(norm.colors[0] || 'Classic');

          trackCustomerEvent('product_view', {
            page: `/product/${id}`,
            entity: {
              id: norm.id,
              product_id: norm.product_id,
              title: norm.title,
              category: norm.category,
              brand: norm.brand,
              price: norm.price,
            },
          });

          if (norm.category) {
            fetchProducts({ category: norm.category, limit: 4 })
              .then((res) => {
                if (active && res?.data) {
                  const filtered = res.data.filter(p => (p._id || p.id) !== norm.id).slice(0, 4);
                  setRelatedProducts(filtered);
                }
              })
              .catch(() => {});
          }
        } else {
          setError('Product not found in catalog.');
        }
      })
      .catch((err) => {
        if (!active) return;
        setError(err.message || 'Unable to fetch product details.');
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [id]);

  if (loading) {
    return <ProductDetailsSkeleton />;
  }

  if (error || !product) {
    return (
      <div className="product-card" style={{ padding: '48px 24px', textAlign: 'center' }}>
        <h3 style={{ fontSize: '1.2rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '8px' }}>
          {error || 'Product Not Found'}
        </h3>
        <p style={{ color: 'var(--text-secondary)', marginBottom: '18px', fontSize: '0.9rem' }}>
          The requested product could not be located in the catalog.
        </p>
        <button onClick={() => navigate('/')} className="btn btn-primary">
          Back to Clothing Catalog
        </button>
      </div>
    );
  }

  const isLiked = isInWishlist(product.id);

  const handleBuyNow = () => {
    addToCart(product, selectedSize, selectedColor, quantity);
    navigate('/cart');
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '32px' }}>
      {/* Navigation Breadcrumb */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.85rem', color: 'var(--text-muted)' }}>
        <button onClick={() => navigate('/')} className="btn btn-ghost" style={{ padding: '4px 8px', fontSize: '0.82rem' }}>
          Catalog
        </button>
        <span>/</span>
        <span style={{ color: 'var(--text-secondary)' }}>{product.category}</span>
        <span>/</span>
        <span style={{ color: 'var(--text-primary)', fontWeight: 600 }}>{product.name}</span>
      </div>

      {/* Main Details Grid */}
      <div className="product-card" style={{
        padding: '28px',
        display: 'grid',
        gridTemplateColumns: '1fr 1.15fr',
        gap: '36px'
      }}>
        {/* Left Side: Image Gallery */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <div style={{
            position: 'relative',
            width: '100%',
            paddingTop: '110%',
            borderRadius: 'var(--radius-sm, 4px)',
            overflow: 'hidden',
            background: 'var(--table-header-bg, #ecefe9)',
            border: '1px solid var(--panel-border)'
          }}>
            {!imgFailed && selectedImage ? (
              <img
                src={getOptimizedImageUrl(selectedImage, 800, 80)}
                alt={product.name}
                loading="eager"
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
                padding: '24px',
                textAlign: 'center'
              }}>
                <span style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--color-primary, #9CAF88)', textTransform: 'uppercase' }}>
                  {product.brand}
                </span>
                <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginTop: '4px' }}>
                  {product.category}
                </span>
              </div>
            )}
          </div>

          {/* Thumbnail Strip */}
          {product.images && product.images.length > 1 && (
            <div style={{ display: 'flex', gap: '10px', overflowX: 'auto' }}>
              {product.images.map((img, i) => (
                <button
                  key={i}
                  onClick={() => {
                    setSelectedImage(img);
                    setImgFailed(false);
                  }}
                  style={{
                    width: '64px',
                    height: '64px',
                    borderRadius: 'var(--radius-sm, 4px)',
                    overflow: 'hidden',
                    border: selectedImage === img ? '2px solid var(--color-primary, #9CAF88)' : '1px solid var(--panel-border)',
                    background: 'transparent',
                    cursor: 'pointer',
                    padding: 0,
                    flexShrink: 0
                  }}
                >
                  <img
                    src={getOptimizedImageUrl(img, 150, 70)}
                    alt=""
                    loading="lazy"
                    decoding="async"
                    style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                  />
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Right Side: Product Info */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
              <span className="badge badge-primary">
                {product.brand}
              </span>
              <div style={{ display: 'flex', alignItems: 'center', gap: '4px', color: 'var(--text-primary)', fontWeight: 700, fontSize: '0.88rem' }}>
                <span style={{ color: 'var(--color-tertiary, #CC5500)', fontSize: '0.95rem' }}>★</span>
                <span>{product.rating}</span>
                <span style={{ color: 'var(--text-muted)', fontWeight: 500, fontSize: '0.78rem' }}>(Verified)</span>
              </div>
            </div>

            <h2 style={{ fontSize: '1.45rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '8px' }}>
              {product.name}
            </h2>

            <p style={{ fontSize: '0.88rem', color: 'var(--text-secondary)', lineHeight: 1.5 }}>
              {product.description}
            </p>
          </div>

          {/* Pricing */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', paddingBottom: '14px', borderBottom: '1px solid var(--panel-border)' }}>
            {product.discount > 0 && (
              <div>
                <span style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  fontSize: '0.72rem',
                  fontWeight: 700,
                  color: 'var(--color-tertiary, #CC5500)',
                  background: 'var(--color-tertiary-light, rgba(204, 85, 0, 0.12))',
                  padding: '3px 8px',
                  borderRadius: '4px',
                  border: '1px solid rgba(204, 85, 0, 0.25)',
                  letterSpacing: '0.04em',
                  textTransform: 'uppercase',
                  lineHeight: 1.2
                }}>
                  Special Offer · Save {product.discount}%
                </span>
              </div>
            )}
            <div style={{ display: 'flex', alignItems: 'baseline', gap: '10px' }}>
              <span style={{ fontSize: '1.75rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                ₹{product.price.toLocaleString('en-IN')}
              </span>
              {product.discount > 0 && (
                <span style={{ fontSize: '0.95rem', color: 'var(--text-muted)', textDecoration: 'line-through' }}>
                  ₹{Math.round(product.price * (1 + product.discount / 100)).toLocaleString('en-IN')}
                </span>
              )}
            </div>
          </div>

          {/* Size Selector */}
          {product.sizes && (
            <div>
              <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '8px' }}>
                Select Size:
              </label>
              <div style={{ display: 'flex', gap: '8px' }}>
                {product.sizes.map(sz => (
                  <button
                    key={sz}
                    onClick={() => setSelectedSize(sz)}
                    style={{
                      minWidth: '40px',
                      height: '38px',
                      borderRadius: 'var(--radius-sm, 4px)',
                      border: selectedSize === sz ? '1px solid var(--color-primary, #9CAF88)' : '1px solid var(--panel-border)',
                      background: selectedSize === sz ? 'var(--color-primary, #9CAF88)' : 'var(--panel-solid)',
                      color: selectedSize === sz ? '#1a2016' : 'var(--text-primary)',
                      fontWeight: 600,
                      fontSize: '0.82rem',
                      cursor: 'pointer'
                    }}
                  >
                    {sz}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Color Selector */}
          {product.colors && (
            <div>
              <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '8px' }}>
                Select Color: <span style={{ color: 'var(--color-primary-dark, #6f805e)' }}>{selectedColor}</span>
              </label>
              <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                {product.colors.map(col => (
                  <button
                    key={col}
                    onClick={() => setSelectedColor(col)}
                    style={{
                      padding: '5px 12px',
                      borderRadius: 'var(--radius-sm, 4px)',
                      border: selectedColor === col ? '1px solid var(--color-primary, #9CAF88)' : '1px solid var(--panel-border)',
                      background: selectedColor === col ? 'var(--color-primary-light, rgba(156, 175, 136, 0.15))' : 'var(--panel-solid)',
                      color: selectedColor === col ? 'var(--color-primary-dark, #6f805e)' : 'var(--text-primary)',
                      fontWeight: 600,
                      fontSize: '0.8rem',
                      cursor: 'pointer'
                    }}
                  >
                    {col}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Quantity & Action Buttons */}
          <div style={{ display: 'flex', gap: '10px', alignItems: 'center', marginTop: '6px' }}>
            <div style={{
              display: 'flex',
              alignItems: 'center',
              border: '1px solid var(--panel-border)',
              borderRadius: 'var(--radius-sm, 4px)',
              background: 'var(--panel-solid)'
            }}>
              <button
                onClick={() => setQuantity(q => Math.max(1, q - 1))}
                style={{ width: '32px', height: '36px', border: 'none', background: 'transparent', cursor: 'pointer', fontWeight: 700 }}
              >
                -
              </button>
              <span style={{ width: '32px', textAlign: 'center', fontWeight: 600, fontSize: '0.85rem' }}>
                {quantity}
              </span>
              <button
                onClick={() => setQuantity(q => q + 1)}
                style={{ width: '32px', height: '36px', border: 'none', background: 'transparent', cursor: 'pointer', fontWeight: 700 }}
              >
                +
              </button>
            </div>

            <div style={{ flex: 1 }}>
              <AddToCartButton
                onClick={() => {
                  addToCart(product, selectedSize, selectedColor, quantity);
                }}
              />
            </div>

            <button
              onClick={handleBuyNow}
              className="btn btn-tertiary"
              style={{ padding: '10px 18px', fontSize: '0.88rem' }}
            >
              Buy Now
            </button>

            <div
              style={{
                width: '42px',
                height: '42px',
                borderRadius: 'var(--radius-sm, 4px)',
                border: '1px solid var(--panel-border)',
                background: 'var(--panel-solid)',
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: 'pointer',
                flexShrink: 0
              }}
            >
              <WishlistHeartButton
                isLiked={isLiked}
                onToggle={() => toggleWishlist(product)}
                size={38}
                heartColor="var(--color-tertiary, #CC5500)"
              />
            </div>
          </div>

          {/* Specifications */}
          <div style={{
            marginTop: '12px',
            padding: '14px',
            borderRadius: 'var(--radius-sm, 4px)',
            background: 'var(--table-header-bg, #ecefe9)',
            border: '1px solid var(--panel-border)',
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            gap: '10px',
            fontSize: '0.82rem'
          }}>
            <div><strong>Fabric:</strong> {product.fabric}</div>
            <div><strong>Material:</strong> {product.material}</div>
            <div><strong>Fit Type:</strong> {product.fit}</div>
            <div><strong>Wash Care:</strong> {product.washInstructions}</div>
          </div>
        </div>
      </div>

      {/* Related Products Section */}
      {relatedProducts.length > 0 && (
        <div style={{ marginTop: '16px' }}>
          <h3 style={{ fontSize: '1.15rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '16px' }}>
            More from {product.category}
          </h3>
          <div className="grid-4" style={{ rowGap: '24px', columnGap: '20px' }}>
            {relatedProducts.map(rel => (
              <ProductCard key={rel._id || rel.id} product={normalizeProduct(rel)} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default ProductDetails;
