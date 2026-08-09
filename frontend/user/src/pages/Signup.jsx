import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import '../styles/auth.css';

function Signup() {
  const navigate = useNavigate();
  const { signup } = useAuth();
  const [formData, setFormData] = useState({
    fullName: '',
    age: '',
    gender: 'Select gender',
    dob: '',
    phone: '',
    email: '',
    password: '',
    confirmPassword: '',
  });
  const [errors, setErrors] = useState({});
  const [message, setMessage] = useState('');

  const validateForm = (data) => {
    const nextErrors = {};
    if (!data.fullName.trim()) {
      nextErrors.fullName = 'Full name is required.';
    }
    
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!data.email.trim() || !emailRegex.test(data.email.trim())) {
      nextErrors.email = 'Enter a valid email address.';
    }
    
    if (!data.phone.trim() || !/^\d{10}$/.test(data.phone.trim())) {
      nextErrors.phone = 'Phone number must contain exactly 10 digits.';
    }
    
    if (!data.dob) {
      nextErrors.dob = 'Date of birth is required.';
    }
    
    if (!data.age || Number(data.age) <= 13 || Number(data.age) > 120) {
      nextErrors.age = 'Age must be between 14 and 120.';
    }
    
    if (!data.gender || data.gender === 'Select gender') {
      nextErrors.gender = 'Please choose a gender.';
    }
    
    if (data.password.length < 8) {
      nextErrors.password = 'Password must contain at least 8 characters.';
    }
    
    if (data.password !== data.confirmPassword) {
      nextErrors.confirmPassword = 'Passwords do not match.';
    }
    
    return nextErrors;
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setMessage('');

    const validationErrors = validateForm(formData);
    setErrors(validationErrors);

    if (Object.keys(validationErrors).length > 0) {
      setMessage('Please complete all required fields correctly.');
      return;
    }

    const result = await signup({
      fullName: formData.fullName.trim(),
      username: formData.fullName.trim().toLowerCase().replace(/\s+/g, ''),
      age: Number(formData.age),
      gender: formData.gender,
      dob: formData.dob,
      phone: formData.phone.trim(),
      email: formData.email.trim(),
      password: formData.password,
    });

    if (!result.success) {
      setMessage(result.message);
      return;
    }

    setMessage('');
    navigate('/login', {
      state: {
        email: formData.email.trim(),
        message: 'Account created successfully! Please log in with your credentials.',
      },
    });
  };

  const updateField = (field, value) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
    if (errors[field]) {
      setErrors((prev) => ({ ...prev, [field]: undefined }));
    }
    if (message) setMessage('');
  };

  return (
    <div className="auth-shell">
      <div className="auth-card glass-panel">
        <div className="auth-card-header">
          <p className="eyebrow">Lead Magnet Store</p>
          <h2>Create User Account</h2>
          <p>Register a new customer profile to enjoy personalized shopping & rewards.</p>
        </div>

        <form className="auth-form" onSubmit={handleSubmit} noValidate>
          <label>
            Full Name
            <input 
              placeholder="e.g. Rahul Sharma"
              value={formData.fullName} 
              onChange={(e) => updateField('fullName', e.target.value)} 
            />
          </label>
          {errors.fullName ? <div className="error-text">{errors.fullName}</div> : null}

          <div className="input-row">
            <label>
              Age
              <input 
                type="number" 
                min="14" 
                max="120"
                placeholder="e.g. 24"
                value={formData.age} 
                onChange={(e) => updateField('age', e.target.value)} 
              />
            </label>
            <label>
              Gender
              <select 
                value={formData.gender} 
                onChange={(e) => updateField('gender', e.target.value)}
              >
                <option disabled>Select gender</option>
                <option value="Male">Male</option>
                <option value="Female">Female</option>
                <option value="Non-binary">Non-binary</option>
                <option value="Prefer not to say">Prefer not to say</option>
              </select>
            </label>
          </div>
          {errors.age ? <div className="error-text">{errors.age}</div> : null}
          {errors.gender ? <div className="error-text">{errors.gender}</div> : null}

          <label>
            Date of Birth
            <input 
              type="date" 
              value={formData.dob} 
              onChange={(e) => updateField('dob', e.target.value)} 
            />
          </label>
          {errors.dob ? <div className="error-text">{errors.dob}</div> : null}

          <label>
            Phone Number
            <input 
              placeholder="e.g. 9876543210"
              value={formData.phone} 
              onChange={(e) => updateField('phone', e.target.value)} 
            />
          </label>
          {errors.phone ? <div className="error-text">{errors.phone}</div> : null}

          <label>
            Email Address
            <input 
              type="email" 
              placeholder="e.g. rahul@gmail.com"
              value={formData.email} 
              onChange={(e) => updateField('email', e.target.value)} 
            />
          </label>
          {errors.email ? <div className="error-text">{errors.email}</div> : null}

          <label>
            Password
            <input 
              type="password" 
              placeholder="At least 8 characters"
              value={formData.password} 
              onChange={(e) => updateField('password', e.target.value)} 
            />
          </label>
          {errors.password ? <div className="error-text">{errors.password}</div> : null}

          <label>
            Confirm Password
            <input 
              type="password" 
              placeholder="Re-enter password"
              value={formData.confirmPassword} 
              onChange={(e) => updateField('confirmPassword', e.target.value)} 
            />
          </label>
          {errors.confirmPassword ? <div className="error-text">{errors.confirmPassword}</div> : null}

          {message ? <div className="error-text">{message}</div> : null}
          <button className="btn" type="submit">
            Register Account
          </button>
        </form>

        <div className="auth-links">
          <Link to="/login">Already have an account? Sign in</Link>
          <Link to="/">Back to Store</Link>
        </div>
      </div>
    </div>
  );
}

export default Signup;
