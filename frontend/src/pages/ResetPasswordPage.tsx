import { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api';

export function ResetPasswordPage({ confirm = false }: { confirm?: boolean }) {
  const location = useLocation();
  const params = new URLSearchParams(location.search);
  const uid = params.get('uid');
  const token = params.get('token');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(!confirm || (uid && token) ? '' : 'This password reset link is invalid or incomplete.');
  const [success, setSuccess] = useState('');

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLoading(true);
    setError('');

    const formData = new FormData(event.currentTarget);
    const payload = confirm
      ? {
          uid,
          token,
          password: formData.get('password'),
          password_confirm: formData.get('passwordConfirm'),
        }
      : { email: formData.get('email') };

    try {
      const response = await fetch(
        `${API_BASE_URL}/auth/password-reset/${confirm ? 'confirm/' : ''}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        },
      );
      const data = await response.json();

      if (!response.ok) {
        const validationMessage = Object.values(data).flat().join(' ');
        throw new Error(data.detail || validationMessage || 'Unable to reset your password.');
      }

      setSuccess(data.detail);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to reset your password right now.');
    } finally {
      setLoading(false);
    }
  };

  const isInvalidLink = confirm && (!uid || !token);

  return (
    <main className="login-shell">
      <section className="login-card signup-card reset-card">
        <aside className="login-visual sso-visual">
          <div className="brand-row">
            <Link to="/login" className="signup-brand" aria-label="Travel Agent home">
              <span className="brand-mark" aria-hidden="true">T</span>
              <span className="brand-name">Travel Agent</span>
            </Link>
            <span className="scan-pill">Account security</span>
          </div>
          <div className="hero-copy">
            <span className="hero-kicker">A fresh start</span>
            <h1 className="hero-title">Back to<br />the journey.</h1>
            <p className="hero-subtext">Reset your password securely and get back to planning.</p>
          </div>
        </aside>

        <section className="login-form-panel">
          <div className="login-form-wrap signup-form-wrap">
            <p className="form-label">{confirm ? 'Choose a new password' : 'Account recovery'}</p>
            <h2>{confirm ? 'Reset password' : 'Forgot your password?'}</h2>
            <p className="subtle-text">
              {confirm
                ? 'Choose a new password for your Travel Agent account.'
                : 'Enter your email and we’ll send you a secure reset link.'}
            </p>

            {error ? <div className="auth-message error-message" role="alert">{error}</div> : null}
            {success ? <div className="auth-message success-message" role="status">{success}</div> : null}

            {success || isInvalidLink ? null : (
              <form className="signup-form" onSubmit={handleSubmit}>
                {confirm ? (
                  <>
                    <label className="signup-field">
                      <span>New password</span>
                      <input className="form-input" type="password" name="password" autoComplete="new-password" minLength={8} required />
                    </label>
                    <label className="signup-field">
                      <span>Confirm new password</span>
                      <input className="form-input" type="password" name="passwordConfirm" autoComplete="new-password" minLength={8} required />
                    </label>
                  </>
                ) : (
                  <label className="signup-field">
                    <span>Email address</span>
                    <input className="form-input" type="email" name="email" autoComplete="email" required />
                  </label>
                )}
                <button className="primary-btn signup-submit" type="submit" disabled={loading}>
                  {loading
                    ? 'Please wait…'
                    : confirm
                      ? 'Set new password'
                      : 'Send reset link'}
                </button>
              </form>
            )}

            <p className="signup-login-link">
              <Link to="/login">Back to sign in</Link>
            </p>
          </div>
        </section>
      </section>
    </main>
  );
}
