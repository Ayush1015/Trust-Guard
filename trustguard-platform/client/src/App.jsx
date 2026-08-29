import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import Navbar from "./components/Navbar";
import AuthModal from "./components/AuthModal";
import TabNavigation from "./components/TabNavigation";
import NewsInput from "./components/NewsInput";
import ReviewInput from "./components/ReviewInput";
import PhishingInput from "./components/PhishingInput";
import ResultCard from "./components/ResultCard";
import EvidenceDashboard from "./components/EvidenceDashboard";
import LiveAnalysisProgress from "./components/LiveAnalysisProgress";

const API_BASE_URL = (
  import.meta.env.VITE_API_URL ||
  "http://localhost:5000/api/v1"
).replace(/\/+$/, "");

const REQUEST_TIMEOUT = Number(
  import.meta.env.VITE_REQUEST_TIMEOUT || 120000
);

const GEMINI_CONNECT_URL =
  import.meta.env.VITE_GEMINI_CONNECT_URL ||
  "https://aistudio.google.com/apikey";

const THEME_STORAGE_KEY = "trustguard:theme";
const AUTH_STORAGE_KEY = "trustguard:user";

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

function clean(value) {
  return typeof value === "string" ? value.trim() : "";
}

function normalizePayload(tab, payload = {}) {
  if (tab === "news") {
    const headline = clean(payload.headline);
    const articleUrl = clean(payload.article_url);
    const articleText = clean(payload.article_text);

    return {
      ...payload,
      text: clean(payload.text) || headline,
      headline,
      article_url: articleUrl,
      article_text: articleText,
      mode: payload.mode || "auto",
    };
  }

  if (tab === "review") {
    return {
      ...payload,
      text: clean(payload.text),
      product_url: clean(payload.product_url),
    };
  }

  if (tab === "phishing") {
    return { ...payload, url: clean(payload.url) };
  }

  return payload;
}

function hasInput(tab, payload) {
  if (tab === "news") {
    return Boolean(
      payload.headline ||
      payload.article_url ||
      payload.article_text ||
      payload.text
    );
  }

  return tab === "phishing"
    ? Boolean(payload.url)
    : Boolean(payload.text);
}

function modelCount(result) {
  return (
    result?.poll?.totalVotes ??
    result?.metrics?.totalModels ??
    result?.models?.length ??
    0
  );
}

function getWinner(result) {
  return result?.poll?.winner || result?.label || null;
}

function labelTone(label) {
  const value = String(label || "").toLowerCase();

  if (
    value.includes("fake") ||
    value.includes("phishing") ||
    value.includes("malicious")
  ) {
    return "danger";
  }

  if (
    value.includes("real") ||
    value.includes("genuine") ||
    value.includes("safe")
  ) {
    return "success";
  }

  return "info";
}

function ToneBadge({ children, tone = "info" }) {
  const palette = {
    info: {
      color: UI.cyan,
      background: UI.cyanSoft,
      border: UI.cyanBorder,
    },
    success: {
      color: "var(--success)",
      background: "var(--success-glow)",
      border: "color-mix(in srgb, var(--success) 35%, transparent)",
    },
    danger: {
      color: "var(--danger)",
      background: "var(--danger-glow)",
      border: "color-mix(in srgb, var(--danger) 35%, transparent)",
    },
    warning: {
      color: "var(--warning)",
      background: "var(--warning-glow)",
      border: "color-mix(in srgb, var(--warning) 35%, transparent)",
    },
    neutral: {
      color: "var(--text-secondary)",
      background: "var(--bg-elevated)",
      border: "var(--border-color)",
    },
  };

  const p = palette[tone] || palette.info;

  return (
    <span
      className="d-inline-flex align-items-center gap-2 rounded-pill px-3 py-2 small fw-semibold"
      style={{
        color: p.color,
        background: p.background,
        border: `1px solid ${p.border}`,
        lineHeight: 1,
      }}
    >
      {children}
    </span>
  );
}

function SectionCard({ icon, title, subtitle, children, className = "" }) {
  return (
    <section
      className={`glass-card ${className}`}
      style={{
        background: UI.card,
        border: `1px solid ${UI.cardBorder}`,
        borderRadius: 18,
        boxShadow: "var(--shadow-soft)",
      }}
    >
      <div className="p-4 p-md-4">
        {(title || subtitle) && (
          <div className="d-flex align-items-start gap-3 mb-4">
            {icon && (
              <div
                className="d-flex align-items-center justify-content-center rounded-3 flex-shrink-0"
                style={{
                  width: 42,
                  height: 42,
                  background: UI.cyanSoft,
                  border: `1px solid ${UI.cyanBorder}`,
                }}
              >
                <i className={`bi ${icon} text-info`} />
              </div>
            )}

            <div className="min-w-0">
              {title && (
                <h5 className="fw-semibold mb-1" style={{ color: UI.text }}>{title}</h5>
              )}
              {subtitle && (
                <div
                  className="small"
                  style={{ color: UI.muted, lineHeight: 1.55 }}
                >
                  {subtitle}
                </div>
              )}
            </div>
          </div>
        )}

        {children}
      </div>
    </section>
  );
}

async function request(
  endpoint,
  {
    method = "GET",
    body,
    signal,
    timeout = REQUEST_TIMEOUT,
    geminiApiKey = "",
  } = {}
) {
  const controller = new AbortController();
  let timedOut = false;

  const timeoutId = window.setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeout);

  const abortHandler = () => controller.abort();

  if (signal) {
    if (signal.aborted) controller.abort();
    else signal.addEventListener("abort", abortHandler, { once: true });
  }

  try {
    const headers = {
      Accept: "application/json",
      ...(body ? { "Content-Type": "application/json" } : {}),
    };

    if (clean(geminiApiKey)) {
      headers["X-Gemini-API-Key"] = clean(geminiApiKey);
    }

    const response = await fetch(`${API_BASE_URL}${endpoint}`, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });

    const contentType =
      response.headers.get("content-type") || "";
    const raw = await response.text();

    let data = {};

    if (raw.trim()) {
      if (contentType.includes("application/json")) {
        try {
          data = JSON.parse(raw);
        } catch {
          throw new Error("The API returned invalid JSON.");
        }
      } else {
        throw new Error(
          response.status === 404
            ? "API route not found. Check the Node.js gateway routes."
            : `Server returned an unexpected response (HTTP ${response.status}).`
        );
      }
    }

    if (!response.ok) {
      throw new Error(
        data?.error?.message ||
        data?.detail ||
        data?.message ||
        `Request failed with HTTP ${response.status}.`
      );
    }

    return data;
  } catch (error) {
    if (error?.name === "AbortError") {
      if (timedOut) {
        throw new Error(
          "The request timed out. The ML/Gemini analysis may be taking too long."
        );
      }
      throw error;
    }

    if (error instanceof TypeError) {
      throw new Error(
        "Cannot connect to the TrustGuard API gateway. Make sure the Node.js server is running."
      );
    }

    throw error;
  } finally {
    window.clearTimeout(timeoutId);
    if (signal) {
      signal.removeEventListener("abort", abortHandler);
    }
  }
}

function App() {
  const [activeTab, setActiveTab] = useState("news");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [backend, setBackend] = useState({
    status: "checking",
    models: null,
  });
  const [lastPayload, setLastPayload] = useState(null);

  const [theme, setTheme] = useState(() => {
    if (typeof window === "undefined") return "dark";
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    if (stored === "light" || stored === "dark") return stored;
    return window.matchMedia?.("(prefers-color-scheme: light)").matches
      ? "light"
      : "dark";
  });

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  }, [theme]);

  const toggleTheme = useCallback(() => {
    setTheme((prev) => (prev === "dark" ? "light" : "dark"));
  }, []);

  const [authModalMode, setAuthModalMode] = useState(null);
  const [user, setUser] = useState(() => {
    if (typeof window === "undefined") return null;
    try {
      const stored = window.localStorage.getItem(AUTH_STORAGE_KEY);
      return stored ? JSON.parse(stored) : null;
    } catch {
      return null;
    }
  });

  const handleAuthenticated = useCallback((nextUser) => {
    setUser(nextUser);
    window.localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(nextUser));
    setAuthModalMode(null);
  }, []);

  const handleLogout = useCallback(() => {
    setUser(null);
    window.localStorage.removeItem(AUTH_STORAGE_KEY);
  }, []);

  const [geminiApiKey, setGeminiApiKey] = useState("");
  const [showGeminiKey, setShowGeminiKey] = useState(false);
  const [showGeminiPassword, setShowGeminiPassword] = useState(false);
  const [geminiConfigured, setGeminiConfigured] = useState(false);

  const controllerRef = useRef(null);
  const mountedRef = useRef(true);
  const [liveMode, setLiveMode] = useState(false);

  const saveGeminiKey = useCallback(() => {
    const key = clean(geminiApiKey);
    if (!key) return;

    setGeminiApiKey(key);
    setGeminiConfigured(true);
    setShowGeminiKey(false);
  }, [geminiApiKey]);

  const clearGeminiKey = useCallback(() => {
    setGeminiApiKey("");
    setGeminiConfigured(false);
    setShowGeminiPassword(false);
  }, []);

  useEffect(() => {
    mountedRef.current = true;

    return () => {
      mountedRef.current = false;
      controllerRef.current?.abort();
    };
  }, []);

  const refreshHealth = useCallback(async () => {
    try {
      const data = await request("/analyze/health", { timeout: 5000 });

      if (!mountedRef.current) return;

      setBackend({
        status: "online",
        models: data?.models || null,
      });
    } catch (healthError) {
      if (!mountedRef.current) return;

      console.warn(
        "TrustGuard health check failed:",
        healthError?.message
      );

      setBackend({
        status: "offline",
        models: null,
      });
    }
  }, []);

  useEffect(() => {
    void refreshHealth();

    const timer = window.setInterval(refreshHealth, 30000);

    return () => window.clearInterval(timer);
  }, [refreshHealth]);

  const changeTab = useCallback(
    (tab) => {
      if (loading) return;

      setActiveTab(tab);
      setResult(null);
      setError("");
      setLastPayload(null);
    },
    [loading]
  );

  const analyze = useCallback(
    async (payload) => {
      if (loading) return;

      const normalized = normalizePayload(activeTab, payload);

      if (!hasInput(activeTab, normalized)) {
        setError(
          activeTab === "news"
            ? "Enter a headline, article URL, or article text."
            : activeTab === "phishing"
              ? "Enter a URL to analyze."
              : "Enter review text to analyze."
        );
        return;
      }

      controllerRef.current?.abort();

      const controller = new AbortController();
      controllerRef.current = controller;

      setLoading(true);
      setResult(null);
      setError("");
      setLastPayload(normalized);

      // Live mode (news only) hands the request off entirely to
      // LiveAnalysisProgress, which owns its own SSE connection and
      // reports back via onComplete/onError. Nothing else to do here —
      // and critically, we must NOT also fire the blocking request below,
      // or two competing analyses would race for the same result.
      if (activeTab === "news" && liveMode) {
        return;
      }

      try {
        const data = await request(`/analyze/${activeTab}`, {
          method: "POST",
          body: normalized,
          signal: controller.signal,
          timeout: activeTab === "news" ? 180000 : 60000,
          geminiApiKey,
        });

        if (!mountedRef.current) return;

        setResult(data);
        void refreshHealth();
      } catch (analysisError) {
        if (analysisError?.name === "AbortError") return;
        if (!mountedRef.current) return;

        console.error("TrustGuard analysis failed:", analysisError);
        setError(analysisError?.message || "Analysis failed.");
      } finally {
        if (
          mountedRef.current &&
          controllerRef.current === controller
        ) {
          controllerRef.current = null;
          setLoading(false);
        }
      }
    },
    [
      activeTab,
      geminiApiKey,
      liveMode,
      loading,
      refreshHealth,
    ]
  );

  const cancel = useCallback(() => {
    controllerRef.current?.abort();
    controllerRef.current = null;
    setLoading(false);
    setError("Analysis cancelled.");
  }, []);

  const retry = useCallback(() => {
    if (!lastPayload || loading) return;
    void analyze(lastPayload);
  }, [analyze, lastPayload, loading]);

  const clear = useCallback(() => {
    if (loading) return;
    setResult(null);
    setError("");
    setLastPayload(null);
  }, [loading]);

  const activeModelCount = useMemo(() => {
    if (backend.models?.totalActive != null) {
      return backend.models.totalActive;
    }
    return modelCount(result);
  }, [backend.models, result]);

  const resultModelCount = useMemo(
    () => modelCount(result),
    [result]
  );

  const resultWinner = useMemo(
    () => getWinner(result),
    [result]
  );

  const relatedSources = useMemo(() => {
    const sources =
      result?.relatedNews ||
      result?.webVerification?.sources ||
      [];

    if (!Array.isArray(sources)) return [];

    const seen = new Set();

    return sources.filter((source) => {
      const url = clean(source?.url);

      if (!url || seen.has(url)) return false;

      seen.add(url);
      return true;
    });
  }, [result]);

  const geminiAvailable = Boolean(
    result?.webVerification?.available
  );

  const statusLabel =
    backend.status === "online"
      ? "ML Engine Online"
      : backend.status === "checking"
        ? "Checking ML Engine"
        : "ML Engine Offline";

  return (
    <div
      className="d-flex flex-column min-vh-100"
      style={{ color: UI.text }}
    >
      <Navbar
        theme={theme}
        onToggleTheme={toggleTheme}
        onOpenAuth={setAuthModalMode}
        isAuthenticated={Boolean(user)}
        user={user}
        onLogout={handleLogout}
        backendStatus={backend.status}
      />

      {authModalMode && (
        <AuthModal
          mode={authModalMode}
          onClose={() => setAuthModalMode(null)}
          onAuthenticated={handleAuthenticated}
        />
      )}

      <main className="container flex-grow-1 py-4 py-lg-5">
        {/* HERO */}
        <section className="text-center mb-4 mb-lg-5 hero-stage">
          <div className="hero-orbit" aria-hidden="true" />
          <ToneBadge
            tone={
              backend.status === "online"
                ? "success"
                : backend.status === "checking"
                  ? "warning"
                  : "danger"
            }
          >
            <span
              className="rounded-circle"
              style={{
                width: 7,
                height: 7,
                background:
                  backend.status === "online"
                    ? "var(--success)"
                    : backend.status === "checking"
                      ? "var(--warning)"
                      : "var(--danger)",
              }}
            />
            {statusLabel}
          </ToneBadge>

          <h1
            className="display-5 fw-bold mt-3 mb-2"
            style={{ letterSpacing: "-.025em", color: UI.text }}
          >
            Verifiable Digital Intelligence
          </h1>

          <p
            className="mx-auto mb-0"
            style={{
              maxWidth: 720,
              color: UI.muted,
              fontSize: "1.04rem",
              lineHeight: 1.7,
            }}
          >
            {user ? `Welcome back, ${user.name}. ` : ""}
            Detect misinformation, fake reviews and phishing URLs
            with compatible ML models, ensemble voting and optional
            Gemini web verification.
          </p>
        </section>

        {/* STATUS */}
        <div className="row g-3 mb-4">
          <div className="col-md-4">
            <StatusCard
              icon="bi-cpu"
              title="ML Ensemble"
              value={
                activeModelCount > 0
                  ? `${activeModelCount} active models`
                  : "No models loaded"
              }
              detail={
                backend.status === "online"
                  ? "Live backend status"
                  : "Backend unavailable"
              }
            />
          </div>

          <div className="col-md-4">
            <StatusCard
              icon="bi-stars"
              title="Gemini"
              value={
                geminiConfigured
                  ? "Your key configured"
                  : geminiAvailable
                    ? "Web verification active"
                    : "Optional verification"
              }
              detail={
                geminiConfigured
                  ? "Used on the next analysis request"
                  : "Use your own key or server fallback"
              }
              action={
                <button
                  type="button"
                  className="btn btn-sm btn-outline-info"
                  onClick={() => setShowGeminiKey(true)}
                >
                  {geminiConfigured ? "Edit" : "Configure"}
                </button>
              }
            />
          </div>

          <div className="col-md-4">
            <StatusCard
              icon="bi-bar-chart-fill"
              title="Model Poll"
              value={
                resultWinner
                  ? `Winner: ${resultWinner}`
                  : "Ready"
              }
              detail={
                result
                  ? `${resultModelCount} participating votes`
                  : "Only successful predictions vote"
              }
            />
          </div>
        </div>

        {/* GEMINI CONFIGURATION */}
        {showGeminiKey && (
          <SectionCard
            icon="bi-stars"
            title="Configure Gemini"
            subtitle="Use your own Gemini API key for the current browser session. The key is kept in memory and sent only with analysis requests."
            className="mb-4"
          >
            <div className="row g-3 align-items-end">
              <div className="col-lg-8">
                <label
                  htmlFor="gemini-key"
                  className="form-label small fw-semibold"
                  style={{ color: UI.text }}
                >
                  Gemini API key
                </label>

                <div className="input-group">
                  <input
                    id="gemini-key"
                    type={
                      showGeminiPassword
                        ? "text"
                        : "password"
                    }
                    className="form-control form-control-custom"
                    placeholder="Paste your Gemini API key"
                    value={geminiApiKey}
                    onChange={(event) =>
                      setGeminiApiKey(event.target.value)
                    }
                    autoComplete="off"
                  />

                  <button
                    type="button"
                    className="btn btn-outline-secondary"
                    onClick={() =>
                      setShowGeminiPassword(
                        (value) => !value
                      )
                    }
                    aria-label={
                      showGeminiPassword
                        ? "Hide Gemini API key"
                        : "Show Gemini API key"
                    }
                  >
                    <i
                      className={
                        showGeminiPassword
                          ? "bi bi-eye-slash"
                          : "bi bi-eye"
                      }
                    />
                  </button>
                </div>
              </div>

              <div className="col-lg-4">
                <div className="d-flex gap-2">
                  <button
                    type="button"
                    className="btn btn-info flex-grow-1"
                    disabled={!clean(geminiApiKey)}
                    onClick={saveGeminiKey}
                  >
                    <i className="bi bi-check2-circle me-2" />
                    Use This Key
                  </button>

                  <button
                    type="button"
                    className="btn btn-outline-secondary"
                    onClick={() => setShowGeminiKey(false)}
                  >
                    Close
                  </button>
                </div>
              </div>
            </div>

            <div className="d-flex flex-wrap gap-3 align-items-center mt-3">
              <span
                className="small"
                style={{ color: UI.muted }}
              >
                <i className="bi bi-shield-lock me-2 text-info" />
                Never logged or stored by this component.
              </span>

              <a
                href={GEMINI_CONNECT_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="small text-decoration-none"
                style={{ color: UI.cyan }}
              >
                Get a Gemini API key
                <i className="bi bi-box-arrow-up-right ms-1" />
              </a>

              {geminiConfigured && (
                <button
                  type="button"
                  className="btn btn-link btn-sm text-danger text-decoration-none p-0"
                  onClick={clearGeminiKey}
                >
                  Clear key
                </button>
              )}
            </div>
          </SectionCard>
        )}

        {/* MODULE */}
        <SectionCard
          icon={
            activeTab === "news"
              ? "bi-newspaper"
              : activeTab === "review"
                ? "bi-star"
                : "bi-shield-lock"
          }
          title={
            activeTab === "news"
              ? "News Verification"
              : activeTab === "review"
                ? "Review Verification"
                : "Phishing URL Analysis"
          }
          subtitle={
            activeTab === "news"
              ? "Check a headline, URL, article text, or combine multiple sources for stronger verification."
              : activeTab === "review"
                ? "Evaluate a product review using compatible local and pretrained classifiers."
                : "Analyze URL structure and available phishing classifiers."
          }
          className="mb-4"
        >
          <TabNavigation
            activeTab={activeTab}
            setActiveTab={changeTab}
          />

          <div
            className={`verification-seal ${loading ? "is-scanning" : result ? "is-flipped" : ""}`}
            aria-hidden="true"
          >
            <div className="verification-seal-inner">
              <div className="verification-seal-face verification-seal-front">
                <i className="bi bi-shield-lock" />
                <span>READY</span>
              </div>
              <div className="verification-seal-face verification-seal-back">
                <i className={`bi ${result ? "bi-check-lg" : "bi-search"}`} />
                <span>{result?.label || "VERIFYING"}</span>
              </div>
            </div>
          </div>

          {activeTab === "news" && (
            <div className="form-check form-switch mb-2">
              <input
                className="form-check-input"
                type="checkbox"
                id="live-mode"
                checked={liveMode}
                onChange={(e) => setLiveMode(e.target.checked)}
              />
              <label
                className="form-check-label small"
                htmlFor="live-mode"
                style={{ color: "var(--text-secondary)" }}
              >
                Live analysis (show progress in real time)
              </label>
            </div>
          )}

          <div className="mt-4">
            {activeTab === "news" && (
              <NewsInput
                onSubmit={analyze}
                loading={loading}
              />
            )}

            {activeTab === "review" && (
              <ReviewInput
                onSubmit={analyze}
                loading={loading}
              />
            )}

            {activeTab === "phishing" && (
              <PhishingInput
                onSubmit={analyze}
                loading={loading}
              />
            )}
          </div>
        </SectionCard>

        {/* LOADING */}
        {loading && (
          <SectionCard className="mb-4">
            <div
              className="d-flex align-items-center gap-3"
              role="status"
              aria-live="polite"
              aria-busy="true"
            >
              <div className="scan-orbit" role="status">
                <span className="visually-hidden">Loading...</span>
              </div>

              <div className="flex-grow-1">
                <div className="fw-semibold" style={{ color: UI.text }}>
                  Running TrustGuard analysis
                </div>
                <div className="small mt-1" style={{ color: UI.muted }}>
                  {activeTab === "news" && liveMode ? (
                    <LiveAnalysisProgress
                      streamUrl={`${API_BASE_URL}/analyze/news/stream`}
                      payload={lastPayload}
                      geminiApiKey={geminiApiKey}
                      onComplete={(finalResult) => {
                        setResult(finalResult);
                        setLoading(false);
                      }}
                      onError={(message) => {
                        setError(message);
                        setLoading(false);
                      }}
                    />
                  ) : activeTab === "news" ? (
                    "Polling compatible news models and optional web evidence..."
                  ) : activeTab === "review" ? (
                    "Polling compatible review models..."
                  ) : (
                    "Analyzing URL features and phishing models..."
                  )}
                </div>
              </div>

              <button
                type="button"
                className="btn btn-sm btn-outline-danger"
                onClick={cancel}
              >
                Cancel
              </button>
            </div>

            <div
              className="progress mt-3"
              style={{
                height: 4,
                background: "var(--bg-elevated)",
              }}
            >
              <div
                className="progress-bar progress-bar-striped progress-bar-animated bg-info"
                style={{ width: "100%" }}
              />
            </div>
          </SectionCard>
        )}

        {/* ERROR */}
        {error && !loading && (
          <SectionCard
            icon="bi-exclamation-triangle"
            title="Analysis Halt"
            subtitle={error}
            className="mb-4"
          >
            <div className="d-flex flex-wrap gap-2">
              {lastPayload && (
                <button
                  type="button"
                  className="btn btn-sm btn-outline-light"
                  onClick={retry}
                >
                  <i className="bi bi-arrow-repeat me-1" />
                  Retry
                </button>
              )}

              <button
                type="button"
                className="btn btn-sm btn-outline-secondary"
                onClick={refreshHealth}
              >
                <i className="bi bi-heart-pulse me-1" />
                Check Server
              </button>
            </div>
          </SectionCard>
        )}

        {/* RESULTS */}
        {result && !error && (
          <>
            <div className="mb-4">
              <ResultCard result={result} type={activeTab} />
            </div>

            {activeTab === "news" && (
              <EvidenceDashboard result={result} />
            )}

            {/* POLL */}
            {result.poll && (
              <SectionCard
                icon="bi-bar-chart-fill"
                title="Model Poll"
                subtitle="Only compatible models that successfully returned a prediction are counted."
                className="mb-4"
              >
                <div className="row g-3">
                  {Object.entries(result.poll.votes || {}).map(
                    ([label, votes]) => (
                      <div className="col-md-6" key={label}>
                        <div
                          className="p-3 rounded-3 h-100"
                          style={{
                            background: "var(--bg-elevated)",
                            border: `1px solid ${UI.cardBorder}`,
                          }}
                        >
                          <div className="d-flex justify-content-between align-items-center">
                            <span className="fw-semibold" style={{ color: UI.text }}>
                              {label}
                            </span>
                            <ToneBadge tone={labelTone(label)}>
                              {votes} vote{votes === 1 ? "" : "s"}
                            </ToneBadge>
                          </div>
                        </div>
                      </div>
                    )
                  )}
                </div>

                <div
                  className="d-flex flex-wrap justify-content-between align-items-center gap-3 mt-4 pt-3"
                  style={{ borderTop: `1px solid ${UI.cardBorder}` }}
                >
                  <div>
                    <span className="small" style={{ color: UI.muted }}>
                      Final winner
                    </span>
                    <div className="fw-bold fs-5" style={{ color: UI.text }}>
                      {result.poll.winner || "Unknown"}
                    </div>
                  </div>

                  <div className="text-md-end">
                    <span className="small" style={{ color: UI.muted }}>
                      Vote confidence
                    </span>
                    <div className="fw-bold fs-5" style={{ color: UI.cyan }}>
                      {result.poll.confidence ?? "N/A"}
                      {result.poll.confidence != null ? "%" : ""}
                    </div>
                  </div>
                </div>
              </SectionCard>
            )}

            {/* MODEL DETAILS */}
            {Array.isArray(result.models) && result.models.length > 0 && (
              <SectionCard
                icon="bi-cpu"
                title="Model Outputs"
                subtitle="Individual predictions used to calculate the ensemble result."
                className="mb-4"
              >
                <div className="table-responsive">
                  <table
                    className="table table-dark align-middle mb-0"
                    style={{
                      "--bs-table-bg": "transparent",
                      "--bs-table-border-color": "var(--border-color)",
                      color: UI.text,
                    }}
                  >
                    <thead>
                      <tr>
                        <th className="small" style={{ color: UI.muted }}>MODEL</th>
                        <th className="small" style={{ color: UI.muted }}>VOTE</th>
                        <th className="small" style={{ color: UI.muted }}>CONFIDENCE</th>
                      </tr>
                    </thead>

                    <tbody>
                      {result.models.map((model, index) => (
                        <tr key={model.model || `${index}`}>
                          <td className="fw-medium" style={{ color: UI.text }}>
                            {model.model}
                          </td>
                          <td>
                            <ToneBadge tone={labelTone(model.label)}>
                              {model.label}
                            </ToneBadge>
                          </td>
                          <td style={{ color: UI.muted }}>
                            {model.confidence != null ? `${model.confidence}%` : "N/A"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </SectionCard>
            )}

            {/* WEB VERIFICATION */}
            {activeTab === "news" && result.webVerification && (
              <SectionCard
                icon="bi-globe2"
                title="Web Verification"
                subtitle="Gemini-assisted analysis and current web evidence."
                className="mb-4"
              >
                <div className="d-flex flex-wrap align-items-center gap-2 mb-3">
                  {(() => {
                    const wv = result.webVerification;
                    const isOffline = wv.mode === "offline";
                    const tone = !wv.available ? "neutral" : isOffline ? "warning" : "success";
                    const badgeLabel = !wv.available
                      ? "UNAVAILABLE"
                      : isOffline
                        ? "OFFLINE MODE"
                        : "ACTIVE";
                    const icon = !wv.available
                      ? "bi-dash-circle"
                      : isOffline
                        ? "bi-wifi-off"
                        : "bi-check-circle";
                    return (
                      <ToneBadge tone={tone}>
                        <i className={`bi ${icon}`} />
                        {badgeLabel}
                      </ToneBadge>
                    );
                  })()}

                  {result.webVerification.vote &&
                    result.webVerification.vote !== "Unknown" && (
                      <ToneBadge tone={labelTone(result.webVerification.vote)}>
                        {result.webVerification.mode === "offline" ? "Offline check" : "Gemini"}:{" "}
                        {result.webVerification.vote}
                      </ToneBadge>
                    )}
                </div>

                {result.webVerification.explanation && (
                  <p
                    className="mb-0"
                    style={{
                      color: UI.muted,
                      lineHeight: 1.7,
                      whiteSpace: "pre-wrap",
                    }}
                  >
                    {result.webVerification.explanation}
                  </p>
                )}
              </SectionCard>
            )}

            {activeTab === "news" && result?.pibFactCheck?.covered && (
              <SectionCard
                icon="bi-bank"
                title="PIB Fact Check"
                subtitle="Verdict from India's Press Information Bureau fact-check unit."
                className="mb-4"
              >
                <div className="d-flex flex-wrap align-items-center gap-2 mb-3">
                  <ToneBadge tone={labelTone(result?.pibFactCheck?.vote)}>
                    PIB: {result?.pibFactCheck?.vote}
                  </ToneBadge>
                </div>
                {result?.pibFactCheck?.explanation && (
                  <p className="mb-0" style={{ color: UI.muted, whiteSpace: "pre-wrap", lineHeight: 1.6 }}>
                    {result.pibFactCheck.explanation}
                  </p>
                )}
              </SectionCard>
            )}

            {activeTab === "news" &&
              result?.urlTrust?.embedded?.checked?.length > 0 && (
                <SectionCard
                  icon="bi-link-45deg"
                  title="URL Trust Analysis"
                  subtitle="Links found inside the article/headline, checked for phishing-style red flags."
                  className="mb-4"
                >
                  {result.urlTrust.embedded.checked.map((u, i) => (
                    <div
                      key={i}
                      className="d-flex justify-content-between align-items-center gap-2 p-2 mb-2 rounded"
                      style={{ background: "rgba(255,255,255,.03)" }}
                    >
                      <span className="small text-truncate" style={{ maxWidth: "70%" }}>
                        {u.url}
                      </span>
                      <ToneBadge tone={u.trusted ? "success" : "danger"}>
                        {u.trusted ? "Trusted" : u.reasons?.join(", ") || "Untrusted"}
                      </ToneBadge>
                    </div>
                  ))}
                </SectionCard>
              )}

            {/* RELATED NEWS */}
            {activeTab === "news" && relatedSources.length > 0 && (
              <SectionCard
                icon="bi-newspaper"
                title="Related Sources"
                subtitle="External articles and evidence returned by the verification pipeline."
                className="mb-4"
              >
                <div className="d-grid gap-2">
                  {relatedSources.map((source, index) => (
                    <a
                      key={source.url || index}
                      href={source.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-decoration-none"
                      style={{ color: UI.text }}
                    >
                      <div
                        className="p-3 rounded-3 d-flex align-items-start gap-3"
                        style={{
                          background: "var(--bg-elevated)",
                          border: `1px solid ${UI.cardBorder}`,
                        }}
                      >
                        <span className="fw-bold" style={{ color: UI.cyan }}>
                          {index + 1}
                        </span>

                        <div className="min-w-0">
                          <div className="fw-semibold">
                            {source.title || source.url}
                          </div>
                          <div className="small text-truncate mt-1" style={{ color: UI.subtle }}>
                            {source.url}
                          </div>
                        </div>

                        <i className="bi bi-box-arrow-up-right ms-auto" style={{ color: UI.subtle }} />
                      </div>
                    </a>
                  ))}
                </div>
              </SectionCard>
            )}

            {/* RESULT ACTIONS */}
            <div className="d-flex justify-content-end gap-2 mb-5">
              <button
                type="button"
                className="btn btn-outline-secondary"
                onClick={clear}
              >
                <i className="bi bi-x-circle me-1" />
                Clear
              </button>

              <button
                type="button"
                className="btn btn-outline-info"
                onClick={async () => {
                  try {
                    await navigator.clipboard.writeText(
                      JSON.stringify(result, null, 2)
                    );
                  } catch {
                    setError("Unable to copy the result.");
                  }
                }}
              >
                <i className="bi bi-clipboard me-1" />
                Copy JSON
              </button>
            </div>
          </>
        )}
      </main>

      <footer
        className="mt-auto py-4"
        style={{
          borderTop: `1px solid ${UI.cardBorder}`,
          background: "var(--bg-card)",
        }}
      >
        <div className="container">
          <div className="row align-items-center g-3">
            <div className="col-md">
              <div className="fw-semibold" style={{ color: UI.text }}>
                TrustGuard Digital Forensics
              </div>
              <div className="small mt-1" style={{ color: UI.subtle }}>
                ML-assisted verification with optional Gemini web evidence.
              </div>
            </div>

            <div className="col-md-auto">
              <div className="d-flex flex-wrap gap-2">
                <FooterPill label="Node.js Gateway" />
                <FooterPill label="Python ML" />
                <FooterPill label="Ensemble Voting" />
                <FooterPill label="Gemini" />
              </div>
            </div>
          </div>

          <div
            className="small text-center mt-4 pt-3"
            style={{
              color: UI.subtle,
              borderTop: `1px solid ${UI.cardBorder}`,
            }}
          >
            © 2026 TrustGuard Digital Forensics. Results are model-based risk assessments,
            not absolute proof.
          </div>
        </div>
      </footer>
    </div>
  );
}

function StatusCard({ icon, title, value, detail, action }) {
  return (
    <div
      className="h-100 p-3 glass-card status-card"
      style={{
        background: UI.card,
        border: `1px solid ${UI.cardBorder}`,
        borderRadius: 16,
        boxShadow: "var(--shadow-soft)",
      }}
    >
      <div className="d-flex align-items-center gap-3">
        <div
          className="d-flex align-items-center justify-content-center rounded-3 flex-shrink-0"
          style={{
            width: 44,
            height: 44,
            background: UI.cyanSoft,
            border: `1px solid ${UI.cyanBorder}`,
          }}
        >
          <i className={`bi ${icon} text-info`} />
        </div>

        <div className="flex-grow-1 min-w-0">
          <div className="small fw-semibold" style={{ color: UI.muted }}>
            {title}
          </div>
          <div className="fw-semibold text-truncate mt-1" style={{ color: UI.text }}>
            {value}
          </div>
          <div className="small text-truncate mt-1" style={{ color: UI.subtle }}>
            {detail}
          </div>
        </div>

        {action && <div>{action}</div>}
      </div>
    </div>
  );
}

function FooterPill({ label }) {
  return (
    <span
      className="small rounded-pill px-3 py-2"
      style={{
        color: UI.muted,
        background: "var(--bg-elevated)",
        border: `1px solid ${UI.cardBorder}`,
      }}
    >
      {label}
    </span>
  );
}

export default App;