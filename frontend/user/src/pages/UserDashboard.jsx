import React, { useEffect, useState, useCallback } from 'react';
import { HeroBanner } from '../components/HeroBanner';
import { CategorySection } from '../components/CategorySection';
import { ProductGrid } from '../components/ProductGrid';
import { FilterPanel } from '../components/FilterPanel';
import { fetchProducts, fetchProductMeta, trackCustomerEvent } from '../services/api';

function normalizeProduct(product) {
  return {
    ...product,
    id: product.product_id || product.id || product._id,
    product_id: product.product_id || product.id || product._id,
    name: product.title || product.name || '',
    title: product.title || product.name || '',
    image: product.primary_image || product.image || product.images?.[0] || '',
    primary_image: product.primary_image || product.image || product.images?.[0] || '',
    rating: product.rating || 4.3,
    discount: product.discount_percent || product.discount || 0,
    originalPrice: product.mrp || product.price_before_discount || null,
    gender: product.gender || 'Unisex',
    category: product.category || 'Clothing',
    brand: product.brand || 'Lead Magnet',
    price: Number(product.price || 0),
  };
}

export const UserDashboard = ({ searchQuery, selectedGender, setSelectedGender }) => {
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedCategory, setSelectedCategory] = useState('all');
  const [selectedBrand, setSelectedBrand] = useState('all');
  const [maxPrice, setMaxPrice] = useState(10000);
  const [minRating, setMinRating] = useState(0);
  const [page, setPage] = useState(1);
  const [pagination, setPagination] = useState({ page: 1, limit: 24, total: 0, pages: 1 });
  const [availableBrands, setAvailableBrands] = useState([]);
  const [totalCatalogCount, setTotalCatalogCount] = useState(0);
  const [mobileFilterOpen, setMobileFilterOpen] = useState(false);

  // Load catalog metadata once on mount
  useEffect(() => {
    trackCustomerEvent('page_view', { page: '/' });
    fetchProductMeta()
      .then((meta) => {
        if (meta) {
          if (Array.isArray(meta.brands) && meta.brands.length > 0) {
            setAvailableBrands(meta.brands);
          }
          if (meta.total || meta.total_catalog) {
            setTotalCatalogCount(meta.total || meta.total_catalog);
          }
        }
      })
      .catch(() => {
        // Non-blocking metadata fallback
      });
  }, []);

  const [debouncedSearch, setDebouncedSearch] = useState(searchQuery || '');

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchQuery || '');
    }, 300);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  // Fetch products with server-side pagination & filtering
  const loadProducts = useCallback(async (currentPage = page) => {
    setLoading(true);
    setError(null);
    try {
      const params = {
        page: currentPage,
        limit: 24,
      };

      if (selectedGender && selectedGender !== 'all') {
        params.gender = selectedGender;
      }
      if (selectedCategory && selectedCategory !== 'all') {
        params.category = selectedCategory;
      }
      if (selectedBrand && selectedBrand !== 'all') {
        params.brand = selectedBrand;
      }
      if (debouncedSearch && debouncedSearch.trim()) {
        params.search = debouncedSearch.trim();
      }
      if (maxPrice && maxPrice < 10000) {
        params.max_price = maxPrice;
      }
      if (minRating && minRating > 0) {
        params.min_rating = minRating;
      }

      const result = await fetchProducts(params);
      const rawProducts = Array.isArray(result?.data) ? result.data : [];
      setProducts(rawProducts.map(normalizeProduct));

      if (result?.pagination) {
        setPagination(result.pagination);
      } else {
        setPagination({
          page: currentPage,
          limit: 24,
          total: rawProducts.length,
          pages: 1,
        });
      }
    } catch (err) {
      console.error('Failed to load products:', err);
      setError(err.message || 'Unable to connect to product catalog service.');
      setProducts([]);
    } finally {
      setLoading(false);
    }
  }, [page, selectedGender, selectedCategory, selectedBrand, debouncedSearch, maxPrice, minRating]);

  // When filters or search change, reset to page 1 and fetch
  useEffect(() => {
    setPage(1);
    loadProducts(1);
  }, [selectedGender, selectedCategory, selectedBrand, debouncedSearch, maxPrice, minRating]);

  // Trigger search tracking event
  useEffect(() => {
    if (debouncedSearch && debouncedSearch.trim()) {
      trackCustomerEvent('search', {
        metadata: { query: debouncedSearch.trim() },
      });
    }
  }, [debouncedSearch]);

  const handlePageChange = (newPage) => {
    if (newPage < 1 || (pagination.pages && newPage > pagination.pages) || newPage === page) return;
    setPage(newPage);
    loadProducts(newPage);
    window.scrollTo({ top: 350, behavior: 'smooth' });
  };

  const handleResetFilters = () => {
    setSelectedGender && setSelectedGender('all');
    setSelectedCategory('all');
    setSelectedBrand('all');
    setMaxPrice(10000);
    setMinRating(0);
    setPage(1);
  };

  return (
    <div className="main-page-wrapper" style={{ position: 'relative', width: '100%' }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '24px', position: 'relative', zIndex: 1 }}>
        {/* Hero Clothing Banner Carousel */}
        <HeroBanner />

      {/* Category Pills & Gender Tabs */}
      <CategorySection
        selectedGender={selectedGender}
        setSelectedGender={setSelectedGender}
        selectedCategory={selectedCategory}
        setSelectedCategory={setSelectedCategory}
        totalItemsCount={pagination.total || totalCatalogCount}
      />

      {/* Mobile/Tablet Filter Toggle Button */}
      <div className="filter-mobile-toggle" style={{ display: 'none', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
        <button
          onClick={() => setMobileFilterOpen(!mobileFilterOpen)}
          className="btn btn-secondary"
          style={{ width: '100%', padding: '10px 16px', fontWeight: 700 }}
        >
          {mobileFilterOpen ? '✕ Hide Filters' : '⚡ Filter Products (Brand, Price, Rating)'}
        </button>
      </div>

      {/* Main Content Layout: Sidebar Filter + Product Grid */}
      <div className="dashboard-layout">
        <div className={`filter-sidebar-wrapper ${mobileFilterOpen ? 'is-open' : ''}`}>
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
            availableBrands={availableBrands}
          />
        </div>

        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px', flexWrap: 'wrap', gap: '8px' }}>
            <h3 className="heading-md" style={{ color: 'var(--text-primary)' }}>
              {loading ? (
                'Loading clothing items...'
              ) : pagination.total > 0 ? (
                `Showing ${products.length} of ${pagination.total.toLocaleString('en-IN')} Clothing Items`
              ) : (
                '0 Clothing Items Found'
              )}
            </h3>
            {pagination.pages > 1 && !loading && (
              <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', fontWeight: 600 }}>
                Page {pagination.page} of {pagination.pages}
              </span>
            )}
          </div>

          <ProductGrid
            products={products}
            loading={loading}
            error={error}
            onRetry={() => loadProducts(page)}
            onResetFilters={handleResetFilters}
          />

          {/* Server-Side Pagination Bar */}
          {!loading && !error && pagination.pages > 1 && (
            <div style={{
              display: 'flex',
              justifyContent: 'center',
              alignItems: 'center',
              gap: '12px',
              marginTop: '36px',
              paddingTop: '20px',
              borderTop: '1px solid var(--panel-border)'
            }}>
              <button
                onClick={() => handlePageChange(page - 1)}
                disabled={page <= 1}
                className="btn btn-secondary"
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '6px',
                  padding: '8px 16px',
                  fontSize: '0.85rem'
                }}
              >
                ‹ Previous
              </button>

              <span style={{
                fontSize: '0.88rem',
                fontWeight: 700,
                color: 'var(--text-primary)',
                padding: '0 8px'
              }}>
                Page {page} of {pagination.pages.toLocaleString('en-IN')}
              </span>

              <button
                onClick={() => handlePageChange(page + 1)}
                disabled={page >= pagination.pages}
                className="btn btn-secondary"
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '6px',
                  padding: '8px 16px',
                  fontSize: '0.85rem'
                }}
              >
                Next ›
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
    </div>
  );
};

export default UserDashboard;
