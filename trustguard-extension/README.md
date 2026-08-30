# TrustGuard Browser Extension

A Manifest V3 extension that brings TrustGuard's news / review / phishing
checks into the browser: a popup for manual checks, a right-click context
menu for links and selected text, and an automatic scan that flags risky
external links on any page you visit.

It talks to your existing **Node.js gateway** (`trustguard-platform/server`),
which in turn talks to the Python ML service — nothing else to run.

## 1. Update the server's CORS (one-time)

Browser extensions call the API from a `chrome-extension://` /
`moz-extension://` origin, which the original server config didn't allow.
Replace `trustguard-platform/server/src/index.js` with the updated
`server-index.js` included in this download (or merge the CORS block
yourself), then restart the server:

```powershell
npm run dev
```

## 2. Load the extension

Make sure the Node gateway (`http://localhost:5000`) and the Python ML
service (`http://127.0.0.1:8000`) are both running first.

### Chrome / Edge / Brave
1. Go to `chrome://extensions` (or `edge://extensions`, `brave://extensions`).
2. Enable **Developer mode** (top-right toggle).
3. Click **Load unpacked** and select the `trustguard-extension` folder.
4. Pin the TrustGuard icon to the toolbar if you'd like quick access.

### Firefox
1. Go to `about:debugging#/runtime/this-firefox`.
2. Click **Load Temporary Add-on…**.
3. Select `manifest.json` inside the `trustguard-extension` folder.
   (Temporary add-ons are removed when Firefox closes — for a permanent
   install you'd package and sign it via addons.mozilla.org.)

## 3. Using it

- **Popup** — click the toolbar icon for manual News / Review / URL checks,
  a "Last Scan" tab showing your most recent right-click result, and an
  auto-scan on/off toggle.
- **Right-click a link** → "TrustGuard: Scan this link for phishing".
- **Select text, right-click** → "Check selection as a review" or
  "Fact-check selected text".
- **Auto-scan** — external links on the page get a small ⚠ badge if they
  trip the phishing ensemble. Only up to 40 links per page are checked, and
  results are cached for 10 minutes to avoid hammering your local ML
  service.

## 4. Changing the API URL

By default the extension points at `http://localhost:5000/api/v1`. If you
later deploy the gateway somewhere else, click the ⚙ icon in the popup (or
open the extension's Options page) and update the URL there — no rebuild
needed.

## Notes

- All requests happen from the extension's background service worker /
  popup, never from a webpage's own context, so this doesn't inject your
  API into third-party sites.
- The auto-scan and context-menu checks reuse the exact same
  `/api/v1/analyze/*` endpoints as the original web app, so behavior
  (model ensemble, poll, Gemini step) is identical.
- If the server is offline, the popup status will show "Server
  unreachable" and context-menu actions will surface an error toast
  instead of silently failing.
