import React, { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import '../styles/auth.css';

function Login() {
  const navigate = useNavigate();
  const location = useLocation();
  const { login } = useAuth();
  
  const [customerForm, setCustomerForm] = useState({ identifier: '', password: '' });
  const [error, setError] = useState('');
  const [successNotice, setSuccessNotice] = useState('');

  useEffect(() => {
    if (location.state?.message) {
      setSuccessNotice(location.state.message);
    }
    if (location.state?.email) {
      setCustomerForm((prev) => ({ ...prev, identifier: location.state.email }));
    }
  }, [location.state]);

  const isCustomerValid = useMemo(
    () => customerForm.identifier.trim().length >= 1 && customerForm.password.length >= 1,
    [customerForm.identifier, customerForm.password]
  );

  const handleCustomerSubmit = (event) => {
    event.preventDefault();
    setError('');
    setSuccessNotice('');

    if (!isCustomerValid) {
      setError('Please enter your email/username and password.');
      return;
    }

    const result = login(customerForm.identifier, customerForm.password);
    if (!result.success) {
      setError(result.message);
      return;
    }
    navigate('/');
  };

  return (
    <div className="auth-shell">
      <div className="auth-card glass-panel">
        <div className="auth-card-header">
          <p className="eyebrow">Lead Magnet Store</p>
          <h2>User Login</h2>
          <p>Welcome back! Sign in to your account to continue shopping.</p>
        </div>

        {successNotice ? <div className="success-text" style={{ marginBottom: '14px' }}>{successNotice}</div> : null}

        <form className="auth-form" onSubmit={handleCustomerSubmit} noValidate>
          <label>
            Email Address, Username or Phone
            <input 
              type="text" 
              placeholder="e.g. rahul@gmail.com or rahul"
              value={customerForm.identifier} 
              onChange={(e) => {
                setError('');
                setCustomerForm({ ...customerForm, identifier: e.target.value });
              }} 
              required 
            />
          </label>
          <label>
            Password
            <input 
              type="password" 
              placeholder="Enter your password"
              value={customerForm.password} 
              onChange={(e) => {
                setError('');
                setCustomerForm({ ...customerForm, password: e.target.value });
              }} 
              required 
            />
          </label>
          {error ? <div className="error-text">{error}</div> : null}
          <button className="btn" type="submit" disabled={!isCustomerValid}>
            Sign In
          </button>
        </form>

        <div className="auth-links">
          <Link to="/signup">Don't have an account? Register here</Link>
          <Link to="/">Back to Store</Link>
        </div>
      </div>
    </div>
  );
}

export default Login;
