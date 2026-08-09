import React, { useEffect, useState, useMemo } from 'react';
import { HeroBanner } from '../components/HeroBanner';
import { CategorySection } from '../components/CategorySection';
import { ProductGrid } from '../components/ProductGrid';
import { FilterPanel } from '../components/FilterPanel';
import { CLOTHING_PRODUCTS } from '../data/clothingProducts';
import { API_BASE_URL, parseJsonResponse, trackCustomerEvent } from '../services/api';

function normalizeProduct(product) {
  return {
    ...product,
    id: product._id || product.id,
    image: product.image || product.images?.[0] || 'https://via.placeholder.com/600x800?text=Clothing',
    rating: product.rating || 4.3,
    discount: product.discount || 0,
    gender: product.gender || 'Unisex',
    category: product.category || 'Clothing',
    brand: product.brand || 'Lead Magnet',
    price: Number(product.price || 0),
  };
}

export const UserDashboard = ({ searchQuery, selectedGender, setSelectedGender }) => {
  const [products, setProducts] = useState(CLOTHING_PRODUCTS);
  const [selectedCategory, setSelectedCategory] = useState('all');
  const [selectedBrand, setSelectedBrand] = useState('all');
  const [maxPrice, setMaxPrice] = useState(10000);
  const [minRating, setMinRating] = useState(0);

  useEffect(() => {
    trackCustomerEvent('page_view', { page: '/' });
    fetch(`${API_BASE_URL}/api/products`)
      .then((response) => parseJsonResponse(response))
      .then((payload) => {
        if (payload.success && Array.isArray(payload.data)) {
          setProducts(payload.data.map(normalizeProduct));
        }
      })
      .catch(() => {
        setProducts(CLOTHING_PRODUCTS);
      });
  }, []);

  useEffect(() => {
    if (searchQuery && searchQuery.trim()) {
      trackCustomerEvent('search', {
        metadata: { query: searchQuery.trim() },
      });
    }
  }, [searchQuery]);

  const filteredProducts = useMemo(() => {
    return products.filter(product => {
      // 1. Gender Filter
      if (selectedGender && selectedGender !== 'all') {
        if (product.gender.toLowerCase() !== selectedGender.toLowerCase()) return false;
      }

      // 2. Category Filter
      if (selectedCategory && selectedCategory !== 'all') {
        if (product.category.toLowerCase() !== selectedCategory.toLowerCase()) return false;
      }

      // 3. Brand Filter
      if (selectedBrand && selectedBrand !== 'all') {
        if (product.brand.toLowerCase() !== selectedBrand.toLowerCase()) return false;
      }

      // 4. Max Price Filter
      if (product.price > maxPrice) return false;

      // 5. Min Rating Filter
      if (product.rating < minRating) return false;

      // 6. Search Query Filter
      if (searchQuery && searchQuery.trim() !== '') {
        const q = searchQuery.toLowerCase().trim();
        const matchesName = product.name.toLowerCase().includes(q);
        const matchesBrand = product.brand.toLowerCase().includes(q);
        const matchesCategory = product.category.toLowerCase().includes(q);
        const matchesGender = product.gender.toLowerCase().includes(q);
        if (!matchesName && !matchesBrand && !matchesCategory && !matchesGender) return false;
      }

      return true;
    });
  }, [products, selectedGender, selectedCategory, selectedBrand, maxPrice, minRating, searchQuery]);

  React.useEffect(() => {
    // Reset selected category to 'all' if current category is not available for new gender selection
    if (selectedGender && selectedGender !== 'all' && selectedCategory !== 'all') {
      const isValid = products.some(p => 
        p.gender.toLowerCase() === selectedGender.toLowerCase() && 
        p.category.toLowerCase() === selectedCategory.toLowerCase()
      );
      if (!isValid) {
        setSelectedCategory('all');
      }
    }
  }, [products, selectedGender]);

  const handleResetFilters = () => {
    setSelectedGender && setSelectedGender('all');
    setSelectedCategory('all');
    setSelectedBrand('all');
    setMaxPrice(10000);
    setMinRating(0);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '32px' }}>
      {/* Hero Clothing Banner Carousel */}
      <HeroBanner />

      {/* Category Pills */}
      <CategorySection 
        selectedGender={selectedGender}
        setSelectedGender={setSelectedGender}
        selectedCategory={selectedCategory}
        setSelectedCategory={setSelectedCategory}
      />

      {/* Main Content Layout: Sidebar Filter + Product Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: '260px 1fr', gap: '28px', alignItems: 'start' }}>
        <FilterPanel 
          selectedGender={selectedGender}
          setSelectedGender={setSelectedGender}
          selectedCategory={selectedCategory}
          setSelectedCategory={setSelectedCategory}
          selectedBrand={selectedBrand}
          setSelectedBrand={setSelectedBrand}
          maxPrice={maxPrice}
          setMaxPrice={setMaxPrice}
          minRating={minRating}
          setMinRating={setMinRating}
          onReset={handleResetFilters}
        />

        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '18px' }}>
            <h3 className="heading-md" style={{ color: 'var(--text-primary)' }}>
              Showing {filteredProducts.length} Clothing Items
            </h3>
          </div>

          <ProductGrid 
            products={filteredProducts} 
            onResetFilters={handleResetFilters}
          />
        </div>
      </div>
    </div>
  );
};
