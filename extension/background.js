// TrustGuard background service worker.
// Currently minimal — the popup talks to the API directly. This file exists
// so a right-click "Check this link with TrustGuard" context-menu action can
// be added later without restructuring the extension.

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: 'trustguard-check-link',
    title: 'Check this link with TrustGuard',
    contexts: ['link'],
  });

  chrome.contextMenus.create({
    id: 'trustguard-check-selection',
    title: 'Check selected text with TrustGuard',
    contexts: ['selection'],
  });
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === 'trustguard-check-link' && info.linkUrl) {
    chrome.storage.local.set({ pendingCheck: { type: 'phishing', value: info.linkUrl } });
  }
  if (info.menuItemId === 'trustguard-check-selection' && info.selectionText) {
    chrome.storage.local.set({ pendingCheck: { type: 'news', value: info.selectionText } });
  }
  chrome.action.openPopup?.();
});
