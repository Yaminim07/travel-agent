import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api';

export function SignupPage() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSignup = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLoading(true);
    setError('');

    const formData = new FormData(event.currentTarget);
    try {
      const response = await fetch(`${API_BASE_URL}/auth/signup/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          first_name: formData.get('firstName'),
          last_name: formData.get('lastName'),
          email: formData.get('email'),
          password: formData.get('password'),
        }),
      });
      const data = await response.json();

      if (!response.ok) {
        const validationMessage = Object.values(data).flat().join(' ');
        throw new Error(data.detail || validationMessage || 'Unable to create your account.');
      }

      localStorage.setItem('accessToken', data.access);
      localStorage.setItem('refreshToken', data.refresh);
      localStorage.setItem('userEmail', data.user.email);
      navigate('/dashboard');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to create your account right now.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="login-shell">
      <section className="login-card signup-card">
        <aside className="login-visual sso-visual">
          <div className="brand-row">
            <Link to="/login" className="signup-brand" aria-label="Travel Agent home">
              <span className="brand-mark" aria-hidden="true">T</span>
              <span className="brand-name">Travel Agent</span>
            </Link>
            <span className="scan-pill">AI travel planner</span>
          </div>

          <div className="hero-copy">
            <span className="hero-kicker">Your next chapter</span>
            <h1 className="hero-title">Go places.<br />Feel more.</h1>
            <p className="hero-subtext">
              Make room for the memorable bits. We’ll help you turn your travel ideas into a trip worth taking.
            </p>
          </div>

          <aside className="signup-note">
            <span className="signup-note-icon" aria-hidden="true">✦</span>
            <p><strong>Made for the way you travel</strong><br />Personal plans, all in one place.</p>
          </aside>
        </aside>

        <section className="login-form-panel">
          <div className="login-form-wrap signup-form-wrap">
            <p className="form-label">Join us</p>
            <h2>Create your account</h2>
            <p className="subtle-text">
              Start planning your next adventure. It only takes a minute.
            </p>

            {error ? <div className="auth-message error-message" role="alert">{error}</div> : null}
            <form className="signup-form" onSubmit={handleSignup}>
              <div className="signup-name-fields">
                <label className="signup-field">
                  <span>First name</span>
                  <input className="form-input" type="text" name="firstName" autoComplete="given-name" placeholder="Alex" required />
                </label>
                <label className="signup-field">
                  <span>Last name</span>
                  <input className="form-input" type="text" name="lastName" autoComplete="family-name" placeholder="Morgan" required />
                </label>
              </div>
              <label className="signup-field">
                <span>Email address</span>
                <input className="form-input" type="email" name="email" autoComplete="email" placeholder="you@example.com" required />
              </label>
              <label className="signup-field">
                <span>Password</span>
                <input className="form-input" type="password" name="password" autoComplete="new-password" placeholder="At least 8 characters" minLength={8} required />
              </label>
              <label className="signup-terms">
                <input type="checkbox" name="terms" required />
                <span>I agree to the <a href="#terms">Terms of Service</a> and <a href="#privacy">Privacy Policy</a>.</span>
              </label>
              <button className="primary-btn signup-submit" type="submit" disabled={loading}>
                {loading ? 'Creating account…' : 'Create account'}
              </button>
            </form>

            <p className="signup-login-link">
              Already have an account? <Link to="/login">Sign in</Link>
            </p>
          </div>
        </section>
      </section>
    </main>
  );
}
