export default function ResultCard({ result, type }) {
  if (!result) return null;

  const { label, confidence, metrics, explanation, riskLevel } = result;

  // Custom glows and badges based on results
  const isSafe = label === 'Real' || label === 'Genuine' || label === 'Safe';
  const displayBadgeClass = isSafe ? 'badge-glow-success' : 'badge-glow-danger';
  const displayProgressBarClass = isSafe ? 'progress-bar-success' : 'progress-bar-danger';

  const panelStyle = {
    background: 'var(--bg-elevated)',
    border: '1px solid var(--border-color)',
  };

  return (
    <div className="glass-card result-reveal p-4 mt-4 border-0 shadow-lg" style={{ background: 'var(--bg-card)' }}>
      {/* Header section */}
      <div className="d-flex justify-content-between align-items-center mb-3">
        <h3
          className="m-0 fs-5 fw-semibold text-uppercase"
          style={{ color: 'var(--text-secondary)', letterSpacing: '0.04em', fontSize: '0.8rem' }}
        >
          Analysis Report
        </h3>
        <span className={`badge verdict-mark px-3 py-2 fs-6 rounded-pill ${displayBadgeClass}`}>
          {label}
        </span>
      </div>

      {/* Confidence Score progress */}
      <div className="mb-4">
        <div
          className="d-flex justify-content-between mb-1 small"
          style={{ color: 'var(--text-secondary)' }}
        >
          <span>Confidence Score</span>
          <span className="fw-bold" style={{ color: 'var(--text-primary)' }}>{confidence}%</span>
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

      {/* Explanation text */}
      {explanation && (
        <div
          className="p-3 mb-4 rounded border-start border-3"
          style={{ background: 'var(--bg-elevated)', borderColor: 'var(--border-strong)' }}
        >
          <p className="m-0" style={{ fontSize: '0.92rem', lineHeight: '1.5', color: 'var(--text-secondary)' }}>
            <strong style={{ color: 'var(--text-primary)' }}>Explanation: </strong>
            {explanation}
          </p>
        </div>
      )}

      {/* Metrics Breakdown Grid */}
      <h4 className="fs-6 mb-3 fw-bold" style={{ color: 'var(--text-primary)' }}>
        <i className="bi bi-cpu me-2 text-info"></i>
        Technical Metrics Breakdown
      </h4>

      <div className="row g-3">
        {type === 'news' && metrics && (
          <>
            <div className="col-md-6">
              <div className="p-3 rounded" style={panelStyle}>
                <div className="d-flex justify-content-between mb-1 small" style={{ color: 'var(--text-secondary)' }}>
                  <span>Linguistic Style Match</span>
                  <span className="fw-bold text-info">{metrics.linguisticStyleMatch}%</span>
                </div>
                <div className="progress progress-custom" style={{ height: '6px' }}>
                  <div
                    className="progress-bar progress-bar-cyan"
                    role="progressbar"
                    style={{ width: `${metrics.linguisticStyleMatch}%` }}
                  ></div>
                </div>
              </div>
            </div>

            <div className="col-md-6">
              <div className="p-3 rounded" style={panelStyle}>
                <div className="d-flex justify-content-between mb-1 small" style={{ color: 'var(--text-secondary)' }}>
                  <span>AI Generation Likelihood</span>
                  <span className="fw-bold" style={{ color: 'var(--warning)' }}>{metrics.aiTextProbability}%</span>
                </div>
                <div className="progress progress-custom" style={{ height: '6px' }}>
                  <div
                    className="progress-bar progress-bar-warning"
                    role="progressbar"
                    style={{ width: `${metrics.aiTextProbability}%` }}
                  ></div>
                </div>
              </div>
            </div>
          </>
        )}

        {type === 'review' && metrics && (
          <>
            <div className="col-md-6">
              <div className="p-3 rounded" style={panelStyle}>
                <div className="d-flex justify-content-between mb-1 small" style={{ color: 'var(--text-secondary)' }}>
                  <span>Spam Pattern Score</span>
                  <span
                    className="fw-bold"
                    style={{ color: metrics.spamScore > 50 ? 'var(--danger)' : 'var(--success)' }}
                  >
                    {metrics.spamScore}%
                  </span>
                </div>
                <div className="progress progress-custom" style={{ height: '6px' }}>
                  <div
                    className={`progress-bar ${metrics.spamScore > 50 ? 'progress-bar-danger' : 'progress-bar-success'}`}
                    role="progressbar"
                    style={{ width: `${metrics.spamScore}%` }}
                  ></div>
                </div>
              </div>
            </div>

            <div className="col-md-6">
              <div
                className="p-3 rounded d-flex align-items-center justify-content-between h-100"
                style={panelStyle}
              >
                <span className="small" style={{ color: 'var(--text-secondary)' }}>Readability Index</span>
                <span
                  className="badge p-2"
                  style={{ background: 'var(--bg-card-solid)', color: 'var(--text-primary)', border: '1px solid var(--border-color)' }}
                >
                  {metrics.readabilityIndex || 'N/A'} (Flesch-Kincaid)
                </span>
              </div>
            </div>
          </>
        )}

        {type === 'phishing' && metrics && (
          <>
            <div className="col-md-6 col-lg-3">
              <div className="p-3 rounded text-center" style={panelStyle}>
                <div className="small mb-1" style={{ color: 'var(--text-secondary)' }}>Threat Risk Level</div>
                <span className={`badge ${
                  riskLevel === 'High' ? 'badge-glow-danger' : riskLevel === 'Medium' ? 'badge-glow-warning' : 'badge-glow-success'
                } px-2 py-1`}>
                  {riskLevel} Risk
                </span>
              </div>
            </div>

            <div className="col-md-6 col-lg-3">
              <div className="p-3 rounded text-center" style={panelStyle}>
                <div className="small mb-1" style={{ color: 'var(--text-secondary)' }}>SSL Certificate</div>
                <div className="fw-bold" style={{ fontSize: '0.9rem' }}>
                  {metrics.sslValid ? (
                    <span style={{ color: 'var(--success)' }}><i className="bi bi-shield-fill-check me-1"></i>Secure HTTPS</span>
                  ) : (
                    <span style={{ color: 'var(--danger)' }}><i className="bi bi-shield-fill-x me-1"></i>Insecure HTTP</span>
                  )}
                </div>
              </div>
            </div>

            <div className="col-md-6 col-lg-3">
              <div className="p-3 rounded text-center" style={panelStyle}>
                <div className="small mb-1" style={{ color: 'var(--text-secondary)' }}>Domain Age</div>
                <div className="fw-bold small" style={{ fontSize: '0.85rem', color: 'var(--text-primary)' }}>
                  {metrics.domainAge}
                </div>
              </div>
            </div>

            <div className="col-md-6 col-lg-3">
              <div className="p-3 rounded text-center" style={panelStyle}>
                <div className="small mb-1" style={{ color: 'var(--text-secondary)' }}>TLD Trust Rating</div>
                <div className="fw-bold">
                  <span
                    style={{
                      color:
                        metrics.tldTrust === 'High'
                          ? 'var(--success)'
                          : metrics.tldTrust === 'Medium'
                            ? 'var(--warning)'
                            : 'var(--danger)',
                    }}
                  >
                    {metrics.tldTrust}
                  </span>
                </div>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
