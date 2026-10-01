import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Heart, ShoppingBag, Star, Truck, ShieldCheck, RefreshCw, ArrowLeft, Shirt, Sparkles, AlertCircle, Loader2 } from 'lucide-react';
import { useCart } from '../context/CartContext';
import { useWishlist } from '../context/WishlistContext';
import { useTracking } from '../hooks/useTracking';
import { fetchProductById, fetchProducts, trackCustomerEvent } from '../services/api';
import { ProductCard } from '../components/ProductCard';

function normalizeProduct(product) {
  return {
    ...product,
    id: product._id || product.id,
    image: product.image || product.images?.[0] || '',
    images: product.images || (product.image ? [product.image] : []),
    rating: product.rating || 4.3,
    discount: product.discount || 0,
    sizes: product.sizes || ['S', 'M', 'L', 'XL'],
    colors: product.colors || ['Classic'],
    fabric: product.fabric || '100% Premium Cotton',
    material: product.material || 'Breathable Fabric',
    fit: product.fit || 'Comfort Regular Fit',
    washInstructions: product.washInstructions || 'Machine wash cold with like colors',
    price: Number(product.price || 0),
    description: product.description || `Premium quality ${product.category || 'clothing'} designed by ${product.brand || 'Lead Magnet'} for modern everyday comfort and style.`
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

          // Fetch related products from same category or gender
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

  const isLiked = product ? isInWishlist(product.id) : false;

  const getActiveProduct = () => ({
    ...product,
    image: selectedImage || product?.image
  });

  const handleBuyNow = () => {
    addToCart(getActiveProduct(), selectedSize, selectedColor, quantity);
    navigate('/cart');
  };

  const getFallbackGradient = () => {
    const g = (product?.gender || '').toLowerCase();
    if (g === 'women') return 'linear-gradient(135deg, #fce7f3 0%, #ede9fe 100%)';
    if (g === 'kids') return 'linear-gradient(135deg, #fef3c7 0%, #e0e7ff 100%)';
    return 'linear-gradient(135deg, #e0e7ff 0%, #f1f5f9 100%)';
  };

  if (loading) {
    return (
      <div className="glass-card" style={{ padding: '80px 24px', textAlign: 'center', margin: '40px auto', maxWidth: '600px' }}>
        <Loader2 size={44} className="spin-animation" style={{ color: 'var(--accent-indigo)', marginBottom: '16px', animation: 'spin 1s linear infinite' }} />
        <h3 className="heading-md" style={{ color: 'var(--text-primary)', marginBottom: '6px' }}>Loading Product Details...</h3>
        <p className="text-subtle">Fetching authoritative specifications from MongoDB</p>
      </div>
    );
  }

  if (error || !product) {
    return (
      <div className="glass-card" style={{ padding: '60px 24px', textAlign: 'center', margin: '40px auto', maxWidth: '600px' }}>
        <AlertCircle size={48} style={{ color: 'var(--accent-rose)', marginBottom: '16px' }} />
        <h3 className="heading-lg" style={{ color: 'var(--text-primary)', marginBottom: '8px' }}>Product Not Found</h3>
        <p className="text-subtle" style={{ marginBottom: '24px' }}>{error || "The requested clothing item could not be retrieved from the catalog."}</p>
        <button onClick={() => navigate('/')} className="btn btn-primary">
          <ArrowLeft size={16} /> Return to Clothing Catalog
        </button>
      </div>
    );
  }

  const hasRealImage = selectedImage && !selectedImage.includes('placeholder.com') && !imgFailed;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '32px' }}>
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
        {/* Left Side: Photo Gallery / Visual Representation */}
        <div>
          <div style={{
            position: 'relative',
            width: '100%',
            height: '480px',
            borderRadius: 'var(--radius-lg)',
            overflow: 'hidden',
            background: getFallbackGradient(),
            marginBottom: '16px',
            boxShadow: 'var(--panel-shadow)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center'
          }}>
            {hasRealImage ? (
              <img 
                src={selectedImage} 
                alt={product.name} 
                onError={() => setImgFailed(true)}
                style={{ width: '100%', height: '100%', objectFit: 'cover' }}
              />
            ) : (
              <div style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                textAlign: 'center',
                padding: '24px',
                width: '100%',
                height: '100%'
              }}>
                <div style={{
                  width: '96px',
                  height: '96px',
                  borderRadius: '50%',
                  background: 'rgba(255, 255, 255, 0.85)',
                  boxShadow: '0 8px 24px rgba(79, 70, 229, 0.12)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: 'var(--accent-indigo)',
                  marginBottom: '16px'
                }}>
                  <Shirt size={48} strokeWidth={1.5} />
                </div>
                <span className="badge badge-indigo" style={{ marginBottom: '8px', fontSize: '0.82rem' }}>
                  {product.category}
                </span>
                <span style={{ fontSize: '1.4rem', fontWeight: 800, color: 'var(--text-primary)', letterSpacing: '0.04em' }}>
                  {product.brand}
                </span>
                <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginTop: '4px' }}>
                  Official Authentic Catalog Item
                </span>
              </div>
            )}
          </div>

          {/* Thumbnails if multiple images exist */}
          {product.images && product.images.length > 1 && (
            <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
              {product.images.map((img, idx) => (
                <div 
                  key={idx}
                  onClick={() => { setSelectedImage(img); setImgFailed(false); }}
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
            {product.discount > 0 && (
              <>
                <span style={{ fontSize: '1.1rem', color: 'var(--text-muted)', textDecoration: 'line-through' }}>
                  ₹{Math.round(product.price * (1 + product.discount / 100)).toLocaleString('en-IN')}
                </span>
                <span className="badge badge-rose">
                  Save {product.discount}%
                </span>
              </>
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
                    onClick={() => setSelectedColor(col)}
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

      {/* Related Products Section */}
      {relatedProducts.length > 0 && (
        <div style={{ marginTop: '24px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '18px' }}>
            <Sparkles size={20} style={{ color: 'var(--accent-indigo)' }} />
            <h3 className="heading-md" style={{ color: 'var(--text-primary)' }}>
              More from {product.category}
            </h3>
          </div>
          <div className="grid-4" style={{ rowGap: '28px', columnGap: '24px' }}>
            {relatedProducts.map(rel => (
              <ProductCard key={rel._id || rel.id} product={normalizeProduct(rel)} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
