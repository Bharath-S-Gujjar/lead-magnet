import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Shirt, Lock, User, LogIn } from 'lucide-react';
import { useAdminAuth } from '../context/AdminAuthContext';
import ParticleDrift from '../components/ParticleDrift';

export function AdminLogin() {
  const navigate = useNavigate();
  const { adminLogin } = useAdminAuth();

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = (e) => {
    e.preventDefault();
    setError('');

    if (!username || !password) {
      setError('Please enter your administrator username and password.');
      return;
    }

    const submitLogin = async () => {
      setLoading(true);
      const res = await adminLogin(username, password);
      setLoading(false);
      if (!res.success) {
        setError(res.message);
      } else {
        navigate('/');
      }
    };

    submitLogin();
  };

  return (
    <div style={{
      minHeight: '100vh',
      width: '100%',
      position: 'relative',
      background: 'var(--bg-app)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '20px',
      overflow: 'hidden'
    }}>
      {/* Particle Drift 2 Interactive Background */}
      <div
        style={{
          position: 'fixed',
          top: 0,
          left: 0,
          width: '100vw',
          height: '100vh',
          zIndex: 0,
          pointerEvents: 'none',
          overflow: 'hidden'
        }}
      >
        <ParticleDrift
          background="transparent"
          baseColor="#A7A7A7"
          accentColor="#CC5500"
          density={120}
          dotSize={3.5}
          speed={20}
          hover={200}
        />
      </div>

      <div style={{
        position: 'relative',
        zIndex: 1,
        width: '100%',
        maxWidth: '460px',
        background: 'var(--panel-solid)',
        border: '1px solid var(--panel-border)',
        boxShadow: '0 8px 30px rgba(0, 0, 0, 0.12)',
        borderRadius: 'var(--radius-md, 6px)',
        padding: '36px 32px',
        display: 'flex',
        flexDirection: 'column',
        gap: '24px'
      }}>
        {/* Header Branding */}
        <div style={{ textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '10px' }}>
          <div style={{
            width: '52px',
            height: '52px',
            borderRadius: '8px',
            background: 'var(--color-primary, #9CAF88)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#1a1d18',
            fontWeight: 800,
            fontSize: '1.2rem',
            boxShadow: '0 4px 16px rgba(156, 175, 136, 0.4)'
          }}>
            LM
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
              Admin Username
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
              <User size={18} style={{ color: 'var(--text-muted)' }} />
              <input 
                type="text"
                placeholder="admin"
                value={username}
                onChange={(e) => { setUsername(e.target.value); setError(''); }}
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
