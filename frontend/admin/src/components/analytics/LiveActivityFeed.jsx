import React, { useState, useEffect, useRef } from 'react';
import { Activity, Zap, Target, ShoppingBag, Mail, UserPlus, Eye, Search, Heart, RefreshCcw } from 'lucide-react';

const EVENT_CONFIG = {
  lead_score_updated:  { icon: Target,      color: '#6366f1', label: 'Score Updated'     },
  lead_qualified:      { icon: Zap,          color: '#10b981', label: 'Lead Qualified'    },
  lead_disqualified:   { icon: Target,       color: '#ef4444', label: 'Lead Dropped'     },
  order_placed:        { icon: ShoppingBag,  color: '#f59e0b', label: 'Order Placed'     },
  marketing_sent:      { icon: Mail,         color: '#3b82f6', label: 'Marketing Sent'   },
  new_customer:        { icon: UserPlus,     color: '#8b5cf6', label: 'New Customer'     },
  customer_activity:   { icon: Activity,     color: '#94a3b8', label: 'User Activity'    },
  lead_update:         { icon: RefreshCcw,   color: '#f59e0b', label: 'Lead Scored'      },
  rescore_complete:    { icon: Zap,          color: '#10b981', label: 'Rescored'         },
  page_view:           { icon: Eye,          color: '#60a5fa', label: 'Page View'        },
  search:              { icon: Search,       color: '#a78bfa', label: 'Search'           },
  add_to_wishlist:     { icon: Heart,        color: '#f43f5e', label: 'Added to Wishlist'},
  add_to_cart:         { icon: ShoppingBag,  color: '#f59e0b', label: 'Added to Cart'   },
};

function getEventDetail(evt) {
  const d = evt.data || {};
  switch (evt.type) {
    case 'customer_activity':
      return d.event ? `${d.event.replace(/_/g, ' ')}${d.page ? ` · ${d.page}` : ''}` : (d.page || '');
    case 'lead_score_updated':
      return `Score: ${d.lead_score ?? '?'} · ${d.lead_segment ?? ''}`;
    case 'lead_qualified':
      return `Score: ${d.lead_score ?? '?'} · ${d.lead_segment ?? ''} segment`;
    case 'lead_disqualified':
      return `Dropped · prev ${d.previous_score ?? '?'}`;
    case 'order_placed':
      return `₹${(d.total_amount || 0).toLocaleString('en-IN')}`;
    case 'lead_update':
      return `Segment: ${d.segment ?? '?'} · Score: ${d.score ?? '?'}`;
    case 'rescore_complete':
      return `Score: ${d.lead_score ?? '?'}`;
    default:
      return '';
  }
}

export const LiveActivityFeed = () => {
  const [events, setEvents] = useState([]);
  const [connected, setConnected] = useState(false);
  const [lastSeen, setLastSeen] = useState(null);
  const socketRef = useRef(null);
  const maxEvents = 25;

  useEffect(() => {
    let socket = null;
    try {
      const ioUrl = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:5000').replace(/\/$/, '');

      import('socket.io-client').then(({ io }) => {
        socket = io(ioUrl, {
          transports: ['websocket', 'polling'],
          reconnectionAttempts: 10,
          reconnectionDelay: 1000,
        });

        socket.on('connect', () => setConnected(true));
        socket.on('disconnect', () => setConnected(false));

        const pushEvent = (type) => (data) => {
          const entry = {
            type,
            data,
            timestamp: new Date().toISOString(),
            id: `${type}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
          };
          setEvents(prev => [entry, ...prev].slice(0, maxEvents));
          setLastSeen(new Date());
        };

        Object.keys(EVENT_CONFIG).forEach(evtType => {
          socket.on(evtType, pushEvent(evtType));
        });

        socketRef.current = socket;
      }).catch(() => setConnected(false));
    } catch {
      setConnected(false);
    }

    return () => {
      if (socketRef.current) socketRef.current.disconnect();
    };
  }, []);

  const formatTime = (ts) => {
    try {
      return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    } catch { return ''; }
  };

  return (
    <div className="glass-card" style={{ padding: '24px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '16px' }}>
        <Activity size={18} style={{ color: connected ? '#10b981' : '#94a3b8' }} />
        <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 600 }}>Live Activity</h3>
        <span style={{
          marginLeft: 'auto',
          fontSize: '0.65rem',
          padding: '3px 10px',
          borderRadius: '20px',
          background: connected ? 'rgba(16,185,129,0.15)' : 'rgba(148,163,184,0.15)',
          color: connected ? '#10b981' : '#94a3b8',
          fontWeight: 600,
          display: 'flex',
          alignItems: 'center',
          gap: '5px',
        }}>
          {connected ? (
            <>
              <span style={{ width: 7, height: 7, borderRadius: '50%', background: '#10b981', display: 'inline-block', animation: 'pulse 1.5s ease-in-out infinite' }} />
              Connected
            </>
          ) : '○ Waiting'}
        </span>
      </div>

      {lastSeen && (
        <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', marginBottom: '10px' }}>
          Last event: {formatTime(lastSeen.toISOString())}
        </div>
      )}

      {events.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '32px 0', color: 'var(--text-muted)', fontSize: '0.82rem' }}>
          {connected
            ? '⚡ Listening for real-time events — browse the user store to trigger activity'
            : 'Events will appear here when activity is detected'}
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', maxHeight: '340px', overflowY: 'auto' }}>
          {events.map((evt, idx) => {
            const config = EVENT_CONFIG[evt.type] || EVENT_CONFIG.customer_activity;
            const IconComp = config.icon;
            const detail = getEventDetail(evt);
            const custId = evt.data?.customer_id || evt.data?.visitor_id || '';
            const isNew = idx === 0;
            return (
              <div key={evt.id} style={{
                display: 'flex',
                alignItems: 'flex-start',
                gap: '10px',
                padding: '9px 12px',
                borderRadius: '8px',
                background: isNew ? `${config.color}12` : 'rgba(255,255,255,0.03)',
                border: `1px solid ${isNew ? config.color + '33' : 'rgba(255,255,255,0.06)'}`,
                transition: 'all 0.3s ease',
              }}>
                <div style={{
                  width: 28, height: 28, borderRadius: '50%',
                  background: `${config.color}20`,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  flexShrink: 0, marginTop: 1
                }}>
                  <IconComp size={13} style={{ color: config.color }} />
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span style={{ fontSize: '0.78rem', fontWeight: 700, color: config.color }}>
                      {config.label}
                    </span>
                    <span style={{ fontSize: '0.65rem', color: 'var(--text-muted)', flexShrink: 0, marginLeft: 8 }}>
                      {formatTime(evt.timestamp)}
                    </span>
                  </div>
                  {(detail || custId) && (
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: '2px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {detail}
                      {custId && <span style={{ marginLeft: 6, opacity: 0.6 }}>· {String(custId).slice(0, 10)}…</span>}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
