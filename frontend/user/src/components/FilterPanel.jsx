import React from 'react';

export const FilterPanel = ({
  selectedGender,
  setSelectedGender,
  selectedCategory,
  setSelectedCategory,
  selectedBrand,
  setSelectedBrand,
  maxPrice,
  setMaxPrice,
  minRating,
  setMinRating,
  availableBrands = [],
  onReset
}) => {
  const defaultBrands = [
    "Roadster", "Trendyol", "BAESD", "DressBerry", "KALINI", "Tokyo Talkies",
    "HERE&NOW", "H&M", "Anouk", "Mast & Harbour", "Puma", "FOREVER 21", "max",
    "Sangria", "SHOWOFF", "MANGO", "V-Mart", "Levi's", "Zara", "Allen Solly", "Fabindia"
  ];
  const combinedBrands = ["All Brands", ...(availableBrands.length > 0 ? availableBrands : defaultBrands)];
  const brands = Array.from(new Set(combinedBrands));

  return (
    <aside className="product-card" style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: '18px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h3 style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--text-primary)' }}>Filters</h3>
        <button 
          onClick={onReset}
          className="btn btn-ghost"
          style={{ padding: '4px 8px', fontSize: '0.78rem', color: 'var(--color-primary-dark, #6f805e)' }}
        >
          Reset
        </button>
      </div>

      {/* 1. Brand Filter */}
      <div>
        <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 700, color: 'var(--text-secondary)', marginBottom: '6px', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
          Brand
        </label>
        <select
          value={selectedBrand}
          onChange={(e) => setSelectedBrand(e.target.value)}
          style={{
            width: '100%',
            padding: '8px 10px',
            borderRadius: 'var(--radius-sm, 4px)',
            border: '1.5px solid var(--panel-border)',
            background: 'var(--panel-solid)',
            color: 'var(--text-primary)',
            fontSize: '0.85rem',
            outline: 'none',
            cursor: 'pointer'
          }}
        >
          {brands.map(b => (
            <option key={b} value={b === 'All Brands' ? 'all' : b}>{b}</option>
          ))}
        </select>
      </div>

      {/* 2. Max Price Range Slider */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '8px' }}>
          <span style={{ textTransform: 'uppercase', letterSpacing: '0.04em', fontWeight: 700 }}>Max Price</span>
          <span style={{
            color: 'var(--color-tertiary, #CC5500)',
            fontWeight: 800,
            background: 'var(--color-tertiary-light, rgba(204, 85, 0, 0.12))',
            padding: '1px 7px',
            borderRadius: '4px'
          }}>
            ₹{maxPrice.toLocaleString('en-IN')}
          </span>
        </div>
        <input 
          type="range" 
          min="500" 
          max="10000" 
          step="250"
          value={maxPrice} 
          onChange={(e) => setMaxPrice(Number(e.target.value))}
          style={{ width: '100%', accentColor: 'var(--color-tertiary, #CC5500)', cursor: 'pointer' }}
        />
      </div>

      {/* 3. Minimum Rating Filter */}
      <div>
        <label style={{ display: 'block', fontSize: '0.8rem', fontWeight: 700, color: 'var(--text-secondary)', marginBottom: '6px', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
          Minimum Rating
        </label>
        <select
          value={minRating}
          onChange={(e) => setMinRating(Number(e.target.value))}
          style={{
            width: '100%',
            padding: '8px 10px',
            borderRadius: 'var(--radius-sm, 4px)',
            border: '1.5px solid var(--panel-border)',
            background: 'var(--panel-solid)',
            color: 'var(--text-primary)',
            fontSize: '0.85rem',
            outline: 'none',
            cursor: 'pointer'
          }}
        >
          <option value={0}>Any Rating</option>
          <option value={3.5}>★ 3.5 Stars & Above</option>
          <option value={4.0}>★ 4.0 Stars & Above</option>
          <option value={4.5}>★ 4.5 Stars & Above</option>
        </select>
      </div>
    </aside>
  );
};

export default FilterPanel;
