chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === 'EXTRACT_ARTICLE') {
    const paragraphs = [...document.querySelectorAll('p')]
      .map(p => p.innerText.trim()).filter(t => t.length > 30);
    sendResponse({ title: document.title, text: paragraphs.join('\n'), url: location.href });
  }
  if (msg.type === 'EXTRACT_REVIEWS') {
    // Generic heuristic selector — works on many review-style pages; site-specific
    // selectors can be added later without touching the rest of the extension.
    const reviewEls = [...document.querySelectorAll('[class*="review"], [data-hook*="review"]')];
    const reviews = reviewEls.map(el => el.innerText.trim()).filter(t => t.length > 15).slice(0, 50);
    sendResponse({ reviews, url: location.href });
  }
  return true;
});