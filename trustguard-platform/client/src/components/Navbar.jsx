
export default function Navbar() {
  return (
    <nav className="navbar navbar-expand-lg glass-card border-0 border-bottom rounded-0 py-3 mb-4 sticky-top">
      <div className="container">
        <div className="d-flex align-items-center">
          <span className="fs-3 me-2 logo-shield" role="img" aria-label="shield">🛡️</span>
          <div>
            <h1 className="navbar-brand m-0 sheen-text fs-4 fw-bold tracking-tight">
              TrustGuard
            </h1>
            <span className="text-secondary d-none d-md-inline" style={{ fontSize: '0.85rem' }}>
              AI-Powered Digital Trust & Misinformation Detection System
            </span>
          </div>
        </div>
        <div className="ms-auto d-flex align-items-center">
          <span className="pulse-indicator pulsing-green"></span>
          <span className="text-muted small" style={{color: '#f9f9f9'}}>System Ready</span>
        </div>
      </div>
    </nav>
  );
}
