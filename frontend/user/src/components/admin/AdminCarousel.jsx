import React, { useState, useEffect, useRef } from 'react';

const ADMIN_SLIDES = [
  {
    id: 1,
    badge: 'AI INTELLIGENCE · LIVE PREDICTIONS',
    badgeColor: 'var(--color-primary, #9CAF88)',
    badgeTextColor: '#1a2016',
    title: 'High-Intent Customer Funnel & Conversion Tracking',
    subtitle: 'Real-time behavioral tracking detected 42 active shoppers browsing Summer & Streetwear catalogs with high purchase propensity.',
    cta: 'View Customer Segments',
    metric: '94.8% Predictive Accuracy',
    metricColor: 'var(--color-primary-dark, #6f805e)',
    bgGradient: 'linear-gradient(135deg, rgba(156, 175, 136, 0.16) 0%, rgba(33, 37, 32, 0.95) 100%)',
  },
  {
    id: 2,
    badge: 'HOT TREND ALERT · +38% VELOCITY',
    badgeColor: 'var(--color-tertiary, #CC5500)',
    badgeTextColor: '#ffffff',
    title: 'Heavyweight Hoodies & Organic Linen Trending Fast',
    subtitle: 'Zara & H&M 450 GSM collections leading wishlist adds and cart conversions across urban demographics this week.',
    cta: 'Explore Catalog Demand',
    metric: '₹2.4L Projected Volume',
    metricColor: 'var(--color-tertiary, #CC5500)',
    bgGradient: 'linear-gradient(135deg, rgba(204, 85, 0, 0.18) 0%, rgba(33, 37, 32, 0.95) 100%)',
  },
  {
    id: 3,
    badge: 'AUTOMATED LEAD NURTURING',
    badgeColor: 'var(--color-secondary, #A7A7A7)',
    badgeTextColor: '#1a1a1a',
    title: 'Smart Retargeting & Personalised Email Drops',
    subtitle: 'Automated discount incentives sent to 16 cart-abandoned sessions. Average recovery conversion time: 14 mins.',
    cta: 'Manage Campaign Triggers',
    metric: '18.4% Recovery Rate',
    metricColor: 'var(--color-primary, #9CAF88)',
    bgGradient: 'linear-gradient(135deg, rgba(167, 167, 167, 0.15) 0%, rgba(33, 37, 32, 0.95) 100%)',
  }
];

export const AdminCarousel = ({ onActionClick }) => {
  const [currentSlide, setCurrentSlide] = useState(0);
  const [isPaused, setIsPaused] = useState(false);
  const timerRef = useRef(null);

  const startTimer = () => {
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = setInterval(() => {
      setCurrentSlide(prev => (prev + 1) % ADMIN_SLIDES.length);
    }, 6000);
  };

  useEffect(() => {
    if (!isPaused) {
      startTimer();
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [isPaused]);

  const slide = ADMIN_SLIDES[currentSlide];

  return (
    <div
      className="admin-carousel-container"
      onMouseEnter={() => setIsPaused(true)}
      onMouseLeave={() => setIsPaused(false)}
      style={{
        position: 'relative',
        borderRadius: 'var(--radius-md, 6px)',
        overflow: 'hidden',
        border: '1px solid var(--panel-border)',
        background: 'var(--panel-solid)',
        minHeight: '200px',
        boxShadow: '0 4px 20px rgba(0, 0, 0, 0.08)',
        transition: 'all 0.3s ease',
      }}
    >
      {/* Background Gradient Layer with Animated Transition */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          background: slide.bgGradient,
          transition: 'background 0.8s ease',
          opacity: 0.9,
          zIndex: 0
        }}
      />

      {/* Decorative Grid Lines */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          backgroundImage: 'radial-gradient(var(--panel-border) 1px, transparent 1px)',
          backgroundSize: '24px 24px',
          opacity: 0.25,
          zIndex: 0
        }}
      />

      {/* Slide Content Box */}
      <div
        key={slide.id}
        style={{
          position: 'relative',
          zIndex: 1,
          padding: '28px 36px',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '20px',
          animation: 'adminFadeIn 0.5s ease-out'
        }}
      >
        <div style={{ maxWidth: '680px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '10px' }}>
            <span
              style={{
                backgroundColor: slide.badgeColor,
                color: slide.badgeTextColor,
                padding: '3px 10px',
                borderRadius: '4px',
                fontSize: '0.72rem',
                fontWeight: 800,
                letterSpacing: '0.05em',
                textTransform: 'uppercase'
              }}
            >
              {slide.badge}
            </span>
            <span style={{ fontSize: '0.75rem', fontWeight: 700, color: slide.metricColor }}>
              ⚡ {slide.metric}
            </span>
          </div>

          <h2
            style={{
              fontSize: '1.45rem',
              fontWeight: 800,
              color: 'var(--text-primary)',
              lineHeight: 1.25,
              marginBottom: '8px'
            }}
          >
            {slide.title}
          </h2>

          <p
            style={{
              fontSize: '0.88rem',
              color: 'var(--text-secondary)',
              lineHeight: 1.5,
              margin: 0
            }}
          >
            {slide.subtitle}
          </p>
        </div>

        {/* Carousel Navigation Controls & Action Button */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <div style={{ display: 'flex', gap: '6px' }}>
            {ADMIN_SLIDES.map((s, idx) => (
              <button
                key={s.id}
                onClick={() => setCurrentSlide(idx)}
                style={{
                  width: currentSlide === idx ? '28px' : '8px',
                  height: '8px',
                  borderRadius: '4px',
                  backgroundColor: currentSlide === idx ? 'var(--color-tertiary, #CC5500)' : 'var(--panel-border)',
                  border: 'none',
                  cursor: 'pointer',
                  transition: 'all 0.3s ease',
                  padding: 0
                }}
                title={`Go to slide ${idx + 1}`}
                aria-label={`Slide ${idx + 1}`}
              />
            ))}
          </div>

          <div style={{ display: 'flex', gap: '8px' }}>
            <button
              onClick={() => setCurrentSlide(prev => (prev - 1 + ADMIN_SLIDES.length) % ADMIN_SLIDES.length)}
              className="btn btn-secondary"
              style={{ padding: '8px 14px', fontSize: '0.85rem' }}
              aria-label="Previous Insight"
            >
              ‹
            </button>
            <button
              onClick={() => setCurrentSlide(prev => (prev + 1) % ADMIN_SLIDES.length)}
              className="btn btn-secondary"
              style={{ padding: '8px 14px', fontSize: '0.85rem' }}
              aria-label="Next Insight"
            >
              ›
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default AdminCarousel;
