// ============================================================
// TrustGuard Extension — Background Service Worker (MV3)
// Works in Chrome, Edge, Brave (chrome.*) and Firefox (browser.*)
// ============================================================

const ext = typeof browser !== "undefined" ? browser : chrome;

const DEFAULT_API_BASE = "http://localhost:5000/api/v1";
const REQUEST_TIMEOUT = 60000;
const CACHE_TTL_MS = 10 * 60 * 1000; // 10 minutes

// Simple in-memory cache, cleared on service-worker restart.
const memoryCache = new Map();

// ------------------------------------------------------------
// CONFIG / AUTH STORAGE
// ------------------------------------------------------------

async function getApiBase() {
  try {
    const stored = await ext.storage.local.get("apiBaseUrl");
    return (stored.apiBaseUrl || DEFAULT_API_BASE).replace(/\/+$/, "");
  } catch {
    return DEFAULT_API_BASE;
  }
}

async function getAutoScanEnabled() {
  try {
    const stored = await ext.storage.local.get("autoScanEnabled");
    return stored.autoScanEnabled !== false; // default ON
  } catch {
    return true;
  }
}

async function getAuth() {
  try {
    const stored = await ext.storage.local.get(["authToken", "authUser"]);
    return { token: stored.authToken || null, user: stored.authUser || null };
  } catch {
    return { token: null, user: null };
  }
}

async function setAuth(token, user) {
  await ext.storage.local.set({ authToken: token || null, authUser: user || null });
}

// ------------------------------------------------------------
// FETCH HELPER
// ------------------------------------------------------------
//
// NOTE ON NEW ENDPOINTS: /auth/*, /analyze/review/page and
// /analyze/news/stream were added to the API after this extension was
// first built. The exact response/payload shapes for signup/login/
// history/review-page below are reasonable assumptions (standard
// { token, user } / { items } shapes). If your controllers return a
// different structure, adjust the small "shape" spots marked below —
// everything else (caching, auth headers, timeouts) stays the same.

async function request(endpoint, { method = "POST", payload, auth = false } = {}) {
  const base = await getApiBase();
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT);

  const headers = { "Content-Type": "application/json" };

  if (auth) {
    const { token } = await getAuth();
    if (token) headers.Authorization = `Bearer ${token}`;
  }

  try {
    const response = await fetch(`${base}${endpoint}`, {
      method,
      headers,
      body: method === "GET" ? undefined : JSON.stringify(payload || {}),
      signal: controller.signal,
    });

    const contentType = response.headers.get("content-type") || "";
    const data = contentType.includes("application/json")
      ? await response.json()
      : { error: { message: await response.text() } };

    if (!response.ok) {
      throw new Error(
        data?.error?.message || data?.detail || data?.message || `Request failed (${response.status})`
      );
    }

    return data;
  } finally {
    clearTimeout(timer);
  }
}

const callApi = (endpoint, payload) => request(endpoint, { method: "POST", payload });

// ------------------------------------------------------------
// PHISHING CACHE (used by content-script auto scan + context menu)
// ------------------------------------------------------------

function cacheGet(url) {
  const hit = memoryCache.get(url);
  if (!hit) return null;
  if (Date.now() - hit.time > CACHE_TTL_MS) {
    memoryCache.delete(url);
    return null;
  }
  return hit.data;
}

function cacheSet(url, data) {
  memoryCache.set(url, { data, time: Date.now() });
}

async function checkUrl(url) {
  const cached = cacheGet(url);
  if (cached) return cached;

  const data = await request("/analyze/phishing", { payload: { url }, auth: true });
  cacheSet(url, data);
  return data;
}

// ------------------------------------------------------------
// LAST RESULT (for the popup's History tab)
// ------------------------------------------------------------

async function setLastResult(result) {
  try {
    await ext.storage.local.set({ lastResult: result });
  } catch {
    /* ignore */
  }
}

// ------------------------------------------------------------
// CONTEXT MENUS
// ------------------------------------------------------------

function createContextMenus() {
  ext.contextMenus.removeAll(() => {
    ext.contextMenus.create({
      id: "trustguard-check-link",
      title: "TrustGuard: Scan this link for phishing",
      contexts: ["link"],
    });

    ext.contextMenus.create({
      id: "trustguard-check-review",
      title: "TrustGuard: Check selection as a review",
      contexts: ["selection"],
    });

    ext.contextMenus.create({
      id: "trustguard-check-news",
      title: "TrustGuard: Fact-check selected text",
      contexts: ["selection"],
    });
  });
}

ext.runtime.onInstalled.addListener(() => {
  createContextMenus();
  ext.storage.local.get(["apiBaseUrl", "autoScanEnabled"]).then((stored) => {
    const updates = {};
    if (!stored.apiBaseUrl) updates.apiBaseUrl = DEFAULT_API_BASE;
    if (stored.autoScanEnabled === undefined) updates.autoScanEnabled = true;
    if (Object.keys(updates).length) ext.storage.local.set(updates);
  });
});

async function notifyTab(tabId, payload) {
  if (tabId == null) return;
  try {
    await ext.tabs.sendMessage(tabId, payload);
  } catch {
    // Content script may not be injected on this page (e.g. chrome:// URLs).
  }
}

function safeNotification(title, message) {
  try {
    ext.notifications.create({
      type: "basic",
      iconUrl: "icons/icon128.png",
      title,
      message,
    });
  } catch {
    /* notifications API may be unavailable in some contexts */
  }
}

ext.contextMenus.onClicked.addListener(async (info, tab) => {
  try {
    if (info.menuItemId === "trustguard-check-link") {
      const url = info.linkUrl;
      if (!url) return;

      const data = await checkUrl(url);
      const summary = {
        type: "phishing",
        input: url,
        label: data.label,
        confidence: data.confidence,
        riskLevel: data.riskLevel,
        explanation: data.explanation,
        timestamp: Date.now(),
      };
      await setLastResult(summary);
      await notifyTab(tab?.id, { action: "trustguard-toast", result: summary });
      safeNotification(
        `TrustGuard: ${data.label}`,
        `${url}\n${data.explanation || ""}`.slice(0, 200)
      );
    }

    if (info.menuItemId === "trustguard-check-review") {
      const text = (info.selectionText || "").trim();
      if (text.length < 10) {
        safeNotification("TrustGuard", "Select at least 10 characters of review text.");
        return;
      }

      const data = await request("/analyze/review", { payload: { text }, auth: true });
      const summary = {
        type: "review",
        input: text,
        label: data.label,
        confidence: data.confidence,
        explanation: data.explanation,
        timestamp: Date.now(),
      };
      await setLastResult(summary);
      await notifyTab(tab?.id, { action: "trustguard-toast", result: summary });
      safeNotification(`TrustGuard: ${data.label} review`, data.explanation || "");
    }

    if (info.menuItemId === "trustguard-check-news") {
      const text = (info.selectionText || "").trim();
      if (text.length < 15) {
        safeNotification("TrustGuard", "Select at least 15 characters of text.");
        return;
      }

      const data = await request("/analyze/news", { payload: { text }, auth: true });
      const summary = {
        type: "news",
        input: text,
        label: data.label,
        confidence: data.confidence,
        explanation: data.explanation,
        timestamp: Date.now(),
      };
      await setLastResult(summary);
      await notifyTab(tab?.id, { action: "trustguard-toast", result: summary });
      safeNotification(`TrustGuard: ${data.label}`, data.explanation || "");
    }
  } catch (error) {
    console.error("TrustGuard context action failed:", error);
    safeNotification("TrustGuard error", error.message || "Analysis failed.");
    await notifyTab(tab?.id, {
      action: "trustguard-toast",
      result: {
        type: "error",
        label: "Error",
        explanation: error.message || "Analysis failed. Is the TrustGuard server running?",
        timestamp: Date.now(),
      },
    });
  }
});

// ------------------------------------------------------------
// MESSAGE ROUTER (popup + content script -> background)
// ------------------------------------------------------------

ext.runtime.onMessage.addListener((message, sender, sendResponse) => {
  (async () => {
    try {
      switch (message?.action) {
        // ---------------- config ----------------
        case "trustguard-get-config": {
          const auth = await getAuth();
          sendResponse({
            ok: true,
            apiBase: await getApiBase(),
            autoScanEnabled: await getAutoScanEnabled(),
            loggedIn: Boolean(auth.token),
          });
          break;
        }

        case "trustguard-set-config": {
          const updates = {};
          if (typeof message.apiBaseUrl === "string") {
            updates.apiBaseUrl = message.apiBaseUrl.trim().replace(/\/+$/, "") || DEFAULT_API_BASE;
          }
          if (typeof message.autoScanEnabled === "boolean") {
            updates.autoScanEnabled = message.autoScanEnabled;
          }
          await ext.storage.local.set(updates);
          sendResponse({ ok: true });
          break;
        }

        // ---------------- analysis ----------------
        case "trustguard-analyze-news": {
          const data = await request("/analyze/news", { payload: message.payload, auth: true });
          sendResponse({ ok: true, data });
          break;
        }

        case "trustguard-analyze-review": {
          const data = await request("/analyze/review", { payload: message.payload, auth: true });
          sendResponse({ ok: true, data });
          break;
        }

        // Assumption: POST /analyze/review/page accepts { texts: string[] }
        // and returns { results: [{ text, label, confidence, explanation }] }.
        case "trustguard-analyze-review-page": {
          const data = await request("/analyze/review/page", {
            payload: { texts: message.texts || [] },
            auth: true,
          });
          sendResponse({ ok: true, data });
          break;
        }

        case "trustguard-analyze-phishing": {
          const data = await checkUrl(message.payload.url);
          sendResponse({ ok: true, data });
          break;
        }

        case "trustguard-check-urls-batch": {
          const urls = Array.isArray(message.urls) ? message.urls.slice(0, 40) : [];
          const results = {};
          const concurrency = 4;
          let index = 0;

          async function worker() {
            while (index < urls.length) {
              const current = urls[index++];
              try {
                results[current] = await checkUrl(current);
              } catch (error) {
                results[current] = { error: error.message };
              }
            }
          }

          await Promise.all(
            Array.from({ length: Math.min(concurrency, urls.length) }, worker)
          );

          sendResponse({ ok: true, results });
          break;
        }

        case "trustguard-get-last-result": {
          const stored = await ext.storage.local.get("lastResult");
          sendResponse({ ok: true, result: stored.lastResult || null });
          break;
        }

        // ---------------- auth ----------------
        // Assumption: /auth/signup and /auth/login both return
        // { token, user: { name, email, ... } }.
        case "trustguard-signup": {
          const data = await request("/auth/signup", { payload: message.payload });
          if (data.token) await setAuth(data.token, data.user);
          sendResponse({ ok: true, data });
          break;
        }

        case "trustguard-login": {
          const data = await request("/auth/login", { payload: message.payload });
          if (data.token) await setAuth(data.token, data.user);
          sendResponse({ ok: true, data });
          break;
        }

        case "trustguard-logout": {
          await setAuth(null, null);
          sendResponse({ ok: true });
          break;
        }

        case "trustguard-get-auth": {
          sendResponse({ ok: true, ...(await getAuth()) });
          break;
        }

        // Assumption: GET /auth/me returns { user, usage?: { used, limit } }.
        case "trustguard-me": {
          const data = await request("/auth/me", { method: "GET", auth: true });
          if (data.user) {
            const { token } = await getAuth();
            await setAuth(token, data.user);
          }
          sendResponse({ ok: true, data });
          break;
        }

        // Assumption: GET /auth/history returns { items: [{ id, type, label,
        // input, createdAt }] }.
        case "trustguard-history": {
          const data = await request("/auth/history", { method: "GET", auth: true });
          sendResponse({ ok: true, data });
          break;
        }

        case "trustguard-history-detail": {
          const data = await request(`/auth/history/${encodeURIComponent(message.id)}`, {
            method: "GET",
            auth: true,
          });
          sendResponse({ ok: true, data });
          break;
        }

        case "trustguard-update-preferences": {
          const data = await request("/auth/preferences", {
            method: "PATCH",
            payload: message.payload,
            auth: true,
          });
          sendResponse({ ok: true, data });
          break;
        }

        default:
          sendResponse({ ok: false, error: "Unknown action." });
      }
    } catch (error) {
      sendResponse({ ok: false, error: error.message || "Request failed." });
    }
  })();

  return true; // keep the message channel open for the async response
});