import { useEffect, useState } from 'react';
import { useAuth } from '../context/AuthContext';

const TYPE_ICON = {
  news: 'bi-newspaper',
  review: 'bi-star',
  review_page: 'bi-star-half',
  phishing: 'bi-shield-lock',
};

const TYPE_LABEL = {
  news: 'News',
  review: 'Review',
  review_page: 'Review Page',
  phishing: 'Phishing URL',
};

function toneFor(label) {
  const v = String(label || '').toLowerCase();
  if (v.includes('fake') || v.includes('phishing')) return '#fb7185';
  if (v.includes('real') || v.includes('genuine') || v.includes('safe')) return '#4ade80';
  return '#22d3ee';
}

export default function HistoryPanel({ onClose }) {
  const { fetchHistory, isAuthenticated } = useAuth();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let mounted = true;
    if (!isAuthenticated) {
      setLoading(false);
      return () => {};
    }
    fetchHistory()
      .then((rows) => mounted && setItems(rows))
      .catch((err) => mounted && setError(err.message || 'Could not load history.'))
      .finally(() => mounted && setLoading(false));
    return () => {
      mounted = false;
    };
  }, [fetchHistory, isAuthenticated]);

  return (
    <div
      className="position-fixed top-0 end-0 h-100 glass-card rounded-0"
      style={{ width: 'min(420px, 100vw)', zIndex: 1040, overflowY: 'auto' }}
    >
      <div className="p-4">
        <div className="d-flex justify-content-between align-items-center mb-3">
          <h5 className="text-white fw-bold m-0">
            <i className="bi bi-clock-history me-2 text-info" />
            Your History
          </h5>
          <button type="button" className="btn-close btn-close-white" onClick={onClose} aria-label="Close" />
        </div>

        {!isAuthenticated && (
          <p className="text-secondary small">Log in to see your saved analysis history.</p>
        )}

        {isAuthenticated && loading && (
          <div className="d-flex align-items-center gap-2 text-secondary small">
            <span className="spinner-border spinner-border-sm" role="status" aria-hidden="true" />
            Loading history...
          </div>
        )}

        {error && <p className="text-danger small">{error}</p>}

        {isAuthenticated && !loading && items.length === 0 && !error && (
          <p className="text-secondary small">No analyses yet — run a check to see it here.</p>
        )}

        <div className="d-flex flex-column gap-2">
          {items.map((item) => (
            <div
              key={item.id}
              className="p-3 rounded-3"
              style={{ background: 'rgba(255,255,255,.03)', border: '1px solid rgba(255,255,255,.08)' }}
            >
              <div className="d-flex justify-content-between align-items-start gap-2">
                <div className="d-flex align-items-center gap-2 text-secondary small">
                  <i className={`bi ${TYPE_ICON[item.type] || 'bi-file-earmark'}`} />
                  {TYPE_LABEL[item.type] || item.type}
                </div>
                <span className="small fw-semibold" style={{ color: toneFor(item.result_label) }}>
                  {item.result_label || 'Unknown'}
                </span>
              </div>
              <div className="text-white small mt-2 text-truncate" title={item.input_summary}>
                {item.input_summary || '(no summary)'}
              </div>
              <div className="text-muted small mt-1">
                {item.confidence != null ? `${item.confidence}% confidence · ` : ''}
                {new Date(item.created_at).toLocaleString()}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
