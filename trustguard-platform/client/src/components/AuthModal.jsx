import { useEffect, useState } from 'react';

export default function AuthModal({ mode = 'login', onClose, onAuthenticated }) {
  const [activeMode, setActiveMode] = useState(mode);
  const [form, setForm] = useState({ name: '', email: '', password: '' });
  const [error, setError] = useState('');

  useEffect(() => {
    setActiveMode(mode);
  }, [mode]);

  useEffect(() => {
    const handleKey = (e) => {
      if (e.key === 'Escape') onClose?.();
    };
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [onClose]);

  const update = (field) => (e) => setForm((prev) => ({ ...prev, [field]: e.target.value }));

  const handleSubmit = (e) => {
    e.preventDefault();
    setError('');

    if (activeMode === 'signup' && !form.name.trim()) {
      setError('Enter your name to create an account.');
      return;
    }
    if (!form.email.trim() || !form.email.includes('@')) {
      setError('Enter a valid email address.');
      return;
    }
    if (form.password.length < 6) {
      setError('Password must be at least 6 characters.');
      return;
    }

    onAuthenticated?.({
      name: form.name.trim() || form.email.split('@')[0],
      email: form.email.trim(),
    });
  };

  return (
    <div
      className="tg-modal-overlay"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose?.();
      }}
    >
      <div className="tg-modal-panel" role="dialog" aria-modal="true" aria-label="Authentication">
        <div className="d-flex justify-content-between align-items-start mb-3">
          <div>
            <h2 className="fs-5 fw-bold mb-1">
              {activeMode === 'login' ? 'Welcome back' : 'Create your account'}
            </h2>
            <p className="mb-0 small" style={{ color: 'var(--text-muted)' }}>
              {activeMode === 'login'
                ? 'Log in to save your analysis history.'
                : 'Sign up to track scans and set preferences.'}
            </p>
          </div>
          <button type="button" className="tg-modal-close" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>

        <div className="tg-auth-switch mb-4">
          <button
            type="button"
            className={activeMode === 'login' ? 'active' : ''}
            onClick={() => setActiveMode('login')}
          >
            Log in
          </button>
          <button
            type="button"
            className={activeMode === 'signup' ? 'active' : ''}
            onClick={() => setActiveMode('signup')}
          >
            Sign up
          </button>
        </div>

        <form onSubmit={handleSubmit} className="d-flex flex-column gap-3">
          {activeMode === 'signup' && (
            <div>
              <label htmlFor="auth-name" className="form-label small fw-semibold mb-1">
                Full name
              </label>
              <input
                id="auth-name"
                type="text"
                className="form-control form-control-custom"
                placeholder="Jordan Rivera"
                value={form.name}
                onChange={update('name')}
                autoComplete="name"
              />
            </div>
          )}

          <div>
            <label htmlFor="auth-email" className="form-label small fw-semibold mb-1">
              Email
            </label>
            <input
              id="auth-email"
              type="email"
              className="form-control form-control-custom"
              placeholder="you@example.com"
              value={form.email}
              onChange={update('email')}
              autoComplete="email"
            />
          </div>

          <div>
            <label htmlFor="auth-password" className="form-label small fw-semibold mb-1">
              Password
            </label>
            <input
              id="auth-password"
              type="password"
              className="form-control form-control-custom"
              placeholder="••••••••"
              value={form.password}
              onChange={update('password')}
              autoComplete={activeMode === 'login' ? 'current-password' : 'new-password'}
            />
          </div>

          {error && (
            <div className="small" style={{ color: 'var(--danger)' }}>
              {error}
            </div>
          )}

          <button type="submit" className="btn btn-cyber w-100 justify-content-center mt-1">
            {activeMode === 'login' ? 'Log in' : 'Create account'}
          </button>

          <p className="text-center small mb-0" style={{ color: 'var(--text-muted)' }}>
            {activeMode === 'login' ? (
              <>
                New here?{' '}
                <button
                  type="button"
                  className="btn btn-link btn-sm p-0 align-baseline"
                  style={{ color: 'var(--accent-cyan)' }}
                  onClick={() => setActiveMode('signup')}
                >
                  Create an account
                </button>
              </>
            ) : (
              <>
                Already have an account?{' '}
                <button
                  type="button"
                  className="btn btn-link btn-sm p-0 align-baseline"
                  style={{ color: 'var(--accent-cyan)' }}
                  onClick={() => setActiveMode('login')}
                >
                  Log in
                </button>
              </>
            )}
          </p>
        </form>
      </div>
    </div>
  );
}
