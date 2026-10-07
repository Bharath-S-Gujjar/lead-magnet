import React, { useEffect, useRef, useState, useCallback } from 'react';
import { io } from 'socket.io-client';
import { useAdminAuth } from '../../context/AdminAuthContext';
import { getAdminRecentActivity } from '../../services/api';
import {
  Activity, Wifi, WifiOff, Loader, ShoppingCart, Search, Eye, Heart,
  ShoppingBag, User, Target, Mail, AlertCircle, RefreshCw, TrendingUp
} from 'lucide-react';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5000';
const MAX_FEED_SIZE = 50;

// ─── Icon + label helpers ─────────────────────────────────────────────────────

const EVENT_META = {
  page_view:        { icon: Eye,          color: '#6366f1', label: 'Page View' },
  product_view:     { icon: Eye,          color: '#8b5cf6', label: 'Product View' },
  product_click:    { icon: Eye,          color: '#a78bfa', label: 'Product Click' },
  add_to_cart:      { icon: ShoppingCart, color: '#f59e0b', label: 'Added to Cart' },
  remove_from_cart: { icon: ShoppingCart, color: '#94a3b8', label: 'Removed from Cart' },
  wishlist_add:     { icon: Heart,        color: '#f43f5e', label: 'Wishlist Add' },
  add_to_wishlist:  { icon: Heart,        color: '#f43f5e', label: 'Wishlist Add' },
  wishlist_remove:  { icon: Heart,        color: '#94a3b8', label: 'Wishlist Remove' },
  search:           { icon: Search,       color: '#3b82f6', label: 'Search' },
  filter_apply:     { icon: Search,       color: '#60a5fa', label: 'Filter Applied' },
  checkout_start:   { icon: ShoppingBag, color: '#f97316', label: 'Checkout Started' },
  order_placed:     { icon: ShoppingBag, color: '#10b981', label: 'Order Placed' },
  lead_qualified:   { icon: Target,       color: '#6366f1', label: 'Lead Qualified' },
  lead_score_updated: { icon: TrendingUp, color: '#8b5cf6', label: 'Lead Rescored' },
  marketing_sent:   { icon: Mail,         color: '#06b6d4', label: 'Marketing Sent' },
  new_customer:     { icon: User,         color: '#10b981', label: 'New Registration' },
};

function getEventMeta(type) {
  return EVENT_META[type] || { icon: Activity, color: '#94a3b8', label: type?.replace(/_/g, ' ') || 'Activity' };
}

function formatAge(ts) {
  if (!ts) return '';
  const diff = (Date.now() - new Date(ts).getTime()) / 1000;
  if (diff < 60) return `${Math.round(diff)}s ago`;
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.round(diff / 3600)}h ago`;
  return new Date(ts).toLocaleDateString('en-IN');
}

// Normalize events from socket OR from history API into a common shape
function normalizeEvent(raw, source = 'history') {
  if (!raw) return null;
  const type = raw.type || raw.event_type || 'page_view';
  const customerId = raw.customer_id;
  const customerName = raw.customer_name;
  const description = raw.description || raw.page || (raw.entity || {}).name || '';
  const segment = raw.lead_segment || raw.segment || '';
  const score = raw.lead_score != null ? String(raw.lead_score) : '';
  const ts = raw.timestamp || raw.scored_at || raw.created_at;
  return {
    id: `${source}-${type}-${ts}-${Math.random().toString(36).slice(2, 6)}`,
    type,
    customer_id: customerId ? String(customerId) : null,
    customer_name: customerName || null,
    description,
    segment,
    score,
    timestamp: ts,
    source,
  };
}

// ─── Component ────────────────────────────────────────────────────────────────

export const LiveActivityFeed = () => {
  const { admin } = useAdminAuth();
  const socketRef = useRef(null);
  const [connected, setConnected] = useState(false);
  const [events, setEvents] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyError, setHistoryError] = useState('');
  const seenIds = useRef(new Set());

  const addEvent = useCallback((normalized) => {
    if (!normalized || seenIds.current.has(normalized.id)) return;
    seenIds.current.add(normalized.id);
    setEvents(prev => [normalized, ...prev].slice(0, MAX_FEED_SIZE));
  }, []);

  // ── Load initial history ──
  useEffect(() => {
    if (!admin?.token) return;
    let mounted = true;
    async function load() {
      setHistoryLoading(true);
      setHistoryError('');
      try {
        const history = await getAdminRecentActivity(admin.token, 30);
        if (!mounted) return;
        const normalized = (history || [])
          .map(e => normalizeEvent(e, 'history'))
          .filter(Boolean);
        setEvents(normalized);
        normalized.forEach(e => seenIds.current.add(e.id));
      } catch (err) {
        if (mounted) setHistoryError('Could not load recent history.');
      } finally {
        if (mounted) setHistoryLoading(false);
      }
    }
    load();
    return () => { mounted = false; };
  }, [admin?.token]);

  // ── Real-time socket connection ──
  useEffect(() => {
    const socket = io(API_BASE, {
      transports: ['websocket', 'polling'],
      reconnectionAttempts: 10,
      reconnectionDelay: 1000,
    });
    socketRef.current = socket;

    socket.on('connect', () => setConnected(true));
    socket.on('disconnect', () => setConnected(false));
    socket.on('connect_error', () => setConnected(false));

    // Map every known socket event name to a normalized feed entry
    const handlers = {
      // Customer browsing events
      customer_activity: (data) => {
        const evtType = data.event_type || 'page_view';
        addEvent(normalizeEvent({
          type: evtType,
          customer_id: data.customer_id || data.user_id,
          customer_name: data.customer_name,
          description: data.page || data.description || '',
          timestamp: data.timestamp || new Date().toISOString(),
        }, 'socket'));
      },
      // Lead score updates
      lead_update: (data) => {
        addEvent(normalizeEvent({
          type: 'lead_score_updated',
          customer_id: data.customer_id,
          customer_name: data.customer_name,
          description: data.page || '',
          segment: data.segment,
          score: data.score,
          timestamp: data.scored_at || data.timestamp || new Date().toISOString(),
        }, 'socket'));
      },
      // Rescore completions
      rescore_complete: (data) => {
        if (!data?.success) return;
        addEvent(normalizeEvent({
          type: 'lead_score_updated',
          customer_id: data.customer_id,
          description: 'Manual rescore completed',
          timestamp: new Date().toISOString(),
        }, 'socket'));
      },
      // Order events
      order_placed: (data) => {
        addEvent(normalizeEvent({
          type: 'order_placed',
          customer_id: data.customer_id || data.user_id,
          description: data.total_amount ? `₹${Number(data.total_amount).toLocaleString('en-IN')}` : '',
          timestamp: data.timestamp || new Date().toISOString(),
        }, 'socket'));
      },
    };

    for (const [evt, handler] of Object.entries(handlers)) {
      socket.on(evt, handler);
    }

    return () => {
      socket.disconnect();
    };
  }, [addEvent]);

  // ── UI ──
  const ConnIcon = connected ? Wifi : WifiOff;
  const connColor = connected ? '#10b981' : '#94a3b8';

  return (
    <div className="panel" style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: '400px' }}>

      {/* Header */}
      <div style={{
        padding: '16px 20px', borderBottom: '1px solid var(--panel-border)',
        display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <Activity size={18} style={{ color: 'var(--accent-indigo)' }} />
          <h3 className="heading-md" style={{ color: 'var(--text-primary)' }}>Live Activity</h3>
          <div style={{
            display: 'flex', alignItems: 'center', gap: '5px',
            padding: '2px 10px', borderRadius: '20px',
            background: connected ? 'rgba(16,185,129,0.12)' : 'rgba(148,163,184,0.12)',
            border: `1px solid ${connected ? 'rgba(16,185,129,0.3)' : 'rgba(148,163,184,0.3)'}`,
          }}>
            <ConnIcon size={11} style={{ color: connColor }} />
            <span style={{ fontSize: '0.71rem', fontWeight: 700, color: connColor }}>
              {connected ? 'Live' : 'Offline'}
            </span>
          </div>
        </div>
        <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
          {events.length} events
        </div>
      </div>

      {/* Feed */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '10px 0' }}>
        {historyLoading ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', gap: '10px', color: 'var(--text-muted)' }}>
            <Loader size={20} className="spin" />
            <span style={{ fontSize: '0.82rem' }}>Loading recent activity...</span>
          </div>
        ) : historyError ? (
          <div style={{ margin: '12px', padding: '12px', background: 'var(--table-header-bg)', borderRadius: 8, fontSize: '0.82rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <AlertCircle size={15} />
            {historyError}
          </div>
        ) : events.length === 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', gap: '10px', color: 'var(--text-muted)' }}>
            <Activity size={28} style={{ opacity: 0.35 }} />
            <span style={{ fontSize: '0.82rem' }}>Waiting for activity...</span>
          </div>
        ) : (
          events.map((evt) => {
            const meta = getEventMeta(evt.type);
            const Icon = meta.icon;
            return (
              <div key={evt.id} style={{
                padding: '8px 16px', display: 'flex', alignItems: 'flex-start', gap: '10px',
                borderBottom: '1px solid var(--panel-border)',
                transition: 'background 0.15s',
              }}
                onMouseEnter={e => e.currentTarget.style.background = 'var(--table-header-bg)'}
                onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
              >
                <div style={{
                  width: 28, height: 28, borderRadius: '50%', flexShrink: 0, marginTop: '1px',
                  background: `${meta.color}18`, display: 'flex', alignItems: 'center', justifyContent: 'center'
                }}>
                  <Icon size={13} style={{ color: meta.color }} />
                </div>

                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '6px' }}>
                    <span style={{ fontSize: '0.8rem', fontWeight: 700, color: 'var(--text-primary)', flexShrink: 0 }}>
                      {meta.label}
                    </span>
                    <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)', flexShrink: 0 }}>
                      {formatAge(evt.timestamp)}
                    </span>
                  </div>
                  {(evt.customer_name || evt.customer_id) && (
                    <div style={{ fontSize: '0.73rem', color: 'var(--text-secondary)', marginTop: '1px' }}>
                      {evt.customer_name || evt.customer_id?.slice(-8)}
                    </div>
                  )}
                  {evt.description && (
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: '1px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {evt.description}
                    </div>
                  )}
                  {(evt.score || evt.segment) && (
                    <div style={{ marginTop: '3px', display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
                      {evt.score && (
                        <span style={{ fontSize: '0.68rem', padding: '1px 6px', borderRadius: '10px', background: 'rgba(99,102,241,0.15)', color: '#6366f1', fontWeight: 700 }}>
                          Score: {evt.score}
                        </span>
                      )}
                      {evt.segment && (
                        <span style={{ fontSize: '0.68rem', padding: '1px 6px', borderRadius: '10px', background: 'rgba(139,92,246,0.15)', color: '#8b5cf6', fontWeight: 700 }}>
                          {evt.segment}
                        </span>
                      )}
                    </div>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
