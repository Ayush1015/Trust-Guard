import React from 'react';

export default function ResultCard({ result, type }) {
  if (!result) return null;

  const { label, confidence, badgeClass, metrics, explanation, riskLevel } = result;

  // Custom glows and badges based on results
  const isSafe = label === 'Real' || label === 'Genuine' || label === 'Safe';
  const displayBadgeClass = isSafe ? 'badge-glow-success' : 'badge-glow-danger';
  const displayProgressBarClass = isSafe ? 'progress-bar-success' : 'progress-bar-danger';

  return (
    <div className="glass-card p-4 mt-4 border-0 shadow-lg">
      {/* Header section */}
      <div className="d-flex justify-content-between align-items-center mb-3">
        <h3 className="m-0 fs-5 text-secondary fw-semibold uppercase tracking-wider text-xs">
          Analysis Report
        </h3>
        <span className={`badge px-3 py-2 fs-6 rounded-pill ${displayBadgeClass}`}>
          {label}
        </span>
      </div>

      {/* Confidence Score progress */}
      <div className="mb-4">
        <div className="d-flex justify-content-between mb-1 small text-secondary">
          <span>Confidence Score</span>
          <span className="fw-bold text-white">{confidence}%</span>
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
        <div className="p-3 mb-4 rounded bg-dark border-start border-3 border-secondary" style={{ backgroundColor: 'rgba(0,0,0,0.2) !important' }}>
          <p className="m-0 text-secondary" style={{ fontSize: '0.92rem', lineHeight: '1.5' }}>
            <strong className="text-white">Explanation: </strong>
            {explanation}
          </p>
        </div>
      )}

      {/* Metrics Breakdown Grid */}
      <h4 className="fs-6 text-white mb-3 fw-bold">
        <i className="bi bi-cpu me-2 text-info"></i>
        Technical Metrics Breakdown
      </h4>
      
      <div className="row g-3">
        {type === 'news' && metrics && (
          <>
            <div className="col-md-6">
              <div className="p-3 rounded border border-light-subtle bg-dark bg-opacity-25">
                <div className="d-flex justify-content-between mb-1 small text-secondary">
                  <span>Linguistic Style Match</span>
                  <span className="text-info fw-bold">{metrics.linguisticStyleMatch}%</span>
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
              <div className="p-3 rounded border border-light-subtle bg-dark bg-opacity-25">
                <div className="d-flex justify-content-between mb-1 small text-secondary">
                  <span>AI Generation Likelihood</span>
                  <span className="text-warning fw-bold">{metrics.aiTextProbability}%</span>
                </div>
                <div className="progress progress-custom" style={{ height: '6px' }}>
                  <div
                    className="progress-bar bg-warning"
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
              <div className="p-3 rounded border border-light-subtle bg-dark bg-opacity-25">
                <div className="d-flex justify-content-between mb-1 small text-secondary">
                  <span>Spam Pattern Score</span>
                  <span className={`${metrics.spamScore > 50 ? 'text-danger' : 'text-success'} fw-bold`}>
                    {metrics.spamScore}%
                  </span>
                </div>
                <div className="progress progress-custom" style={{ height: '6px' }}>
                  <div
                    className={`progress-bar ${metrics.spamScore > 50 ? 'bg-danger' : 'bg-success'}`}
                    role="progressbar"
                    style={{ width: `${metrics.spamScore}%` }}
                  ></div>
                </div>
              </div>
            </div>
            
            <div className="col-md-6">
              <div className="p-3 rounded border border-light-subtle bg-dark bg-opacity-25 d-flex align-items-center justify-content-between h-100">
                <span className="small text-secondary">Readability Index</span>
                <span className="badge bg-secondary p-2">{metrics.readabilityIndex || 'N/A'} (Flesch-Kincaid)</span>
              </div>
            </div>
          </>
        )}

        {type === 'phishing' && metrics && (
          <>
            <div className="col-md-6 col-lg-3">
              <div className="p-3 rounded border border-light-subtle bg-dark bg-opacity-25 text-center">
                <div className="small text-secondary mb-1">Threat Risk Level</div>
                <span className={`badge ${
                  riskLevel === 'High' ? 'badge-glow-danger' : riskLevel === 'Medium' ? 'badge-glow-warning' : 'badge-glow-success'
                } px-2 py-1`}>
                  {riskLevel} Risk
                </span>
              </div>
            </div>

            <div className="col-md-6 col-lg-3">
              <div className="p-3 rounded border border-light-subtle bg-dark bg-opacity-25 text-center">
                <div className="small text-secondary mb-1">SSL Certificate</div>
                <div className="fw-bold" style={{ fontSize: '0.9rem' }}>
                  {metrics.sslValid ? (
                    <span className="text-success"><i className="bi bi-shield-fill-check me-1"></i>Secure HTTPS</span>
                  ) : (
                    <span className="text-danger"><i className="bi bi-shield-fill-x me-1"></i>Insecure HTTP</span>
                  )}
                </div>
              </div>
            </div>

            <div className="col-md-6 col-lg-3">
              <div className="p-3 rounded border border-light-subtle bg-dark bg-opacity-25 text-center">
                <div className="small text-secondary mb-1">Domain Age</div>
                <div className="fw-bold text-white small" style={{ fontSize: '0.85rem' }}>
                  {metrics.domainAge}
                </div>
              </div>
            </div>

            <div className="col-md-6 col-lg-3">
              <div className="p-3 rounded border border-light-subtle bg-dark bg-opacity-25 text-center">
                <div className="small text-secondary mb-1">TLD Trust Rating</div>
                <div className="fw-bold">
                  <span className={`text-${metrics.tldTrust === 'High' ? 'success' : metrics.tldTrust === 'Medium' ? 'warning' : 'danger'}`}>
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
