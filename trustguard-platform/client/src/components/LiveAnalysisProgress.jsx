import { useEffect, useMemo, useRef, useState } from 'react';

const STEP_ORDER = [
  {
    key: 'claim',
    label: 'Understanding claim',
    icon: 'bi-lightbulb',
    events: [
      'claim_extraction_started',
      'claim_extracted',
      'claim_extraction_failed',
    ],
    doneEvents: ['claim_extracted', 'claim_extraction_failed'],
  },
  {
    key: 'poll',
    label: 'Polling ML models',
    icon: 'bi-cpu',
    events: [
      'model_started',
      'model_completed',
      'model_unavailable',
      'vote_added',
    ],
    doneEvents: ['vote_added'],
  },
  {
    key: 'temporal',
    label: 'Checking currentness',
    icon: 'bi-clock-history',
    events: ['temporal_classified'],
    doneEvents: ['temporal_classified'],
  },
  {
    key: 'search',
    label: 'Searching for related coverage',
    icon: 'bi-search',
    events: [
      'search_started',
      'search_completed',
      'search_skipped',
      'search_failed',
    ],
    doneEvents: ['search_completed', 'search_skipped', 'search_failed'],
  },
  {
    key: 'articles',
    label: 'Analyzing related articles',
    icon: 'bi-newspaper',
    events: [
      'article_found',
      'article_extracted',
      'article_extraction_failed',
      'article_analyzed',
    ],
    doneEvents: [],
  },
  {
    key: 'cluster',
    label: 'Building source clusters',
    icon: 'bi-diagram-3',
    events: [
      'source_clustering_started',
      'source_cluster_created',
    ],
    doneEvents: ['source_cluster_created'],
  },
  {
    key: 'synthesis',
    label: 'Generating final assessment',
    icon: 'bi-stars',
    events: [
      'cross_evidence_started',
      'cross_evidence_completed',
    ],
    doneEvents: ['cross_evidence_completed'],
  },
];

const STEP_BY_EVENT = new Map(
  STEP_ORDER.flatMap((step) =>
    step.events.map((event) => [event, step]),
  ),
);

const DONE_EVENTS = new Set(
  STEP_ORDER.flatMap((step) => step.doneEvents),
);

const MAX_LOG_LINES = 50;

const UI = {
  cyan: 'var(--accent-cyan)',
  cyanSoft: 'var(--accent-cyan-soft)',
  cyanBorder: 'var(--accent-cyan-border)',
  text: 'var(--text-primary)',
  muted: 'var(--text-secondary)',
  subtle: 'var(--text-muted)',
  card: 'var(--bg-card)',
  cardBorder: 'var(--border-color)',
  tileBg: 'var(--tile-bg)',
  tileBorder: 'var(--tile-border)',
  success: 'var(--success)',
  danger: 'var(--danger)',
  warning: 'var(--warning)',
};

function createInitialStepStatus() {
  return Object.fromEntries(
    STEP_ORDER.map((step) => [step.key, 'pending']),
  );
}

function normalizeSSEChunk(buffer) {
  // Servers/proxies may use CRLF instead of LF.
  return buffer.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
}

function parseSSEFrame(frame) {
  let type = 'message';
  const dataLines = [];

  for (const rawLine of frame.split('\n')) {
    const line = rawLine.trimEnd();

    // SSE comments / keep-alive frames.
    if (!line || line.startsWith(':')) continue;

    if (line.startsWith('event:')) {
      type = line.slice(6).trim() || 'message';
      continue;
    }

    if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).trimStart());
    }
  }

  if (!dataLines.length) {
    return null;
  }

  const rawData = dataLines.join('\n');

  try {
    return {
      type,
      data: JSON.parse(rawData),
    };
  } catch (error) {
    console.warn('[LiveAnalysis] Invalid SSE JSON:', {
      type,
      rawData,
      error,
    });

    return null;
  }
}

async function* readSSE(response, signal) {
  if (!response.body) {
    throw new Error('Server returned an empty response stream.');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8');

  let buffer = '';

  try {
    while (true) {
      if (signal?.aborted) return;

      const { done, value } = await reader.read();

      if (done) {
        buffer += decoder.decode();

        // Process a final frame even if the server forgot the trailing \n\n.
        const remaining = normalizeSSEChunk(buffer).trim();

        if (remaining) {
          const event = parseSSEFrame(remaining);
          if (event) yield event;
        }

        return;
      }

      buffer += decoder.decode(value, { stream: true });
      buffer = normalizeSSEChunk(buffer);

      let boundary;

      while ((boundary = buffer.indexOf('\n\n')) !== -1) {
        const frame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);

        const event = parseSSEFrame(frame);

        if (event) {
          yield event;
        }
      }
    }
  } finally {
    try {
      await reader.cancel();
    } catch {
      // Stream may already be closed.
    }

    reader.releaseLock();
  }
}

function modelKey(model) {
  return `${model.articleId || 'primary'}::${model.model}`;
}

function getModelStatus(type) {
  switch (type) {
    case 'model_started':
      return 'running';

    case 'model_completed':
      return 'done';

    case 'model_unavailable':
      return 'unavailable';

    default:
      return 'unknown';
  }
}

function formatElapsed(ms) {
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
}

function toneColor(tone) {
  return { success: UI.success, danger: UI.danger, warning: UI.warning }[tone] || UI.cyan;
}

// ---------------------------------------------------------------------------

function ModelResult({ model }) {
  const isUnavailable = model.status === 'unavailable';
  const isRunning = model.status === 'running';

  let value = model.label || 'UNKNOWN';
  let color = UI.subtle;
  let dotTone = 'muted';

  if (isRunning) {
    value = 'analyzing…';
    color = UI.cyan;
  } else if (isUnavailable) {
    value = 'NO VOTE';
  } else if (model.label === 'Fake') {
    color = UI.danger;
    dotTone = 'danger';
  } else if (model.label === 'Real') {
    color = UI.success;
    dotTone = 'success';
  } else {
    color = UI.warning;
    dotTone = 'warning';
  }

  return (
    <div
      className="d-flex justify-content-between align-items-center gap-3 small px-2 py-2 rounded"
      style={{ background: UI.tileBg, border: `1px solid ${UI.tileBorder}` }}
    >
      <span className="d-flex align-items-center gap-2 text-truncate" style={{ minWidth: 0 }}>
        {isRunning ? (
          <span className="analysis-spin" style={{ color: UI.cyan, fontSize: '0.7rem' }}>
            <i className="bi bi-arrow-repeat" />
          </span>
        ) : (
          <span
            className="rounded-circle flex-shrink-0"
            style={{
              width: 7,
              height: 7,
              background: dotTone === 'muted' ? UI.subtle : toneColor(dotTone),
            }}
          />
        )}
        <span className="text-truncate" style={{ color: UI.muted }} title={model.model}>
          {model.model}
          {model.articleId ? (
            <span style={{ color: UI.subtle }}> · related article</span>
          ) : null}
        </span>
      </span>

      <span className="fw-semibold flex-shrink-0" style={{ color }}>
        {value}
        {model.confidence != null && !isUnavailable && !isRunning && (
          <span className="ms-1 fw-normal" style={{ color: UI.subtle }}>
            {Number(model.confidence).toFixed(0)}%
          </span>
        )}
      </span>
    </div>
  );
}

const ARTICLE_STATUS_ICON = {
  found: 'bi-search',
  extracted: 'bi-file-earmark-text',
  analyzed: 'bi-check-circle-fill',
};

function ArticleRow({ article }) {
  const status = article.status || 'found';
  const tone = status === 'analyzed' ? UI.success : status === 'extracted' ? UI.cyan : UI.subtle;
  const title = article.title || article.headline || article.url || 'Untitled source';

  return (
    <div className="lap-article-row d-flex align-items-center gap-2 px-2 py-1">
      <i className={`bi ${ARTICLE_STATUS_ICON[status] || 'bi-circle'}`} style={{ color: tone, fontSize: '0.8rem' }} />
      <span className="small text-truncate" style={{ color: UI.muted, minWidth: 0 }} title={title}>
        {title}
      </span>
      <span className="small ms-auto flex-shrink-0" style={{ color: UI.subtle, textTransform: 'capitalize' }}>
        {status}
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------

export default function LiveAnalysisProgress({
  streamUrl,
  payload,
  geminiApiKey,
  onComplete,
  onError,
}) {
  const [stepStatus, setStepStatus] = useState(createInitialStepStatus);
  const [models, setModels] = useState([]);
  const [votes, setVotes] = useState({});
  const [articles, setArticles] = useState([]);
  const [streamStatus, setStreamStatus] = useState('connecting');
  const [analysisId, setAnalysisId] = useState(null);
  const [eventLog, setEventLog] = useState([]);
  const [elapsedMs, setElapsedMs] = useState(0);

  const abortRef = useRef(null);
  const completedRef = useRef(false);
  const startRef = useRef(null);
  const clockRef = useRef(null);

  /*
   * Keep callback changes from restarting the HTTP stream.
   *
   * This is important because parent components frequently create inline
   * callbacks on every render.
   */
  const onCompleteRef = useRef(onComplete);
  const onErrorRef = useRef(onError);

  useEffect(() => {
    onCompleteRef.current = onComplete;
  }, [onComplete]);

  useEffect(() => {
    onErrorRef.current = onError;
  }, [onError]);

  /*
   * Stabilize the request body.
   *
   * Without this, a parent doing:
   *
   *   payload={{ headline, mode: 'auto' }}
   *
   * creates a new object every render and causes this effect to reconnect.
   */
  const serializedPayload = useMemo(
    () => JSON.stringify(payload ?? {}),
    [payload],
  );

  useEffect(() => {
    const controller = new AbortController();

    // Abort any previous request before starting a new one.
    abortRef.current?.abort();
    abortRef.current = controller;

    completedRef.current = false;

    setStepStatus(createInitialStepStatus());
    setModels([]);
    setVotes({});
    setArticles([]);
    setAnalysisId(null);
    setStreamStatus('connecting');
    setEventLog([]);
    setElapsedMs(0);

    startRef.current = Date.now();
    clockRef.current = window.setInterval(() => {
      setElapsedMs(Date.now() - startRef.current);
    }, 250);

    const stopClock = () => {
      if (clockRef.current) {
        window.clearInterval(clockRef.current);
        clockRef.current = null;
      }
    };

    const pushLog = (type) => {
      const time = new Date().toLocaleTimeString([], {
        hour12: false,
        minute: '2-digit',
        second: '2-digit',
      });

      setEventLog((prev) => {
        const next = [...prev, { time, type }];
        return next.length > MAX_LOG_LINES ? next.slice(next.length - MAX_LOG_LINES) : next;
      });
    };

    const reportError = (message) => {
      if (controller.signal.aborted) return;

      setStreamStatus('error');
      stopClock();

      onErrorRef.current?.(
        message || 'Live analysis failed.',
      );
    };

    const run = async () => {
      try {
        const headers = {
          Accept: 'text/event-stream',
          'Content-Type': 'application/json',
          'Cache-Control': 'no-cache',
        };

        if (geminiApiKey?.trim()) {
          headers['X-Gemini-API-Key'] = geminiApiKey.trim();
        }

        const response = await fetch(streamUrl, {
          method: 'POST',
          headers,
          body: serializedPayload,
          signal: controller.signal,
          cache: 'no-store',
        });

        if (!response.ok) {
          let serverMessage = '';

          try {
            const data = await response.json();

            serverMessage =
              data?.detail ||
              data?.message ||
              '';
          } catch {
            // Ignore invalid/non-JSON error bodies.
          }

          throw new Error(
            serverMessage ||
              `Live analysis failed (HTTP ${response.status}).`,
          );
        }

        if (!response.body) {
          throw new Error(
            'The server accepted the request but returned no stream.',
          );
        }

        setStreamStatus('running');

        for await (const evt of readSSE(
          response,
          controller.signal,
        )) {
          if (controller.signal.aborted) return;

          const { type, data = {} } = evt;

          // Useful while debugging, but bounded.
          // Remove this if you do not want console logging.
          if (import.meta.env?.DEV) {
            console.debug('[LiveAnalysis]', type, data);
          }

          pushLog(type);

          if (type === 'analysis_started') {
            setAnalysisId(data.analysisId || null);
          }

          const step = STEP_BY_EVENT.get(type);

          if (step) {
            setStepStatus((prev) => ({
              ...prev,
              [step.key]: DONE_EVENTS.has(type)
                ? 'done'
                : 'active',
            }));
          }

          if (
            type === 'model_started' ||
            type === 'model_completed' ||
            type === 'model_unavailable'
          ) {
            const nextModel = {
              model: data.model || 'Unknown model',
              articleId: data.articleId || null,
              status: getModelStatus(type),
              label: data.label,
              confidence: data.confidence,
              reason: data.reason,
            };

            const key = modelKey(nextModel);

            setModels((prev) => {
              const index = prev.findIndex(
                (item) => modelKey(item) === key,
              );

              if (index === -1) {
                return [...prev, nextModel];
              }

              const next = [...prev];

              next[index] = {
                ...next[index],
                ...nextModel,
              };

              return next;
            });
          }

          if (type === 'vote_added') {
            setVotes(data.votes || {});
            setStepStatus((prev) => ({
              ...prev,
              poll: 'done',
            }));
          }

          if (type === 'article_found') {
            const id = data.id || data.url;

            if (id) {
              setArticles((prev) => {
                if (prev.some((article) => article.id === id)) {
                  return prev;
                }

                return [
                  ...prev,
                  {
                    ...data,
                    id,
                    status: 'found',
                  },
                ];
              });
            }
          }

          if (type === 'article_extracted') {
            const id = data.id || data.url;

            if (id) {
              setArticles((prev) =>
                prev.map((article) =>
                  article.id === id
                    ? {
                        ...article,
                        ...data,
                        status: 'extracted',
                      }
                    : article,
                ),
              );
            }
          }

          if (type === 'article_analyzed') {
            const id = data.id || data.url;

            if (id) {
              setArticles((prev) => {
                const existing = prev.find(
                  (article) => article.id === id,
                );

                if (!existing) {
                  return [
                    ...prev,
                    {
                      ...data,
                      id,
                      status: 'analyzed',
                    },
                  ];
                }

                return prev.map((article) =>
                  article.id === id
                    ? {
                        ...article,
                        ...data,
                        status: 'analyzed',
                      }
                    : article,
                );
              });
            }
          }

          if (type === 'search_skipped') {
            // In auto/fast mode there will be no articles or clustering.
            setStepStatus((prev) => ({
              ...prev,
              search: 'done',
              articles: 'skipped',
              cluster: 'skipped',
            }));
          }

          if (type === 'search_failed') {
            setStepStatus((prev) => ({
              ...prev,
              search: 'done',
              articles: 'skipped',
              cluster: 'skipped',
            }));
          }

          if (type === 'source_cluster_created') {
            setStepStatus((prev) => ({
              ...prev,
              articles: 'done',
              cluster: 'done',
            }));
          }

          if (type === 'final_result') {
            /*
             * final_result is the useful payload.
             * Guard against accidental duplicate SSE frames.
             */
            if (!completedRef.current) {
              completedRef.current = true;
              setStreamStatus('completed');
              stopClock();

              setStepStatus((prev) => ({
                ...prev,
                synthesis: 'done',
              }));

              onCompleteRef.current?.(data);
            }
          }

          if (type === 'error') {
            reportError(
              data.message ||
                `Analysis failed during ${data.stage || 'processing'}.`,
            );
          }

          if (type === 'analysis_completed') {
            if (data.status === 'FAILED') {
              reportError(
                data.message ||
                  'News analysis could not be completed.',
              );
            } else if (data.status === 'COMPLETED') {
              setStreamStatus('completed');
              stopClock();
            }

            /*
             * The backend has explicitly finished.
             * No reason to keep the stream reader alive.
             */
            break;
          }
        }

        /*
         * If the connection closes without final_result, distinguish it
         * from a successful completion.
         */
        if (
          !controller.signal.aborted &&
          !completedRef.current
        ) {
          throw new Error(
            'The analysis stream closed before a final result was received.',
          );
        }
      } catch (error) {
        if (
          controller.signal.aborted ||
          error?.name === 'AbortError'
        ) {
          return;
        }

        console.error('[LiveAnalysis] Stream error:', error);

        reportError(
          error?.message ||
            'Live analysis connection failed.',
        );
      }
    };

    run();

    return () => {
      controller.abort();
      stopClock();

      if (abortRef.current === controller) {
        abortRef.current = null;
      }
    };
  }, [
    streamUrl,
    serializedPayload,
    geminiApiKey,
  ]);

  const totalVotes = useMemo(
    () =>
      Object.values(votes).reduce(
        (total, value) =>
          total + (Number(value) || 0),
        0,
      ),
    [votes],
  );

  const analyzedArticleCount = useMemo(
    () =>
      articles.filter(
        (article) => article.status === 'analyzed',
      ).length,
    [articles],
  );

  const stepProgress = useMemo(() => {
    const total = STEP_ORDER.length;
    const done = STEP_ORDER.filter((step) => {
      const status = stepStatus[step.key];
      return status === 'done' || status === 'skipped';
    }).length;
    const active = STEP_ORDER.some((step) => stepStatus[step.key] === 'active') ? 0.5 : 0;
    return Math.min(100, ((done + active) / total) * 100);
  }, [stepStatus]);

  const statusMeta = {
    connecting: { label: 'Connecting…', icon: 'bi-broadcast', color: UI.cyan },
    running: { label: 'Analysis in progress', icon: 'bi-activity', color: UI.cyan },
    completed: { label: 'Analysis complete', icon: 'bi-check-circle-fill', color: UI.success },
    error: { label: 'Analysis failed', icon: 'bi-exclamation-circle-fill', color: UI.danger },
  }[streamStatus];

  return (
    <div
      className="p-4 position-relative"
      style={{
        background: UI.card,
        border: `1px solid ${UI.cardBorder}`,
        borderRadius: 18,
        boxShadow: '0 18px 55px rgba(0,0,0,.16)',
        overflow: 'hidden',
      }}
    >
      {(streamStatus === 'running' || streamStatus === 'connecting') && (
        <span className="lap-border-glow" aria-hidden="true" />
      )}

      {/* Header */}
      <div className="d-flex flex-wrap align-items-start justify-content-between gap-3 mb-4 position-relative">
        <div className="d-flex align-items-center gap-3">
          <div className="lap-orb">
            <span className="lap-orb-core" />
            {(streamStatus === 'running' || streamStatus === 'connecting') && (
              <span className="lap-orb-ring" />
            )}
          </div>
          <div>
            <div className="d-flex align-items-center gap-2">
              <i className={`bi ${statusMeta.icon}`} style={{ color: statusMeta.color }} />
              <span className="fw-semibold" style={{ color: UI.text, fontSize: '1.02rem' }}>
                {statusMeta.label}
              </span>
            </div>
            {analysisId && (
              <div className="small text-truncate" style={{ color: UI.subtle, maxWidth: 260 }} title={analysisId}>
                ID: {analysisId}
              </div>
            )}
          </div>
        </div>

        <div className="text-end">
          <div className="lap-timer" style={{ color: UI.cyan }}>
            {formatElapsed(elapsedMs)}
          </div>
          <div className="small" style={{ color: UI.subtle }}>elapsed</div>
        </div>
      </div>

      {/* Overall progress */}
      <div className="lap-track mb-4">
        <div className="lap-track-fill" style={{ width: `${stepProgress}%` }} />
      </div>

      <div className="row g-4">
        {/* Pipeline stepper */}
        <div className="col-lg-6">
          <div className="small fw-semibold mb-3" style={{ color: UI.muted }}>
            PIPELINE
          </div>
          <div className="d-flex flex-column gap-1">
            {STEP_ORDER.map((step, index) => {
              const status = stepStatus[step.key] || 'pending';
              const isDone = status === 'done';
              const isActive = status === 'active';
              const isSkipped = status === 'skipped';
              const state = isDone ? 'done' : isActive ? 'active' : isSkipped ? 'skipped' : 'pending';

              return (
                <div
                  key={step.key}
                  className="lap-step d-flex align-items-start gap-3"
                  style={{ animationDelay: `${index * 50}ms` }}
                >
                  <div className={`lap-step-icon lap-step-icon--${state}`}>
                    {isDone ? (
                      <i className="bi bi-check-lg" />
                    ) : isActive ? (
                      <span className="lap-step-spinner" />
                    ) : isSkipped ? (
                      <i className="bi bi-dash-lg" />
                    ) : (
                      <i className={`bi ${step.icon}`} />
                    )}
                  </div>

                  <div className="flex-grow-1 pb-3">
                    <div
                      className="small fw-semibold"
                      style={{ color: state === 'pending' ? UI.subtle : UI.text }}
                    >
                      {step.label}
                    </div>
                    {isSkipped && (
                      <div className="small" style={{ color: UI.subtle }}>
                        Skipped for this analysis mode
                      </div>
                    )}
                  </div>

                  {isActive && <span className="lap-live-chip" style={{ color: UI.cyan }}>live</span>}
                </div>
              );
            })}
          </div>
        </div>

        {/* Live poll + models + articles */}
        <div className="col-lg-6 d-flex flex-column gap-4">
          {totalVotes > 0 && (
            <div>
              <div className="small fw-semibold mb-2" style={{ color: UI.muted }}>
                LIVE MODEL POLL · {totalVotes} vote{totalVotes === 1 ? '' : 's'}
              </div>
              <div className="d-flex flex-column gap-2">
                {Object.entries(votes).map(([voteLabel, rawCount]) => {
                  const count = Number(rawCount) || 0;
                  const pct = totalVotes > 0 ? (count / totalVotes) * 100 : 0;
                  const tone =
                    voteLabel === 'Fake' || voteLabel === 'Phishing' ? 'danger'
                    : voteLabel === 'Real' || voteLabel === 'Genuine' || voteLabel === 'Safe' ? 'success'
                    : 'warning';

                  return (
                    <div key={voteLabel} className="d-flex align-items-center gap-2">
                      <span className="small flex-shrink-0" style={{ width: 60, color: UI.muted }}>
                        {voteLabel}
                      </span>
                      <div className="lap-poll-track flex-grow-1" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
                        <div className="lap-poll-fill" style={{ width: `${pct}%`, background: toneColor(tone) }} />
                      </div>
                      <span className="small fw-bold flex-shrink-0" style={{ minWidth: 20, textAlign: 'right', color: UI.text }}>
                        {count}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {models.length > 0 && (
            <div>
              <div className="small fw-semibold mb-2" style={{ color: UI.muted }}>
                MODEL RESPONSES
              </div>
              <div className="d-flex flex-column gap-2">
                {models.map((model) => (
                  <ModelResult key={modelKey(model)} model={model} />
                ))}
              </div>
            </div>
          )}

          {articles.length > 0 && (
            <div>
              <div className="d-flex align-items-center justify-content-between mb-2">
                <span className="small fw-semibold" style={{ color: UI.muted }}>
                  RELATED ARTICLES
                </span>
                <span className="small" style={{ color: UI.subtle }}>
                  {analyzedArticleCount}/{articles.length} analyzed
                </span>
              </div>
              <div className="d-flex flex-column">
                {articles.slice(0, 6).map((article) => (
                  <ArticleRow key={article.id} article={article} />
                ))}
                {articles.length > 6 && (
                  <div className="small mt-1" style={{ color: UI.subtle }}>
                    +{articles.length - 6} more
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Live event log */}
      {eventLog.length > 0 && (
        <details className="lap-log mt-4">
          <summary className="small fw-semibold d-flex align-items-center gap-2" style={{ color: UI.muted }}>
            <i className="bi bi-terminal" />
            Live event log ({eventLog.length})
          </summary>
          <div className="mt-2 d-flex flex-column gap-1">
            {eventLog.map((entry, i) => (
              <div key={i} style={{ color: UI.subtle }}>
                <span style={{ color: UI.cyan }}>{entry.time}</span> · {entry.type}
              </div>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}