import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { getCustomerSession } from '../services/api';

export function Profile() {
  const { customer: authCustomer, isCustomerAuthenticated, logout, updateProfile } = useAuth();
  const customer = authCustomer || getCustomerSession();
  const navigate = useNavigate();

  // Active modal state
  const [activeModal, setActiveModal] = useState(null); // 'edit_profile', 'addresses', 'language', 'notifications', 'cards', 'coupons', 'faqs', 'terms'

  const [profileForm, setProfileForm] = useState({
    fullName: customer?.full_name || customer?.fullName || customer?.username || '',
    email: customer?.email || '',
    phone: customer?.phone || '+91 9876543210',
    gender: customer?.gender || 'Male',
  });

  const rawAddresses = Array.isArray(customer?.addresses) && customer.addresses.length > 0 ? customer.addresses : [
    {
      id: 'addr-1',
      name: customer?.full_name || customer?.fullName || customer?.username || 'Valued Shopper',
      phone: customer?.phone || '+91 98765 43210',
      type: 'Home',
      street: '123 Fashion Street, Cyber City',
      city: 'Bengaluru',
      state: 'Karnataka',
      pincode: '560001',
      isDefault: true
    }
  ];
  const [addresses, setAddresses] = useState(rawAddresses);
  const [newAddr, setNewAddr] = useState({ name: '', phone: '', type: 'Home', street: '', city: '', state: '', pincode: '' });
  const [showAddAddr, setShowAddAddr] = useState(false);

  const [notifications, setNotifications] = useState(() => {
    return (customer?.notifications && typeof customer.notifications === 'object') ? customer.notifications : {
      email: true,
      sms: true,
      promotions: false,
      orderUpdates: true,
    };
  });

  const [toastMessage, setToastMessage] = useState('');

  const showToast = (msg) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(''), 3000);
  };

  const handleSaveProfile = (e) => {
    e.preventDefault();
    if (updateProfile) {
      updateProfile(profileForm);
    }
    showToast('Profile details updated successfully.');
    setActiveModal(null);
  };

  const handleAddAddress = (e) => {
    e.preventDefault();
    if (!newAddr.street || !newAddr.city) return;
    const added = { id: `addr-${Date.now()}`, ...newAddr, isDefault: addresses.length === 0 };
    const updated = [...addresses, added];
    setAddresses(updated);
    if (updateProfile) updateProfile({ addresses: updated });
    setNewAddr({ name: '', phone: '', type: 'Home', street: '', city: '', state: '', pincode: '' });
    setShowAddAddr(false);
    showToast('New address saved successfully.');
  };

  const handleToggleNotification = (key) => {
    const updated = { ...notifications, [key]: !notifications[key] };
    setNotifications(updated);
    if (updateProfile) updateProfile({ notifications: updated });
    showToast('Notification preference saved.');
  };

  const handleLogout = () => {
    if (logout) logout();
    navigate('/login');
  };

  const isAuth = Boolean(isCustomerAuthenticated || customer?.email || customer?.token);

  if (!isAuth) {
    return (
      <div style={{ maxWidth: '600px', margin: '40px auto', padding: '0 20px', textAlign: 'center' }}>
        <div style={{
          padding: '40px 24px',
          borderRadius: '4px',
          background: 'var(--panel-solid)',
          border: '1px solid var(--panel-border)'
        }}>
          <div style={{
            width: '52px',
            height: '52px',
            borderRadius: '4px',
            background: 'var(--bg-app)',
            border: '1px solid var(--panel-border)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'var(--brand-primary)',
            margin: '0 auto 16px'
          }}>
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
              <circle cx="12" cy="7" r="4" />
            </svg>
          </div>
          <h2 className="heading-lg" style={{ marginBottom: '8px' }}>Sign in to view your profile</h2>
          <p className="text-subtle" style={{ marginBottom: '24px' }}>
            Access your orders, saved wishlist, coupons, address book and profile settings.
          </p>
          <div style={{ display: 'flex', gap: '12px', justifyContent: 'center' }}>
            <Link to="/login" className="btn btn-primary" style={{ padding: '10px 24px', borderRadius: '4px' }}>
              Sign In
            </Link>
            <Link to="/signup" className="btn btn-secondary" style={{ padding: '10px 24px', borderRadius: '4px' }}>
              Create Account
            </Link>
          </div>
        </div>
      </div>
    );
  }

  const userName = customer?.full_name || customer?.fullName || customer?.username || 'Valued Customer';
  const userEmail = customer?.email || 'user@example.com';
  const userUsername = customer?.username || (customer?.email ? customer.email.split('@')[0] : 'customer');
  const userPhone = customer?.phone || 'Not provided';
  const userGender = customer?.gender || 'Unknown';
  const userAge = customer?.age ? `${customer.age} yrs` : 'Not specified';
  const points = customer?.points ?? 150;

  return (
    <div style={{ maxWidth: '850px', margin: '0 auto', width: '100%', display: 'flex', flexDirection: 'column', gap: '20px' }}>
      
      {/* Toast Notification */}
      {toastMessage && (
        <div style={{
          position: 'fixed',
          bottom: '24px',
          right: '24px',
          zIndex: 100,
          background: 'var(--brand-primary)',
          color: '#1a1d18',
          padding: '12px 20px',
          borderRadius: '4px',
          border: '1px solid var(--panel-border)',
          display: 'flex',
          alignItems: 'center',
          gap: '10px',
          fontSize: '0.9rem',
          fontWeight: 600
        }}>
          <span>{toastMessage}</span>
        </div>
      )}

      {/* 1. Header Profile & VIP Card */}
      <div style={{
        padding: '24px',
        borderRadius: '4px',
        background: 'var(--panel-solid)',
        border: '1px solid var(--panel-border)'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
            <img 
              src={`https://api.dicebear.com/7.x/avataaars/svg?seed=${encodeURIComponent(userEmail)}`} 
              alt={userName}
              loading="lazy"
              decoding="async"
              style={{
                width: '56px',
                height: '56px',
                borderRadius: '4px',
                background: 'var(--bg-app)',
                border: '1px solid var(--panel-border)'
              }}
            />
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <h2 className="heading-lg" style={{ color: 'var(--text-primary)' }}>{userName}</h2>
                <span className="badge badge-primary" style={{ fontSize: '0.75rem' }}>
                  @{userUsername}
                </span>
              </div>
              <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginTop: '2px' }}>
                {userEmail} • {userPhone}
              </p>
              <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: '2px' }}>
                Gender: {userGender} • Age: {userAge}
              </p>
            </div>
          </div>

          <div style={{
            background: 'var(--bg-app)',
            border: '1px solid var(--panel-border)',
            borderRadius: '4px',
            padding: '10px 16px',
            display: 'flex',
            alignItems: 'center',
            gap: '12px'
          }}>
            <div>
              <div style={{ fontSize: '0.9rem', fontWeight: 700, color: 'var(--brand-tertiary)' }}>
                {points} Magnet Coins
              </div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Available Rewards Balance</div>
            </div>
          </div>
        </div>

        {/* User Profile View Card */}
        <div style={{
          marginTop: '20px',
          padding: '16px 20px',
          borderRadius: '4px',
          background: 'var(--bg-app)',
          border: '1px solid var(--panel-border)'
        }}>
          <h4 style={{ fontSize: '0.9rem', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '10px' }}>
            User Profile
          </h4>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '12px', fontSize: '0.84rem' }}>
            <div>
              <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>Logged-in Email:</span>
              <div style={{ fontWeight: 700, color: 'var(--text-primary)' }}>{userEmail}</div>
            </div>
            <div>
              <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>Full Name:</span>
              <div style={{ fontWeight: 700, color: 'var(--text-primary)' }}>{userName}</div>
            </div>
            <div>
              <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>Username:</span>
              <div style={{ fontWeight: 700, color: 'var(--brand-tertiary)' }}>@{userUsername}</div>
            </div>
          </div>
        </div>

        {/* Promo Banner inside card */}
        <div style={{
          marginTop: '16px',
          padding: '12px 16px',
          borderRadius: '4px',
          background: 'var(--bg-app)',
          border: '1px solid var(--panel-border)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '10px'
        }}>
          <span style={{ fontSize: '0.84rem', color: 'var(--text-primary)', fontWeight: 500 }}>
            Enjoy <strong>Free Express Shipping</strong> and early access with Lead Magnet VIP.
          </span>
          <button onClick={() => setActiveModal('coupons')} className="btn btn-primary" style={{ padding: '6px 14px', fontSize: '0.78rem', borderRadius: '4px' }}>
            Explore Rewards
          </button>
        </div>

        {/* Quick Action Grid (Orders, Wishlist, Coupons, Help) */}
        <div className="grid-4" style={{ marginTop: '24px' }}>
          <Link to="/orders" className="btn btn-secondary" style={{ flexDirection: 'column', gap: '8px', padding: '16px 12px', textAlign: 'center', height: '100%', borderRadius: '4px' }}>
            <img width="24" height="24" src="https://img.icons8.com/material-outlined/24/box--v1.png" alt="box--v1" loading="lazy" decoding="async" style={{ display: 'block', margin: '0 auto' }} />
            <span style={{ fontSize: '0.88rem', fontWeight: 700 }}>Orders</span>
          </Link>

          <Link to="/wishlist" className="btn btn-secondary" style={{ flexDirection: 'column', gap: '8px', padding: '16px 12px', textAlign: 'center', height: '100%', borderRadius: '4px' }}>
            <span style={{ fontSize: '0.88rem', fontWeight: 700 }}>Wishlist</span>
          </Link>

          <button onClick={() => setActiveModal('coupons')} className="btn btn-secondary" style={{ flexDirection: 'column', gap: '8px', padding: '16px 12px', textAlign: 'center', height: '100%', borderRadius: '4px' }}>
            <span style={{ fontSize: '0.88rem', fontWeight: 700 }}>Coupons</span>
          </button>

          <button onClick={() => setActiveModal('faqs')} className="btn btn-secondary" style={{ flexDirection: 'column', gap: '8px', padding: '16px 12px', textAlign: 'center', height: '100%', borderRadius: '4px' }}>
            <span style={{ fontSize: '0.88rem', fontWeight: 700 }}>Help Center</span>
          </button>
        </div>
      </div>

      {/* 2. Account Settings Section */}
      <div style={{
        padding: '24px',
        borderRadius: '4px',
        background: 'var(--panel-solid)',
        border: '1px solid var(--panel-border)'
      }}>
        <h3 className="heading-md" style={{ marginBottom: '16px', color: 'var(--text-primary)' }}>
          Account Settings
        </h3>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '2px', background: 'var(--panel-border)', borderRadius: '4px', overflow: 'hidden' }}>
          
          {/* Edit Profile */}
          <button onClick={() => setActiveModal('edit_profile')} style={menuItemStyle}>
            <div style={{ textAlign: 'left' }}>
              <div style={{ fontWeight: 600, fontSize: '0.92rem', color: 'var(--text-primary)' }}>Edit Profile</div>
              <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>Name, Email, Phone number, Gender</div>
            </div>
            <span style={{ color: 'var(--text-muted)' }}>›</span>
          </button>

          {/* Saved Addresses */}
          <button onClick={() => setActiveModal('addresses')} style={menuItemStyle}>
            <div style={{ textAlign: 'left' }}>
              <div style={{ fontWeight: 600, fontSize: '0.92rem', color: 'var(--text-primary)' }}>Saved Addresses</div>
              <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>{addresses.length} delivery addresses saved</div>
            </div>
            <span style={{ color: 'var(--text-muted)' }}>›</span>
          </button>

          {/* Saved Credit / Debit & Gift Cards */}
          <button onClick={() => setActiveModal('cards')} style={menuItemStyle}>
            <div style={{ textAlign: 'left' }}>
              <div style={{ fontWeight: 600, fontSize: '0.92rem', color: 'var(--text-primary)' }}>Saved Payment Methods</div>
              <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>Manage payment methods and vouchers</div>
            </div>
            <span style={{ color: 'var(--text-muted)' }}>›</span>
          </button>

          {/* Notification Settings */}
          <button onClick={() => setActiveModal('notifications')} style={menuItemStyle}>
            <div style={{ textAlign: 'left' }}>
              <div style={{ fontWeight: 600, fontSize: '0.92rem', color: 'var(--text-primary)' }}>Notification Settings</div>
              <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>Email alerts, SMS and promotional offers</div>
            </div>
            <span style={{ color: 'var(--text-muted)' }}>›</span>
          </button>
        </div>
      </div>

      {/* 3. Feedback & Information Section */}
      <div style={{
        padding: '24px',
        borderRadius: '4px',
        background: 'var(--panel-solid)',
        border: '1px solid var(--panel-border)'
      }}>
        <h3 className="heading-md" style={{ marginBottom: '16px', color: 'var(--text-primary)' }}>
          Information & Support
        </h3>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '2px', background: 'var(--panel-border)', borderRadius: '4px', overflow: 'hidden' }}>
          <button onClick={() => setActiveModal('terms')} style={menuItemStyle}>
            <div style={{ textAlign: 'left' }}>
              <div style={{ fontWeight: 600, fontSize: '0.92rem', color: 'var(--text-primary)' }}>Terms, Policies and Licenses</div>
              <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>Refunds, shipping terms and privacy terms</div>
            </div>
            <span style={{ color: 'var(--text-muted)' }}>›</span>
          </button>

          <button onClick={() => setActiveModal('faqs')} style={menuItemStyle}>
            <div style={{ textAlign: 'left' }}>
              <div style={{ fontWeight: 600, fontSize: '0.92rem', color: 'var(--text-primary)' }}>Browse FAQs</div>
              <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>Common questions about delivery and returns</div>
            </div>
            <span style={{ color: 'var(--text-muted)' }}>›</span>
          </button>
        </div>
      </div>

      {/* 4. Prominent Log Out Button */}
      <div style={{ marginTop: '10px', marginBottom: '40px' }}>
        <button 
          onClick={handleLogout}
          className="btn btn-secondary"
          style={{
            width: '100%',
            padding: '14px',
            borderRadius: '4px',
            color: 'var(--brand-tertiary)',
            fontWeight: 700,
            fontSize: '1rem',
            border: '1px solid var(--panel-border)',
            background: 'var(--panel-solid)'
          }}
        >
          Log Out
        </button>
      </div>

      {/* ========================================================================= */}
      {/* MODALS / OVERLAYS FOR SETTINGS */}
      {/* ========================================================================= */}

      {/* Edit Profile Modal */}
      {activeModal === 'edit_profile' && (
        <ModalOverlay title="Edit Profile Details" onClose={() => setActiveModal(null)}>
          <form onSubmit={handleSaveProfile} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div>
              <label style={labelStyle}>Full Name</label>
              <input 
                type="text" 
                value={profileForm.fullName} 
                onChange={(e) => setProfileForm({ ...profileForm, fullName: e.target.value })}
                required 
                style={inputStyle}
              />
            </div>
            <div>
              <label style={labelStyle}>Email Address</label>
              <input 
                type="email" 
                value={profileForm.email} 
                onChange={(e) => setProfileForm({ ...profileForm, email: e.target.value })}
                required 
                style={inputStyle}
              />
            </div>
            <div>
              <label style={labelStyle}>Phone Number</label>
              <input 
                type="tel" 
                value={profileForm.phone} 
                onChange={(e) => setProfileForm({ ...profileForm, phone: e.target.value })}
                style={inputStyle}
              />
            </div>
            <div>
              <label style={labelStyle}>Gender</label>
              <div style={{ display: 'flex', gap: '12px', marginTop: '6px' }}>
                {['Male', 'Female', 'Other'].map((g) => (
                  <label key={g} style={{
                    flex: 1,
                    padding: '10px',
                    borderRadius: '4px',
                    border: '1px solid var(--panel-border)',
                    background: profileForm.gender === g ? 'var(--bg-app)' : 'var(--panel-solid)',
                    borderColor: profileForm.gender === g ? 'var(--brand-primary)' : 'var(--panel-border)',
                    textAlign: 'center',
                    cursor: 'pointer',
                    fontWeight: 600,
                    fontSize: '0.88rem'
                  }}>
                    <input 
                      type="radio" 
                      name="gender" 
                      checked={profileForm.gender === g} 
                      onChange={() => setProfileForm({ ...profileForm, gender: g })}
                      style={{ display: 'none' }}
                    />
                    {g}
                  </label>
                ))}
              </div>
            </div>
            <button type="submit" className="btn btn-primary" style={{ marginTop: '8px', padding: '12px', borderRadius: '4px' }}>
              Save Profile Changes
            </button>
          </form>
        </ModalOverlay>
      )}

      {/* Saved Addresses Modal */}
      {activeModal === 'addresses' && (
        <ModalOverlay title="Saved Delivery Addresses" onClose={() => setActiveModal(null)}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {addresses.map((addr) => (
              <div key={addr.id} style={{
                padding: '14px',
                borderRadius: '4px',
                border: '1px solid var(--panel-border)',
                background: 'var(--panel-solid)'
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                  <span style={{ fontWeight: 700, fontSize: '0.92rem' }}>{addr.name}</span>
                  <span className="badge badge-primary" style={{ fontSize: '0.72rem' }}>{addr.type}</span>
                </div>
                <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                  {addr.street}, {addr.city}, {addr.state} - {addr.pincode}
                </div>
                <div style={{ fontSize: '0.82rem', color: 'var(--text-muted)', marginTop: '4px' }}>Phone: {addr.phone}</div>
              </div>
            ))}

            {!showAddAddr ? (
              <button 
                onClick={() => setShowAddAddr(true)} 
                className="btn btn-secondary" 
                style={{ width: '100%', padding: '10px', marginTop: '8px', borderStyle: 'dashed', borderRadius: '4px' }}
              >
                + Add New Delivery Address
              </button>
            ) : (
              <form onSubmit={handleAddAddress} style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginTop: '10px', padding: '14px', border: '1px solid var(--panel-border)', borderRadius: '4px' }}>
                <h4 style={{ fontSize: '0.9rem', fontWeight: 700 }}>Add New Address</h4>
                <input placeholder="Full Name" value={newAddr.name} onChange={(e) => setNewAddr({ ...newAddr, name: e.target.value })} required style={inputStyle} />
                <input placeholder="Phone Number" value={newAddr.phone} onChange={(e) => setNewAddr({ ...newAddr, phone: e.target.value })} required style={inputStyle} />
                <input placeholder="Street Address / House No." value={newAddr.street} onChange={(e) => setNewAddr({ ...newAddr, street: e.target.value })} required style={inputStyle} />
                <div style={{ display: 'flex', gap: '8px' }}>
                  <input placeholder="City" value={newAddr.city} onChange={(e) => setNewAddr({ ...newAddr, city: e.target.value })} required style={inputStyle} />
                  <input placeholder="Pincode" value={newAddr.pincode} onChange={(e) => setNewAddr({ ...newAddr, pincode: e.target.value })} required style={inputStyle} />
                </div>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <button type="submit" className="btn btn-primary" style={{ flex: 1, padding: '8px', borderRadius: '4px' }}>Save Address</button>
                  <button type="button" onClick={() => setShowAddAddr(false)} className="btn btn-secondary" style={{ padding: '8px', borderRadius: '4px' }}>Cancel</button>
                </div>
              </form>
            )}
          </div>
        </ModalOverlay>
      )}

      {/* Notification Settings Modal */}
      {activeModal === 'notifications' && (
        <ModalOverlay title="Notification Preferences" onClose={() => setActiveModal(null)}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
            {[
              { key: 'orderUpdates', title: 'Order Updates', desc: 'Receive real-time tracking alerts for your orders' },
              { key: 'email', title: 'Email Notifications', desc: 'Invoices, order confirmation and receipts' },
              { key: 'sms', title: 'SMS Notifications', desc: 'Delivery updates sent to your phone' },
              { key: 'promotions', title: 'Promotional Offers and Sales', desc: 'Exclusive discount codes and sale notifications' },
            ].map(({ key, title, desc }) => (
              <div key={key} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 14px', border: '1px solid var(--panel-border)', borderRadius: '4px' }}>
                <div>
                  <div style={{ fontWeight: 600, fontSize: '0.9rem' }}>{title}</div>
                  <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>{desc}</div>
                </div>
                <input 
                  type="checkbox" 
                  checked={notifications[key]} 
                  onChange={() => handleToggleNotification(key)} 
                  style={{ width: '18px', height: '18px', accentColor: 'var(--brand-primary)', cursor: 'pointer' }}
                />
              </div>
            ))}
          </div>
        </ModalOverlay>
      )}

      {/* Cards Modal */}
      {activeModal === 'cards' && (
        <ModalOverlay title="Saved Payment Methods" onClose={() => setActiveModal(null)}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <div style={{ padding: '16px', borderRadius: '4px', background: 'var(--panel-solid)', border: '1px solid var(--panel-border)', color: 'var(--text-primary)' }}>
              <div style={{ fontSize: '0.75rem', textTransform: 'uppercase', color: 'var(--text-secondary)' }}>Standard Bank Card</div>
              <div style={{ fontSize: '1.1rem', letterSpacing: '2px', margin: '14px 0', fontWeight: 600 }}>•••• •••• •••• 4291</div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                <span>Expires 08/28</span>
                <span>{userName.toUpperCase()}</span>
              </div>
            </div>
            <button onClick={() => showToast('Redirecting to secure card vault...')} className="btn btn-secondary" style={{ width: '100%', padding: '10px', borderRadius: '4px' }}>
              + Add New Payment Card
            </button>
          </div>
        </ModalOverlay>
      )}

      {/* Coupons Modal */}
      {activeModal === 'coupons' && (
        <ModalOverlay title="Available Vouchers and Coupons" onClose={() => setActiveModal(null)}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {[
              { code: 'MAGNET20', discount: '20% OFF', desc: 'Flat 20% discount on all hoodies and jackets', min: 'Min Order: $49' },
              { code: 'FREESHIP', discount: 'FREE SHIPPING', desc: 'Zero delivery charges on your next order', min: 'No Minimum' },
              { code: 'WELCOME500', discount: '$15 OFF', desc: 'Exclusive welcome voucher for VIP members', min: 'Min Order: $75' },
            ].map(({ code, discount, desc, min }) => (
              <div key={code} style={{ padding: '14px', border: '1px dashed var(--panel-border)', borderRadius: '4px', background: 'var(--panel-solid)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ fontWeight: 800, color: 'var(--brand-tertiary)', fontSize: '1rem' }}>{code}</span>
                    <span className="badge badge-primary" style={{ fontSize: '0.7rem' }}>{discount}</span>
                  </div>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: '4px' }}>{desc}</div>
                  <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: '2px' }}>{min}</div>
                </div>
                <button onClick={() => { navigator.clipboard.writeText(code); showToast(`Coupon ${code} copied to clipboard.`); }} className="btn btn-secondary" style={{ padding: '6px 12px', fontSize: '0.78rem', borderRadius: '4px' }}>
                  Copy
                </button>
              </div>
            ))}
          </div>
        </ModalOverlay>
      )}

      {/* FAQs Modal */}
      {activeModal === 'faqs' && (
        <ModalOverlay title="Frequently Asked Questions" onClose={() => setActiveModal(null)}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {[
              { q: 'How long does shipping take?', a: 'Standard delivery takes 3 to 5 business days. Express delivery takes 1 to 2 days.' },
              { q: 'What is the return policy?', a: 'You can return any unworn item with tags attached within 30 days of delivery.' },
              { q: 'How do I earn Magnet Coins?', a: 'You earn 10 Magnet Coins for every $10 spent on Lead Magnet store items.' },
              { q: 'How can I contact customer support?', a: 'Our support team is available via email at support@leadmagnet.com.' },
            ].map(({ q, a }, idx) => (
              <div key={idx} style={{ padding: '12px 14px', border: '1px solid var(--panel-border)', borderRadius: '4px', background: 'var(--panel-solid)' }}>
                <div style={{ fontWeight: 700, fontSize: '0.88rem', color: 'var(--text-primary)', marginBottom: '4px' }}>{q}</div>
                <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', lineHeight: 1.4 }}>{a}</div>
              </div>
            ))}
          </div>
        </ModalOverlay>
      )}

      {/* Terms Modal */}
      {activeModal === 'terms' && (
        <ModalOverlay title="Terms, Policies and Licenses" onClose={() => setActiveModal(null)}>
          <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', lineHeight: 1.6, display: 'flex', flexDirection: 'column', gap: '10px' }}>
            <p><strong>1. Lead Magnet Store Terms:</strong> By using our platform, you agree to our standard customer purchasing and delivery guidelines.</p>
            <p><strong>2. Return and Refund Policy:</strong> Unworn items with original tags can be returned within 30 days for full store credit or refund.</p>
            <p><strong>3. Data Privacy:</strong> We strictly protect user data and payment credentials under security standards.</p>
          </div>
        </ModalOverlay>
      )}

    </div>
  );
}

/* Modal Helper Component */
function ModalOverlay({ title, onClose, children }) {
  return (
    <div style={{
      position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, zIndex: 90,
      background: 'rgba(0, 0, 0, 0.5)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '20px'
    }}>
      <div style={{
        width: '100%', maxWidth: '520px', background: 'var(--panel-solid)',
        borderRadius: '4px', padding: '24px',
        border: '1px solid var(--panel-border)',
        maxHeight: '90vh', overflowY: 'auto'
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '18px' }}>
          <h3 className="heading-md" style={{ color: 'var(--text-primary)' }}>{title}</h3>
          <button onClick={onClose} className="btn btn-secondary" style={{ padding: '4px 10px', borderRadius: '4px' }}>
            ✕
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

/* Reusable styles */
const menuItemStyle = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  padding: '14px 16px',
  background: 'var(--panel-solid)',
  border: 'none',
  width: '100%',
  cursor: 'pointer',
  textAlign: 'left'
};

const labelStyle = {
  fontSize: '0.82rem',
  fontWeight: 700,
  color: 'var(--text-secondary)',
  display: 'block',
  marginBottom: '4px'
};

const inputStyle = {
  width: '100%',
  padding: '10px 14px',
  borderRadius: '4px',
  border: '1px solid var(--panel-border)',
  background: 'var(--bg-app)',
  color: 'var(--text-primary)',
  outline: 'none',
  fontSize: '0.88rem'
};
