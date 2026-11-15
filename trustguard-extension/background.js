// No automatic browsing capture. All reads/checks start in the popup.
chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.local.remove(['autoScanEnabled', 'lastResult']);
});
