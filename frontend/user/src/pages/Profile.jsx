import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { 
  User, Package, Heart, Tag, HelpCircle, MapPin, CreditCard, 
  Globe, Bell, Shield, Star, MessageSquare, Store, FileText, 
  LogOut, ChevronRight, Edit3, Check, X, Plus, Sparkles, AlertCircle
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';

export function Profile() {
  const { customer, isCustomerAuthenticated, logout, updateProfile } = useAuth();
  const navigate = useNavigate();

  // Active modal state
  const [activeModal, setActiveModal] = useState(null); // 'edit_profile', 'addresses', 'language', 'notifications', 'cards', 'privacy', 'coupons', 'faqs', 'terms'

  // Edit profile form state
  const [profileForm, setProfileForm] = useState({
    fullName: customer?.fullName || customer?.username || '',
    email: customer?.email || '',
    phone: customer?.phone || '+91 9876543210',
    gender: customer?.gender || 'Male',
  });

  // Saved address state
  const rawAddresses = Array.isArray(customer?.addresses) && customer.addresses.length > 0 ? customer.addresses : [
    {
      id: 'addr-1',
      name: customer?.fullName || customer?.username || 'Bharati Bhat',
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

  // Preferences state
  const [language, setLanguage] = useState(customer?.language || 'English');
  const [notifications, setNotifications] = useState(() => {
    return (customer?.notifications && typeof customer.notifications === 'object') ? customer.notifications : {
      email: true,
      sms: true,
      promotions: false,
      orderUpdates: true,
    };
  });

  // Alert message banner
  const [toastMessage, setToastMessage] = useState('');

  const showToast = (msg) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(''), 3000);
  };

  const handleSaveProfile = (e) => {
    e.preventDefault();
    const res = updateProfile(profileForm);
    if (res.success) {
      showToast('Profile details updated successfully!');
      setActiveModal(null);
    }
  };

  const handleAddAddress = (e) => {
    e.preventDefault();
    if (!newAddr.street || !newAddr.city) return;
    const added = { id: `addr-${Date.now()}`, ...newAddr, isDefault: addresses.length === 0 };
    const updated = [...addresses, added];
    setAddresses(updated);
    updateProfile({ addresses: updated });
    setNewAddr({ name: '', phone: '', type: 'Home', street: '', city: '', state: '', pincode: '' });
    setShowAddAddr(false);
    showToast('New address saved successfully!');
  };

  const handleToggleNotification = (key) => {
    const updated = { ...notifications, [key]: !notifications[key] };
    setNotifications(updated);
    updateProfile({ notifications: updated });
    showToast('Notification preference saved!');
  };

  const handleSelectLanguage = (lang) => {
    setLanguage(lang);
    updateProfile({ language: lang });
    showToast(`Language changed to ${lang}`);
    setActiveModal(null);
  };

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  if (!isCustomerAuthenticated) {
    return (
      <div style={{ maxWidth: '600px', margin: '40px auto', padding: '0 20px', textAlign: 'center' }}>
        <div className="glass-card" style={{ padding: '40px 24px', borderRadius: 'var(--radius-lg)' }}>
          <div style={{
            width: '64px', height: '64px', borderRadius: '50%', background: 'rgba(79, 70, 229, 0.1)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--accent-indigo)',
            margin: '0 auto 16px'
          }}>
            <User size={32} />
          </div>
          <h2 className="heading-lg" style={{ marginBottom: '8px' }}>Sign in to view your profile</h2>
          <p className="text-subtle" style={{ marginBottom: '24px' }}>
            Access your orders, saved wishlist, coupons, address book and profile settings.
          </p>
          <div style={{ display: 'flex', gap: '12px', justifyContent: 'center' }}>
            <Link to="/login" className="btn btn-primary" style={{ padding: '10px 24px', borderRadius: 'var(--radius-full)' }}>
              Sign In
            </Link>
            <Link to="/signup" className="btn btn-secondary" style={{ padding: '10px 24px', borderRadius: 'var(--radius-full)' }}>
              Create Account
            </Link>
          </div>
        </div>
      </div>
    );
  }

  const userName = customer?.fullName || customer?.username || 'Valued Customer';
  const userEmail = customer?.email || 'user@example.com';
  const points = customer?.points ?? 150;

  return (
    <div style={{ maxWidth: '850px', margin: '0 auto', width: '100%', display: 'flex', flexDirection: 'column', gap: '20px' }}>
      
      {/* Toast Notification */}
      {toastMessage && (
        <div style={{
          position: 'fixed', bottom: '24px', right: '24px', zIndex: 100,
          background: 'var(--accent-indigo)', color: 'white', padding: '12px 20px',
          borderRadius: 'var(--radius-md)', boxShadow: '0 10px 25px rgba(0,0,0,0.2)',
          display: 'flex', alignItems: 'center', gap: '10px', fontSize: '0.9rem', fontWeight: 600
        }}>
          <Check size={18} />
          <span>{toastMessage}</span>
        </div>
      )}

      {/* 1. Header Profile & VIP Card */}
      <div className="glass-card" style={{ padding: '24px', borderRadius: 'var(--radius-lg)' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
            <img 
              src={`https://api.dicebear.com/7.x/avataaars/svg?seed=${encodeURIComponent(userEmail)}`} 
              alt={userName}
              style={{
                width: '64px', height: '64px', borderRadius: '50%', background: '#e2e8f0',
                border: '3px solid var(--accent-indigo)', boxShadow: '0 4px 12px rgba(79, 70, 229, 0.2)'
              }}
            />
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <h2 className="heading-lg" style={{ color: 'var(--text-primary)' }}>{userName}</h2>
                <span className="badge badge-indigo" style={{ fontSize: '0.75rem' }}>
                  <Sparkles size={12} /> VIP Member
                </span>
              </div>
              <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginTop: '2px' }}>{userEmail}</p>
            </div>
          </div>

          <div style={{
            background: 'rgba(79, 70, 229, 0.08)', border: '1px solid rgba(79, 70, 229, 0.2)',
            borderRadius: 'var(--radius-md)', padding: '10px 16px', display: 'flex', alignItems: 'center', gap: '12px'
          }}>
            <div style={{ fontSize: '1.4rem' }}>⚡</div>
            <div>
              <div style={{ fontSize: '0.9rem', fontWeight: 800, color: 'var(--accent-indigo)' }}>
                {points} Magnet Coins
              </div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Available Rewards Balance</div>
            </div>
          </div>
        </div>

        {/* Promo Banner inside card */}
        <div style={{
          marginTop: '20px', padding: '12px 16px', borderRadius: 'var(--radius-md)',
          background: 'linear-gradient(135deg, rgba(79, 70, 229, 0.12) 0%, rgba(59, 130, 246, 0.08) 100%)',
          border: '1px dashed rgba(79, 70, 229, 0.3)', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          flexWrap: 'wrap', gap: '10px'
        }}>
          <span style={{ fontSize: '0.84rem', color: 'var(--text-primary)', fontWeight: 500 }}>
            ✨ Enjoy <strong>FREE Express Shipping</strong> & Early Access to Flash Sales with Lead Magnet VIP.
          </span>
          <button onClick={() => setActiveModal('coupons')} className="btn btn-primary" style={{ padding: '6px 14px', fontSize: '0.78rem', borderRadius: 'var(--radius-full)' }}>
            Explore Rewards
          </button>
        </div>

        {/* Quick Action Grid (Orders, Wishlist, Coupons, Help) */}
        <div className="grid-4" style={{ marginTop: '24px' }}>
          <Link to="/orders" className="btn btn-secondary" style={{ flexDirection: 'column', gap: '8px', padding: '16px 12px', textAlign: 'center', height: '100%' }}>
            <Package size={22} style={{ color: 'var(--accent-indigo)' }} />
            <span style={{ fontSize: '0.88rem', fontWeight: 700 }}>Orders</span>
          </Link>

          <Link to="/wishlist" className="btn btn-secondary" style={{ flexDirection: 'column', gap: '8px', padding: '16px 12px', textAlign: 'center', height: '100%' }}>
            <Heart size={22} style={{ color: 'var(--accent-rose)' }} />
            <span style={{ fontSize: '0.88rem', fontWeight: 700 }}>Wishlist</span>
          </Link>

          <button onClick={() => setActiveModal('coupons')} className="btn btn-secondary" style={{ flexDirection: 'column', gap: '8px', padding: '16px 12px', textAlign: 'center', height: '100%' }}>
            <Tag size={22} style={{ color: 'var(--accent-amber)' }} />
            <span style={{ fontSize: '0.88rem', fontWeight: 700 }}>Coupons</span>
          </button>

          <button onClick={() => setActiveModal('faqs')} className="btn btn-secondary" style={{ flexDirection: 'column', gap: '8px', padding: '16px 12px', textAlign: 'center', height: '100%' }}>
            <HelpCircle size={22} style={{ color: 'var(--accent-blue)' }} />
            <span style={{ fontSize: '0.88rem', fontWeight: 700 }}>Help Center</span>
          </button>
        </div>
      </div>

      {/* 2. Account Settings Section */}
      <div className="glass-card" style={{ padding: '24px', borderRadius: 'var(--radius-lg)' }}>
        <h3 className="heading-md" style={{ marginBottom: '16px', color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '8px' }}>
          Account Settings
        </h3>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '2px', background: 'var(--panel-border)', borderRadius: 'var(--radius-md)', overflow: 'hidden' }}>
          
          {/* Edit Profile */}
          <button onClick={() => setActiveModal('edit_profile')} style={menuItemStyle}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
              <User size={19} style={{ color: 'var(--accent-indigo)' }} />
              <div style={{ textAlign: 'left' }}>
                <div style={{ fontWeight: 600, fontSize: '0.92rem', color: 'var(--text-primary)' }}>Edit Profile</div>
                <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>Name, Email, Phone number, Gender</div>
              </div>
            </div>
            <ChevronRight size={18} style={{ color: 'var(--text-muted)' }} />
          </button>

          {/* Saved Addresses */}
          <button onClick={() => setActiveModal('addresses')} style={menuItemStyle}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
              <MapPin size={19} style={{ color: 'var(--accent-rose)' }} />
              <div style={{ textAlign: 'left' }}>
                <div style={{ fontWeight: 600, fontSize: '0.92rem', color: 'var(--text-primary)' }}>Saved Addresses</div>
                <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>{addresses.length} delivery addresses saved</div>
              </div>
            </div>
            <ChevronRight size={18} style={{ color: 'var(--text-muted)' }} />
          </button>

          {/* Saved Credit / Debit & Gift Cards */}
          <button onClick={() => setActiveModal('cards')} style={menuItemStyle}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
              <CreditCard size={19} style={{ color: 'var(--accent-blue)' }} />
              <div style={{ textAlign: 'left' }}>
                <div style={{ fontWeight: 600, fontSize: '0.92rem', color: 'var(--text-primary)' }}>Saved Credit / Debit & Gift Cards</div>
                <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>Manage payment methods and vouchers</div>
              </div>
            </div>
            <ChevronRight size={18} style={{ color: 'var(--text-muted)' }} />
          </button>

          {/* Notification Settings */}
          <button onClick={() => setActiveModal('notifications')} style={menuItemStyle}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
              <Bell size={19} style={{ color: 'var(--accent-amber)' }} />
              <div style={{ textAlign: 'left' }}>
                <div style={{ fontWeight: 600, fontSize: '0.92rem', color: 'var(--text-primary)' }}>Notification Settings</div>
                <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>Email alerts, SMS and promotional offers</div>
              </div>
            </div>
            <ChevronRight size={18} style={{ color: 'var(--text-muted)' }} />
          </button>
        </div>
      </div>

      {/* 5. Feedback & Information Section */}
      <div className="glass-card" style={{ padding: '24px', borderRadius: 'var(--radius-lg)' }}>
        <h3 className="heading-md" style={{ marginBottom: '16px', color: 'var(--text-primary)' }}>
          Feedback & Information
        </h3>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '2px', background: 'var(--panel-border)', borderRadius: 'var(--radius-md)', overflow: 'hidden' }}>
          <button onClick={() => setActiveModal('terms')} style={menuItemStyle}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
              <FileText size={19} style={{ color: 'var(--accent-blue)' }} />
              <div style={{ textAlign: 'left' }}>
                <div style={{ fontWeight: 600, fontSize: '0.92rem', color: 'var(--text-primary)' }}>Terms, Policies and Licenses</div>
                <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>Refunds, shipping terms & privacy terms</div>
              </div>
            </div>
            <ChevronRight size={18} style={{ color: 'var(--text-muted)' }} />
          </button>

          <button onClick={() => setActiveModal('faqs')} style={menuItemStyle}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
              <HelpCircle size={19} style={{ color: 'var(--accent-emerald)' }} />
              <div style={{ textAlign: 'left' }}>
                <div style={{ fontWeight: 600, fontSize: '0.92rem', color: 'var(--text-primary)' }}>Browse FAQs</div>
                <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>Common questions about delivery and returns</div>
              </div>
            </div>
            <ChevronRight size={18} style={{ color: 'var(--text-muted)' }} />
          </button>
        </div>
      </div>

      {/* 6. Prominent Log Out Button */}
      <div style={{ marginTop: '10px', marginBottom: '40px' }}>
        <button 
          onClick={handleLogout}
          className="btn btn-secondary"
          style={{
            width: '100%', padding: '14px', borderRadius: 'var(--radius-md)',
            color: 'var(--accent-rose)', fontWeight: 700, fontSize: '1rem',
            border: '1px solid var(--panel-border)', background: 'var(--panel-solid)',
            boxShadow: '0 2px 8px rgba(0,0,0,0.03)', gap: '10px'
          }}
        >
          <LogOut size={20} />
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
                    flex: 1, padding: '10px', borderRadius: 'var(--radius-md)', border: '1px solid var(--panel-border)',
                    background: profileForm.gender === g ? 'rgba(79, 70, 229, 0.1)' : 'var(--panel-solid)',
                    borderColor: profileForm.gender === g ? 'var(--accent-indigo)' : 'var(--panel-border)',
                    textAlign: 'center', cursor: 'pointer', fontWeight: 600, fontSize: '0.88rem'
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
            <button type="submit" className="btn btn-primary" style={{ marginTop: '8px', padding: '12px', borderRadius: 'var(--radius-md)' }}>
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
                padding: '14px', borderRadius: 'var(--radius-md)', border: '1px solid var(--panel-border)',
                background: addr.isDefault ? 'rgba(79, 70, 229, 0.04)' : 'var(--panel-solid)'
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
                  <span style={{ fontWeight: 700, fontSize: '0.92rem' }}>{addr.name}</span>
                  <span className="badge badge-indigo" style={{ fontSize: '0.72rem' }}>{addr.type}</span>
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
                style={{ width: '100%', padding: '10px', marginTop: '8px', borderStyle: 'dashed' }}
              >
                <Plus size={16} /> Add New Delivery Address
              </button>
            ) : (
              <form onSubmit={handleAddAddress} style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginTop: '10px', padding: '14px', border: '1px solid var(--panel-border)', borderRadius: 'var(--radius-md)' }}>
                <h4 style={{ fontSize: '0.9rem', fontWeight: 700 }}>Add New Address</h4>
                <input placeholder="Full Name" value={newAddr.name} onChange={(e) => setNewAddr({ ...newAddr, name: e.target.value })} required style={inputStyle} />
                <input placeholder="Phone Number" value={newAddr.phone} onChange={(e) => setNewAddr({ ...newAddr, phone: e.target.value })} required style={inputStyle} />
                <input placeholder="Street Address / House No." value={newAddr.street} onChange={(e) => setNewAddr({ ...newAddr, street: e.target.value })} required style={inputStyle} />
                <div style={{ display: 'flex', gap: '8px' }}>
                  <input placeholder="City" value={newAddr.city} onChange={(e) => setNewAddr({ ...newAddr, city: e.target.value })} required style={inputStyle} />
                  <input placeholder="Pincode" value={newAddr.pincode} onChange={(e) => setNewAddr({ ...newAddr, pincode: e.target.value })} required style={inputStyle} />
                </div>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <button type="submit" className="btn btn-primary" style={{ flex: 1, padding: '8px' }}>Save Address</button>
                  <button type="button" onClick={() => setShowAddAddr(false)} className="btn btn-ghost" style={{ padding: '8px' }}>Cancel</button>
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
              { key: 'promotions', title: 'Promotional Offers & Sales', desc: 'Exclusive discount codes and flash sale notifications' },
            ].map(({ key, title, desc }) => (
              <div key={key} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 14px', border: '1px solid var(--panel-border)', borderRadius: 'var(--radius-md)' }}>
                <div>
                  <div style={{ fontWeight: 600, fontSize: '0.9rem' }}>{title}</div>
                  <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>{desc}</div>
                </div>
                <input 
                  type="checkbox" 
                  checked={notifications[key]} 
                  onChange={() => handleToggleNotification(key)} 
                  style={{ width: '20px', height: '20px', accentColor: 'var(--accent-indigo)', cursor: 'pointer' }}
                />
              </div>
            ))}
          </div>
        </ModalOverlay>
      )}

      {/* Cards Modal */}
      {activeModal === 'cards' && (
        <ModalOverlay title="Saved Credit / Debit Cards" onClose={() => setActiveModal(null)}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <div style={{ padding: '16px', borderRadius: 'var(--radius-md)', background: 'linear-gradient(135deg, #1e293b 0%, #0f172a 100%)', color: 'white' }}>
              <div style={{ fontSize: '0.75rem', textTransform: 'uppercase', opacity: 0.7 }}>HDFC Bank Credit Card</div>
              <div style={{ fontSize: '1.1rem', letterSpacing: '2px', margin: '14px 0', fontWeight: 600 }}>•••• •••• •••• 4291</div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', opacity: 0.8 }}>
                <span>Expires 08/28</span>
                <span>{userName.toUpperCase()}</span>
              </div>
            </div>
            <button onClick={() => showToast('Redirecting to secure card vault...')} className="btn btn-secondary" style={{ width: '100%', padding: '10px' }}>
              <Plus size={16} /> Add New Payment Card
            </button>
          </div>
        </ModalOverlay>
      )}

      {/* Coupons Modal */}
      {activeModal === 'coupons' && (
        <ModalOverlay title="Available Vouchers & Coupons" onClose={() => setActiveModal(null)}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {[
              { code: 'MAGNET20', discount: '20% OFF', desc: 'Flat 20% discount on all hoodies & jackets', min: 'Min Order: $49' },
              { code: 'FREESHIP', discount: 'FREE SHIPPING', desc: 'Zero delivery charges on your next order', min: 'No Minimum' },
              { code: 'WELCOME500', discount: '$15 OFF', desc: 'Exclusive welcome voucher for VIP members', min: 'Min Order: $75' },
            ].map(({ code, discount, desc, min }) => (
              <div key={code} style={{ padding: '14px', border: '1px dashed var(--accent-indigo)', borderRadius: 'var(--radius-md)', background: 'rgba(79, 70, 229, 0.03)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ fontWeight: 800, color: 'var(--accent-indigo)', fontSize: '1rem' }}>{code}</span>
                    <span className="badge badge-indigo" style={{ fontSize: '0.7rem' }}>{discount}</span>
                  </div>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: '4px' }}>{desc}</div>
                  <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: '2px' }}>{min}</div>
                </div>
                <button onClick={() => { navigator.clipboard.writeText(code); showToast(`Coupon ${code} copied to clipboard!`); }} className="btn btn-secondary" style={{ padding: '6px 12px', fontSize: '0.78rem' }}>
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
              { q: 'How long does shipping take?', a: 'Standard delivery takes 3-5 business days. Express VIP delivery takes 1-2 days.' },
              { q: 'What is the return policy?', a: 'You can return any unworn item with tags attached within 30 days of delivery.' },
              { q: 'How do I earn Magnet Coins?', a: 'You earn 10 Magnet Coins for every $10 spent on Lead Magnet store items.' },
              { q: 'How can I contact customer support?', a: 'Our support team is available 24/7 via email at support@leadmagnet.com.' },
            ].map(({ q, a }, idx) => (
              <div key={idx} style={{ padding: '12px 14px', border: '1px solid var(--panel-border)', borderRadius: 'var(--radius-md)', background: 'var(--panel-solid)' }}>
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
            <p><strong>2. Return & Refund Policy:</strong> Unworn items with original tags can be returned within 30 days for full store credit or refund.</p>
            <p><strong>3. Data Privacy:</strong> We strictly protect user data and payment credentials under PCI-DSS compliance standards.</p>
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
      background: 'rgba(0, 0, 0, 0.45)', backdropFilter: 'blur(4px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '20px'
    }}>
      <div className="glass-card" style={{
        width: '100%', maxWidth: '520px', background: 'var(--panel-solid)',
        borderRadius: 'var(--radius-lg)', padding: '24px', boxShadow: '0 20px 40px rgba(0,0,0,0.2)',
        maxHeight: '90vh', overflowY: 'auto'
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '18px' }}>
          <h3 className="heading-md" style={{ color: 'var(--text-primary)' }}>{title}</h3>
          <button onClick={onClose} className="btn btn-ghost" style={{ padding: '6px', borderRadius: '50%' }}>
            <X size={20} />
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
  transition: 'background 0.15s ease',
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
  borderRadius: 'var(--radius-md)',
  border: '1px solid var(--panel-border)',
  background: 'var(--bg-app)',
  color: 'var(--text-primary)',
  outline: 'none',
  fontSize: '0.88rem'
};
