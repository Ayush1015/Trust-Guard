// ============================================================
// TrustGuard Extension — Content Script
// Runs on every page: badges risky links, shows result toasts,
// and can collect review-like text blocks for bulk scanning.
// ============================================================

(() => {
  const ext = typeof browser !== "undefined" ? browser : chrome;
  const BADGE_CLASS = "trustguard-badge";
  const SCANNED_ATTR = "data-trustguard-scanned";
  const MAX_LINKS_PER_SCAN = 40;

  function sendMessage(message) {
    return new Promise((resolve) => {
      try {
        ext.runtime.sendMessage(message, (response) => {
          resolve(response || { ok: false });
        });
      } catch {
        resolve({ ok: false });
      }
    });
  }

  // ----------------------------------------------------------
  // TOAST (shown when a right-click / context-menu check finishes)
  // ----------------------------------------------------------

  function ensureToastRoot() {
    let root = document.getElementById("trustguard-toast-root");
    if (!root) {
      root = document.createElement("div");
      root.id = "trustguard-toast-root";
      document.documentElement.appendChild(root);
    }
    return root;
  }

  function toneForLabel(label) {
    const v = String(label || "").toLowerCase();
    if (v.includes("fake") || v.includes("phishing") || v.includes("error")) return "danger";
    if (v.includes("real") || v.includes("genuine") || v.includes("safe")) return "success";
    return "warning";
  }

  function showToast(result) {
    const root = ensureToastRoot();
    const toast = document.createElement("div");
    toast.className = `trustguard-toast trustguard-toast-${toneForLabel(result.label)}`;

    const title = document.createElement("div");
    title.className = "trustguard-toast-title";
    title.textContent = `TrustGuard: ${result.label || "Result"}`;

    const body = document.createElement("div");
    body.className = "trustguard-toast-body";
    body.textContent = (result.explanation || "").slice(0, 220);

    const close = document.createElement("button");
    close.className = "trustguard-toast-close";
    close.setAttribute("aria-label", "Dismiss");
    close.textContent = "\u00d7";
    close.onclick = () => toast.remove();

    toast.appendChild(close);
    toast.appendChild(title);
    if (result.explanation) toast.appendChild(body);
    root.appendChild(toast);

    setTimeout(() => toast.classList.add("trustguard-toast-visible"), 10);
    setTimeout(() => {
      toast.classList.remove("trustguard-toast-visible");
      setTimeout(() => toast.remove(), 300);
    }, 9000);
  }

  // ----------------------------------------------------------
  // PAGE-WIDE REVIEW COLLECTION (for the popup's bulk scan button)
  // ----------------------------------------------------------

  function collectReviewTexts() {
    const selectors = [
      '[class*="review" i]',
      '[data-hook*="review" i]',
      '[id*="review" i]',
      "article",
    ];

    const seen = new Set();
    const texts = [];

    for (const selector of selectors) {
      let nodes;
      try {
        nodes = document.querySelectorAll(selector);
      } catch {
        continue;
      }

      for (const node of nodes) {
        if (texts.length >= 25) break;

        const text = (node.innerText || "").trim().replace(/\s+/g, " ");
        if (text.length < 25 || text.length > 1200) continue;
        if (seen.has(text)) continue;

        seen.add(text);
        texts.push(text);
      }

      if (texts.length >= 25) break;
    }

    return texts;
  }

  ext.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message?.action === "trustguard-toast" && message.result) {
      showToast(message.result);
    }

    if (message?.action === "trustguard-collect-reviews") {
      sendResponse({ ok: true, texts: collectReviewTexts() });
      return true;
    }
  });

  // ----------------------------------------------------------
  // AUTO-SCAN: badge external links with a phishing risk icon
  // ----------------------------------------------------------

  function collectCandidateLinks() {
    const here = window.location.hostname;
    const anchors = Array.from(document.querySelectorAll(`a[href^="http"]:not([${SCANNED_ATTR}])`));

    const seen = new Set();
    const candidates = [];

    for (const a of anchors) {
      if (candidates.length >= MAX_LINKS_PER_SCAN) break;

      let url;
      try {
        url = new URL(a.href);
      } catch {
        continue;
      }

      if (url.hostname === here) {
        a.setAttribute(SCANNED_ATTR, "skip");
        continue;
      }

      a.setAttribute(SCANNED_ATTR, "pending");

      if (!seen.has(url.href)) {
        seen.add(url.href);
        candidates.push(url.href);
      }
    }

    return { anchors, candidates, seenUrls: seen };
  }

  function badgeFor(label) {
    const span = document.createElement("span");
    span.className = `${BADGE_CLASS} trustguard-badge-${toneForLabel(label)}`;
    span.title =
      label === "Phishing"
        ? "TrustGuard: this link shows phishing indicators"
        : label === "Safe"
          ? "TrustGuard: no obvious phishing indicators"
          : "TrustGuard: could not classify this link";
    span.textContent = label === "Phishing" ? "⚠" : label === "Safe" ? "✓" : "?";
    return span;
  }

  function applyResults(anchors, results) {
    const byHref = new Map();
    for (const a of anchors) {
      try {
        byHref.set(new URL(a.href).href, a);
      } catch {
        /* ignore */
      }
    }

    for (const [href, data] of Object.entries(results)) {
      const anchor = byHref.get(href);
      if (!anchor) continue;

      anchor.setAttribute(SCANNED_ATTR, "done");

      if (data?.error) continue;
      if (data.label !== "Phishing") continue; // only badge risky links to stay unobtrusive

      if (!anchor.querySelector(`.${BADGE_CLASS}`)) {
        anchor.appendChild(badgeFor(data.label));
      }
    }
  }

  let scanScheduled = false;

  async function runAutoScan() {
    if (scanScheduled) return;
    scanScheduled = true;

    try {
      const config = await sendMessage({ action: "trustguard-get-config" });
      if (!config?.ok || !config.autoScanEnabled) return;

      const { anchors, candidates } = collectCandidateLinks();
      if (!candidates.length) return;

      const response = await sendMessage({
        action: "trustguard-check-urls-batch",
        urls: candidates,
      });

      if (response?.ok) {
        applyResults(anchors, response.results);
      }
    } catch (error) {
      console.debug("TrustGuard auto-scan skipped:", error);
    } finally {
      scanScheduled = false;
    }
  }

  let debounceTimer = null;
  function scheduleScan() {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(runAutoScan, 1200);
  }

  scheduleScan();

  const observer = new MutationObserver((mutations) => {
    const hasNewNodes = mutations.some((m) => m.addedNodes.length > 0);
    if (hasNewNodes) scheduleScan();
  });

  observer.observe(document.documentElement, { childList: true, subtree: true });
})();