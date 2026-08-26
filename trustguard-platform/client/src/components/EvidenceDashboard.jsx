// Renders the Phase II fields (claim, temporal, pythonSynthesis,
// relatedEvidence) that main.py now adds to /analyze/news responses.
// Every field here is OPTIONAL — a Node gateway or ML service running
// only Phase I, or ENABLE_WEB_SEARCH_VERIFICATION=false, will simply
// omit these keys, and every section below no-ops cleanly in that case.
// This intentionally does not touch ResultCard.jsx or the existing
// Model Poll section in App.jsx — it's an additional panel, not a
// replacement.

function Badge({ children, tone = 'neutral' }) {
  const palette = {
    success: { color: 'var(--success)', bg: 'var(--success-glow)', border: 'color-mix(in srgb, var(--success) 35%, transparent)' },
    danger: { color: 'var(--danger)', bg: 'var(--danger-glow)', border: 'color-mix(in srgb, var(--danger) 35%, transparent)' },
    warning: { color: 'var(--warning)', bg: 'var(--warning-glow)', border: 'color-mix(in srgb, var(--warning) 35%, transparent)' },
    info: { color: 'var(--accent-cyan)', bg: 'var(--accent-cyan-soft)', border: 'var(--accent-cyan-border)' },
    neutral: { color: 'var(--text-secondary)', bg: 'var(--bg-elevated)', border: 'var(--border-color)' },
  };
  const p = palette[tone] || palette.neutral;
  return (
    <span
      className="d-inline-flex align-items-center gap-1 rounded-pill px-2 py-1 small fw-semibold"
      style={{ color: p.color, background: p.bg, border: `1px solid ${p.border}`, lineHeight: 1 }}
    >
      {children}
    </span>
  );
}

function Panel({ title, icon, children }) {
  return (
    <section
      className="glass-card mb-3"

      style={{ background: 'var(--bg-card)', border: '1px solid var(--border-color)', borderRadius: 16 }}
    >
      <div className="p-3 p-md-4">
        <h5 className="fw-semibold mb-3 d-flex align-items-center gap-2" style={{ color: 'var(--text-primary)', fontSize: '1rem' }}>
          {icon && <i className={`bi ${icon}`} style={{ color: 'var(--accent-cyan)' }} />}
          {title}
        </h5>
        {children}
      </div>
    </section>
  );
}

// §25 CLAIM CARD — entities are heuristic when spaCy isn't installed
// (see claim_service.py); shown as-is, not overstated.
function ClaimCard({ claim }) {
  if (!claim) return null;
  const { entities, clickbait, has_explicit_time_reference: hasTimeRef } = claim;
  const groups = [
    ['People', entities?.people],
    ['Organizations', entities?.organizations],
    ['Locations', entities?.locations],
    ['Dates', entities?.dates],
    ['Money', entities?.money],
    ['Percentages', entities?.percentages],
    ['Other terms', entities?.misc],
  ].filter(([, values]) => Array.isArray(values) && values.length > 0);

  return (
    <Panel title="Detected Claim" icon="bi-quote">
      <p className="mb-3" style={{ color: 'var(--text-secondary)', fontStyle: 'italic' }}>
        "{claim.raw_text}"

      </p>

      {groups.length > 0 ? (
        <div className="d-flex flex-column gap-2 mb-3">
          {groups.map(([label, values]) => (
            <div key={label} className="d-flex flex-wrap align-items-center gap-2">
              <span className="small fw-semibold" style={{ color: 'var(--text-muted)', minWidth: 100 }}>
                {label}
              </span>
              {values.map((v, i) => (
                <Badge key={`${label}-${i}`} tone="info">{v}</Badge>
              ))}
            </div>
          ))}
        </div>
      ) : (
        <p className="small mb-3" style={{ color: 'var(--text-muted)' }}>
          No named entities were detected in this content.
        </p>
      )}

      <div className="d-flex flex-wrap gap-2 pt-2" style={{ borderTop: '1px solid var(--border-color)' }}>
        <Badge tone={hasTimeRef ? 'info' : 'neutral'}>
          {hasTimeRef ? 'Contains dated references' : 'No explicit dates found'}
        </Badge>
        {clickbait && (
          <Badge tone={clickbait.score >= 60 ? 'warning' : 'neutral'}>
            Headline sensationalism: {clickbait.score}/100
          </Badge>
        )}
      </div>
    </Panel>

  );
}

// §29 TIMELINE-lite / §5 CURRENTNESS — status text always accompanies
// color (accessibility requirement §44: never color-only).
const TEMPORAL_TONE = {
  CURRENT: 'success',
  RECENT: 'success',
  UPDATED: 'info',
  OLD: 'warning',
  MISLEADINGLY_PRESENTED: 'danger',
  NO_RECENT_CONFIRMATION: 'neutral',
  UNKNOWN: 'neutral',
};

const TEMPORAL_LABEL = {
  CURRENT: 'Current',
  RECENT: 'Recent',
  UPDATED: 'Updated / Reconfirmed',
  OLD: 'Old',
  MISLEADINGLY_PRESENTED: 'Misleadingly presented as current',
  NO_RECENT_CONFIRMATION: 'No recent confirmation found',
  UNKNOWN: 'Currentness unclear',
};

function TemporalCard({ temporal }) {
  if (!temporal) return null;
  const tone = TEMPORAL_TONE[temporal.status] || 'neutral';
  const label = TEMPORAL_LABEL[temporal.status] || temporal.status;

  return (
    <Panel title="Currentness" icon="bi-clock-history">

      <div className="d-flex align-items-center gap-2 mb-3">
        <Badge tone={tone}>{label}</Badge>
        {temporal.confidence === 'heuristic' && (
          <span className="small" style={{ color: 'var(--text-muted)' }}>
            (text-level heuristic, not cross-source confirmed)
          </span>
        )}
      </div>

      {Array.isArray(temporal.reasoning) && temporal.reasoning.length > 0 && (
        <ul className="mb-0 ps-3" style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
          {temporal.reasoning.map((line, i) => (
            <li key={i} className="mb-1">{line}</li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

// §46 FINAL VERDICT — explicitly separate from the raw ML poll, with
// its own "why" list, per §30's requirement that this be MORE
// prominent than the raw model vote, not less.
function SynthesisCard({ synthesis }) {
  if (!synthesis) return null;
  const isPositive = ['LIKELY TRUE', 'MOSTLY TRUE'].includes(synthesis.classification);
  const isNegative = ['LIKELY FALSE', 'FALSE'].includes(synthesis.classification);
  const tone = isPositive ? 'success' : isNegative ? 'danger' : 'warning';

  return (
    <Panel title="Evidence-Based Assessment" icon="bi-clipboard-check">
      <div className="d-flex flex-wrap align-items-center gap-3 mb-3">

        <Badge tone={tone}>{synthesis.classification}</Badge>
        <span style={{ color: 'var(--text-secondary)' }}>
          Confidence: <strong style={{ color: 'var(--text-primary)' }}>{synthesis.confidence}%</strong>
        </span>
        <Badge tone="neutral">
          {synthesis.basis === 'python_plus_gemini' ? 'ML + web verification' : 'ML + heuristics only'}
        </Badge>
      </div>

      {Array.isArray(synthesis.reasoning) && synthesis.reasoning.length > 0 && (
        <div className="mb-2">
          <div className="small fw-semibold mb-1" style={{ color: 'var(--text-muted)' }}>WHY THIS RESULT?</div>
          <ul className="mb-0 ps-3" style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
            {synthesis.reasoning.map((line, i) => (
              <li key={i} className="mb-1">{line}</li>
            ))}
          </ul>
        </div>
      )}

      {Array.isArray(synthesis.caveats) && synthesis.caveats.length > 0 && (
        <div
          className="mt-3 p-2 rounded small"
          style={{ background: 'var(--warning-glow)', color: 'var(--text-secondary)', border: '1px solid color-mix(in srgb, var(--warning) 30%, transparent)' }}
        >
          {synthesis.caveats.map((line, i) => (
            <div key={i} className="d-flex gap-2">
              <i className="bi bi-exclamation-triangle" style={{ color: 'var(--warning)' }} />
              <span>{line}</span>
            </div>
          ))}
        </div>

      )}
    </Panel>
  );
}

// §27 RELATED ARTICLES + §11 SOURCE CLUSTERS. Note the wording here is
// deliberately "same label as this analysis" / "different label" —
// NOT "supports" / "contradicts". See the articleLabelAgreement
// comment in main.py: real semantic entailment isn't built yet, and
// mislabeling this would overstate what the system actually checked.
const AGREEMENT_LABEL = {
  MATCHES_PRIMARY: 'Same label as this analysis',
  DIFFERS_FROM_PRIMARY: 'Different label from this analysis',
  INSUFFICIENT: 'Insufficient signal',
};

const AGREEMENT_TONE = {
  MATCHES_PRIMARY: 'success',
  DIFFERS_FROM_PRIMARY: 'warning',
  INSUFFICIENT: 'neutral',
};

function RelatedEvidencePanel({ evidence }) {
  if (!evidence) return null;

  if (evidence.enabled === false) {
    return (
      <Panel title="Related Coverage" icon="bi-globe2">
        <p className="small mb-0" style={{ color: 'var(--text-muted)' }}>
          Web-based related-article search is not enabled for this deployment
          (<code>ENABLE_WEB_SEARCH_VERIFICATION=false</code>).
        </p>

      </Panel>
    );
  }

  if (evidence.error) {
    return (
      <Panel title="Related Coverage" icon="bi-globe2">
        <p className="small mb-0" style={{ color: 'var(--warning)' }}>
          <i className="bi bi-exclamation-triangle me-1" />
          Related-article search failed: {evidence.error}
        </p>
      </Panel>
    );
  }

  const { summary, clusters = [], articles = [] } = evidence;

  return (
    <Panel title="Related Coverage" icon="bi-globe2">
      {summary && (
        <div className="d-flex flex-wrap gap-3 mb-3 pb-3" style={{ borderBottom: '1px solid var(--border-color)' }}>
          <StatBlock label="Articles found" value={evidence.articlesFound ?? articles.length} />
          <StatBlock label="Successfully analyzed" value={evidence.articlesExtracted ?? articles.length} />
          <StatBlock label="Independent source clusters" value={summary.independentClusters} highlight />
        </div>
      )}

      {clusters.length === 0 && (
        <p className="small mb-0" style={{ color: 'var(--text-muted)' }}>
          No related articles could be retrieved for this claim.
        </p>
      )}


      <div className="d-flex flex-column gap-2">
        {clusters.map((cluster) => {
          const clusterArticles = articles.filter((a) => cluster.articleIds.includes(a.id));
          return (
            <div
              key={cluster.clusterId}
              className="p-3 rounded"
              style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border-color)' }}
            >
              <div className="d-flex flex-wrap align-items-center justify-content-between gap-2 mb-2">
                <span className="fw-semibold small" style={{ color: 'var(--text-primary)' }}>
                  {cluster.representativeTitle || 'Untitled cluster'}
                </span>
                <Badge tone={cluster.domainCount > 1 ? 'info' : 'neutral'}>
                  {cluster.domainCount} independent domain{cluster.domainCount === 1 ? '' : 's'}
                </Badge>
              </div>

              <div className="d-flex flex-column gap-2">
                {clusterArticles.map((article) => (
                  <a
                    key={article.id}
                    href={article.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="d-flex align-items-start justify-content-between gap-2 text-decoration-none small"
                    style={{ color: 'var(--text-secondary)' }}
                  >
                    <span className="text-truncate">{article.domain}</span>
                    {article.articleLabelAgreement && (
                      <Badge tone={AGREEMENT_TONE[article.articleLabelAgreement] || 'neutral'}>

                        {AGREEMENT_LABEL[article.articleLabelAgreement] || article.articleLabelAgreement}
                      </Badge>
                    )}
                  </a>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </Panel>
  );
}

function StatBlock({ label, value, highlight = false }) {
  return (
    <div>
      <div className="small" style={{ color: 'var(--text-muted)' }}>{label}</div>
      <div className="fw-bold fs-5" style={{ color: highlight ? 'var(--accent-cyan)' : 'var(--text-primary)' }}>
        {value ?? '—'}
      </div>
    </div>
  );
}

export default function EvidenceDashboard({ result }) {
  if (!result) return null;

  const { claim, temporal, pythonSynthesis, relatedEvidence } = result;

  // Nothing to show at all — e.g. a Node gateway still on Phase I.
  if (!claim && !temporal && !pythonSynthesis && !relatedEvidence) return null;


  return (
    <div className="mb-2">
      <SynthesisCard synthesis={pythonSynthesis} />
      <div className="row g-3 mb-1">
        <div className="col-md-6">
          <ClaimCard claim={claim} />
        </div>
        <div className="col-md-6">
          <TemporalCard temporal={temporal} />
        </div>
      </div>
      <RelatedEvidencePanel evidence={relatedEvidence} />
    </div>
  );
}