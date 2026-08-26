const API_BASE = 'http://localhost:5000/api/v1';

const els = {
  tabs: document.querySelectorAll('.tab'),
  panels: {
    news: document.getElementById('panel-news'),
    review: document.getElementById('panel-review'),
    phishing: document.getElementById('panel-phishing'),
  },
  loading: document.getElementById('loading'),
  result: document.getElementById('result'),
  error: document.getElementById('error'),
};

els.tabs.forEach((tab) => {
  tab.addEventListener('click', () => {
    els.tabs.forEach((t) => t.classList.remove('active'));
    tab.classList.add('active');
    Object.values(els.panels).forEach((p) => p.classList.remove('active'));
    els.panels[tab.dataset.tab].classList.add('active');
    resetOutput();
  });
});

function resetOutput() {
  els.result.classList.add('hidden');
  els.error.classList.add('hidden');
  els.loading.classList.add('hidden');
}

function showLoading() {
  resetOutput();
  els.loading.classList.remove('hidden');
}

function showError(message) {
  resetOutput();
  els.error.textContent = message;
  els.error.classList.remove('hidden');
}

function toneClass(label) {
  const v = String(label || '').toLowerCase();
  if (v.includes('fake') || v.includes('phishing')) return 'danger';
  if (v.includes('real') || v.includes('genuine') || v.includes('safe')) return 'safe';
  return 'warn';
}

function showResult({ label, confidence, extra }) {
  resetOutput();
  els.result.innerHTML = `
    <div class="label ${toneClass(label)}">${label ?? 'Unknown'}</div>
    <div class="meta">${confidence != null ? `${confidence}% confidence` : ''}</div>
    ${extra ? `<div class="meta" style="margin-top:6px">${extra}</div>` : ''}
  `;
  els.result.classList.remove('hidden');
}

async function getToken() {
  const { authToken } = await chrome.storage.local.get('authToken');
  return authToken || null;
}

async function getActiveTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab;
}

async function callApi(endpoint, body) {
  const token = await getToken();
  const res = await fetch(`${API_BASE}${endpoint}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data?.error?.message || `Request failed (${res.status}).`);
  }
  return data;
}

document.getElementById('checkNews').addEventListener('click', async () => {
  try {
    showLoading();
    const tab = await getActiveTab();
    const article = await chrome.tabs.sendMessage(tab.id, { type: 'TRUSTGUARD_EXTRACT_ARTICLE' });

    if (!article?.text || article.text.length < 15) {
      showError('Could not find enough article text on this page.');
      return;
    }

    const data = await callApi('/analyze/news', {
      headline: article.title,
      article_text: article.text,
      article_url: article.url,
    });

    showResult({
      label: data.label,
      confidence: data.confidence,
      extra: data.webVerification?.available ? 'Verified against live web sources' : null,
    });
  } catch (err) {
    showError(err.message || 'Something went wrong.');
  }
});

document.getElementById('checkReviews').addEventListener('click', async () => {
  try {
    showLoading();
    const tab = await getActiveTab();
    const { reviews, ratings } = await chrome.tabs.sendMessage(tab.id, {
      type: 'TRUSTGUARD_EXTRACT_REVIEWS',
    });

    if (!reviews || reviews.length === 0) {
      showError('No reviews detected on this page. Try scrolling to load more, then retry.');
      return;
    }

    const data = await callApi('/analyze/review/page', { reviews, ratings });

    showResult({
      label: data.verdict,
      confidence: data.fakeReviewRatio,
      extra: `${data.reviewsAnalyzed} reviews analyzed${
        data.ratingPatternAssessment ? ` · ${data.ratingPatternAssessment}` : ''
      }`,
    });
  } catch (err) {
    showError(err.message || 'Something went wrong.');
  }
});

document.getElementById('checkPhishing').addEventListener('click', async () => {
  try {
    showLoading();
    const tab = await getActiveTab();
    const { url } = await chrome.tabs.sendMessage(tab.id, { type: 'TRUSTGUARD_GET_URL' });

    const data = await callApi('/analyze/phishing', { url });

    const flags = [];
    if (data.standardChecklist?.typosquattingOf) {
      flags.push(`resembles ${data.standardChecklist.typosquattingOf}`);
    }
    if (data.standardChecklist?.redirectHops > 0) {
      flags.push(`${data.standardChecklist.redirectHops} redirects`);
    }

    showResult({
      label: data.label,
      confidence: data.confidence,
      extra: flags.length ? flags.join(' · ') : `Risk: ${data.riskLevel}`,
    });
  } catch (err) {
    showError(err.message || 'Something went wrong.');
  }
});

// Pick up a pending check queued from the right-click context menu.
chrome.storage.local.get('pendingCheck').then(({ pendingCheck }) => {
  if (!pendingCheck) return;
  chrome.storage.local.remove('pendingCheck');
  if (pendingCheck.type === 'phishing') {
    document.querySelector('.tab[data-tab="phishing"]').click();
  } else if (pendingCheck.type === 'news') {
    document.querySelector('.tab[data-tab="news"]').click();
  }
});
