import React, { useState, useEffect, useRef } from 'react';

const ADMIN_SLIDES = [
  {
    id: 1,
    badge: "AI INTELLIGENCE · LIVE PREDICTIONS",
    badgeColor: "var(--color-primary, #9CAF88)",
    badgeTextColor: "#1a2016",
    title: "High-Intent Customer Funnel & Conversion Tracking",
    subtitle: "Real-time behavioral tracking detected 42 active shoppers browsing Summer & Streetwear catalogs with high purchase propensity.",
    cta: "Explore Customer Leads",
    ctaClass: "btn btn-primary",
    image: "https://images.unsplash.com/photo-1490481651871-ab68de25d43d?w=1200&auto=format&fit=crop&q=80",
  },
  {
    id: 2,
    badge: "HOT TREND ALERT · +38% VELOCITY",
    badgeColor: "var(--color-tertiary, #CC5500)",
    badgeTextColor: "#ffffff",
    title: "Heavyweight Hoodies & Organic Linen Trending Fast",
    subtitle: "Zara & H&M 450 GSM French terry collections leading wishlist adds and cart conversions across urban demographics this week.",
    cta: "Inspect Catalog Demand",
    ctaClass: "btn btn-tertiary",
    image: "https://images.unsplash.com/photo-1556905055-8f358a7a47b2?w=1200&auto=format&fit=crop&q=80",
  },
  {
    id: 3,
    badge: "AUTOMATED LEAD NURTURING",
    badgeColor: "var(--color-secondary, #A7A7A7)",
    badgeTextColor: "#1a1a1a",
    title: "Smart Retargeting & Personalised Email Drops",
    subtitle: "Automated discount incentives sent to 16 cart-abandoned sessions. Average recovery conversion time: 14 mins.",
    cta: "Manage Campaign Triggers",
    ctaClass: "btn btn-secondary",
    image: "https://images.unsplash.com/photo-1610030469983-98e550d6193c?w=1200&auto=format&fit=crop&q=80",
  }
];

export const AdminCarousel = () => {
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

  const handlePrev = (e) => {
    e.stopPropagation();
    setCurrentSlide(prev => (prev === 0 ? ADMIN_SLIDES.length - 1 : prev - 1));
  };

  const handleNext = (e) => {
    e.stopPropagation();
    setCurrentSlide(prev => (prev + 1) % ADMIN_SLIDES.length);
  };

  return (
    <section
      onMouseEnter={() => setIsPaused(true)}
      onMouseLeave={() => setIsPaused(false)}
      className="product-card"
      style={{
        position: 'relative',
        minHeight: '260px',
        maxHeight: '360px',
        height: 'clamp(260px, 32vw, 320px)',
        overflow: 'hidden',
        borderRadius: 'var(--radius-md, 6px)',
        border: '1px solid var(--panel-border)',
        userSelect: 'none',
        marginBottom: '24px'
      }}
    >
      {/* Sliding Carousel Track for Smooth Transition */}
      <div
        style={{
          display: 'flex',
          width: '100%',
          height: '100%',
          transform: `translateX(-${currentSlide * 100}%)`,
          transition: 'transform 0.55s cubic-bezier(0.16, 1, 0.3, 1)',
        }}
      >
        {ADMIN_SLIDES.map((slide) => (
          <div
            key={slide.id}
            style={{
              minWidth: '100%',
              width: '100%',
              height: '100%',
              position: 'relative',
              flexShrink: 0,
            }}
          >
            {/* Slide Background Image */}
            <img
              src={slide.image}
              alt={slide.title}
              loading={slide.id === 1 ? 'eager' : 'lazy'}
              decoding="async"
              style={{
                position: 'absolute',
                inset: 0,
                width: '100%',
                height: '100%',
                objectFit: 'cover',
              }}
            />

            {/* Matte Dark Gradient Overlay */}
            <div style={{
              position: 'absolute',
              inset: 0,
              background: 'linear-gradient(90deg, rgba(24, 27, 23, 0.94) 0%, rgba(24, 27, 23, 0.78) 50%, rgba(24, 27, 23, 0.35) 100%)',
              display: 'flex',
              alignItems: 'center',
              padding: 'clamp(20px, 4vw, 40px) clamp(64px, 7vw, 92px)',
              color: '#ffffff',
            }}>
              <div style={{ maxWidth: '560px', zIndex: 2 }}>
                <div style={{
                  display: 'inline-block',
                  background: slide.badgeColor || 'var(--color-primary, #9CAF88)',
                  color: slide.badgeTextColor || '#1a2016',
                  padding: '4px 10px',
                  borderRadius: 'var(--radius-xs, 2px)',
                  fontSize: 'clamp(0.68rem, 1.8vw, 0.75rem)',
                  fontWeight: 700,
                  marginBottom: '10px',
                  letterSpacing: '0.05em',
                  textTransform: 'uppercase',
                }}>
                  {slide.badge}
                </div>

                <h2 style={{
                  fontSize: 'clamp(1.25rem, 3vw, 1.85rem)',
                  fontWeight: 700,
                  lineHeight: 1.2,
                  marginBottom: '8px',
                  color: '#ffffff',
                  textShadow: '0 1px 2px rgba(0,0,0,0.3)',
                }}>
                  {slide.title}
                </h2>

                <p style={{
                  fontSize: 'clamp(0.8rem, 1.8vw, 0.88rem)',
                  opacity: 0.9,
                  lineHeight: 1.45,
                  marginBottom: '16px',
                  color: '#e5ebe2',
                  maxWidth: '480px',
                  display: '-webkit-box',
                  WebkitLineClamp: 2,
                  WebkitBoxOrient: 'vertical',
                  overflow: 'hidden',
                }}>
                  {slide.subtitle}
                </p>

                <button
                  className={slide.ctaClass || 'btn btn-primary'}
                  style={{
                    fontWeight: 700,
                    padding: '9px 20px',
                    fontSize: 'clamp(0.8rem, 1.8vw, 0.85rem)'
                  }}
                >
                  {slide.cta}
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Previous Navigation Button (Left) */}
      <div className="carousel-btn-prev">
        <button
          className="button carousel-prev"
          onClick={handlePrev}
          aria-label="Previous Slide"
          title="Previous Slide"
        >
          <div className="button-box">
            <svg className="button-elem" viewBox="0 0 46 40">
              <path d="M0 20.038c0-.7.3-1.5.8-2.1l16-17c1.1-1 3.2-1.4 4.4-.3 1.2 1.1 1.2 3.3 0 4.4L9.9 17H43c1.7 0 3 1.3 3 3s-1.3 3-3 3H9.9l11.3 11.9c1.2 1.1 1.2 3.3 0 4.4-1.2 1.1-3.3.8-4.4-.3l-16-17C.3 21.5 0 20.9 0 20z" />
            </svg>
            <svg className="button-elem" viewBox="0 0 46 40">
              <path d="M0 20.038c0-.7.3-1.5.8-2.1l16-17c1.1-1 3.2-1.4 4.4-.3 1.2 1.1 1.2 3.3 0 4.4L9.9 17H43c1.7 0 3 1.3 3 3s-1.3 3-3 3H9.9l11.3 11.9c1.2 1.1 1.2 3.3 0 4.4-1.2 1.1-3.3.8-4.4-.3l-16-17C.3 21.5 0 20.9 0 20z" />
            </svg>
          </div>
        </button>
      </div>

      {/* Next Navigation Button (Right) */}
      <div className="carousel-btn-next">
        <button
          className="button carousel-next"
          onClick={handleNext}
          aria-label="Next Slide"
          title="Next Slide"
        >
          <div className="button-box">
            <svg className="button-elem" viewBox="0 0 46 40">
              <path d="M46 20.038c0-.7-.3-1.5-.8-2.1l-16-17c-1.1-1-3.2-1.4-4.4-.3-1.2 1.1-1.2 3.3 0 4.4l11.3 11.9H3c-1.7 0-3 1.3-3 3s1.3 3 3 3h33.1L24.8 35c-1.2 1.1-1.2 3.3 0 4.4 1.2 1.1 3.3.8 4.4-.3l16-17c.5-.5.8-1.1.8-2.062z" />
            </svg>
            <svg className="button-elem" viewBox="0 0 46 40">
              <path d="M46 20.038c0-.7-.3-1.5-.8-2.1l-16-17c-1.1-1-3.2-1.4-4.4-.3-1.2 1.1-1.2 3.3 0 4.4l11.3 11.9H3c-1.7 0-3 1.3-3 3s1.3 3 3 3h33.1L24.8 35c-1.2 1.1-1.2 3.3 0 4.4 1.2 1.1 3.3.8 4.4-.3l16-17c.5-.5.8-1.1.8-2.062z" />
            </svg>
          </div>
        </button>
      </div>

      {/* Pagination Dot Indicators */}
      <div style={{
        position: 'absolute',
        bottom: '12px',
        left: '50%',
        transform: 'translateX(-50%)',
        display: 'flex',
        gap: '6px',
        zIndex: 10,
      }}>
        {ADMIN_SLIDES.map((_, i) => (
          <button
            key={i}
            onClick={() => setCurrentSlide(i)}
            aria-label={`Go to slide ${i + 1}`}
            style={{
              width: i === currentSlide ? '22px' : '6px',
              height: '4px',
              borderRadius: '2px',
              background: i === currentSlide ? 'var(--color-primary, #9CAF88)' : 'rgba(255, 255, 255, 0.45)',
              border: 'none',
              padding: 0,
              cursor: 'pointer',
              transition: 'all 0.25s ease',
            }}
          />
        ))}
      </div>
    </section>
  );
};

export default AdminCarousel;
