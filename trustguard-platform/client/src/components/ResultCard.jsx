export default function ResultCard({ result, type }) {
  if (!result) return null;

  const {
    label,
    confidence,
    metrics,
    explanation,
    riskLevel,
    factCheckStatus,
    factChecks,
    source
  } = result;

  // Custom glows and badges based on results
  const isSafe = label === 'Real' || label === 'Genuine' || label === 'Safe';
  const displayBadgeClass = isSafe ? 'badge-glow-success' : 'badge-glow-danger';
  const displayProgressBarClass = isSafe ? 'progress-bar-success' : 'progress-bar-danger';

  const getSourceLabel = (src) => {
    switch (src) {
      case 'google_fact_check_api':
        return 'Verified Fact Check (Google API)';
      case 'local_ml_model':
        return 'Local ML Model Prediction';
      case 'fallback_heuristic':
        return 'Demo Mode (Keyword Heuristic)';
      default:
        return 'Analysis Source';
    }
  };

  return (
    <div className="glass-card tilt-card p-4 mt-4 border-0 shadow-lg">
      {/* Header section */}
      <div className="d-flex justify-content-between align-items-center mb-3">
        <div>
          <h3 className="m-0 fs-5 text-secondary fw-semibold uppercase tracking-wider text-xs">
            Analysis Report
          </h3>
          {type === 'news' && source && (
            <span className="text-secondary opacity-75" style={{ fontSize: '0.8rem' }}>
              Source: <strong className="text-white">{getSourceLabel(source)}</strong>
            </span>
          )}
        </div>
        <span className={`badge px-3 py-2 fs-6 rounded-pill ${displayBadgeClass}`}>
          {label}
        </span>
      </div>

      {/* Heuristic warning banner */}
      {type === 'news' && source === 'fallback_heuristic' && (
        <div className="alert alert-warning border-0 badge-glow-warning bg-opacity-10 py-2 px-3 mb-4 rounded-3 text-warning" style={{ fontSize: '0.85rem' }}>
          <i className="bi bi-exclamation-triangle-fill me-2"></i>
          <strong>Demo Mode:</strong> The ML microservice is offline. Running on local keyword heuristics.
        </div>
      )}

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

      {/* News-Specific Fact Check Evidence Section */}
      {type === 'news' && (
        <>
          {factCheckStatus === 'match_found' && factChecks && factChecks.length > 0 && (
            <div className="mb-4 border-top border-light-subtle pt-4">
              <h4 className="fs-6 text-white mb-3 fw-bold">
                <i className="bi bi-shield-check me-2 text-info"></i>
                Fact-Check Evidence ({factChecks.length} Matches)
              </h4>
              <div className="d-flex flex-column gap-3">
                {factChecks.map((fc, index) => (
                  <div key={index} className="p-3 rounded border border-light-subtle bg-dark bg-opacity-25">
                    <div className="d-flex justify-content-between align-items-start gap-2 mb-2">
                      <span className="badge bg-secondary rounded-pill text-xs">{fc.publisher}</span>
                      <span className={`badge ${
                        /\b(false|fake|incorrect|misleading|debunked|pants on fire|myth|untrue|inaccurate)\b/i.test(fc.rating) ? 'badge-glow-danger' : 'badge-glow-success'
                      } rounded-pill text-xs`}>
                        {fc.rating}
                      </span>
                    </div>
                    <p className="text-secondary small mb-2" style={{ fontStyle: 'italic' }}>
                      "{fc.claimText}"
                    </p>
                    {fc.reviewUrl && (
                      <a
                        href={fc.reviewUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="btn btn-link p-0 text-info small d-inline-flex align-items-center gap-1"
                        style={{ textDecoration: 'none', fontSize: '0.85rem' }}
                      >
                        <i className="bi bi-box-arrow-up-right"></i> Read publisher's review
                      </a>
                    )}
                    {fc.reviewDate && (
                      <div className="text-muted text-end" style={{ fontSize: '0.75rem' }}>
                        Reviewed: {new Date(fc.reviewDate).toLocaleDateString()}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {factCheckStatus === 'no_match' && (
            <div className="alert alert-secondary border-0 bg-dark bg-opacity-25 py-2 px-3 mb-4 rounded-3 text-secondary" style={{ fontSize: '0.85rem' }}>
              <i className="bi bi-search me-2"></i>
              No matching published fact check was found.
            </div>
          )}

          {factCheckStatus === 'unavailable' && (
            <div className="alert alert-secondary border-0 bg-dark bg-opacity-25 py-2 px-3 mb-4 rounded-3 text-secondary" style={{ fontSize: '0.85rem' }}>
              <i className="bi bi-cloud-slash me-2"></i>
              Fact check query unavailable (API key not configured or service error).
            </div>
          )}
        </>
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
                  <span>Local ML Prediction (Fake News Probability)</span>
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
