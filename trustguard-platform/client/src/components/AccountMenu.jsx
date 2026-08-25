import { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import AuthModal from './AuthModal';
import HistoryPanel from './HistoryPanel';

export default function AccountMenu() {
  const { user, isAuthenticated, logout } = useAuth();
  const [showAuth, setShowAuth] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  if (!isAuthenticated) {
    return (
      <>
        <button
          type="button"
          className="btn btn-sm btn-outline-info"
          onClick={() => setShowAuth(true)}
        >
          <i className="bi bi-person-circle me-1" />
          Log in
        </button>
        {showAuth && <AuthModal onClose={() => setShowAuth(false)} />}
      </>
    );
  }

  const pct = user.tokenLimit ? Math.min(100, Math.round((user.tokensUsed / user.tokenLimit) * 100)) : 0;

  return (
    <div className="position-relative">
      <button
        type="button"
        className="btn btn-sm btn-outline-light d-flex align-items-center gap-2"
        onClick={() => setMenuOpen((o) => !o)}
      >
        <i className="bi bi-person-check-fill text-info" />
        <span className="d-none d-sm-inline">{user.email}</span>
      </button>

      {menuOpen && (
        <div
          className="glass-card position-absolute end-0 mt-2 p-3"
          style={{ width: 260, zIndex: 1030 }}
        >
          <div className="small text-secondary mb-2">Signed in as</div>
          <div className="text-white fw-semibold text-truncate mb-3">{user.email}</div>

          <div className="mb-3">
            <div className="d-flex justify-content-between small text-secondary mb-1">
              <span>Tokens used</span>
              <span>{user.tokensUsed} / {user.tokenLimit}</span>
            </div>
            <div className="progress progress-custom" style={{ height: 6 }}>
              <div
                className={`progress-bar ${pct > 85 ? 'progress-bar-danger' : 'progress-bar-cyan'}`}
                style={{ width: `${pct}%` }}
              />
            </div>
          </div>

          <button
            type="button"
            className="btn btn-sm btn-outline-info w-100 mb-2"
            onClick={() => {
              setShowHistory(true);
              setMenuOpen(false);
            }}
          >
            <i className="bi bi-clock-history me-1" />
            View history
          </button>

          <button
            type="button"
            className="btn btn-sm btn-outline-danger w-100"
            onClick={() => {
              logout();
              setMenuOpen(false);
            }}
          >
            <i className="bi bi-box-arrow-right me-1" />
            Log out
          </button>
        </div>
      )}

      {showHistory && <HistoryPanel onClose={() => setShowHistory(false)} />}
    </div>
  );
}
