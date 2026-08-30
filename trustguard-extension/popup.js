const ext = typeof browser !== "undefined" ? browser : chrome;

function sendMessage(message) {
  return new Promise((resolve) => {
    try {
      ext.runtime.sendMessage(message, (response) => resolve(response || { ok: false }));
    } catch {
      resolve({ ok: false, error: "Extension messaging failed." });
    }
  });
}

function toneFor(label) {
  const v = String(label || "").toLowerCase();
  if (v.includes("fake") || v.includes("phishing") || v.includes("error")) return "tone-danger";
  if (v.includes("real") || v.includes("genuine") || v.includes("safe")) return "tone-success";
  return "tone-warning";
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str ?? "";
  return div.innerHTML;
}

const els = {
  root: document.documentElement,
  themeBtn: document.getElementById("tg-theme-btn"),
  dot: document.getElementById("tg-dot"),
  statusText: document.getElementById("tg-status-text"),
  tabs: document.querySelectorAll(".tg-tab"),
  panels: {
    news: document.getElementById("panel-news"),
    review: document.getElementById("panel-review"),
    phishing: document.getElementById("panel-phishing"),
    history: document.getElementById("panel-history"),
    account: document.getElementById("panel-account"),
  },
  result: document.getElementById("result"),
  loading: document.getElementById("loading"),
  error: document.getElementById("error"),
  successMsg: document.getElementById("success-msg"),
  autoScanToggle: document.getElementById("autoscan-toggle"),
  settingsBtn: document.getElementById("tg-settings-btn"),
  lastEmpty: document.getElementById("last-result-empty"),
  lastResult: document.getElementById("last-result"),
};

// ------------------------------------------------------------
// THEME
// ------------------------------------------------------------

async function applyTheme(theme) {
  if (theme === "system") {
    els.root.removeAttribute("data-theme");
  } else {
    els.root.setAttribute("data-theme", theme);
  }
}

async function initTheme() {
  const stored = await ext.storage.local.get("theme");
  await applyTheme(stored.theme || "system");
}

els.themeBtn.addEventListener("click", async () => {
  const current = els.root.getAttribute("data-theme") || "system";
  const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  const effectiveCurrent = current === "system" ? (prefersDark ? "dark" : "light") : current;
  const next = effectiveCurrent === "light" ? "dark" : "light";

  await applyTheme(next);
  await ext.storage.local.set({ theme: next });
});

// ------------------------------------------------------------
// UI HELPERS
// ------------------------------------------------------------

function clearStateBlocks() {
  els.result.hidden = true;
  els.error.hidden = true;
  els.successMsg.hidden = true;
}

function showResult({ label, confidence, explanation }) {
  clearStateBlocks();
  els.result.hidden = false;
  els.result.innerHTML = `
    <span class="tg-result-label ${toneFor(label)}">${escapeHtml(label ?? "Unknown")}</span>
    ${confidence != null ? `<div class="tg-muted">Confidence: ${confidence}%</div>` : ""}
    ${explanation ? `<div class="tg-result-explanation">${escapeHtml(explanation)}</div>` : ""}
  `;
}

function showError(message) {
  clearStateBlocks();
  els.error.hidden = false;
  els.error.textContent = message;
}

function showSuccess(message) {
  clearStateBlocks();
  els.successMsg.hidden = false;
  els.successMsg.textContent = message;
}

function setLoading(isLoading) {
  els.loading.hidden = !isLoading;
  if (isLoading) {
    els.result.hidden = true;
    els.error.hidden = true;
    els.successMsg.hidden = true;
  }
}

// ------------------------------------------------------------
// TABS
// ------------------------------------------------------------

els.tabs.forEach((btn) => {
  btn.addEventListener("click", () => {
    els.tabs.forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");

    Object.entries(els.panels).forEach(([key, panel]) => {
      panel.hidden = key !== btn.dataset.tab;
    });

    clearStateBlocks();

    if (btn.dataset.tab === "history") loadHistoryTab();
    if (btn.dataset.tab === "account") loadAccountTab();
  });
});

// ------------------------------------------------------------
// SERVER STATUS
// ------------------------------------------------------------

async function refreshStatus() {
  const config = await sendMessage({ action: "trustguard-get-config" });
  const base = (config?.apiBase || "").replace(/\/api\/v1$/, "");

  els.dot.className = "tg-dot checking";
  els.statusText.textContent = "Checking server…";

  try {
    const res = await fetch(`${base}/health`, { method: "GET" });
    if (res.ok) {
      els.dot.className = "tg-dot online";
      els.statusText.textContent = "Server online";
    } else {
      els.dot.className = "tg-dot offline";
      els.statusText.textContent = "Server error";
    }
  } catch {
    els.dot.className = "tg-dot offline";
    els.statusText.textContent = "Server unreachable";
  }
}

// ------------------------------------------------------------
// NEWS (with optional streaming via /analyze/news/stream)
// ------------------------------------------------------------

document.getElementById("news-submit").addEventListener("click", async () => {
  const text = document.getElementById("news-text").value.trim();
  if (text.length < 15) return showError("Enter at least 15 characters.");

  const streaming = document.getElementById("news-stream-toggle").checked;

  if (!streaming) {
    setLoading(true);
    const res = await sendMessage({
      action: "trustguard-analyze-news",
      payload: { headline: text, text },
    });
    setLoading(false);

    if (res.ok) showResult(res.data);
    else showError(res.error || "News analysis failed.");
    return;
  }

  // Streaming path talks directly to the API so we can read the response
  // body incrementally. Assumption: /analyze/news/stream sends
  // newline-delimited JSON chunks (optionally prefixed with "data:", as
  // in SSE) that eventually include a final chunk with label/confidence.
  clearStateBlocks();
  setLoading(true);
  els.result.hidden = false;
  els.result.innerHTML = `<div class="tg-result-explanation" id="stream-output"></div>`;
  const streamOut = document.getElementById("stream-output");

  try {
    const config = await sendMessage({ action: "trustguard-get-config" });
    const auth = await sendMessage({ action: "trustguard-get-auth" });
    const base = config?.apiBase || "http://localhost:5000/api/v1";

    const response = await fetch(`${base}/analyze/news/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(auth?.token ? { Authorization: `Bearer ${auth.token}` } : {}),
      },
      body: JSON.stringify({ headline: text, text }),
    });

    if (!response.ok || !response.body) {
      throw new Error(`Stream request failed (${response.status})`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let latest = null;

    setLoading(false);

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop(); // keep last partial line

      for (const rawLine of lines) {
        const line = rawLine.replace(/^data:\s*/, "").trim();
        if (!line) continue;

        try {
          const parsed = JSON.parse(line);
          latest = parsed;
          const chunkText = parsed.chunk || parsed.text || parsed.explanation || "";
          if (chunkText) streamOut.textContent += chunkText;
        } catch {
          // Not JSON — treat as a raw text token from the stream.
          streamOut.textContent += line;
        }
      }
    }

    if (latest?.label) {
      els.result.innerHTML =
        `<span class="tg-result-label ${toneFor(latest.label)}">${escapeHtml(latest.label)}</span>` +
        (latest.confidence != null ? `<div class="tg-muted">Confidence: ${latest.confidence}%</div>` : "") +
        `<div class="tg-result-explanation">${escapeHtml(streamOut.textContent)}</div>`;
    }
  } catch (error) {
    setLoading(false);
    showError(error.message || "Streaming analysis failed.");
  }
});

// ------------------------------------------------------------
// REVIEW (single + full-page bulk via /analyze/review/page)
// ------------------------------------------------------------

document.getElementById("review-submit").addEventListener("click", async () => {
  const text = document.getElementById("review-text").value.trim();
  if (text.length < 10) return showError("Enter at least 10 characters.");

  setLoading(true);
  const res = await sendMessage({ action: "trustguard-analyze-review", payload: { text } });
  setLoading(false);

  if (res.ok) showResult(res.data);
  else showError(res.error || "Review analysis failed.");
});

document.getElementById("review-page-submit").addEventListener("click", async () => {
  const resultsBox = document.getElementById("review-page-results");
  resultsBox.innerHTML = "";
  setLoading(true);

  try {
    const [tab] = await ext.tabs.query({ active: true, currentWindow: true });
    if (!tab?.id) throw new Error("No active tab.");

    const collected = await ext.tabs.sendMessage(tab.id, { action: "trustguard-collect-reviews" });
    const texts = collected?.texts || [];

    if (!texts.length) {
      setLoading(false);
      showError("No review-like text blocks were found on this page.");
      return;
    }

    const res = await sendMessage({ action: "trustguard-analyze-review-page", texts });
    setLoading(false);

    if (!res.ok) {
      showError(res.error || "Bulk review scan failed.");
      return;
    }

    // Assumption: data.results is an array of { text, label, confidence,
    // explanation }. Falls back to showing the raw texts if the backend
    // returns a different shape.
    const items = res.data?.results || res.data?.items || [];

    if (!items.length) {
      showError("The server did not return per-review results.");
      return;
    }

    clearStateBlocks();
    resultsBox.innerHTML = items
      .map(
        (item) => `
        <div class="tg-review-item">
          <span class="tg-result-label ${toneFor(item.label)}">${escapeHtml(item.label ?? "Unknown")}</span>
          <div class="tg-result-explanation">${escapeHtml((item.text || "").slice(0, 140))}</div>
        </div>`
      )
      .join("");
  } catch (error) {
    setLoading(false);
    showError(error.message || "Could not scan this page. Try reloading it first.");
  }
});

// ------------------------------------------------------------
// PHISHING
// ------------------------------------------------------------

document.getElementById("url-submit").addEventListener("click", async () => {
  const url = document.getElementById("url-input").value.trim();
  if (!url) return showError("Enter a URL.");

  setLoading(true);
  const res = await sendMessage({ action: "trustguard-analyze-phishing", payload: { url } });
  setLoading(false);

  if (res.ok) showResult(res.data);
  else showError(res.error || "Phishing scan failed.");
});

// ------------------------------------------------------------
// HISTORY (local last-scan + account history)
// ------------------------------------------------------------

async function loadHistoryTab() {
  const lastRes = await sendMessage({ action: "trustguard-get-last-result" });
  const last = lastRes?.result;

  if (!last) {
    els.lastEmpty.hidden = false;
    els.lastResult.hidden = true;
  } else {
    els.lastEmpty.hidden = true;
    els.lastResult.hidden = false;
    els.lastResult.innerHTML = `
      <div class="tg-muted" style="margin-bottom:6px;">
        ${escapeHtml((last.type || "").toUpperCase())} · ${new Date(last.timestamp).toLocaleTimeString()}
      </div>
      <span class="tg-result-label ${toneFor(last.label)}">${escapeHtml(last.label ?? "Unknown")}</span>
      <div class="tg-result-explanation" style="margin-top:8px;">${escapeHtml((last.input || "").slice(0, 160))}</div>
      ${last.explanation ? `<div class="tg-result-explanation" style="margin-top:6px;">${escapeHtml(last.explanation)}</div>` : ""}
    `;
  }

  const auth = await sendMessage({ action: "trustguard-get-auth" });
  const signInHint = document.getElementById("history-signin-hint");
  const accountBlock = document.getElementById("account-history-block");

  if (!auth?.token) {
    signInHint.hidden = false;
    accountBlock.hidden = true;
    return;
  }

  signInHint.hidden = true;
  accountBlock.hidden = false;

  const listEl = document.getElementById("history-list");
  const detailEl = document.getElementById("history-detail");
  detailEl.hidden = true;
  listEl.innerHTML = `<div class="tg-muted">Loading…</div>`;

  const res = await sendMessage({ action: "trustguard-history" });
  if (!res.ok) {
    listEl.innerHTML = `<div class="tg-muted">Could not load history: ${escapeHtml(res.error || "")}</div>`;
    return;
  }

  // Assumption: data.items is an array of { id, type, label, input, createdAt }.
  const items = res.data?.items || res.data?.history || [];

  if (!items.length) {
    listEl.innerHTML = `<div class="tg-muted">No saved analyses yet.</div>`;
    return;
  }

  listEl.innerHTML = "";
  for (const item of items) {
    const row = document.createElement("div");
    row.className = "tg-history-item";
    row.innerHTML = `
      <div class="tg-history-meta">
        <span class="tg-history-type">${escapeHtml(item.type || "")}</span>
        <span class="tg-history-snippet">${escapeHtml(item.input || item.headline || item.url || "")}</span>
      </div>
      <span class="tg-result-label ${toneFor(item.label)}">${escapeHtml(item.label ?? "")}</span>
    `;
    row.addEventListener("click", () => loadHistoryDetail(item.id));
    listEl.appendChild(row);
  }
}

async function loadHistoryDetail(id) {
  const detailEl = document.getElementById("history-detail");
  detailEl.hidden = false;
  detailEl.innerHTML = `<div class="tg-muted">Loading detail…</div>`;

  const res = await sendMessage({ action: "trustguard-history-detail", id });
  if (!res.ok) {
    detailEl.innerHTML = `<div class="tg-muted">${escapeHtml(res.error || "Could not load detail.")}</div>`;
    return;
  }

  const data = res.data?.item || res.data;
  detailEl.innerHTML = `
    <div class="tg-result" style="margin-top:8px;">
      <span class="tg-result-label ${toneFor(data.label)}">${escapeHtml(data.label ?? "Unknown")}</span>
      ${data.confidence != null ? `<div class="tg-muted">Confidence: ${data.confidence}%</div>` : ""}
      ${data.explanation ? `<div class="tg-result-explanation">${escapeHtml(data.explanation)}</div>` : ""}
    </div>
  `;
}

// ------------------------------------------------------------
// ACCOUNT / AUTH
// ------------------------------------------------------------

async function loadAccountTab() {
  const auth = await sendMessage({ action: "trustguard-get-auth" });
  const signedOut = document.getElementById("account-signed-out");
  const signedIn = document.getElementById("account-signed-in");

  if (!auth?.token) {
    signedOut.hidden = false;
    signedIn.hidden = true;
    return;
  }

  signedOut.hidden = true;
  signedIn.hidden = false;

  document.getElementById("account-name").textContent = auth.user?.name || "Signed in";
  document.getElementById("account-email").textContent = auth.user?.email || "";

  // Refresh from /auth/me in case the token/quota changed server-side.
  const me = await sendMessage({ action: "trustguard-me" });
  if (me.ok) {
    const usage = me.data?.usage;
    const quotaWrap = document.getElementById("account-quota-wrap");
    if (usage && usage.limit) {
      quotaWrap.hidden = false;
      const pct = Math.min(100, Math.round((usage.used / usage.limit) * 100));
      document.getElementById("account-quota-text").textContent =
        `${usage.used} / ${usage.limit} requests used`;
      document.getElementById("account-quota-fill").style.width = `${pct}%`;
    } else {
      quotaWrap.hidden = true;
    }

    if (me.data?.user) {
      document.getElementById("account-name").textContent = me.data.user.name || "Signed in";
      document.getElementById("account-email").textContent = me.data.user.email || "";
    }
  }
}

document.getElementById("login-submit").addEventListener("click", async () => {
  const email = document.getElementById("auth-email").value.trim();
  const password = document.getElementById("auth-password").value;
  if (!email || !password) return showError("Enter email and password.");

  setLoading(true);
  const res = await sendMessage({ action: "trustguard-login", payload: { email, password } });
  setLoading(false);

  if (res.ok) {
    showSuccess("Logged in.");
    loadAccountTab();
  } else {
    showError(res.error || "Login failed.");
  }
});

document.getElementById("signup-submit").addEventListener("click", async () => {
  const email = document.getElementById("auth-email").value.trim();
  const password = document.getElementById("auth-password").value;
  if (!email || !password) return showError("Enter email and password.");

  setLoading(true);
  const res = await sendMessage({ action: "trustguard-signup", payload: { email, password } });
  setLoading(false);

  if (res.ok) {
    showSuccess("Account created.");
    loadAccountTab();
  } else {
    showError(res.error || "Sign up failed.");
  }
});

document.getElementById("logout-btn").addEventListener("click", async () => {
  await sendMessage({ action: "trustguard-logout" });
  loadAccountTab();
});

// ------------------------------------------------------------
// AUTO-SCAN TOGGLE
// ------------------------------------------------------------

async function initAutoScanToggle() {
  const config = await sendMessage({ action: "trustguard-get-config" });
  els.autoScanToggle.checked = Boolean(config?.autoScanEnabled);
}

els.autoScanToggle.addEventListener("change", async () => {
  await sendMessage({
    action: "trustguard-set-config",
    autoScanEnabled: els.autoScanToggle.checked,
  });
});

els.settingsBtn.addEventListener("click", () => {
  if (ext.runtime.openOptionsPage) ext.runtime.openOptionsPage();
});

// ------------------------------------------------------------
// INIT
// ------------------------------------------------------------

initTheme();
refreshStatus();
initAutoScanToggle();