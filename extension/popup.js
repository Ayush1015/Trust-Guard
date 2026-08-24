const API_BASE = 'http://localhost:5000/api/v1';

async function getToken() {
  const { authToken } = await chrome.storage.local.get('authToken');
  return authToken;
}

document.getElementById('checkNews').addEventListener('click', async () => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const article = await chrome.tabs.sendMessage(tab.id, { type: 'EXTRACT_ARTICLE' });
  const token = await getToken();

  const res = await fetch(`${API_BASE}/analyze/news`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {})
    },
    body: JSON.stringify({ headline: article.title, article_text: article.text, article_url: article.url })
  });
  const data = await res.json();
  document.getElementById('result').textContent = `${data.label} (${data.confidence}% confidence)`;
});