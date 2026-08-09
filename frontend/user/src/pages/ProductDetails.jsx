import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Heart, ShoppingBag, Star, Truck, ShieldCheck, RefreshCw, ArrowLeft, Check } from 'lucide-react';
import { CLOTHING_PRODUCTS } from '../data/clothingProducts';
import { useCart } from '../context/CartContext';
import { useWishlist } from '../context/WishlistContext';
import { useTracking } from '../hooks/useTracking';
import { API_BASE_URL, parseJsonResponse, trackCustomerEvent } from '../services/api';

function normalizeProduct(product) {
  return {
    ...product,
    id: product._id || product.id,
    image: product.image || product.images?.[0] || 'https://via.placeholder.com/600x800?text=Clothing',
    images: product.images || [product.image || 'https://via.placeholder.com/600x800?text=Clothing'],
    rating: product.rating || 4.3,
    discount: product.discount || 0,
    sizes: product.sizes || ['M', 'L', 'XL'],
    colors: product.colors || ['Standard'],
    fabric: product.fabric || 'Cotton Blend',
    material: product.material || 'Premium Fabric',
    fit: product.fit || 'Regular Fit',
    washInstructions: product.washInstructions || 'Machine wash',
    price: Number(product.price || 0),
  };
}

export const ProductDetails = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const { addToCart } = useCart();
  const { toggleWishlist, isInWishlist } = useWishlist();

  const [product, setProduct] = useState(() => CLOTHING_PRODUCTS.find(p => p.id === id) || null);

  useEffect(() => {
    fetch(`${API_BASE_URL}/api/products/${id}`)
      .then((response) => parseJsonResponse(response))
      .then((payload) => {
        if (payload.success && payload.data) {
          setProduct(normalizeProduct(payload.data));
        }
      })
      .catch(() => {
        setProduct(CLOTHING_PRODUCTS.find(p => p.id === id) || CLOTHING_PRODUCTS[0]);
      });
  }, [id]);

  useEffect(() => {
    if (product) {
      trackCustomerEvent('product_view', {
        page: `/product/${product.id}`,
        entity: {
          type: 'product',
          id: product.id,
          name: product.name,
          category: product.category,
          brand: product.brand,
          price: product.price,
        },
      });
    }
  }, [product]);

  // Silent Background Customer Telemetry Tracking
  useTracking(product);

  const [selectedImage, setSelectedImage] = useState(product?.image);
  const [selectedSize, setSelectedSize] = useState(product?.sizes ? product.sizes[0] : 'M');
  const [selectedColor, setSelectedColor] = useState(product?.colors ? product.colors[0] : 'Standard');
  const [quantity, setQuantity] = useState(1);

  useEffect(() => {
    if (!product) return;
    setSelectedImage(product.image);
    setSelectedColor(product.colors ? product.colors[0] : 'Standard');
    setSelectedSize(product.sizes ? product.sizes[0] : 'M');
    setQuantity(1);
  }, [product]);

  if (!product) {
    return null;
  }

  const handleColorSelect = (col) => {
    setSelectedColor(col);
    if (product.colorImages && product.colorImages[col]) {
      setSelectedImage(product.colorImages[col]);
    }
  };

  const handleThumbnailClick = (img) => {
    setSelectedImage(img);
    if (product.colorImages) {
      const matchedColor = Object.keys(product.colorImages).find(c => product.colorImages[c] === img);
      if (matchedColor) {
        setSelectedColor(matchedColor);
      }
    }
  };

  const isLiked = isInWishlist(product.id);

  const getActiveProduct = () => ({
    ...product,
    image: selectedImage || product.image
  });

  const handleBuyNow = () => {
    addToCart(getActiveProduct(), selectedSize, selectedColor, quantity);
    navigate('/cart');
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
      {/* Back Button */}
      <button 
        onClick={() => navigate('/')} 
        className="btn btn-ghost" 
        style={{ width: 'fit-content', padding: '6px 12px', fontSize: '0.85rem' }}
      >
        <ArrowLeft size={16} /> Back to Clothing Store
      </button>

      {/* Main Details Card */}
      <div className="glass-card" style={{ padding: '36px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '48px', alignItems: 'start' }}>
        {/* Left Side: Photo Gallery */}
        <div>
          <div style={{
            width: '100%',
            height: '480px',
            borderRadius: 'var(--radius-lg)',
            overflow: 'hidden',
            background: '#f1f5f9',
            marginBottom: '16px',
            boxShadow: 'var(--panel-shadow)'
          }}>
            <img 
              src={selectedImage || product.image} 
              alt={product.name} 
              style={{ width: '100%', height: '100%', objectFit: 'cover' }}
            />
          </div>

          {/* Thumbnails */}
          {product.images && product.images.length > 1 && (
            <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
              {product.images.map((img, idx) => (
                <div 
                  key={idx}
                  onClick={() => handleThumbnailClick(img)}
                  style={{
                    width: '80px',
                    height: '80px',
                    borderRadius: 'var(--radius-md)',
                    overflow: 'hidden',
                    cursor: 'pointer',
                    border: selectedImage === img ? '2px solid var(--accent-indigo)' : '1px solid var(--panel-border)',
                    boxShadow: selectedImage === img ? '0 4px 10px rgba(79,70,229,0.2)' : 'none',
                    transition: 'all 0.2s ease'
                  }}
                >
                  <img src={img} alt="Thumbnail" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Right Side: Product Info */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
              <span className="badge badge-indigo" style={{ textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                {product.brand}
              </span>
              <div style={{ display: 'flex', alignItems: 'center', gap: '4px', color: 'var(--accent-amber)', fontWeight: 800, fontSize: '0.9rem' }}>
                <Star size={16} fill="#f59e0b" />
                <span>{product.rating}</span>
              </div>
            </div>

            <h2 className="heading-xl" style={{ color: 'var(--text-primary)', marginBottom: '10px' }}>
              {product.name}
            </h2>

            <p style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
              {product.description}
            </p>
          </div>

          {/* Pricing */}
          <div style={{ display: 'flex', alignItems: 'baseline', gap: '12px', paddingBottom: '16px', borderBottom: '1px solid var(--panel-border)' }}>
            <span style={{ fontFamily: 'var(--font-heading)', fontSize: '2.2rem', fontWeight: 800, color: 'var(--text-primary)' }}>
              ₹{product.price.toLocaleString('en-IN')}
            </span>
            {product.originalPrice && (
              <span style={{ fontSize: '1.1rem', color: 'var(--text-muted)', textDecoration: 'line-through' }}>
                ₹{product.originalPrice.toLocaleString('en-IN')}
              </span>
            )}
            {product.discount > 0 && (
              <span className="badge badge-rose">
                Save {product.discount}%
              </span>
            )}
          </div>

          {/* Size Selector */}
          {product.sizes && (
            <div>
              <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 700, color: 'var(--text-secondary)', marginBottom: '10px' }}>
                Select Size:
              </label>
              <div style={{ display: 'flex', gap: '10px' }}>
                {product.sizes.map(sz => (
                  <button
                    key={sz}
                    onClick={() => setSelectedSize(sz)}
                    style={{
                      minWidth: '44px',
                      height: '44px',
                      borderRadius: 'var(--radius-md)',
                      border: selectedSize === sz ? '2px solid var(--accent-indigo)' : '1px solid var(--panel-border)',
                      background: selectedSize === sz ? 'var(--accent-indigo)' : 'var(--panel-solid)',
                      color: selectedSize === sz ? 'white' : 'var(--text-primary)',
                      fontWeight: 800,
                      fontSize: '0.85rem',
                      cursor: 'pointer'
                    }}
                  >
                    {sz}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Color Swatches */}
          {product.colors && (
            <div>
              <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 700, color: 'var(--text-secondary)', marginBottom: '10px' }}>
                Select Color: <span style={{ color: 'var(--accent-indigo)' }}>{selectedColor}</span>
              </label>
              <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
                {product.colors.map(col => (
                  <button
                    key={col}
                    onClick={() => handleColorSelect(col)}
                    style={{
                      padding: '6px 14px',
                      borderRadius: 'var(--radius-full)',
                      border: selectedColor === col ? '2px solid var(--accent-indigo)' : '1px solid var(--panel-border)',
                      background: selectedColor === col ? 'rgba(79, 70, 229, 0.12)' : 'var(--panel-solid)',
                      color: selectedColor === col ? 'var(--accent-indigo)' : 'var(--text-primary)',
                      fontWeight: 700,
                      fontSize: '0.82rem',
                      cursor: 'pointer',
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '8px',
                      transition: 'all 0.2s ease'
                    }}
                  >
                    {product.colorImages && product.colorImages[col] && (
                      <img 
                        src={product.colorImages[col]} 
                        alt={col} 
                        style={{ width: '20px', height: '20px', borderRadius: '50%', objectFit: 'cover', border: '1px solid rgba(0,0,0,0.1)' }} 
                      />
                    )}
                    <span>{col}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Quantity Selector & Action Buttons */}
          <div style={{ display: 'flex', gap: '16px', alignItems: 'center', marginTop: '10px' }}>
            <div style={{
              display: 'flex',
              alignItems: 'center',
              border: '1px solid var(--panel-border)',
              borderRadius: 'var(--radius-md)',
              background: 'var(--panel-solid)'
            }}>
              <button 
                onClick={() => setQuantity(q => Math.max(1, q - 1))}
                style={{ width: '36px', height: '40px', border: 'none', background: 'transparent', cursor: 'pointer', fontWeight: 800 }}
              >
                -
              </button>
              <span style={{ width: '36px', textAlign: 'center', fontWeight: 800, fontSize: '0.9rem' }}>
                {quantity}
              </span>
              <button 
                onClick={() => setQuantity(q => q + 1)}
                style={{ width: '36px', height: '40px', border: 'none', background: 'transparent', cursor: 'pointer', fontWeight: 800 }}
              >
                +
              </button>
            </div>

            <button 
              onClick={() => addToCart(getActiveProduct(), selectedSize, selectedColor, quantity)}
              className="btn btn-primary"
              style={{ flex: 1, padding: '12px', fontSize: '0.95rem' }}
            >
              <ShoppingBag size={18} /> Add to Cart
            </button>

            <button 
              onClick={handleBuyNow}
              className="btn btn-secondary"
              style={{ padding: '12px 20px', fontSize: '0.95rem', background: 'var(--accent-emerald)', color: 'white', border: 'none' }}
            >
              Buy Now
            </button>

            <button 
              onClick={() => toggleWishlist(product)}
              className="btn btn-secondary"
              style={{ padding: '12px' }}
              title={isLiked ? "Remove from Wishlist" : "Add to Wishlist"}
            >
              <Heart size={20} fill={isLiked ? '#f43f5e' : 'none'} color={isLiked ? '#f43f5e' : '#64748b'} />
            </button>
          </div>

          {/* Fabric & Product Specifications */}
          <div style={{
            marginTop: '16px',
            padding: '18px',
            borderRadius: 'var(--radius-md)',
            background: 'var(--table-header-bg)',
            border: '1px solid var(--panel-border)',
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            gap: '12px',
            fontSize: '0.82rem'
          }}>
            <div><strong>Fabric:</strong> {product.fabric}</div>
            <div><strong>Material:</strong> {product.material}</div>
            <div><strong>Fit Type:</strong> {product.fit}</div>
            <div><strong>Wash Care:</strong> {product.washInstructions}</div>
          </div>

          {/* Guarantees */}
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.78rem', color: 'var(--text-secondary)', marginTop: '8px' }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><Truck size={15} /> Free Express Delivery</span>
            <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><ShieldCheck size={15} /> 100% Authentic Brand Guarantee</span>
            <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}><RefreshCw size={15} /> 30-Day Easy Returns</span>
          </div>
        </div>
      </div>
    </div>
  );
};
