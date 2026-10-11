import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, Text } from '@mantine/core';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api';

export function LoginPage() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const accessToken = params.get('access');
    const refreshToken = params.get('refresh');
    const email = params.get('email');

    if (accessToken && refreshToken) {
      localStorage.setItem('accessToken', accessToken);
      localStorage.setItem('refreshToken', refreshToken);
      if (email) {
        localStorage.setItem('userEmail', email);
      }

      window.history.replaceState({}, '', '/login');
      navigate('/dashboard');
    }
  }, [navigate]);

  const handleGoogleLogin = async () => {
    setLoading(true);
    setError('');

    try {
      const response = await fetch(`${API_BASE_URL}/auth/google/connect/`);
      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || 'Unable to start Google login.');
      }

      window.location.href = data.auth_url;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Google sign-in is unavailable right now.');
      setLoading(false);
    }
  };

  return (
    <div className="login-shell">
      <div className="login-card sso-card">
        <div className="login-visual sso-visual">
          <div className="brand-row">
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <div className="brand-mark">T</div>
              <div className="brand-name">Travel Agent</div>
            </div>
            <div className="scan-pill">AI travel planner</div>
          </div>

          <div className="hero-copy">
            <div className="hero-kicker">Plan smarter</div>
            <h1 className="hero-title">Travel better. Together.</h1>
            <p className="hero-subtext">
              Discover personalized itineraries, trusted support, and smoother planning for every journey.
            </p>
          </div>

          <div className="mock-travel-card">
            <div className="trip-thumb" />
            <div className="mock-trip-meta">
              <div>
                <strong>Sunset Escape</strong>
                <div style={{ color: '#5e6577', marginTop: 4 }}>Hawaii • 4 days</div>
              </div>
              <span className="mock-tag">Popular</span>
            </div>
          </div>
        </div>

        <div className="login-form-panel">
          <div className="login-form-wrap sso-form-wrap">
            <div className="form-label">Welcome</div>
            <h2>Continue with Google</h2>
            <p className="subtle-text">
              Sign in with your Google account to access your trips, bookings, and travel insights.
            </p>

            {error ? (
              <div style={{ marginTop: 8, color: '#b42318', fontWeight: 600 }}>{error}</div>
            ) : null}

            <Button
              className="google-btn"
              radius={18}
              size="lg"
              loading={loading}
              onClick={handleGoogleLogin}
              leftSection={<span aria-hidden="true">G</span>}
            >
              Continue with Google
            </Button>

            <div className="divider-row">
              <span />
              <small>Secure SSO</small>
              <span />
            </div>

            <Text size="sm" c="dimmed" ta="center">
              We only use Google sign-in to protect your itinerary data and keep your travel plans synced.
            </Text>
          </div>
        </div>
      </div>
    </div>
  );
}
