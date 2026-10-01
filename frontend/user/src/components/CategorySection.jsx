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
    <section style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
      {/* Gender Selection Tabs */}
      <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', alignItems: 'center' }}>
        {genderTabs.map((g) => {
          const isSelected = selectedGender === g.value || (!selectedGender && g.value === 'all');
          return (
            <button
              key={g.value}
              onClick={() => {
                setSelectedGender && setSelectedGender(g.value);
                // Reset category if switching gender and current category isn't in gender list
                if (g.value !== 'all' && GENDER_CATEGORIES[g.value] && selectedCategory !== 'all') {
                  if (!GENDER_CATEGORIES[g.value].includes(selectedCategory)) {
                    setSelectedCategory && setSelectedCategory('all');
                  }
                }
              }}
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
        <span style={{ fontSize: '0.82rem', color: 'var(--text-muted)', fontWeight: 600 }}>
          {totalItemsCount > 0 ? `${totalItemsCount.toLocaleString('en-IN')} Clothing Items Available` : 'Clothing Catalog'}
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
              onClick={() => setSelectedCategory && setSelectedCategory(cat === 'All Categories' ? 'all' : cat)}
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
