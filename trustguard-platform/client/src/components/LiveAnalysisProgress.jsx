import { useEffect, useRef, useState } from 'react';

const STEP_ORDER = [
  { key: 'claim', label: 'Understanding claim', events: ['claim_extraction_started', 'claim_extracted', 'claim_extraction_failed'] },
  { key: 'poll', label: 'Polling ML models', events: ['model_started', 'model_completed', 'model_unavailable', 'vote_added'] },
  { key: 'temporal', label: 'Checking currentness', events: ['temporal_classified'] },
  { key: 'search', label: 'Searching for related coverage', events: ['search_started', 'search_completed', 'search_skipped', 'search_failed'] },
  { key: 'articles', label: 'Analyzing related articles', events: ['article_found', 'article_extracted', 'article_analyzed'] },
  { key: 'cluster', label: 'Building source clusters', events: ['source_clustering_started', 'source_cluster_created'] },
  { key: 'synthesis', label: 'Generating final assessment', events: ['cross_evidence_started', 'cross_evidence_completed'] },
];

async function* readSSE(response) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let boundary;
    while ((boundary = buffer.indexOf('\n\n')) !== -1) {
      const frame = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);

      let eventType = 'message';
      let data = '';
      for (const line of frame.split('\n')) {
        if (line.startsWith('event: ')) eventType = line.slice(7).trim();
        else if (line.startsWith('data: ')) data += line.slice(6);

      }
      if (data) {
        try {
          yield { type: eventType, data: JSON.parse(data) };
        } catch {
          // Malformed frame — skip rather than crash the stream reader.
        }
      }
    }
  }
}

export default function LiveAnalysisProgress({ streamUrl, payload, geminiApiKey, onComplete, onError }) {
  const [stepStatus, setStepStatus] = useState({});
  const [models, setModels] = useState([]); // [{model, label, confidence, status}]
  const [votes, setVotes] = useState({});
  const [articles, setArticles] = useState([]);
  const [logLines, setLogLines] = useState([]);
  const abortRef = useRef(null);

  useEffect(() => {
    const controller = new AbortController();
    abortRef.current = controller;

    (async () => {
      try {
        const headers = { 'Content-Type': 'application/json' };
        if (geminiApiKey) headers['X-Gemini-API-Key'] = geminiApiKey;

        const response = await fetch(streamUrl, {
          method: 'POST', headers, body: JSON.stringify(payload), signal: controller.signal,
        });


        if (!response.ok || !response.body) {
          throw new Error(`Live analysis stream failed (HTTP ${response.status}).`);
        }

        for await (const evt of readSSE(response)) {
          setLogLines((prev) => [...prev.slice(-49), evt]);

          const step = STEP_ORDER.find((s) => s.events.includes(evt.type));
          if (step) {
            setStepStatus((prev) => ({ ...prev, [step.key]: 'active' }));
          }

          if (evt.type === 'model_started' || evt.type === 'model_completed' || evt.type === 'model_unavailable') {
            setModels((prev) => {
              const others = prev.filter((m) => m.model !== evt.data.model || m.articleId !== evt.data.articleId);
              return [...others, {
                model: evt.data.model, articleId: evt.data.articleId,
                status: evt.type === 'model_started' ? 'running' : evt.type === 'model_completed' ? 'done' : 'unavailable',
                label: evt.data.label, confidence: evt.data.confidence,
              }];
            });
          }

          if (evt.type === 'vote_added') setVotes(evt.data.votes || {});

          if (evt.type === 'article_analyzed') {
            setArticles((prev) => [...prev.filter((a) => a.id !== evt.data.id), evt.data]);
          }

          if (['claim_extracted', 'search_completed', 'search_skipped', 'search_failed', 'source_cluster_created']
            .includes(evt.type)) {

            const s = STEP_ORDER.find((x) => x.events.includes(evt.type));
            if (s) setStepStatus((prev) => ({ ...prev, [s.key]: 'done' }));
          }

          if (evt.type === 'cross_evidence_completed') {
            setStepStatus((prev) => ({ ...prev, synthesis: 'done' }));
          }

          if (evt.type === 'error') {
            onError?.(evt.data.message || 'Live analysis reported an error.');
          }

          if (evt.type === 'final_result') {
            onComplete?.(evt.data);
          }
        }
      } catch (err) {
        if (err?.name !== 'AbortError') onError?.(err.message || 'Live analysis connection failed.');
      }
    })();

    return () => controller.abort();
  }, [streamUrl, payload, geminiApiKey, onComplete, onError]);

  const totalVotes = Object.values(votes).reduce((a, b) => a + b, 0) || 0;

  return (
    <div className="d-flex flex-column gap-3">
      <div className="d-flex flex-column gap-2">
        {STEP_ORDER.map((step) => {
          const status = stepStatus[step.key] || 'pending';
          const icon = status === 'done' ? 'bi-check-circle-fill' : status === 'active' ? 'bi-arrow-repeat' : 'bi-circle';

          const color = status === 'done' ? 'var(--success)' : status === 'active' ? 'var(--accent-cyan)' : 'var(--text-muted)';
          return (
            <div key={step.key} className="d-flex align-items-center gap-2">
              <i className={`bi ${icon}`} style={{ color, fontSize: '0.95rem' }} />
              <span className="small" style={{ color: status === 'pending' ? 'var(--text-muted)' : 'var(--text-primary)' }}>
                {step.label}
              </span>
            </div>
          );
        })}
      </div>

      {totalVotes > 0 && (
        <div>
          <div className="small fw-semibold mb-1" style={{ color: 'var(--text-muted)' }}>LIVE MODEL POLL</div>
          {Object.entries(votes).map(([label, count]) => (
            <div key={label} className="d-flex align-items-center gap-2 mb-1">
              <span className="small" style={{ width: 50, color: 'var(--text-secondary)' }}>{label}</span>
              <div className="progress flex-grow-1" style={{ height: 8, background: 'var(--bg-elevated)' }}>
                <div
                  className="progress-bar"
                  style={{ width: `${(count / totalVotes) * 100}%`, background: 'linear-gradient(90deg, var(--accent-blue), var(--accent-cyan))' }}
                />
              </div>
              <span className="small fw-bold" style={{ color: 'var(--text-primary)' }}>{count}</span>
            </div>
          ))}
        </div>
      )}

      {models.length > 0 && (
        <div className="d-flex flex-column gap-1">

          {models.map((m, i) => (
            <div key={`${m.model}-${m.articleId || 'primary'}-${i}`} className="d-flex justify-content-between small">
              <span style={{ color: 'var(--text-secondary)' }}>
                {m.model}{m.articleId ? ' (related article)' : ''}
              </span>
              <span style={{ color: m.status === 'unavailable' ? 'var(--text-muted)' : m.label === 'Fake' ? 'var(--danger)' : 'var(--success)' }}>
                {m.status === 'running' ? 'analyzing…' : m.status === 'unavailable' ? 'NO VOTE' : m.label}
              </span>
            </div>
          ))}
        </div>
      )}

      {articles.length > 0 && (
        <div className="small" style={{ color: 'var(--text-muted)' }}>
          {articles.length} related article{articles.length === 1 ? '' : 's'} analyzed
        </div>
      )}
    </div>
  );
}