import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Shirt, Lock, Mail, LogIn } from 'lucide-react';
import { useAdminAuth } from '../context/AdminAuthContext';

export function AdminLogin() {
  const navigate = useNavigate();
  const { adminLogin } = useAdminAuth();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = (e) => {
    e.preventDefault();
    setError('');

    if (!email || !password) {
      setError('Please enter your administrator email and password.');
      return;
    }

    setLoading(true);
    setTimeout(() => {
      const res = adminLogin(email, password);
      setLoading(false);
      if (!res.success) {
        setError(res.message);
      } else {
        navigate('/');
      }
    }, 400);
  };

  return (
    <div style={{
      minHeight: '100vh',
      width: '100%',
      background: 'var(--bg-app)',
      backgroundImage: 'var(--bg-gradient)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '20px'
    }}>
      <div style={{
        width: '100%',
        maxWidth: '480px',
        background: 'var(--panel-solid)',
        border: '1px solid var(--panel-border)',
        boxShadow: 'var(--panel-shadow-hover)',
        borderRadius: 'var(--radius-lg)',
        padding: '36px 32px',
        display: 'flex',
        flexDirection: 'column',
        gap: '24px'
      }}>
        {/* Header Branding */}
        <div style={{ textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '10px' }}>
          <div style={{
            width: '56px',
            height: '56px',
            borderRadius: '16px',
            background: 'linear-gradient(135deg, #4f46e5 0%, #3b82f6 100%)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'white',
            boxShadow: '0 8px 20px rgba(79, 70, 229, 0.3)'
          }}>
            <Shirt size={30} />
          </div>
          <div>
            <h2 style={{ fontFamily: 'var(--font-heading)', fontSize: '1.6rem', fontWeight: 800, color: 'var(--text-primary)' }}>
              Lead Magnet Admin
            </h2>
            <p style={{ fontSize: '0.86rem', color: 'var(--text-secondary)', marginTop: '4px' }}>
              Clothing Brand Intelligence & Analytics Portal
            </p>
          </div>
        </div>

        {/* Error Notification */}
        {error && (
          <div style={{
            padding: '12px 14px',
            borderRadius: 'var(--radius-sm)',
            background: 'rgba(244, 63, 94, 0.1)',
            border: '1px solid rgba(244, 63, 94, 0.3)',
            color: 'var(--accent-rose)',
            fontSize: '0.85rem',
            fontWeight: 600
          }}>
            {error}
          </div>
        )}

        {/* Login Form */}
        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div>
            <label style={{ fontSize: '0.82rem', fontWeight: 700, color: 'var(--text-primary)', display: 'block', marginBottom: '6px' }}>
              Admin Email Address
            </label>
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              border: '1px solid var(--panel-border)',
              borderRadius: 'var(--radius-md)',
              padding: '10px 14px',
              background: 'var(--bg-app)'
            }}>
              <Mail size={18} style={{ color: 'var(--text-muted)' }} />
              <input 
                type="email"
                placeholder="admin@leadmagnet.com"
                value={email}
                onChange={(e) => { setEmail(e.target.value); setError(''); }}
                required
                style={{
                  border: 'none',
                  background: 'transparent',
                  outline: 'none',
                  width: '100%',
                  fontSize: '0.88rem',
                  color: 'var(--text-primary)'
                }}
              />
            </div>
          </div>

          <div>
            <label style={{ fontSize: '0.82rem', fontWeight: 700, color: 'var(--text-primary)', display: 'block', marginBottom: '6px' }}>
              Admin Password
            </label>
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              border: '1px solid var(--panel-border)',
              borderRadius: 'var(--radius-md)',
              padding: '10px 14px',
              background: 'var(--bg-app)'
            }}>
              <Lock size={18} style={{ color: 'var(--text-muted)' }} />
              <input 
                type="password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => { setPassword(e.target.value); setError(''); }}
                required
                style={{
                  border: 'none',
                  background: 'transparent',
                  outline: 'none',
                  width: '100%',
                  fontSize: '0.88rem',
                  color: 'var(--text-primary)'
                }}
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="btn btn-primary"
            style={{
              width: '100%',
              padding: '12px',
              borderRadius: 'var(--radius-md)',
              fontSize: '0.92rem',
              fontWeight: 700,
              marginTop: '8px',
              gap: '8px'
            }}
          >
            <LogIn size={18} />
            {loading ? 'Authenticating Admin...' : 'Sign In to Admin Dashboard'}
          </button>
        </form>
      </div>
    </div>
  );
}
