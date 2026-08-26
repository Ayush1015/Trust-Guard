export default function Navbar({
  theme = 'dark',
  onToggleTheme,
  onOpenAuth,
  isAuthenticated = false,
  user = null,
  onLogout,
  backendStatus = 'checking',
}) {
  const statusColor =
    backendStatus === 'online'
      ? '#4ade80'
      : backendStatus === 'checking'
        ? '#fbbf24'
        : '#fb7185';

  return (
    <nav className="tg-navbar navbar navbar-expand-lg border-0 rounded-0 py-3 mb-4 sticky-top">
      <div className="container d-flex align-items-center flex-wrap gap-3">
        {/* Brand */}
        <div className="d-flex align-items-center gap-2 me-auto">
          <div className="tg-brand-mark" aria-hidden="true">🛡️</div>
          <div>
            <h1 className="navbar-brand m-0 fs-4 fw-bold" style={{ letterSpacing: '-0.02em' }}>
              TrustGuard
            </h1>
            <span
              className="d-none d-md-inline-flex align-items-center gap-2"
              style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}
            >
              <span
                className="rounded-circle pulse-indicator"
                style={{ background: statusColor, color: statusColor, margin: 0, width: 6, height: 6 }}
              />
              AI-Powered Digital Trust & Misinformation Detection
            </span>
          </div>
        </div>

        {/* Right cluster: theme toggle + auth */}
        <div className="d-flex align-items-center gap-3">
          <button
            type="button"
            className="theme-toggle"
            onClick={onToggleTheme}
            role="switch"
            aria-checked={theme === 'light'}
            aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
            title={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
          >
            <span className="theme-toggle-knob">{theme === 'dark' ? '🌙' : '☀️'}</span>
          </button>

          {isAuthenticated ? (
            <div className="d-flex align-items-center gap-2">
              <div
                className="d-none d-sm-flex align-items-center justify-content-center rounded-circle fw-bold"
                style={{
                  width: 34,
                  height: 34,
                  background: 'var(--accent-cyan-soft)',
                  color: 'var(--accent-cyan)',
                  border: '1px solid var(--accent-cyan-border)',
                  fontSize: '0.85rem',
                }}
                title={user?.name || 'Account'}
              >
                {(user?.name || 'U').slice(0, 1).toUpperCase()}
              </div>
              <span className="d-none d-md-inline small fw-semibold" style={{ color: 'var(--text-secondary)' }}>
                {user?.name || 'Account'}
              </span>
              <button type="button" className="btn-ghost" onClick={onLogout}>
                Log out
              </button>
            </div>
          ) : (
            <div className="d-flex align-items-center gap-2">
              <button
                type="button"
                className="btn-ghost"
                onClick={() => onOpenAuth?.('login')}
              >
                Log in
              </button>
              <button
                type="button"
                className="btn btn-cyber py-2 px-3"
                onClick={() => onOpenAuth?.('signup')}
              >
                Sign up
              </button>
            </div>
          )}
        </div>
      </div>
    </nav>
  );
}
