# TrustGuard Page Check (Chrome MV3)

On-demand companion to the same TrustGuard gateway used by the website.
It does not scan all browsing, inject a script into every page, or send data
until a user chooses a check.

## Run for the mentor demo
1. Start the Python ML service and Node gateway using the root SETUP_NOTES.txt.
2. Open chrome://extensions, enable Developer mode, choose Load unpacked, and
   select this folder. This is local installation, not Web Store publication.
3. Visit a normal HTTP(S) web page. Click the extension icon, or Alt+Shift+G.
4. Check this URL, or copy selected/page text into the editable preview.
5. Review the preview before pressing Check news claim or Estimate review
   writing origin. Keep the popup open while the server checks it.

The default backend is http://localhost:5000/api/v1. To connect a deployed
backend, enter its HTTPS API address and approve access to that origin.
No public backend is supplied by this source package yet. Browser internal
pages and some protected pages cannot be read.

## Privacy and permissions
- activeTab: temporary access to the tab the user invokes the extension on.
- scripting: read selected text or a maximum 10,000-character page preview,
  only after the corresponding user click.
- storage: remember the chosen backend address. No auth token, page text,
  scan result or browsing history is saved by this extension.
- host permissions: local gateway only by default; HTTPS origins optional,
  requested at connection time.

Checks transmit the chosen URL or edited text to the configured backend.
That backend may query search services and fetch public sources for news.
It may log requests; do not send private documents, credentials or payment
information. No analytics, ads or background capture is included.

## Meaning and limits
News outputs combine model signals with estimated source support/refute
and quoted passages. Source repetition is not independent truth proof.
Review writing-origin estimation is NOT fake-review/deception detection.
URL structural risk is NOT a malware scan or safety guarantee. Redirect
inspection is explicitly unavailable rather than using an unsafe fetch.

## Publication status
Not submitted to Chrome Web Store. Publisher account, one-time registration
fee, public HTTPS backend, hosted privacy disclosure, store questionnaire,
listing copy/screenshots and review are separate requirements. Do not
market this as an approved or published extension.
