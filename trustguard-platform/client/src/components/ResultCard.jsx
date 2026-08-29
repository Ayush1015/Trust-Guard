export default function ResultCard({ result, type }) {
  if (!result) return null;

  const { label, confidence, metrics, explanation, riskLevel } = result;

  const isSafe = label === 'Real' || label === 'Genuine' || label === 'Safe';
  const displayBadgeClass = isSafe ? 'badge-glow-success' : 'badge-glow-danger';
  const displayProgressBarClass = isSafe ? 'progress-bar-success' : 'progress-bar-danger';

  const weightedShare = result?.poll?.weightedSharePercent || {};
  const hasVoteBreakdown = Object.keys(weightedShare).length > 0;
const UI = {
  cyan: "var(--accent-cyan)",
  cyanSoft: "var(--accent-cyan-soft)",
  cyanBorder: "var(--accent-cyan-border)",
  text: "var(--text-primary)",
  muted: "var(--text-secondary)",
  subtle: "var(--text-muted)",
  card: "var(--bg-card)",
  cardBorder: "var(--border-color)",
};
  return (
    <div className="glass-card p-4 mt-4 border-0 shadow-lg">
      {/* Header */}
      <div className="d-flex justify-content-between align-items-center mb-3">
        <h3 className="m-0 fs-5 fw-semibold" style={{ color: UI.text }}>
          Analysis Report
        </h3>
        <span className={`badge px-3 py-2 fs-6 rounded-pill ${displayBadgeClass}`}>
          {label}
        </span>
      </div>

      {/* Confidence Score */}
      <div className="mb-4">
        <div className="d-flex justify-content-between mb-1 small text-secondary">
          <span>Confidence Score</span>
          <span className="fw-bold" style={{ color: UI.text }}>
            {confidence}%
          </span>
        </div>
        <div className="progress progress-custom">
          <div
            className={`progress-bar progress-bar-striped progress-bar-animated ${displayProgressBarClass}`}
            role="progressbar"
            style={{ width: `${confidence}%` }}
            aria-valuenow={confidence}
            aria-valuemin="0"
            aria-valuemax="100"
          ></div>
        </div>
      </div>

      {/* Explanation */}
      {explanation && (
        <div className="p-3 mb-4 rounded border-start border-3 border-secondary"
             style={{ background: "var(--card-bg-alt)" }}>
          <p className="m-0 text-secondary" style={{ fontSize: '0.92rem', lineHeight: '1.5' }}>
            <strong style={{ color: UI.text }}>Explanation: </strong>
            {explanation}
          </p>
        </div>
      )}

      {/* Metrics */}
      <h4 className="fs-6 mb-3 fw-bold " style={{ color: UI.text }}>
        <i className="bi bi-cpu me-2 text-info"></i>
        Technical Metrics Breakdown
      </h4>

      <div className="row g-3">
        {type === 'news' && (
          <>
            {hasVoteBreakdown ? (
              Object.entries(weightedShare).map(([voteLabel, percent]) => {
                const isWinner = voteLabel === label;
                return (
                  <div className="col-md-6" key={voteLabel}>
                    <div className="p-3 rounded border" style={{ background: "var(--card-bg-alt)", borderColor: "var(--border-color)" }}>
                      <div className="d-flex justify-content-between mb-1 small text-secondary">
                        <span>{voteLabel} — Weighted Vote Share</span>
                        <span className={`fw-bold ${isWinner ? 'text-info' : 'text-secondary'}`}>
                          {percent}%
                        </span>
                      </div>
                      <div className="progress progress-custom" style={{ height: '6px' }}>
                        <div
                          className={isWinner ? 'progress-bar progress-bar-cyan' : 'progress-bar bg-secondary'}
                          role="progressbar"
                          style={{ width: `${percent}%` }}
                        ></div>
                      </div>
                    </div>
                  </div>
                );
              })
            ) : (
              <div className="col-12">
                <div className="p-3 rounded border text-secondary small"
                     style={{ background: "var(--card-bg-alt)", borderColor: "var(--border-color)" }}>
                  No model breakdown is available for this result yet.
                </div>
              </div>
            )}
          </>
        )}

        {/* Other types (review, phishing) remain similar but swap bg-dark/text-white for theme vars */}
      </div>
    </div>
  );
}
