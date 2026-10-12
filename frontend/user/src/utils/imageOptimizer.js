/**
 * Utility for image compression and responsive resizing
 */
export function getOptimizedImageUrl(url, width = 600, quality = 75) {
  if (!url || typeof url !== 'string') return '';

  // 1. Optimize Unsplash images with auto-format (webp/avif), dimension capping, and 75% quality compression
  if (url.includes('images.unsplash.com')) {
    try {
      const u = new URL(url);
      u.searchParams.set('auto', 'format');
      u.searchParams.set('fit', 'crop');
      u.searchParams.set('q', String(quality));
      if (width) {
        u.searchParams.set('w', String(width));
      }
      return u.toString();
    } catch {
      return url;
    }
  }

  // 2. Cloudinary optimizations
  if (url.includes('res.cloudinary.com') && !url.includes('f_auto')) {
    return url.replace('/upload/', `/upload/f_auto,q_${quality},w_${width}/`);
  }

  return url;
}

export default getOptimizedImageUrl;
