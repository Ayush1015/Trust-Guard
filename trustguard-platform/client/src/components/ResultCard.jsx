import { useMemo } from 'react';

/**
 * ResultCard — "Certified Assessment" redesign
 * ------------------------------------------------------------
 * Signature element: a wax-seal style verdict medallion (gold
 * hairline ring + tick marks) standing in for a bank/notary
 * certification stamp — because TrustGuard's job is literally
 * to certify whether something can be trusted.
 *
 * Palette adds one deliberate accent — a champagne/gold hairline
 * — layered on top of the existing obsidian + cyan system, used
 * ONLY for structural framing (rules, seal ring, eyebrow) so it
 * reads as "certified document" rather than "decoration".
 *
 * All new variables fall back gracefully if not defined in your
 * global stylesheet — see the block of --rc-* custom properties
 * set on the root wrapper below.
 */

const UI = {
  text: 'var(--text-primary)',
  muted: 'var(--text-secondary)',
  subtle: 'var(--text-muted)',

  card: 'var(--bg-card)',
  cardBorder: 'var(--border-color)',

  tileBg: 'var(--rc-tile-bg)',
  tileBorder: 'var(--rc-tile-border)',
  chipBg: 'var(--rc-chip-bg)',
  chipBorder: 'var(--rc-chip-border)',
  trackBg: 'var(--rc-track-bg)',

  gold: 'var(--rc-gold)',
  goldSoft: 'var(--rc-gold-soft)',
  goldBorder: 'var(--rc-gold-border)',

  success: 'var(--success, #10b981)',
  successSoft: 'var(--rc-success-soft)',
  successBorder: 'var(--rc-success-border)',

  danger: 'var(--danger, #ef4444)',
  dangerSoft: 'var(--rc-danger-soft)',
  dangerBorder: 'var(--rc-danger-border)',

  warning: 'var(--warning, #f59e0b)',
  warningSoft: 'var(--rc-warning-soft)',
  warningBorder: 'var(--rc-warning-border)',
};

const TYPE_META = {
  news: { icon: 'bi-newspaper', title: 'News Verification', doc: 'Editorial Integrity Report' },
  review: { icon: 'bi-star', title: 'Review Verification', doc: 'Authenticity Assessment' },
  phishing: { icon: 'bi-shield-lock', title: 'Phishing Analysis', doc: 'Domain Risk Certificate' },
};

const GAUGE_GRADIENTS = {
  success: ['#059669', '#4ade80'],
  danger: ['#dc2626', '#fb7185'],
  warning: ['#d97706', '#fbbf24'],
};

function labelTone(label) {
  const value = String(label || '').toLowerCase();
  if (value.includes('fake') || value.includes('phishing') || value.includes('malicious')) return 'danger';
  if (value.includes('real') || value.includes('genuine') || value.includes('safe')) return 'success';
  return 'warning';
}

function toneStyle(tone) {
  const map = {
    success: { color: UI.success, background: UI.successSoft, borderColor: UI.successBorder },
    danger: { color: UI.danger, background: UI.dangerSoft, borderColor: UI.dangerBorder },
    warning: { color: UI.warning, background: UI.warningSoft, borderColor: UI.warningBorder },
  };
  return map[tone] || map.warning;
}

function toneColor(tone) {
  return { success: UI.success, danger: UI.danger, warning: UI.warning }[tone] || UI.warning;
}

function toneIcon(tone) {
  return { success: 'bi-patch-check-fill', danger: 'bi-exclamation-octagon-fill', warning: 'bi-question-diamond-fill' }[tone] || 'bi-question-diamond-fill';
}

// ---------------------------------------------------------------------------
// Small building blocks
// ---------------------------------------------------------------------------

function ToneBadge({ children, tone = 'warning', className = '' }) {
  const style = toneStyle(tone);
  return (
    <span
      className={`badge px-3 py-2 rounded-pill fw-semibold ${className}`}
      style={{ color: style.color, background: style.background, border: `1px solid ${style.borderColor}` }}
    >
      {children}
    </span>
  );
}

function Tile({ children, className = '', hover = true }) {
  return (
    <div
      className={`p-3 rounded h-100 ${hover ? 'rc-tile-hover' : ''} ${className}`}
      style={{ background: UI.tileBg, border: `1px solid ${UI.tileBorder}` }}
    >
      {children}
    </div>
  );
}

function MetricTile({ icon, label, value }) {
  return (
    <Tile>
      <div className="d-flex align-items-center gap-2 small mb-1" style={{ color: UI.muted }}>
        {icon && <i className={`bi ${icon}`} style={{ color: UI.gold }} />}
        {label}
      </div>
      <div className="fw-bold" style={{ color: UI.text, fontSize: '0.95rem' }}>{value ?? 'N/A'}</div>
    </Tile>
  );
}

function ModelChipList({ models }) {
  if (!Array.isArray(models) || models.length === 0) return null;
  return (
    <div className="d-flex flex-wrap gap-2 mt-2">
      {models.map((name) => (
        <span
          key={name}
          className="small px-3 py-1 rounded-pill"
          style={{ color: UI.muted, background: UI.chipBg, border: `1px solid ${UI.chipBorder}` }}
        >
          {name}
        </span>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Certification seal — circular gauge wrapped in a gold hairline + ticks
// ---------------------------------------------------------------------------

function CertificationSeal({ value = 0, tone = 'warning', size = 176, strokeWidth = 12 }) {
  const clamped = Math.max(0, Math.min(100, value ?? 0));
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const dash = (clamped / 100) * circumference;
  const center = size / 2;
  const gradientId = `rc-gauge-gradient-${tone}`;
  const [from, to] = GAUGE_GRADIENTS[tone] || GAUGE_GRADIENTS.warning;

  const outerR = size / 2 - 2;
  const tickR1 = outerR - 3;
  const tickR2 = outerR - 8;
  const ticks = Array.from({ length: 36 }, (_, i) => {
    const angle = (i / 36) * Math.PI * 2;
    const x1 = center + tickR1 * Math.cos(angle);
    const y1 = center + tickR1 * Math.sin(angle);
    const x2 = center + tickR2 * Math.cos(angle);
    const y2 = center + tickR2 * Math.sin(angle);
    return <line key={i} x1={x1} y1={y1} x2={x2} y2={y2} stroke="var(--rc-gold)" strokeWidth="1" opacity="0.55" />;
  });

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`Confidence ${clamped}%`} className="rc-seal">
      <defs>
        <linearGradient id={gradientId} x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor={from} />
          <stop offset="100%" stopColor={to} />
        </linearGradient>
      </defs>

      {/* Outer certification ring + engraved ticks */}
      <circle cx={center} cy={center} r={outerR} fill="none" stroke="var(--rc-gold-border)" strokeWidth="1" />
      {ticks}

      <g transform={`rotate(-90 ${center} ${center})`}>
        <circle cx={center} cy={center} r={radius} fill="none" stroke={UI.trackBg} strokeWidth={strokeWidth} />
        <circle
          cx={center}
          cy={center}
          r={radius}
          fill="none"
          stroke={`url(#${gradientId})`}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={`${dash} ${circumference - dash}`}
          className="rc-gauge-arc"
        />
      </g>

      <text x={center} y={center - 6} textAnchor="middle" fontSize="32" fontWeight="700" fill={UI.text} className="rc-serif">
        {clamped}
      </text>
      <text x={center} y={center + 19} textAnchor="middle" fontSize="10" fill="var(--rc-gold)" letterSpacing="2.5">
        CONFIDENCE
      </text>
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Vote share pie (filled wedges, not a ring — reads as a proper pie chart)
// ---------------------------------------------------------------------------

function polarToCartesian(cx, cy, r, angleDeg) {
  const angleRad = ((angleDeg - 90) * Math.PI) / 180;
  return { x: cx + r * Math.cos(angleRad), y: cy + r * Math.sin(angleRad) };
}

function wedgePath(cx, cy, r, startAngle, endAngle) {
  const start = polarToCartesian(cx, cy, r, endAngle);
  const end = polarToCartesian(cx, cy, r, startAngle);
  const largeArc = endAngle - startAngle > 180 ? 1 : 0;
  return `M ${cx} ${cy} L ${start.x} ${start.y} A ${r} ${r} 0 ${largeArc} 0 ${end.x} ${end.y} Z`;
}

function VotePieChart({ votes, size = 128 }) {
  const entries = useMemo(() => Object.entries(votes || {}).filter(([, count]) => count > 0), [votes]);
  const total = entries.reduce((sum, [, count]) => sum + count, 0);
  const r = size / 2 - 4;
  const cx = size / 2;
  const cy = size / 2;

  if (!total) {
    return (
      <div
        className="d-flex align-items-center justify-content-center small rounded-circle mx-auto"
        style={{ width: size, height: size, border: `1px dashed ${UI.cardBorder}`, color: UI.subtle }}
      >
        No votes yet
      </div>
    );
  }

  let cursor = 0;

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label="Model vote breakdown" className="rc-pie">
      {entries.map(([voteLabel, count]) => {
        const sweep = (count / total) * 360;
        const path = wedgePath(cx, cy, r, cursor, cursor + sweep);
        cursor += sweep;
        return (
          <path key={voteLabel} d={path} fill={toneColor(labelTone(voteLabel))} stroke="var(--bg-primary, #080c14)" strokeWidth="2">
            <title>{`${voteLabel}: ${count} vote${count === 1 ? '' : 's'}`}</title>
          </path>
        );
      })}
      <circle cx={cx} cy={cy} r={r * 0.52} fill="var(--bg-card)" stroke="var(--rc-gold-border)" strokeWidth="1" />
      <text x={cx} y={cy - 1} textAnchor="middle" fontSize="18" fontWeight="700" fill={UI.text}>{total}</text>
      <text x={cx} y={cy + 14} textAnchor="middle" fontSize="8" fill={UI.subtle} letterSpacing="1">
        MODEL{total === 1 ? '' : 'S'}
      </text>
    </svg>
  );
}

function VoteLegend({ votes }) {
  const entries = Object.entries(votes || {}).filter(([, count]) => count > 0);
  const total = entries.reduce((sum, [, count]) => sum + count, 0);
  if (!entries.length) return null;

  return (
    <ul className="list-unstyled mb-0 d-flex flex-column gap-2">
      {entries.map(([voteLabel, count]) => {
        const pct = total ? Math.round((count / total) * 100) : 0;
        return (
          <li key={voteLabel} className="d-flex align-items-center justify-content-between gap-2">
            <span className="d-flex align-items-center gap-2 small" style={{ color: UI.muted }}>
              <span className="rounded-circle flex-shrink-0" style={{ width: 9, height: 9, backgroundColor: toneColor(labelTone(voteLabel)) }} />
              {voteLabel}
            </span>
            <span className="small fw-semibold" style={{ color: UI.text }}>
              {count} <span style={{ color: UI.muted, fontWeight: 400 }}>({pct}%)</span>
            </span>
          </li>
        );
      })}
    </ul>
  );
}

// ---------------------------------------------------------------------------
// Per-model confidence ledger — horizontal percentage bars
// ---------------------------------------------------------------------------

// Track color is intentionally NOT theme-locked: it's a neutral slate
// that reads on both a dark obsidian card and a warm ivory one, so the
// bar never disappears when someone flips the site's light/dark toggle.
const LEDGER_TRACK = 'rgba(148, 163, 184, 0.28)';

function ConfidenceLedger({ models }) {
  const rows = useMemo(() => {
    if (!Array.isArray(models)) return [];
    return [...models]
      .filter((m) => m && m.label)
      .sort((a, b) => (b.confidence ?? -1) - (a.confidence ?? -1));
  }, [models]);

  if (!rows.length) return null;

  return (
    <Tile hover={false}>
      <div className="d-flex align-items-center justify-content-between mb-1">
        <div className="small fw-semibold d-flex align-items-center gap-2" style={{ color: UI.muted }}>
          <i className="bi bi-bar-chart-steps" style={{ color: UI.gold }} />
          Model Confidence Ledger
        </div>
        <span className="small" style={{ color: UI.subtle }}>
          {rows.length} voter{rows.length === 1 ? '' : 's'}
        </span>
      </div>

      <div className="d-flex flex-column">
        {rows.map((m, i) => {
          const tone = labelTone(m.label);
          const toneHex = toneColor(tone);
          const hasScore = m.confidence != null;
          const pct = hasScore ? Math.max(0, Math.min(100, m.confidence)) : null;

          return (
            <div
              key={`${m.model}-${i}`}
              className="py-3 d-flex align-items-center gap-3"
              style={{ borderTop: i === 0 ? 'none' : `1px solid ${UI.tileBorder}` }}
            >
              {/* rank */}
              <span
                className="small text-center flex-shrink-0"
                style={{ color: UI.subtle, width: 18, fontVariantNumeric: 'tabular-nums' }}
              >
                {String(i + 1).padStart(2, '0')}
              </span>

              {/* name + bar */}
              <div className="flex-grow-1 min-w-0">
                <div className="small fw-medium text-truncate mb-1" style={{ color: UI.text }}>
                  {m.model}
                </div>
                <div
                  style={{
                    height: 6,
                    borderRadius: 20,
                    background: LEDGER_TRACK,
                    overflow: 'hidden',
                  }}
                >
                  <div
                    style={{
                      height: '100%',
                      width: `${pct ?? 100}%`,
                      borderRadius: 20,
                      background: hasScore
                        ? `linear-gradient(90deg, ${toneHex}aa, ${toneHex})`
                        : `repeating-linear-gradient(90deg, ${toneHex}55 0 6px, transparent 6px 12px)`,
                      transition: 'width 0.8s cubic-bezier(.4,0,.2,1)',
                    }}
                  />
                </div>
              </div>

              {/* verdict + score */}
              <div className="d-flex align-items-center gap-2 flex-shrink-0">
                <ToneBadge
                  tone={tone}
                  className="py-1 px-2"
                  style={{ fontSize: '0.66rem', textTransform: 'uppercase', letterSpacing: '0.04em' }}
                >
                  {m.label}
                </ToneBadge>
                <span
                  className="small fw-bold text-end"
                  style={{
                    color: hasScore ? toneHex : UI.subtle,
                    minWidth: 52,
                    fontVariantNumeric: 'tabular-nums',
                  }}
                  title={hasScore ? undefined : 'No confidence score reported by this model'}
                >
                  {hasScore ? `${pct.toFixed(2)}%` : 'n/a'}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </Tile>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function ResultCard({ result, type }) {
  if (!result) return null;

  const { label, confidence, metrics, explanation, riskLevel, urlVerification } = result;
  const votes = result.poll?.votes || metrics?.modelVotes || {};
  const tone = labelTone(label);
  const meta = TYPE_META[type] || TYPE_META.news;
  const hasVotes = Object.keys(votes).length > 0;
  const hasLedger = Array.isArray(result.models) && result.models.length > 0;

  const friendlyLabel =
    label === 'Real' ? 'Likely Real'
    : label === 'Fake' ? 'Likely Fake'
    : label === 'Genuine' ? 'Likely Genuine'
    : label === 'Safe' ? 'Looks Safe'
    : label === 'Phishing' ? 'Likely Phishing'
    : label || 'Unknown';

  return (
    <div className="rc-premium-card glass-card p-4 border-0 shadow-lg position-relative">
      <style>{`
        :root {
          --rc-gold: #d4af6a;
          --rc-gold-soft: rgba(212, 175, 106, 0.10);
          --rc-gold-border: rgba(212, 175, 106, 0.35);
          --rc-tile-bg: rgba(255, 255, 255, 0.03);
          --rc-tile-border: rgba(255, 255, 255, 0.08);
          --rc-chip-bg: rgba(255, 255, 255, 0.035);
          --rc-chip-border: rgba(255, 255, 255, 0.09);
          --rc-track-bg: rgba(255, 255, 255, 0.06);
          --rc-success-soft: rgba(16, 185, 129, 0.12);
          --rc-success-border: rgba(16, 185, 129, 0.32);
          --rc-danger-soft: rgba(239, 68, 68, 0.12);
          --rc-danger-border: rgba(239, 68, 68, 0.32);
          --rc-warning-soft: rgba(245, 158, 11, 0.12);
          --rc-warning-border: rgba(245, 158, 11, 0.32);
        }
        .rc-serif { font-family: 'Fraunces', Georgia, 'Times New Roman', serif; }
        .rc-premium-card {
          border-radius: 20px !important;
          border: 1px solid var(--rc-gold-border) !important;
          background:
            linear-gradient(180deg, rgba(212,175,106,0.05), transparent 40%),
            var(--bg-card, rgba(22,33,54,0.65)) !important;
          box-shadow: 0 24px 70px rgba(0,0,0,.45), inset 0 1px 0 rgba(255,255,255,.03) !important;
          overflow: hidden;
        }
        .rc-premium-card::before {
          content: '';
          position: absolute;
          inset: 0 0 auto 0;
          height: 2px;
          background: linear-gradient(90deg, transparent, var(--rc-gold), transparent);
          opacity: .8;
        }
        .rc-eyebrow {
          text-transform: uppercase;
          letter-spacing: 2.5px;
          color: var(--rc-gold);
          font-weight: 600;
        }
        .rc-tile-hover { transition: transform .25s ease, border-color .25s ease; }
        .rc-tile-hover:hover { transform: translateY(-2px); border-color: var(--rc-gold-border) !important; }
        .rc-fade-up { animation: rcFadeUp .5s ease both; }
        @keyframes rcFadeUp {
          from { opacity: 0; transform: translateY(10px); }
          to { opacity: 1; transform: translateY(0); }
        }
        .rc-gauge-arc { transition: stroke-dasharray 0.9s cubic-bezier(.4,0,.2,1); }
        .rc-seal { filter: drop-shadow(0 6px 18px rgba(212,175,106,0.12)); }
        .rc-bar-track {
          height: 8px;
          border-radius: 20px;
          background: var(--rc-track-bg);
          overflow: hidden;
        }
        .rc-bar-fill {
          height: 100%;
          border-radius: 20px;
          transition: width 0.8s cubic-bezier(.4,0,.2,1);
        }
        .rc-doc-footer {
          border-top: 1px dashed var(--rc-gold-border);
        }
        @media (prefers-reduced-motion: reduce) {
          .rc-fade-up, .rc-gauge-arc, .rc-bar-fill, .rc-tile-hover { animation: none !important; transition: none !important; }
        }
      `}</style>

      {/* Header */}
      <div className="d-flex flex-wrap justify-content-between align-items-start gap-3 mb-4 rc-fade-up">
        <div>
          <div className="rc-eyebrow small mb-1" style={{ fontSize: '0.7rem' }}>
            {meta.doc} · Ensemble Certified
          </div>
          <div className="d-flex align-items-center gap-2">
            <span
              className="d-flex align-items-center justify-content-center rounded-3 flex-shrink-0"
              style={{ width: 34, height: 34, background: UI.goldSoft, border: `1px solid ${UI.goldBorder}` }}
            >
              <i className={`bi ${meta.icon}`} style={{ color: UI.gold }} />
            </span>
            <h3 className="m-0 rc-serif" style={{ color: UI.text, fontWeight: 600, fontSize: '1.4rem' }}>
              {meta.title}
            </h3>
          </div>
        </div>

        <ToneBadge tone={tone} className="fs-6">
          <i className={`bi ${toneIcon(tone)} me-1`} />
          {friendlyLabel}
        </ToneBadge>
      </div>

      {/* Hero: seal + explanation + pie */}
      <div className="row g-3 mb-4 rc-fade-up" style={{ animationDelay: '60ms' }}>
        <div className={hasVotes ? 'col-lg-4' : 'col-lg-5'}>
          <Tile className="d-flex align-items-center justify-content-center text-center" hover={false}>
            <CertificationSeal value={confidence} tone={tone} />
          </Tile>
        </div>

        <div className={hasVotes ? 'col-lg-4' : 'col-lg-7'}>
          <Tile hover={false} className="h-100">
            <div className="small fw-semibold mb-2 d-flex align-items-center gap-2" style={{ color: UI.muted }}>
              <i className="bi bi-file-earmark-text" style={{ color: UI.gold }} />
              Findings
            </div>
            <p className="m-0" style={{ color: UI.muted, fontSize: '0.92rem', lineHeight: 1.6 }}>
              {explanation || 'No explanation was returned for this analysis.'}
            </p>
          </Tile>
        </div>

        {hasVotes && (
          <div className="col-lg-4">
            <Tile hover={false} className="h-100">
              <div className="small fw-semibold mb-3 d-flex align-items-center gap-2" style={{ color: UI.muted }}>
                <i className="bi bi-pie-chart-fill" style={{ color: UI.gold }} />
                Vote Share
              </div>
              <div className="row g-3 align-items-center">
                <div className="col-auto mx-auto">
                  <VotePieChart votes={votes} />
                </div>
                <div className="col">
                  <VoteLegend votes={votes} />
                </div>
              </div>
            </Tile>
          </div>
        )}
      </div>

      {/* Confidence ledger — percentage bars per model */}
      {hasLedger && (
        <div className="mb-4 rc-fade-up" style={{ animationDelay: '110ms' }}>
          <ConfidenceLedger models={result.models} />
        </div>
      )}

      {/* Technical metrics */}
      <h4 className="fs-6 mb-3 fw-bold rc-fade-up d-flex align-items-center gap-2" style={{ color: UI.text, animationDelay: '160ms' }}>
        <i className="bi bi-cpu" style={{ color: UI.gold }} />
        Technical Metrics Breakdown
      </h4>

      <div className="row g-3 rc-fade-up" style={{ animationDelay: '200ms' }}>
        {type === 'news' && (
          <>
            <div className="col-md-6">
              <MetricTile icon="bi-diagram-3" label="Participating Models" value={metrics?.totalModels ?? 0} />
            </div>
            <div className="col-md-6">
              <MetricTile
                icon="bi-trophy"
                label="Winning Votes"
                value={result.poll ? `${result.poll.winningVotes} / ${result.poll.totalVotes}` : 'N/A'}
              />
            </div>
            <div className="col-12">
              <Tile>
                <div className="small mb-1" style={{ color: UI.muted }}>Models Consulted</div>
                <ModelChipList models={metrics?.participatingModels} />
              </Tile>
            </div>
          </>
        )}

        {type === 'review' && (
          <>
            <div className="col-md-6">
              <Tile>
                <div className="d-flex justify-content-between mb-1 small" style={{ color: UI.muted }}>
                  <span>Spam Pattern Score</span>
                  <span className="fw-bold" style={{ color: (metrics?.spamScore ?? 0) > 50 ? UI.danger : UI.success }}>
                    {metrics?.spamScore ?? 0}%
                  </span>
                </div>
                <div className="rc-bar-track">
                  <div
                    className="rc-bar-fill"
                    style={{
                      width: `${metrics?.spamScore ?? 0}%`,
                      background: (metrics?.spamScore ?? 0) > 50
                        ? `linear-gradient(90deg, ${UI.danger}99, ${UI.danger})`
                        : `linear-gradient(90deg, ${UI.success}99, ${UI.success})`,
                    }}
                  />
                </div>
              </Tile>
            </div>

            <div className="col-md-6">
              <MetricTile icon="bi-diagram-3" label="Participating Models" value={metrics?.totalModels ?? 0} />
            </div>

            <div className="col-12">
              <Tile>
                <div className="small mb-1" style={{ color: UI.muted }}>Models Consulted</div>
                <ModelChipList models={metrics?.participatingModels} />
              </Tile>
            </div>

            {urlVerification?.checked && (
              <div className="col-12">
                <Tile>
                  <div className="d-flex justify-content-between align-items-center mb-2">
                    <span className="small fw-semibold" style={{ color: UI.muted }}>
                      <i className="bi bi-link-45deg me-1" />
                      Product/Seller URL Check
                    </span>
                    {urlVerification.valid ? (
                      <ToneBadge tone={labelTone(urlVerification.label)}>
                        {urlVerification.label === 'Phishing' ? 'Looks Like a Scam URL'
                          : urlVerification.label === 'Safe' ? 'Looks Legitimate'
                          : 'Inconclusive'}
                      </ToneBadge>
                    ) : (
                      <ToneBadge tone="warning">Could Not Verify</ToneBadge>
                    )}
                  </div>

                  {urlVerification.valid ? (
                    <>
                      <div className="small mb-2" style={{ color: UI.muted }}>
                        Risk level: <strong style={{ color: UI.text }}>{urlVerification.riskLevel}</strong>
                        {urlVerification.confidence != null && (
                          <> · Vote confidence: <strong style={{ color: UI.text }}>{urlVerification.confidence}%</strong></>
                        )}
                      </div>
                      {urlVerification.indicators?.length > 0 ? (
                        <ul className="small mb-0 ps-3" style={{ color: UI.muted }}>
                          {urlVerification.indicators.map((indicator, i) => <li key={i}>{indicator}</li>)}
                        </ul>
                      ) : (
                        <div className="small mb-0" style={{ color: UI.muted }}>
                          No obvious structural red flags detected in the URL.
                        </div>
                      )}
                    </>
                  ) : (
                    <div className="small mb-0" style={{ color: UI.warning }}>{urlVerification.error}</div>
                  )}
                </Tile>
              </div>
            )}
          </>
        )}

        {type === 'phishing' && (
          <>
            <div className="col-md-6 col-lg-3">
              <Tile className="text-center">
                <div className="small mb-1" style={{ color: UI.muted }}>Threat Risk Level</div>
                <ToneBadge
                  tone={riskLevel === 'High' ? 'danger' : riskLevel === 'Medium' ? 'warning' : 'success'}
                  className="px-2 py-1"
                >
                  {riskLevel ?? 'Unknown'} Risk
                </ToneBadge>
              </Tile>
            </div>

            <div className="col-md-6 col-lg-3">
              <Tile className="text-center">
                <div className="small mb-1" style={{ color: UI.muted }}>SSL Certificate</div>
                <div className="fw-bold" style={{ fontSize: '0.9rem' }}>
                  {metrics?.sslValid ? (
                    <span style={{ color: UI.success }}><i className="bi bi-shield-fill-check me-1" />Secure HTTPS</span>
                  ) : (
                    <span style={{ color: UI.danger }}><i className="bi bi-shield-fill-x me-1" />Insecure HTTP</span>
                  )}
                </div>
              </Tile>
            </div>

            <div className="col-md-6 col-lg-3">
              <Tile className="text-center">
                <div className="small mb-1" style={{ color: UI.muted }}>Domain Age</div>
                <div className="fw-bold small" style={{ color: UI.text }}>{metrics?.domainAge ?? 'N/A'}</div>
              </Tile>
            </div>

            <div className="col-md-6 col-lg-3">
              <Tile className="text-center">
                <div className="small mb-1" style={{ color: UI.muted }}>TLD Trust Rating</div>
                <div
                  className="fw-bold"
                  style={{
                    color: metrics?.tldTrust === 'High' ? UI.success
                      : metrics?.tldTrust === 'Medium' ? UI.warning
                      : UI.danger,
                  }}
                >
                  {metrics?.tldTrust ?? 'Unknown'}
                </div>
              </Tile>
            </div>

            <div className="col-12">
              <Tile>
                <div className="small mb-1" style={{ color: UI.muted }}>Models Consulted</div>
                <ModelChipList models={metrics?.participatingModels} />
              </Tile>
            </div>
          </>
        )}
      </div>

      {/* Certification footer */}
      <div className="rc-doc-footer d-flex flex-wrap justify-content-between align-items-center gap-2 mt-4 pt-3 rc-fade-up" style={{ animationDelay: '240ms' }}>
        <span className="small" style={{ color: UI.subtle }}>
          <i className="bi bi-award me-1" style={{ color: UI.gold }} />
          TrustGuard Ensemble Certification — model-based assessment, not a guarantee
        </span>
        <span className="small" style={{ color: UI.subtle }}>
          {new Date().toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })}
        </span>
      </div>
    </div>
  );
}