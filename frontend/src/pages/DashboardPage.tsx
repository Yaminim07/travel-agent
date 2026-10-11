import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api';

function isJwtExpired(token: string | null) {
  if (!token) return true;

  try {
    const payload = token.split('.')[1];
    if (!payload) return true;
    const decoded = JSON.parse(atob(payload.replace(/-/g, '+').replace(/_/g, '/')));
    return typeof decoded.exp === 'number' ? decoded.exp * 1000 < Date.now() : false;
  } catch {
    return true;
  }
}

function clearAuthSession() {
  localStorage.removeItem('accessToken');
  localStorage.removeItem('refreshToken');
  localStorage.removeItem('userEmail');
}

type GmailMessage = {
  id: string;
  threadId?: string;
  snippet?: string;
};

export function DashboardPage() {
  const navigate = useNavigate();
  const menuRef = useRef<HTMLDivElement | null>(null);
  const [messages, setMessages] = useState<GmailMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [menuOpen, setMenuOpen] = useState(false);
  const userEmail = localStorage.getItem('userEmail') || 'User';

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    }

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleLogout = async () => {
    const accessToken = localStorage.getItem('accessToken');
    const refreshToken = localStorage.getItem('refreshToken');

    if (!accessToken || isJwtExpired(accessToken)) {
      clearAuthSession();
      navigate('/login', { replace: true });
      return;
    }

    try {
      if (refreshToken) {
        await fetch(`${API_BASE_URL}/auth/logout/`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${accessToken}`,
          },
          body: JSON.stringify({ refresh: refreshToken }),
        });
      }
    } catch (err) {
      console.error('Logout request failed:', err);
    } finally {
      clearAuthSession();
      navigate('/login', { replace: true });
    }
  };

  useEffect(() => {
    const accessToken = localStorage.getItem('accessToken');

    if (!accessToken || isJwtExpired(accessToken)) {
      clearAuthSession();
      navigate('/login', { replace: true });
      return;
    }

    fetch(`${API_BASE_URL}/gmail/messages/`, {
      headers: {
        Authorization: `Bearer ${accessToken}`,
      },
    })
      .then(async (response) => {
        if (response.status === 401 || response.status === 403) {
          clearAuthSession();
          navigate('/login', { replace: true });
          return;
        }

        const data = await response.json();
        if (!response.ok) {
          throw new Error(data.detail || 'Unable to load Gmail messages.');
        }
        setMessages(data.messages || []);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : 'Unable to load Gmail messages.');
        clearAuthSession();
        navigate('/login', { replace: true });
      })
      .finally(() => {
        setLoading(false);
      });
  }, [navigate]);

  return (
    <div className="dashboard-shell">
      <div className="dashboard-app">
        <header className="top-nav">
          <div className="brand-cluster">
            <div className="logo-badge">T</div>
            <div className="logo-word">Travel Agent</div>
          </div>

          <div className="search-bar">
            <span className="search-icon">⌕</span>
            <span className="search-text">Jammu &amp; Kashmir</span>
            <span className="search-divider" />
            <span className="search-text">2 adults</span>
            <button className="search-button" aria-label="Search">
              ⌕
            </button>
          </div>

          <div className="nav-actions">
            <button className="nav-button nav-button-light">Add trip</button>
            <div className="profile-menu" ref={menuRef}>
              <button className="profile-pill" type="button" onClick={() => setMenuOpen((open) => !open)}>
                <span className="menu-icon">☰</span>
                <div className="avatar-circle">P</div>
              </button>

              {menuOpen ? (
                <div className="profile-dropdown">
                  <div className="profile-email">{userEmail}</div>
                  <button type="button" className="menu-logout" onClick={handleLogout}>
                    Logout
                  </button>
                </div>
              ) : null}
            </div>
          </div>
        </header>

        <main className="dashboard-main">
          <div className="title-row">
            <div>
              <div className="eyebrow">Namaste, Priya ✦ 2026 season</div>
              <h1>2026 — your year in travel</h1>
              <p>
                All 6 trips from this year in one view — 2 still upcoming, 4 already stamped.
              </p>
            </div>

            <div className="filter-row">
              <button className="filter-pill active">All · 6</button>
              <button className="filter-pill">Upcoming · 2</button>
              <button className="filter-pill">Completed · 4</button>
            </div>
          </div>

          <div className="year-selector">
            <div className="selector-left">
              <div className="selector-icon">📅</div>
              <div className="selector-copy">
                <div className="selector-title">2026 at a glance</div>
                <div className="selector-subtitle">Showing full year · switch to revisit old trips</div>
              </div>
              <div className="selector-tabs">
                <button className="tab active">2026</button>
                <button className="tab">2025</button>
                <button className="tab">2024</button>
                <button className="tab">2023</button>
                <button className="tab tab-more">▾</button>
              </div>
            </div>

            <div className="selector-right">
              <div className="mini-stat">
                <span>6</span>
                <small>trips</small>
              </div>
              <div className="mini-stat-divider" />
              <div className="mini-stat">
                <span>10</span>
                <small>flights</small>
              </div>
              <div className="mini-stat-divider" />
              <div className="mini-stat">
                <span>24</span>
                <small>nights</small>
              </div>
              <div className="mini-stat-divider" />
              <div className="mini-stat">
                <span>5</span>
                <small>countries</small>
              </div>
              <button className="nav-button secondary">Year report</button>
            </div>
          </div>

          <div className="section-header">
            <span>Gmail messages</span>
            <span className="floating-badge">{messages.length} recent</span>
          </div>

          <div className="booking-panel" style={{ marginBottom: 24 }}>
            <div className="booking-header">
              <span>Latest emails</span>
              <a href="/">Refresh</a>
            </div>

            {loading ? (
              <div className="booking-list" style={{ padding: '16px 0' }}>
                <div className="booking-copy">
                  <strong>Loading Gmail messages...</strong>
                </div>
              </div>
            ) : error ? (
              <div className="booking-list" style={{ padding: '16px 0' }}>
                <div className="booking-copy">
                  <strong>{error}</strong>
                </div>
              </div>
            ) : messages.length === 0 ? (
              <div className="booking-list" style={{ padding: '16px 0' }}>
                <div className="booking-copy">
                  <strong>No Gmail messages found.</strong>
                </div>
              </div>
            ) : (
              <div className="booking-list">
                {messages.map((message) => (
                  <div className="booking-item" key={message.id}>
                    <div className="booking-thumb travel-one" />
                    <div className="booking-copy">
                      <strong>{message.threadId || 'Gmail message'}</strong>
                      <span>{message.snippet || 'No preview available.'}</span>
                    </div>
                    <div className="booking-status complete">Inbox</div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="section-header">
            <span>Happening next · Oct — Nov 2026</span>
            <span className="floating-badge">2 upcoming</span>
          </div>

          <div className="trip-layout">
            <div className="feature-trip">
              <div className="feature-image">
                <div className="image-badges">
                  <span>Leisure · 8 days</span>
                  <span className="dark-badge">In 23 days</span>
                </div>

                <div className="location-card">
                  <div className="location-main">
                    <span className="pin">📍</span>
                    <div>
                      <div className="location-title">Kyoto + Osaka, Japan</div>
                      <div className="location-subtitle">Oct 24 – Oct 31 · 2 travellers</div>
                    </div>
                  </div>
                  <button className="nav-button primary">Itinerary</button>
                </div>
              </div>
            </div>

            <div className="booking-panel">
              <div className="booking-header">
                <span>Next up — bookings</span>
                <a href="/">Manage trip</a>
              </div>

              <div className="countdown-row">
                <div className="countdown-box">
                  <span>23</span>
                  <small>days to go</small>
                </div>
                <div className="countdown-box">
                  <span>04</span>
                  <small>hotels</small>
                </div>
                <div className="countdown-box">
                  <span>2</span>
                  <small>flights</small>
                </div>
              </div>

              <div className="booking-list">
                <div className="booking-item">
                  <div className="booking-thumb travel-one" />
                  <div className="booking-copy">
                    <strong>Japan rail pass</strong>
                    <span>Booked · 2 passes</span>
                  </div>
                  <div className="booking-status complete">Ready</div>
                </div>

                <div className="booking-item">
                  <div className="booking-thumb travel-two" />
                  <div className="booking-copy">
                    <strong>Hotel in Kyoto</strong>
                    <span>Awaiting check-in</span>
                  </div>
                  <div className="booking-status pending">Review</div>
                </div>

                <div className="booking-item">
                  <div className="booking-thumb travel-three" />
                  <div className="booking-copy">
                    <strong>Osaka dining plan</strong>
                    <span>Curated by agent</span>
                  </div>
                  <div className="booking-status complete">Saved</div>
                </div>
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
