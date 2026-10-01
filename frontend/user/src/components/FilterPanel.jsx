import React from 'react';
import { Filter, RotateCcw } from 'lucide-react';

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
    <aside className="glass-card" style={{ padding: '24px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Filter size={18} style={{ color: 'var(--accent-indigo)' }} />
          <h3 className="heading-md" style={{ color: 'var(--text-primary)' }}>Filters</h3>
        </div>
        <button 
          onClick={onReset}
          className="btn btn-ghost"
          style={{ padding: '4px 8px', fontSize: '0.78rem', color: 'var(--accent-indigo)' }}
        >
          <RotateCcw size={12} /> Reset
        </button>
      </div>

      {/* 1. Brand Filter */}
      <div>
        <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 700, color: 'var(--text-secondary)', marginBottom: '8px' }}>
          Brand
        </label>
        <select
          value={selectedBrand}
          onChange={(e) => setSelectedBrand(e.target.value)}
          style={{
            width: '100%',
            padding: '9px 12px',
            borderRadius: 'var(--radius-md)',
            border: '1px solid var(--panel-border)',
            background: 'var(--panel-solid)',
            color: 'var(--text-primary)',
            fontSize: '0.85rem',
            outline: 'none'
          }}
        >
          {brands.map(b => (
            <option key={b} value={b === 'All Brands' ? 'all' : b}>{b}</option>
          ))}
        </select>
      </div>

      {/* 2. Max Price Range Slider */}
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.82rem', fontWeight: 700, color: 'var(--text-secondary)', marginBottom: '8px' }}>
          <span>Max Price:</span>
          <span style={{ color: 'var(--accent-indigo)' }}>₹{maxPrice.toLocaleString('en-IN')}</span>
        </div>
        <input 
          type="range" 
          min="500" 
          max="10000" 
          step="250"
          value={maxPrice} 
          onChange={(e) => setMaxPrice(Number(e.target.value))}
          style={{ width: '100%', accentColor: 'var(--accent-indigo)', cursor: 'pointer' }}
        />
      </div>

      {/* 3. Minimum Rating Filter */}
      <div>
        <label style={{ display: 'block', fontSize: '0.82rem', fontWeight: 700, color: 'var(--text-secondary)', marginBottom: '8px' }}>
          Minimum Rating
        </label>
        <select
          value={minRating}
          onChange={(e) => setMinRating(Number(e.target.value))}
          style={{
            width: '100%',
            padding: '9px 12px',
            borderRadius: 'var(--radius-md)',
            border: '1px solid var(--panel-border)',
            background: 'var(--panel-solid)',
            color: 'var(--text-primary)',
            fontSize: '0.85rem',
            outline: 'none'
          }}
        >
          <option value="0">All Ratings</option>
          <option value="4.0">4.0+ Stars</option>
          <option value="4.5">4.5+ Stars</option>
          <option value="4.8">4.8+ Stars</option>
        </select>
      </div>
    </aside>
  );
};
