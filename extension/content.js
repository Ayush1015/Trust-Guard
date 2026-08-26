// TrustGuard content script
// Runs on every page (read-only DOM inspection only — no page modification,
// no data sent anywhere until the user clicks a button in the popup).

function extractArticle() {
  const paragraphs = Array.from(document.querySelectorAll('p'))
    .map((p) => p.innerText.trim())
    .filter((t) => t.length > 30);

  return {
    title: document.title || '',
    text: paragraphs.join('\n').slice(0, 30000),
    url: location.href,
  };
}

function extractReviews() {
  // Generic heuristic selector set. Works reasonably on many review-style
  // pages out of the box; site-specific selectors (Amazon, Google, Yelp...)
  // can be added here later without touching the popup or backend.
  const candidates = document.querySelectorAll(
    '[class*="review" i], [data-hook*="review" i], [itemprop="review"]'
  );

  const seen = new Set();
  const reviews = [];
  const ratings = [];

  candidates.forEach((el) => {
    const text = el.innerText?.trim();
    if (!text || text.length < 15 || text.length > 4000) return;
    if (seen.has(text)) return;
    seen.add(text);
    reviews.push(text);

    const ratingEl = el.querySelector('[class*="star" i], [aria-label*="star" i], [itemprop="ratingValue"]');
    const ariaLabel = ratingEl?.getAttribute('aria-label') || '';
    const match = ariaLabel.match(/(\d(\.\d)?)\s*(out of|\/)\s*5/i) || ariaLabel.match(/(\d(\.\d)?)/);
    if (match) ratings.push(parseFloat(match[1]));
  });

  return { reviews: reviews.slice(0, 100), ratings: ratings.slice(0, 100), url: location.href };
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg?.type === 'TRUSTGUARD_EXTRACT_ARTICLE') {
    sendResponse(extractArticle());
    return true;
  }
  if (msg?.type === 'TRUSTGUARD_EXTRACT_REVIEWS') {
    sendResponse(extractReviews());
    return true;
  }
  if (msg?.type === 'TRUSTGUARD_GET_URL') {
    sendResponse({ url: location.href });
    return true;
  }
  return false;
});
