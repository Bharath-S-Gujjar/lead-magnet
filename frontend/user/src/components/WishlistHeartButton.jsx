import React from 'react';

/**
 * Uiverse.io Heart Wishlist Checkbox Button by catraco
 */
export const WishlistHeartButton = ({
  isLiked = false,
  onToggle,
  size = 38,
  heartColor = '#CC5500',
  style = {},
  className = '',
  title = 'Wishlist'
}) => {
  return (
    <div
      className={`heart-container ${className}`}
      style={{
        '--heart-color': heartColor,
        width: typeof size === 'number' ? `${size}px` : size,
        height: typeof size === 'number' ? `${size}px` : size,
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        ...style
      }}
      onClick={(e) => e.stopPropagation()}
      title={title || (isLiked ? 'Remove from Wishlist' : 'Add to Wishlist')}
    >
      <input
        type="checkbox"
        className="checkbox"
        checked={Boolean(isLiked)}
        onChange={(e) => {
          e.stopPropagation();
          onToggle && onToggle();
        }}
        aria-label={isLiked ? 'Remove from Wishlist' : 'Add to Wishlist'}
      />
      <div className="svg-container">
        <svg
          viewBox="0 0 24 24"
          className="svg-outline"
          xmlns="http://www.w3.org/2000/svg"
          style={{ width: '56%', height: '56%' }}
        >
          <path d="M17.5,1.917 a6.4,6.4,0,0,0-5.5,3.3,6.4,6.4,0,0,0-5.5-3.3A6.8,6.8,0,0,0,0,8.967c0,4.547,4.786,9.513,8.8,12.88a4.974,4.974,0,0,0,6.4,0C19.214,18.48,24,13.514,24,8.967A6.8,6.8,0,0,0,17.5,1.917Zm-3.585,18.4a2.973,2.973,0,0,1-3.83,0C4.947,16.006,2,11.87,2,8.967a4.8,4.8,0,0,1,4.5-5.05A4.8,4.8,0,0,1,11,8.967a1,1,0,0,0,2,0,4.8,4.8,0,0,1,4.5-5.05A4.8,4.8,0,0,1,22,8.967C22,11.87,19.053,16.006,13.915,20.313Z" />
        </svg>
        <svg
          viewBox="0 0 24 24"
          className="svg-filled"
          xmlns="http://www.w3.org/2000/svg"
          style={{ width: '56%', height: '56%' }}
        >
          <path d="M17.5,1.917 a6.4,6.4,0,0,0-5.5,3.3,6.4,6.4,0,0,0-5.5-3.3A6.8,6.8,0,0,0,0,8.967c0,4.547,4.786,9.513,8.8,12.88a4.974,4.974,0,0,0,6.4,0C19.214,18.48,24,13.514,24,8.967A6.8,6.8,0,0,0,17.5,1.917Z" />
        </svg>
        <svg
          className="svg-celebrate"
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 100 100"
          style={{ width: '100%', height: '100%' }}
        >
          <polygon points="10,10 20,20"></polygon>
          <polygon points="10,50 20,50"></polygon>
          <polygon points="20,80 30,70"></polygon>
          <polygon points="90,10 80,20"></polygon>
          <polygon points="90,50 80,50"></polygon>
          <polygon points="80,80 70,70"></polygon>
        </svg>
      </div>
    </div>
  );
};

export default WishlistHeartButton;
