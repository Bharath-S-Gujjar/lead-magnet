// From Uiverse.io by reglobby
import React from 'react';
import { useNavigate } from 'react-router-dom';

export const UserLoginButton = ({
  label = 'Log In',
  to,
  onClick,
  style,
  className = '',
  disabled = false,
  ...props
}) => {
  const navigate = useNavigate();

  const handleClick = (e) => {
    if (disabled) return;
    if (onClick) {
      onClick(e);
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

  return (
    <div
      aria-label="User Login Button"
      tabIndex={disabled ? -1 : 0}
      role="button"
      className={`user-profile user-profile-login ${className}`}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
      style={{
        opacity: disabled ? 0.5 : 1,
        cursor: disabled ? 'not-allowed' : 'pointer',
        ...style,
      }}
      {...props}
    >
      <div className="user-profile-inner">
        <svg
          aria-hidden="true"
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 24 24"
        >
          <g data-name="Layer 2" id="Layer_2">
            <path
              d="m15.626 11.769a6 6 0 1 0 -7.252 0 9.008 9.008 0 0 0 -5.374 8.231 3 3 0 0 0 3 3h12a3 3 0 0 0 3-3 9.008 9.008 0 0 0 -5.374-8.231zm-7.626-4.769a4 4 0 1 1 4 4 4 4 0 0 1 -4-4zm10 14h-12a1 1 0 0 1 -1-1 7 7 0 0 1 14 0 1 1 0 0 1 -1 1z"
            />
          </g>
        </svg>
        <p>{label}</p>
      </div>
    </div>
  );
};

export default UserLoginButton;
