import React, { useState, useEffect, useRef } from 'react';
import { Activity, Zap, Target, ShoppingBag, Mail, UserPlus } from 'lucide-react';

const EVENT_ICONS = {
  lead_score_updated: { icon: Target, color: '#6366f1' },
  lead_qualified: { icon: Zap, color: '#10b981' },
  lead_disqualified: { icon: Target, color: '#ef4444' },
  order_placed: { icon: ShoppingBag, color: '#f59e0b' },
  marketing_sent: { icon: Mail, color: '#3b82f6' },
  new_customer: { icon: UserPlus, color: '#8b5cf6' },
  customer_activity: { icon: Activity, color: '#94a3b8' },
};

export const LiveActivityFeed = () => {
  const [events, setEvents] = useState([]);
  const [connected, setConnected] = useState(false);
  const socketRef = useRef(null);
  const maxEvents = 20;

  useEffect(() => {
    // Attempt SocketIO connection
    let socket = null;
    try {
      const ioUrl = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:5000').replace(/\/$/, '');
      
      // Dynamic import for socket.io-client (graceful fallback if not installed)
      import('socket.io-client').then(({ io }) => {
        socket = io(ioUrl, {
          transports: ['websocket', 'polling'],
          reconnectionAttempts: 5,
        });

        socket.on('connect', () => setConnected(true));
        socket.on('disconnect', () => setConnected(false));

        // Listen for all live events
        const eventTypes = Object.keys(EVENT_ICONS);
        eventTypes.forEach(evtType => {
          socket.on(evtType, (data) => {
            setEvents(prev => [{
              type: evtType,
              data,
              timestamp: new Date().toISOString(),
              id: `${evtType}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
            }, ...prev].slice(0, maxEvents));
          });
        });

        socketRef.current = socket;
      }).catch(() => {
        // socket.io-client not installed — show static fallback
        setConnected(false);
      });
    } catch {
      setConnected(false);
    }

    return () => {
      if (socketRef.current) {
        socketRef.current.disconnect();
      }
    };
  }, []);

  const formatTime = (ts) => {
    try {
      const d = new Date(ts);
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    } catch {
      return '';
    }
  };

  const getEventLabel = (type) => {
    switch (type) {
      case 'lead_score_updated': return 'Score Updated';
      case 'lead_qualified': return 'Lead Qualified';
      case 'lead_disqualified': return 'Lead Disqualified';
      case 'order_placed': return 'Order Placed';
      case 'marketing_sent': return 'Marketing Sent';
      case 'new_customer': return 'New Customer';
      case 'customer_activity': return 'Activity';
      default: return type;
    }
  };

  return (
    <div className="glass-card" style={{ padding: '24px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '16px' }}>
        <Activity size={18} style={{ color: connected ? '#10b981' : '#94a3b8' }} />
        <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 600 }}>Live Activity</h3>
        <span style={{
          marginLeft: 'auto',
          fontSize: '0.65rem',
          padding: '3px 8px',
          borderRadius: '20px',
          background: connected ? 'rgba(16,185,129,0.15)' : 'rgba(148,163,184,0.15)',
          color: connected ? '#10b981' : '#94a3b8',
          fontWeight: 600,
        }}>
          {connected ? '● Connected' : '○ Waiting'}
        </span>
      </div>

      {events.length === 0 ? (
        <div style={{
          textAlign: 'center',
          padding: '24px',
          color: 'var(--text-muted)',
          fontSize: '0.8rem',
        }}>
          {connected
            ? 'Listening for real-time events...'
            : 'Events will appear here when activity is detected'
          }
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', maxHeight: '300px', overflowY: 'auto' }}>
          {events.map(evt => {
            const config = EVENT_ICONS[evt.type] || EVENT_ICONS.customer_activity;
            const IconComp = config.icon;
            return (
              <div key={evt.id} style={{
                display: 'flex',
                alignItems: 'center',
                gap: '10px',
                padding: '8px 12px',
                borderRadius: '8px',
                background: 'rgba(255,255,255,0.03)',
                border: '1px solid rgba(255,255,255,0.05)',
                animation: 'fadeIn 0.3s ease',
              }}>
                <IconComp size={14} style={{ color: config.color, flexShrink: 0 }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <span style={{ fontSize: '0.75rem', fontWeight: 600, color: config.color }}>
                    {getEventLabel(evt.type)}
                  </span>
                  {evt.data?.customer_id && (
                    <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginLeft: '8px' }}>
                      {evt.data.customer_id.slice(0, 8)}...
                    </span>
                  )}
                </div>
                <span style={{ fontSize: '0.65rem', color: 'var(--text-muted)', flexShrink: 0 }}>
                  {formatTime(evt.timestamp)}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
