/**
 * Admin Intelligence API Service
 * 
 * Centralized API client connecting frontend/admin to backend intelligence APIs.
 * Supports authentication headers, query parameter formatting, error handling,
 * and clean data response unwrapping.
 */

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:5000').replace(/\/$/, '');

/**
 * Helper to construct Authorization header.
 */
function authHeaders(token) {
  const headers = { 'Content-Type': 'application/json' };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  return headers;
}

/**
 * Base fetch handler with error handling for 401, 403, and network errors.
 */
async function apiFetch(endpoint, options = {}) {
  const url = `${API_BASE_URL}${endpoint}`;
  try {
    const res = await fetch(url, options);
    const data = await res.json().catch(() => ({}));

    if (!res.ok) {
      const errorMsg = data.message || `Request failed with status ${res.status}`;
      const err = new Error(errorMsg);
      err.status = res.status;
      err.data = data;
      throw err;
    }

    return data;
  } catch (err) {
    if (!err.status) {
      err.status = 500;
      err.message = err.message || 'Unable to connect to backend service.';
    }
    throw err;
  }
}

/**
 * Fetch real-time aggregate dashboard KPIs.
 */
export async function getAdminIntelligenceOverview(token) {
  const res = await apiFetch('/api/admin/intelligence/overview', {
    headers: authHeaders(token),
  });
  return res.data;
}

/**
 * Fetch customer-level lead directory with pagination, filtering, and sorting.
 */
export async function getAdminIntelligenceLeads({
  token,
  qualification_status = 'qualified',
  segment = 'all',
  sort_by = 'lead_score',
  sort_order = 'desc',
  page = 1,
  limit = 25,
} = {}) {
  const params = new URLSearchParams();
  if (qualification_status) params.append('qualification_status', qualification_status);
  if (segment) params.append('segment', segment);
  if (sort_by) params.append('sort_by', sort_by);
  if (sort_order) params.append('sort_order', sort_order);
  if (page) params.append('page', page.toString());
  if (limit) params.append('limit', limit.toString());

  const res = await apiFetch(`/api/admin/intelligence/leads?${params.toString()}`, {
    headers: authHeaders(token),
  });
  return res.data;
}

/**
 * Fetch full unified customer intelligence profile deep-dive.
 */
export async function getAdminCustomerIntelligence(customerId, token) {
  if (!customerId) throw new Error('Customer ID is required');
  const res = await apiFetch(`/api/admin/intelligence/customers/${customerId}`, {
    headers: authHeaders(token),
  });
  return res.data;
}

/**
 * Fetch lead distribution breakdown across segments and qualification statuses.
 */
export async function getAdminLeadDistribution(token) {
  const res = await apiFetch('/api/admin/intelligence/lead-distribution', {
    headers: authHeaders(token),
  });
  return res.data;
}

/**
 * Fetch recent qualified leads feed.
 */
export async function getAdminRecentLeads({ token, page = 1, limit = 10 } = {}) {
  const params = new URLSearchParams({ page: page.toString(), limit: limit.toString() });
  const res = await apiFetch(`/api/admin/intelligence/recent-leads?${params.toString()}`, {
    headers: authHeaders(token),
  });
  return res.data;
}

/**
 * Fetch recent marketing automation events and channel dispatches.
 */
export async function getAdminMarketingActivity({ token, page = 1, limit = 25 } = {}) {
  const params = new URLSearchParams({ page: page.toString(), limit: limit.toString() });
  const res = await apiFetch(`/api/admin/intelligence/marketing-activity?${params.toString()}`, {
    headers: authHeaders(token),
  });
  return res.data;
}

/**
 * Fetch administrative internal notification log.
 */
export async function getAdminNotifications({ token, read, page = 1, limit = 25 } = {}) {
  const params = new URLSearchParams({ page: page.toString(), limit: limit.toString() });
  if (read !== undefined && read !== null) {
    params.append('read', read.toString());
  }
  const res = await apiFetch(`/api/admin/intelligence/notifications?${params.toString()}`, {
    headers: authHeaders(token),
  });
  return res.data;
}

/**
 * Mark a single admin notification as read.
 */
export async function markNotificationRead(notificationId, token) {
  if (!notificationId) throw new Error('Notification ID is required');
  const res = await apiFetch(`/api/admin/intelligence/notifications/${notificationId}/read`, {
    method: 'PATCH',
    headers: authHeaders(token),
  });
  return res.data;
}

/**
 * Mark all unread admin notifications as read.
 */
export async function markAllNotificationsRead(token) {
  const res = await apiFetch('/api/admin/intelligence/notifications/mark-all-read', {
    method: 'POST',
    headers: authHeaders(token),
  });
  return res.data;
}

// --- Phase 17A: New Intelligence APIs ---

/**
 * Fetch score history for a specific customer.
 */
export async function getScoreHistory(customerId, token, limit = 50) {
  if (!customerId) throw new Error('Customer ID is required');
  const params = new URLSearchParams({ limit: limit.toString() });
  const res = await apiFetch(`/api/admin/intelligence/customers/${customerId}/score-history?${params.toString()}`, {
    headers: authHeaders(token),
  });
  return res.data;
}

/**
 * Fetch full Customer 360 view for a customer.
 */
export async function getCustomer360(customerId, token) {
  if (!customerId) throw new Error('Customer ID is required');
  const res = await apiFetch(`/api/admin/intelligence/customers/${customerId}/360`, {
    headers: authHeaders(token),
  });
  return res.data;
}

/**
 * Fetch model explainability for a customer's lead score.
 */
export async function getLeadExplanation(customerId, token) {
  if (!customerId) throw new Error('Customer ID is required');
  const res = await apiFetch(`/api/admin/intelligence/customers/${customerId}/explain`, {
    headers: authHeaders(token),
  });
  return res.data;
}

/**
 * Fetch purchase funnel analytics.
 */
export async function getFunnelAnalytics(token) {
  const res = await apiFetch('/api/admin/intelligence/funnel', {
    headers: authHeaders(token),
  });
  return res.data;
}

/**
 * Fetch RFM segment distribution.
 */
export async function getRFMDistribution(token) {
  const res = await apiFetch('/api/admin/intelligence/rfm', {
    headers: authHeaders(token),
  });
  return res.data;
}

/**
 * Fetch retention/inactivity overview.
 */
export async function getRetentionOverview(token) {
  const res = await apiFetch('/api/admin/intelligence/retention', {
    headers: authHeaders(token),
  });
  return res.data;
}

/**
 * Fetch lead-to-revenue attribution metrics.
 */
export async function getRevenueAttribution(token) {
  const res = await apiFetch('/api/admin/intelligence/revenue-attribution', {
    headers: authHeaders(token),
  });
  return res.data;
}

/**
 * Run what-if lead score simulation.
 */
export async function simulateLeadScore({ token, customer_id, feature_overrides } = {}) {
  const res = await apiFetch('/api/admin/intelligence/simulate', {
    method: 'POST',
    headers: authHeaders(token),
    body: JSON.stringify({ customer_id, feature_overrides }),
  });
  return res.data;
}

/**
 * Fetch recent activity history for the live activity feed initial load.
 */
export async function getAdminRecentActivity(token, limit = 50) {
  const params = new URLSearchParams({ limit: limit.toString() });
  const res = await apiFetch(`/api/admin/intelligence/recent-activity?${params.toString()}`, {
    headers: authHeaders(token),
  });
  return res.data || [];
}
