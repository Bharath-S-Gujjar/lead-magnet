// From Uiverse.io by reglobby
import React from 'react';
import { useNavigate } from 'react-router-dom';

export const NavPillButton = ({
  icon,
  label,
  badge,
  avatar,
  to,
  href,
  onClick,
  variant = 'default',
  className = '',
  style = {},
  innerStyle = {},
  title,
  ariaLabel,
  disabled = false,
  ...props
}) => {
  const navigate = useNavigate();

  const handleClick = (e) => {
    if (disabled) return;
    if (onClick) {
      onClick(e);
    } else if (href) {
      window.location.href = href;
    } else if (to) {
      navigate(to);
    }
  };

  const handleKeyDown = (e) => {
    if (disabled) return;
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      handleClick(e);
    }
  };

  const isIconOnly = !label && !avatar;

  return (
    <div
      role="button"
      tabIndex={disabled ? -1 : 0}
      aria-label={ariaLabel || (typeof label === 'string' ? label : title)}
      title={title || (typeof label === 'string' ? label : undefined)}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
      className={`user-profile user-profile-${variant} ${isIconOnly ? 'user-profile-icon-only' : ''} ${className}`}
      style={{
        opacity: disabled ? 0.5 : 1,
        cursor: disabled ? 'not-allowed' : 'pointer',
        ...style,
      }}
      {...props}
    >
      <div className="user-profile-inner" style={innerStyle}>
        {avatar ? (
          <img
            src={avatar}
            alt={typeof label === 'string' ? label : 'User'}
            className="user-profile-avatar"
            style={{
              width: '24px',
              height: '24px',
              borderRadius: '50%',
              objectFit: 'cover',
              flexShrink: 0,
            }}
          />
        ) : (
          icon && <span className="user-profile-icon">{icon}</span>
        )}

        {label && <p className="user-profile-label">{label}</p>}

        {badge !== undefined && badge !== null && badge > 0 && (
          <span className="user-profile-badge">{badge}</span>
        )}
      </div>
    </div>
  );
};

export default NavPillButton;
