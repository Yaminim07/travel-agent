import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
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

  const handlePasswordLogin = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLoading(true);
    setError('');

    const formData = new FormData(event.currentTarget);
    try {
      const response = await fetch(`${API_BASE_URL}/auth/login/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: formData.get('email'),
          password: formData.get('password'),
        }),
      });
      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || 'Unable to sign in with those credentials.');
      }

      localStorage.setItem('accessToken', data.access);
      localStorage.setItem('refreshToken', data.refresh);
      localStorage.setItem('userEmail', data.user.email);
      navigate('/dashboard');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to sign in right now.');
    } finally {
      setLoading(false);
    }
  };

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
            <div className="form-label">Welcome back</div>
            <h2>Sign in</h2>
            <p className="subtle-text">
              Sign in to access your trips, bookings, and travel insights.
            </p>

            {error ? <div className="auth-message error-message" role="alert">{error}</div> : null}

            <form className="signup-form login-auth-form" onSubmit={handlePasswordLogin}>
              <label className="signup-field">
                <span>Email address</span>
                <input className="form-input" type="email" name="email" autoComplete="email" required />
              </label>
              <label className="signup-field">
                <span>Password</span>
                <input className="form-input" type="password" name="password" autoComplete="current-password" required />
              </label>
              <div className="login-auth-footer">
                <Link to="/reset-password">Forgot password?</Link>
              </div>
              <button className="primary-btn signup-submit" type="submit" disabled={loading}>
                {loading ? 'Signing in…' : 'Sign in'}
              </button>
            </form>

            <div className="divider-row">
              <span />
              <small>or continue with Google</small>
              <span />
            </div>

            <Button
              className="google-btn"
              radius={18}
              size="md"
              loading={loading}
              onClick={handleGoogleLogin}
              leftSection={<span aria-hidden="true">G</span>}
            >
              Continue with Google
            </Button>

            <p className="sign-up-link">
              New to Travel Agent? <Link to="/signup">Create an account</Link>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
