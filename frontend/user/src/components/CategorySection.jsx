import React, { useMemo } from 'react';
import { CLOTHING_PRODUCTS } from '../data/clothingProducts';

export const CategorySection = ({ selectedGender, setSelectedGender, selectedCategory, setSelectedCategory }) => {
  // Dynamically compute categories that contain items for selectedGender
  const categories = useMemo(() => {
    let prods = CLOTHING_PRODUCTS;
    if (selectedGender && selectedGender !== 'all') {
      prods = prods.filter(p => p.gender.toLowerCase() === selectedGender.toLowerCase());
    }
    const catSet = new Set();
    prods.forEach(p => catSet.add(p.category));
    
    // Order standard categories logically
    const standardOrder = ["T-Shirts", "Shirts", "Jeans", "Hoodies", "Jackets", "Dresses", "Kurtas", "Sarees", "Trousers", "Kids Wear"];
    const filteredCats = catSet.size > 0 ? standardOrder.filter(c => catSet.has(c)) : standardOrder;
    
    return ["All Categories", ...filteredCats];
  }, [selectedGender]);

  const totalItemsCount = useMemo(() => {
    if (selectedGender && selectedGender !== 'all') {
      return CLOTHING_PRODUCTS.filter(p => p.gender.toLowerCase() === selectedGender.toLowerCase()).length;
    }
    return CLOTHING_PRODUCTS.length;
  }, [selectedGender]);

  const sectionTitle = selectedGender && selectedGender !== 'all' 
    ? `${selectedGender}'s Clothing Categories` 
    : 'Clothing Categories';

  const genderTabs = [
    { label: 'All Clothing', value: 'all' },
    { label: "Men's Clothing", value: 'Men' },
    { label: "Women's Clothing", value: 'Women' },
    { label: "Kids' Clothing", value: 'Kids' }
  ];

  return (
    <section style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
      {/* Gender Selection Tabs */}
      <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', alignItems: 'center' }}>
        {genderTabs.map((g) => {
          const isSelected = selectedGender === g.value || (!selectedGender && g.value === 'all');
          return (
            <button
              key={g.value}
              onClick={() => setSelectedGender && setSelectedGender(g.value)}
              style={{
                padding: '9px 22px',
                borderRadius: 'var(--radius-full)',
                border: isSelected ? '1px solid var(--accent-indigo)' : '1px solid var(--panel-border)',
                background: isSelected ? 'var(--accent-indigo)' : 'var(--panel-solid)',
                color: isSelected ? 'white' : 'var(--text-primary)',
                fontWeight: 800,
                fontSize: '0.88rem',
                cursor: 'pointer',
                boxShadow: isSelected ? '0 4px 14px rgba(79, 70, 229, 0.3)' : 'none',
                transition: 'all 0.2s ease'
              }}
            >
              {g.label}
            </button>
          );
        })}
      </div>

      {/* Category Section Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <h3 className="heading-md" style={{ color: 'var(--text-primary)' }}>{sectionTitle}</h3>
        <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', fontWeight: 600 }}>
          {totalItemsCount} Clothing Items Available
        </span>
      </div>

      {/* Category Pills */}
      <div style={{
        display: 'flex',
        gap: '10px',
        overflowX: 'auto',
        paddingBottom: '8px',
        scrollbarWidth: 'thin'
      }}>
        {categories.map((cat) => {
          const isSelected = (selectedCategory === cat) || (selectedCategory === 'all' && cat === 'All Categories');
          return (
            <button
              key={cat}
              onClick={() => setSelectedCategory(cat === 'All Categories' ? 'all' : cat)}
              style={{
                padding: '8px 18px',
                borderRadius: 'var(--radius-full)',
                border: isSelected ? '1px solid var(--accent-indigo)' : '1px solid var(--panel-border)',
                background: isSelected ? 'var(--accent-indigo)' : 'var(--panel-solid)',
                color: isSelected ? 'white' : 'var(--text-primary)',
                fontSize: '0.85rem',
                fontWeight: 700,
                cursor: 'pointer',
                whiteSpace: 'nowrap',
                boxShadow: isSelected ? '0 4px 12px rgba(79, 70, 229, 0.25)' : 'none',
                transition: 'all 0.2s ease'
              }}
            >
              {cat}
            </button>
          );
        })}
      </div>
    </section>
  );
};
