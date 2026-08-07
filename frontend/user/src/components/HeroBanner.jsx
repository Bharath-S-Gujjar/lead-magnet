import React, { useState, useEffect } from 'react';
import { ChevronLeft, ChevronRight, Sparkles, ShoppingBag } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

const SLIDES = [
  {
    id: 1,
    badge: "NEW ARRIVALS 2026",
    title: "Summer Linen & Denim Collection",
    subtitle: "Discover lightweight organic linen blazers, relaxed tees, and vintage denim.",
    cta: "Shop Summer Collection",
    image: "https://images.unsplash.com/photo-1490481651871-ab68de25d43d?w=1200&auto=format&fit=crop&q=80",
    gradient: "linear-gradient(135deg, rgba(79, 70, 229, 0.85) 0%, rgba(59, 130, 246, 0.85) 100%)"
  },
  {
    id: 2,
    badge: "LIMITED OFFER — FLAT 40% OFF",
    title: "Heavyweight Hoodies & Streetwear",
    subtitle: "Uncompromising 450 GSM French terry cotton hoodies from Zara & H&M.",
    cta: "Claim 40% Offer",
    image: "https://images.unsplash.com/photo-1556905055-8f358a7a47b2?w=1200&auto=format&fit=crop&q=80",
    gradient: "linear-gradient(135deg, rgba(244, 63, 94, 0.85) 0%, rgba(139, 92, 246, 0.85) 100%)"
  },
  {
    id: 3,
    badge: "ETHNIC LUXURY",
    title: "Handloom Kurta & Silk Saree Fest",
    subtitle: "Authentic Chanderi silk sarees & handwoven Khadi kurtas by Biba & Fabindia.",
    cta: "Explore Ethnic Wear",
    image: "https://images.unsplash.com/photo-1610030469983-98e550d6193c?w=1200&auto=format&fit=crop&q=80",
    gradient: "linear-gradient(135deg, rgba(16, 185, 129, 0.85) 0%, rgba(79, 70, 229, 0.85) 100%)"
  }
];

export const HeroBanner = () => {
  const [currentSlide, setCurrentSlide] = useState(0);
  const navigate = useNavigate();

  useEffect(() => {
    const timer = setInterval(() => {
      setCurrentSlide(prev => (prev + 1) % SLIDES.length);
    }, 5500);
    return () => clearInterval(timer);
  }, []);

  const slide = SLIDES[currentSlide];

  return (
    <section className="glass-card" style={{
      position: 'relative',
      height: '360px',
      overflow: 'hidden',
      borderRadius: 'var(--radius-xl)',
      boxShadow: 'var(--panel-shadow-hover)'
    }}>
      {/* Background Image */}
      <img 
        src={slide.image} 
        alt={slide.title} 
        style={{
          position: 'absolute',
          inset: 0,
          width: '100%',
          height: '100%',
          objectFit: 'cover',
          transition: 'opacity 0.6s ease'
        }}
      />

      {/* Gradient Overlay */}
      <div style={{
        position: 'absolute',
        inset: 0,
        background: slide.gradient,
        backdropFilter: 'blur(3px)',
        display: 'flex',
        alignItems: 'center',
        padding: '48px 60px',
        color: 'white'
      }}>
        <div style={{ maxWidth: '640px', animation: 'fadeIn 0.4s ease' }}>
          <div style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '8px',
            background: 'rgba(255, 255, 255, 0.25)',
            padding: '6px 14px',
            borderRadius: 'var(--radius-full)',
            fontSize: '0.78rem',
            fontWeight: 800,
            marginBottom: '14px',
            letterSpacing: '0.05em'
          }}>
            <Sparkles size={14} /> {slide.badge}
          </div>

          <h2 style={{ fontFamily: 'var(--font-heading)', fontSize: '2.4rem', fontWeight: 800, letterSpacing: '-0.02em', lineHeight: 1.1, marginBottom: '10px' }}>
            {slide.title}
          </h2>

          <p style={{ fontSize: '1rem', opacity: 0.95, lineHeight: 1.5, marginBottom: '24px' }}>
            {slide.subtitle}
          </p>

          <button 
            onClick={() => navigate('/')}
            className="btn"
            style={{
              background: 'white',
              color: 'var(--accent-indigo)',
              fontWeight: 800,
              padding: '12px 24px',
              borderRadius: 'var(--radius-full)',
              boxShadow: '0 8px 20px rgba(0,0,0,0.15)'
            }}
          >
            <ShoppingBag size={18} /> {slide.cta}
          </button>
        </div>
      </div>

      {/* Navigation Arrows */}
      <button 
        onClick={() => setCurrentSlide(prev => (prev === 0 ? SLIDES.length - 1 : prev - 1))}
        style={{
          position: 'absolute',
          left: '20px',
          top: '50%',
          transform: 'translateY(-50%)',
          background: 'rgba(255, 255, 255, 0.3)',
          backdropFilter: 'blur(8px)',
          border: 'none',
          color: 'white',
          width: '40px',
          height: '40px',
          borderRadius: '50%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          cursor: 'pointer',
          zIndex: 10
        }}
      >
        <ChevronLeft size={24} />
      </button>

      <button 
        onClick={() => setCurrentSlide(prev => (prev + 1) % SLIDES.length)}
        style={{
          position: 'absolute',
          right: '20px',
          top: '50%',
          transform: 'translateY(-50%)',
          background: 'rgba(255, 255, 255, 0.3)',
          backdropFilter: 'blur(8px)',
          border: 'none',
          color: 'white',
          width: '40px',
          height: '40px',
          borderRadius: '50%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          cursor: 'pointer',
          zIndex: 10
        }}
      >
        <ChevronRight size={24} />
      </button>

      {/* Pagination Dots */}
      <div style={{
        position: 'absolute',
        bottom: '20px',
        left: '50%',
        transform: 'translateX(-50%)',
        display: 'flex',
        gap: '8px',
        zIndex: 10
      }}>
        {SLIDES.map((_, i) => (
          <div 
            key={i}
            onClick={() => setCurrentSlide(i)}
            style={{
              width: i === currentSlide ? '24px' : '8px',
              height: '8px',
              borderRadius: '4px',
              background: i === currentSlide ? 'white' : 'rgba(255, 255, 255, 0.4)',
              cursor: 'pointer',
              transition: 'all 0.3s ease'
            }}
          />
        ))}
      </div>
    </section>
  );
};
