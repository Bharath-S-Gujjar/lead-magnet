import React, { useMemo } from 'react';

// Authoritative clothing categories matching MongoDB Atlas cleaned catalog
const REAL_CATALOG_CATEGORIES = [
  "All Categories",
  "T-Shirts",
  "Kurtas & Kurta Sets",
  "Tops & Tunics",
  "Shirts",
  "Sweaters & Sweatshirts",
  "Trousers & Pants",
  "Jeans",
  "Innerwear & Sleepwear",
  "Skirts",
  "Jackets & Coats",
  "Shorts",
  "Dresses & Jumpsuits"
];

// Gender-specific category sub-sets
const GENDER_CATEGORIES = {
  Men: [
    "All Categories",
    "T-Shirts",
    "Shirts",
    "Jeans",
    "Sweaters & Sweatshirts",
    "Trousers & Pants",
    "Jackets & Coats",
    "Shorts",
    "Innerwear & Sleepwear"
  ],
  Women: [
    "All Categories",
    "Kurtas & Kurta Sets",
    "Tops & Tunics",
    "T-Shirts",
    "Dresses & Jumpsuits",
    "Skirts",
    "Jeans",
    "Trousers & Pants",
    "Sweaters & Sweatshirts",
    "Jackets & Coats"
  ],
  Kids: [
    "All Categories",
    "T-Shirts",
    "Shirts",
    "Jeans",
    "Shorts",
    "Dresses & Jumpsuits",
    "Sweaters & Sweatshirts"
  ]
};

export const CategorySection = ({ 
  selectedGender = 'all', 
  setSelectedGender, 
  selectedCategory = 'all', 
  setSelectedCategory,
  totalItemsCount = 0 
}) => {
  const categories = useMemo(() => {
    if (selectedGender && GENDER_CATEGORIES[selectedGender]) {
      return GENDER_CATEGORIES[selectedGender];
    }
    return REAL_CATALOG_CATEGORIES;
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
    <section style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      {/* Gender Selection Tabs */}
      <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center' }}>
        {genderTabs.map((g) => {
          const isSelected = selectedGender === g.value || (!selectedGender && g.value === 'all');
          return (
            <button
              key={g.value}
              onClick={() => {
                setSelectedGender && setSelectedGender(g.value);
                if (g.value !== 'all' && GENDER_CATEGORIES[g.value] && selectedCategory !== 'all') {
                  if (!GENDER_CATEGORIES[g.value].includes(selectedCategory)) {
                    setSelectedCategory && setSelectedCategory('all');
                  }
                }
              }}
              style={{
                padding: '8px 18px',
                borderRadius: 'var(--radius-sm, 4px)',
                border: isSelected ? '1.5px solid var(--color-primary, #9CAF88)' : '1px solid var(--panel-border)',
                background: isSelected ? 'var(--color-primary, #9CAF88)' : 'var(--panel-solid)',
                color: isSelected ? '#1a2016' : 'var(--text-primary)',
                fontWeight: 700,
                fontSize: '0.85rem',
                cursor: 'pointer',
                boxShadow: 'none',
                transition: 'all 0.18s ease'
              }}
            >
              {g.label}
            </button>
          );
        })}
      </div>

      {/* Category Section Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: 'var(--color-tertiary, #CC5500)', display: 'inline-block' }} />
          <h3 style={{ fontSize: '1.05rem', fontWeight: 700, color: 'var(--text-primary)', letterSpacing: '0.01em' }}>
            {sectionTitle}
          </h3>
        </div>
        <span style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', fontWeight: 600 }}>
          {totalItemsCount > 0 ? (
            <>
              <strong style={{ color: 'var(--color-tertiary, #CC5500)' }}>{totalItemsCount.toLocaleString('en-IN')}</strong> items available
            </>
          ) : 'Clothing Catalog'}
        </span>
      </div>

      {/* Category Buttons */}
      <div style={{
        display: 'flex',
        gap: '8px',
        overflowX: 'auto',
        paddingBottom: '6px',
        scrollbarWidth: 'thin'
      }}>
        {categories.map((cat) => {
          const isSelected = (selectedCategory === cat) || (selectedCategory === 'all' && cat === 'All Categories');
          return (
            <button
              key={cat}
              onClick={() => setSelectedCategory && setSelectedCategory(cat === 'All Categories' ? 'all' : cat)}
              style={{
                padding: '7px 15px',
                borderRadius: 'var(--radius-sm, 4px)',
                border: isSelected ? '1.5px solid var(--color-tertiary, #CC5500)' : '1px solid var(--panel-border)',
                background: isSelected ? 'var(--color-tertiary-light, rgba(204, 85, 0, 0.12))' : 'var(--panel-solid)',
                color: isSelected ? 'var(--color-tertiary, #CC5500)' : 'var(--text-primary)',
                fontSize: '0.82rem',
                fontWeight: isSelected ? 700 : 600,
                cursor: 'pointer',
                whiteSpace: 'nowrap',
                boxShadow: 'none',
                transition: 'all 0.15s ease'
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

export default CategorySection;
