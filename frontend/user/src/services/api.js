export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:5000').replace(/\/$/, '');

const ADMIN_SESSION_KEY = 'lead_magnet_admin_session';
const CUSTOMER_SESSION_KEY = 'lead_magnet_customer_session';
const ANONYMOUS_ID_KEY = 'lead_magnet_anonymous_id';

export function getAdminSession() {
  try {
    const rawSession = localStorage.getItem(ADMIN_SESSION_KEY);
    return rawSession ? JSON.parse(rawSession) : null;
  } catch (error) {
    return null;
  }
}

export function getCustomerSession() {
  try {
    const rawSession = localStorage.getItem(CUSTOMER_SESSION_KEY);
    return rawSession ? JSON.parse(rawSession) : null;
  } catch (error) {
    return null;
  }
}

export function saveCustomerSession(session) {
  localStorage.setItem(CUSTOMER_SESSION_KEY, JSON.stringify(session));
}

export function getAnonymousId() {
  let anonymousId = localStorage.getItem(ANONYMOUS_ID_KEY);
  if (!anonymousId) {
    anonymousId = `anon_${crypto.randomUUID()}`;
    localStorage.setItem(ANONYMOUS_ID_KEY, anonymousId);
  }
  return anonymousId;
}

function customerAuthHeaders(userId) {
  const session = getCustomerSession();
  return userId && session?.token ? { Authorization: `Bearer ${session.token}` } : {};
}

export async function parseJsonResponse(response) {
  const contentType = response.headers.get('content-type') || '';
  if (!contentType.includes('application/json')) {
    throw new Error('Backend API returned HTML instead of JSON');
  }

  const text = await response.text();
  try {
    return JSON.parse(text);
  } catch (error) {
    const preview = text.trim().slice(0, 80);
    throw new Error(preview.startsWith('<') ? 'Backend returned HTML instead of JSON. Check API_BASE_URL and backend route.' : 'Backend returned invalid JSON.');
  }
}

export async function adminFetch(path) {
  const adminSession = getAdminSession();
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      Authorization: `Bearer ${adminSession?.token || ''}`,
    },
  });
  const payload = await parseJsonResponse(response);

  if (!response.ok || !payload.success) {
    throw new Error(payload.message || 'Admin request failed');
  }

  return payload.data;
}

async function apiGet(path) {
  const adminSession = getAdminSession();
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: adminSession?.token ? {
      Authorization: `Bearer ${adminSession.token}`,
    } : {},
  });
  const payload = await parseJsonResponse(response);
  if (!response.ok || payload.success === false) {
    throw new Error(payload.message || 'Backend API request failed');
  }
  return payload;
}

export function fetchAnalyticsOverview() {
  return apiGet('/api/analytics/overview');
}

export function fetchAnalyticsEvents() {
  return apiGet('/api/analytics/events');
}

export function fetchLeads() {
  return apiGet('/api/leads');
}

export function fetchSessions() {
  return apiGet('/api/sessions');
}

export function fetchProfiles() {
  return apiGet('/api/profiles');
}

export function fetchUsersCount() {
  return apiGet('/api/debug/users-count');
}

export function fetchAllOrders() {
  return apiGet('/api/orders');
}

export async function startCustomerSession(customer) {
  const response = await fetch(`${API_BASE_URL}/api/session/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      visitor_id: customer.email,
      anonymous_id: customer.anonymous_id || getAnonymousId(),
    }),
  });
  const payload = await parseJsonResponse(response);
  if (!response.ok || !payload.success) {
    throw new Error(payload.message || 'Unable to start customer session.');
  }
  return payload.data;
}

export async function endCustomerSession() {
  const customer = getCustomerSession();
  if (!customer?.session_id) return;
  try {
    await fetch(`${API_BASE_URL}/api/session/end`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: customer.session_id }),
    });
  } catch (error) {
    // Logout should not be blocked by session close failures.
  }
}

export async function trackCustomerEvent(eventType, details = {}) {
  const customer = getCustomerSession();
  if (!customer?.session_id) return;

  try {
    await fetch(`${API_BASE_URL}/api/session/event`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: customer.session_id,
        event_type: eventType,
        page: details.page || window.location.hash.replace('#', '') || '/',
        entity: details.entity || {},
        metadata: details.metadata || {},
        context: details.context || {},
      }),
    });
  } catch (error) {
    // Customer actions should continue even if tracking is temporarily unavailable.
  }
}

export async function createOrder(order) {
  const customerSession = getCustomerSession();
  if (!customerSession?.token) {
    throw new Error('Please log in before placing an order.');
  }

  const response = await fetch(`${API_BASE_URL}/api/orders`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${customerSession.token}`,
    },
    body: JSON.stringify(order),
  });
  const payload = await parseJsonResponse(response);
  if (!response.ok || !payload.success) {
    throw new Error(payload.message || 'Unable to place order.');
  }
  return payload.data;
}

export async function fetchCustomerOrders(email) {
  const session = getCustomerSession();
  if (!session?.token || !session?.user_id) return [];
  const response = await fetch(`${API_BASE_URL}/api/orders?user_id=${encodeURIComponent(session.user_id)}`, {
    headers: {
      Authorization: `Bearer ${session.token}`,
    },
  });
  const payload = await parseJsonResponse(response);
  if (!response.ok || !payload.success) {
    throw new Error(payload.message || 'Unable to load orders.');
  }
  return payload.data;
}

export async function fetchAdminNotifications() {
  const session = getAdminSession();
  const token = session?.token;
  const headers = token ? { Authorization: `Bearer ${token}` } : {};
  const response = await fetch(`${API_BASE_URL}/api/admin/notifications`, { headers });
  const payload = await parseJsonResponse(response);
  if (!response.ok || !payload.success) {
    return [];
  }
  return payload.data || [];
}
export async function fetchCart(userId, anonymousId) {
  const query = userId ? `user_id=${userId}` : `anonymous_id=${anonymousId}`;
  const response = await fetch(`${API_BASE_URL}/api/cart?${query}`, {
    headers: customerAuthHeaders(userId),
  });
  const payload = await parseJsonResponse(response);
  if (!response.ok || payload.success === false) {
    throw new Error(payload.message || 'Unable to load cart.');
  }
  return payload.data || [];
}

export async function addToCartApi(productId, quantity = 1, userId, anonymousId, sessionId) {
  const response = await fetch(`${API_BASE_URL}/api/cart`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...customerAuthHeaders(userId) },
    body: JSON.stringify({ product_id: productId, quantity, user_id: userId, anonymous_id: anonymousId, session_id: sessionId })
  });
  const payload = await parseJsonResponse(response);
  if (!response.ok || payload.success === false) {
    throw new Error(payload.message || 'Unable to update cart.');
  }
  return payload.data || [];
}

export async function updateCartApi(productId, quantity, userId, anonymousId) {
  const response = await fetch(`${API_BASE_URL}/api/cart/${productId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', ...customerAuthHeaders(userId) },
    body: JSON.stringify({ product_id: productId, quantity, user_id: userId, anonymous_id: anonymousId }),
  });
  const payload = await parseJsonResponse(response);
  if (!response.ok || payload.success === false) {
    throw new Error(payload.message || 'Unable to update cart.');
  }
  return payload.data || [];
}

export async function removeFromCartApi(productId, userId, anonymousId, sessionId) {
  const query = userId ? `user_id=${userId}` : `anonymous_id=${anonymousId}`;
  const response = await fetch(`${API_BASE_URL}/api/cart/${productId}?${query}&session_id=${sessionId || ''}`, {
    method: 'DELETE',
    headers: customerAuthHeaders(userId),
  });
  const payload = await parseJsonResponse(response);
  if (!response.ok || payload.success === false) {
    throw new Error(payload.message || 'Unable to remove cart item.');
  }
  return payload.data || [];
}

export async function clearCartApi(userId, anonymousId) {
  const query = userId ? `user_id=${userId}` : `anonymous_id=${anonymousId}`;
  const response = await fetch(`${API_BASE_URL}/api/cart?${query}`, {
    method: 'DELETE',
    headers: customerAuthHeaders(userId),
  });
  const payload = await parseJsonResponse(response);
  if (!response.ok || payload.success === false) {
    throw new Error(payload.message || 'Unable to clear cart.');
  }
  return payload.data || [];
}

export async function fetchWishlist(userId, anonymousId) {
  const query = userId ? `user_id=${userId}` : `anonymous_id=${anonymousId}`;
  const response = await fetch(`${API_BASE_URL}/api/wishlist?${query}`);
  const payload = await parseJsonResponse(response);
  return payload.data || [];
}

export async function addToWishlistApi(productId, userId, anonymousId, sessionId) {
  const response = await fetch(`${API_BASE_URL}/api/wishlist`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ product_id: productId, user_id: userId, anonymous_id: anonymousId, session_id: sessionId })
  });
  const payload = await parseJsonResponse(response);
  return payload.data || [];
}

export async function removeFromWishlistApi(productId, userId, anonymousId, sessionId) {
  const query = userId ? `user_id=${userId}` : `anonymous_id=${anonymousId}`;
  const response = await fetch(`${API_BASE_URL}/api/wishlist/${productId}?${query}&session_id=${sessionId || ''}`, {
    method: 'DELETE'
  });
  const payload = await parseJsonResponse(response);
  return payload.data || [];
}

export async function fetchRecommendations(userId, anonymousId, limit = 8) {
  const query = userId ? `user_id=${userId}&limit=${limit}` : `anonymous_id=${anonymousId}&limit=${limit}`;
  const response = await fetch(`${API_BASE_URL}/api/recommendations?${query}`);
  const payload = await parseJsonResponse(response);
  return payload.data || [];
}
