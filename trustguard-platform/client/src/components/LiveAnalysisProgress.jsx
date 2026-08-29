import { useEffect, useMemo, useRef, useState } from 'react';

const STEP_ORDER = [
  {
    key: 'claim',
    label: 'Understanding claim',
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
    events: ['temporal_classified'],
    doneEvents: ['temporal_classified'],
  },
  {
    key: 'search',
    label: 'Searching for related coverage',
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
    events: [
      'source_clustering_started',
      'source_cluster_created',
    ],
    doneEvents: ['source_cluster_created'],
  },
  {
    key: 'synthesis',
    label: 'Generating final assessment',
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

function ModelResult({ model }) {
  const isUnavailable = model.status === 'unavailable';
  const isRunning = model.status === 'running';

  let value = model.label || 'UNKNOWN';
  let color = 'var(--text-muted)';

  if (isRunning) {
    value = 'analyzing…';
    color = 'var(--accent-cyan)';
  } else if (isUnavailable) {
    value = 'NO VOTE';
  } else if (model.label === 'Fake') {
    color = 'var(--danger)';
  } else if (model.label === 'Real') {
    color = 'var(--success)';
  } else {
    color = 'var(--warning)';
  }

  return (
    <div className="d-flex justify-content-between align-items-center gap-3 small">
      <span
        className="text-truncate"
        style={{
          color: 'var(--text-secondary)',
          minWidth: 0,
        }}
        title={model.model}
      >
        {model.model}
        {model.articleId ? (
          <span style={{ color: 'var(--text-muted)' }}>
            {' '}· related article
          </span>
        ) : null}
      </span>

      <span
        className="fw-semibold flex-shrink-0"
        style={{ color }}
      >
        {value}

        {model.confidence != null && !isUnavailable && !isRunning && (
          <span
            className="ms-1 fw-normal"
            style={{ color: 'var(--text-muted)' }}
          >
            {Number(model.confidence).toFixed(0)}%
          </span>
        )}
      </span>
    </div>
  );
}

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

  const abortRef = useRef(null);
  const completedRef = useRef(false);

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

    const reportError = (message) => {
      if (controller.signal.aborted) return;

      setStreamStatus('error');

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

  const statusLabel = {
    connecting: 'Connecting…',
    running: 'Analysis in progress',
    completed: 'Analysis complete',
    error: 'Analysis failed',
  }[streamStatus];

  return (
    <div className="d-flex flex-column gap-3">
      {/* Header */}
      <div className="d-flex align-items-center justify-content-between gap-3">
        <div className="d-flex align-items-center gap-2">
          {streamStatus === 'running' ||
          streamStatus === 'connecting' ? (
            <span
              className="spinner-border spinner-border-sm"
              role="status"
              aria-hidden="true"
              style={{ color: 'var(--accent-cyan)' }}
            />
          ) : (
            <i
              className={`bi ${
                streamStatus === 'completed'
                  ? 'bi-check-circle-fill'
                  : 'bi-exclamation-circle-fill'
              }`}
              style={{
                color:
                  streamStatus === 'completed'
                    ? 'var(--success)'
                    : 'var(--danger)',
              }}
            />
          )}

          <span
            className="small fw-semibold"
            style={{ color: 'var(--text-primary)' }}
          >
            {statusLabel}
          </span>
        </div>

        {analysisId && (
          <span
            className="small text-truncate"
            title={analysisId}
            style={{
              color: 'var(--text-muted)',
              maxWidth: 160,
            }}
          >
            {analysisId}
          </span>
        )}
      </div>

      {/* Pipeline */}
      <div className="d-flex flex-column gap-2">
        {STEP_ORDER.map((step) => {
          const status =
            stepStatus[step.key] || 'pending';

          const isDone = status === 'done';
          const isActive = status === 'active';
          const isSkipped = status === 'skipped';

          const icon = isDone
            ? 'bi-check-circle-fill'
            : isActive
              ? 'bi-arrow-repeat'
              : isSkipped
                ? 'bi-dash-circle'
                : 'bi-circle';

          const color = isDone
            ? 'var(--success)'
            : isActive
              ? 'var(--accent-cyan)'
              : 'var(--text-muted)';

          return (
            <div
              key={step.key}
              className="d-flex align-items-center gap-2"
            >
              <i
                className={`bi ${icon} ${
                  isActive ? 'analysis-spin' : ''
                }`}
                style={{
                  color,
                  fontSize: '0.95rem',
                }}
              />

              <span
                className="small"
                style={{
                  color:
                    status === 'pending' || isSkipped
                      ? 'var(--text-muted)'
                      : 'var(--text-primary)',
                }}
              >
                {step.label}

                {isSkipped && (
                  <span className="ms-1">
                    · skipped
                  </span>
                )}
              </span>
            </div>
          );
        })}
      </div>

      {/* Voting */}
      {totalVotes > 0 && (
        <div>
          <div
            className="small fw-semibold mb-2"
            style={{ color: 'var(--text-muted)' }}
          >
            LIVE MODEL POLL
          </div>

          {Object.entries(votes).map(
            ([label, rawCount]) => {
              const count = Number(rawCount) || 0;
              const percentage =
                totalVotes > 0
                  ? (count / totalVotes) * 100
                  : 0;

              return (
                <div
                  key={label}
                  className="d-flex align-items-center gap-2 mb-2"
                >
                  <span
                    className="small"
                    style={{
                      width: 55,
                      color: 'var(--text-secondary)',
                    }}
                  >
                    {label}
                  </span>

                  <div
                    className="progress flex-grow-1"
                    style={{
                      height: 8,
                      background: 'var(--bg-elevated)',
                    }}
                    role="progressbar"
                    aria-label={`${label} votes`}
                    aria-valuenow={percentage}
                    aria-valuemin={0}
                    aria-valuemax={100}
                  >
                    <div
                      className="progress-bar"
                      style={{
                        width: `${percentage}%`,
                        background:
                          'linear-gradient(90deg, var(--accent-blue), var(--accent-cyan))',
                        transition: 'width 250ms ease',
                      }}
                    />
                  </div>

                  <span
                    className="small fw-bold"
                    style={{
                      minWidth: 20,
                      textAlign: 'right',
                      color: 'var(--text-primary)',
                    }}
                  >
                    {count}
                  </span>
                </div>
              );
            },
          )}
        </div>
      )}

      {/* Models */}
      {models.length > 0 && (
        <div className="d-flex flex-column gap-2">
          <div
            className="small fw-semibold"
            style={{ color: 'var(--text-muted)' }}
          >
            MODEL RESPONSES
          </div>

          {models.map((model) => (
            <ModelResult
              key={modelKey(model)}
              model={model}
            />
          ))}
        </div>
      )}

      {/* Articles */}
      {articles.length > 0 && (
        <div
          className="small"
          style={{ color: 'var(--text-muted)' }}
        >
          <i className="bi bi-newspaper me-1" />

          {analyzedArticleCount} of {articles.length}{' '}
          related article
          {articles.length === 1 ? '' : 's'} analyzed
        </div>
      )}
    </div>
  );
}