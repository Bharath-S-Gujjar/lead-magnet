import React, { useEffect, useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { getAnonymousId, getCustomerSession, fetchPostPurchaseRecommendations } from '../services/api';
import { ProductCard } from './ProductCard';

export const PurchasedProductRecommendations = () => {
  const { customer: authCustomer } = useAuth();
  const customer = authCustomer || getCustomerSession();
  const [data, setData] = useState({ has_purchases: false, carousels: [] });
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let isMounted = true;
    const userId = customer?.id || customer?._id || customer?.user_id;
    const anonId = getAnonymousId();

    // If neither authenticated userId nor anonId exists, no purchase history to query
    if (!userId && !anonId) {
      setData({ has_purchases: false, carousels: [] });
      return;
    }

    async function load() {
      setLoading(true);
      try {
        const res = await fetchPostPurchaseRecommendations(userId, anonId, 4, 2);
        if (isMounted && res) {
          setData(res);
        }
      } catch (err) {
        console.debug('Post-purchase recommendations fetch notice:', err);
      } finally {
        if (isMounted) setLoading(false);
      }
    }

    load();
    return () => {
      isMounted = false;
    };
  }, [customer?.id, customer?._id, customer?.email]);

  if (loading || !data?.has_purchases || !data?.carousels || data.carousels.length === 0) {
    return null;
  }

  return (
    <div className="purchased-recommendations-container" style={{ margin: '36px 0 40px 0' }}>
      {data.carousels.map((carousel, idx) => {
        const headlineText = carousel.headline || `Because you purchased '${carousel.anchor_title}':`;
        return (
          <section
            key={carousel.anchor_product_id || idx}
            style={{
              padding: '24px 20px',
              marginBottom: idx < data.carousels.length - 1 ? '32px' : '0',
              background: 'linear-gradient(135deg, rgba(30, 41, 59, 0.4) 0%, rgba(15, 23, 42, 0.6) 100%)',
              border: '1px solid var(--panel-border, rgba(148, 163, 184, 0.15))',
              borderRadius: '16px',
              boxShadow: '0 8px 24px rgba(0, 0, 0, 0.12)',
            }}
          >
            {/* Header: "Because you purchased 'Product name':" */}
            <div style={{ marginBottom: '18px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                <span
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    width: '28px',
                    height: '28px',
                    borderRadius: '50%',
                    background: 'var(--color-primary, #6366f1)',
                    color: '#ffffff',
                    fontSize: '0.85rem',
                  }}
                >
                  ✦
                </span>
                <h3
                  style={{
                    fontSize: '1.2rem',
                    fontWeight: 700,
                    color: 'var(--text-primary, #f8fafc)',
                    margin: 0,
                    letterSpacing: '-0.01em',
                  }}
                >
                  {headlineText.endsWith(':') ? headlineText : `${headlineText}:`}
                </h3>
              </div>
              <p
                style={{
                  fontSize: '0.85rem',
                  color: 'var(--text-secondary, #94a3b8)',
                  margin: '0 0 0 36px',
                }}
              >
                {carousel.subtitle || `Handpicked styles in ${carousel.anchor_category || 'Fashion'} based on your past purchase`}
              </p>
            </div>

            {/* Related Clothing Products Grid */}
            <div className="grid-4" style={{ rowGap: '24px', columnGap: '20px' }}>
              {carousel.recommendations.map(product => (
                <ProductCard key={product.id || product.product_id || product._id} product={product} />
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
};

export default PurchasedProductRecommendations;
