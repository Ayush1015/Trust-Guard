import { useState } from 'react';
import { useAuth } from '../context/AuthContext';

export default function AuthModal({ onClose }) {
  const { login, signup } = useAuth();
  const [mode, setMode] = useState('login'); // 'login' | 'signup'
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');

    if (!email.trim() || !password) {
      setError('Email and password are required.');
      return;
    }
    if (mode === 'signup' && password.length < 8) {
      setError('Password must be at least 8 characters.');
      return;
    }

    setSubmitting(true);
    try {
      if (mode === 'signup') {
        await signup(email.trim(), password);
      } else {
        await login(email.trim(), password);
      }
      onClose?.();
    } catch (err) {
      setError(err.message || 'Something went wrong.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      className="position-fixed top-0 start-0 w-100 h-100 d-flex align-items-center justify-content-center"
      style={{ background: 'rgba(3,8,16,.75)', zIndex: 1050 }}
      onClick={onClose}
    >
      <div
        className="glass-card p-4"
        style={{ width: '100%', maxWidth: 420 }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="d-flex justify-content-between align-items-center mb-3">
          <h4 className="text-white fw-bold m-0">
            {mode === 'login' ? 'Log in' : 'Create your account'}
          </h4>
          <button type="button" className="btn-close btn-close-white" onClick={onClose} aria-label="Close" />
        </div>

        <p className="text-secondary small mb-4">
          Save your analysis history, get your own token quota, and set a default
          translation language.
        </p>

        <form onSubmit={handleSubmit} className="d-flex flex-column gap-3">
          <div>
            <label htmlFor="auth-email" className="form-label text-secondary small fw-semibold">
              Email
            </label>
            <input
              id="auth-email"
              type="email"
              className="form-control form-control-custom"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
              disabled={submitting}
              required
            />
          </div>

          <div>
            <label htmlFor="auth-password" className="form-label text-secondary small fw-semibold">
              Password
            </label>
            <input
              id="auth-password"
              type="password"
              className="form-control form-control-custom"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
              disabled={submitting}
              required
              minLength={mode === 'signup' ? 8 : undefined}
            />
            {mode === 'signup' && (
              <div className="form-text text-muted">At least 8 characters.</div>
            )}
          </div>

          {error && (
            <div className="text-danger small" role="alert">
              <i className="bi bi-exclamation-triangle me-1" />
              {error}
            </div>
          )}

          <button type="submit" className="btn btn-cyber d-flex align-items-center justify-content-center gap-2" disabled={submitting}>
            {submitting ? (
              <>
                <span className="spinner-border spinner-border-sm" role="status" aria-hidden="true" />
                {mode === 'login' ? 'Logging in...' : 'Creating account...'}
              </>
            ) : mode === 'login' ? (
              'Log in'
            ) : (
              'Sign up'
            )}
          </button>
        </form>

        <div className="text-center mt-3">
          <button
            type="button"
            className="btn btn-link btn-sm text-info text-decoration-none"
            onClick={() => {
              setError('');
              setMode((m) => (m === 'login' ? 'signup' : 'login'));
            }}
          >
            {mode === 'login' ? "Don't have an account? Sign up" : 'Already have an account? Log in'}
          </button>
        </div>

        <div className="text-center mt-2">
          <button type="button" className="btn btn-link btn-sm text-secondary text-decoration-none" onClick={onClose}>
            Continue as guest
          </button>
        </div>
      </div>
    </div>
  );
}
