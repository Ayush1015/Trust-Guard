import { useState } from 'react';

const urlRegex = /^(https?:\/\/)?([\da-z.-]+)\.([a-z.]{2,6})([/\w .-]*)*\/?$/;

export default function NewsInput({ onSubmit, loading }) {
  const [text, setText] = useState('');
  const [articleUrl, setArticleUrl] = useState('');
  const minCharCount = 15;

  const trimmedText = text.trim();
  const trimmedUrl = articleUrl.trim();
  const urlProvided = trimmedUrl.length > 0;
  const isUrlValid = !urlProvided || urlRegex.test(trimmedUrl);
  const hasEnoughText = trimmedText.length >= minCharCount;
  const canSubmit = isUrlValid && (hasEnoughText || urlProvided);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!canSubmit) return;
    onSubmit({
      text: trimmedText,
      article_url: urlProvided ? trimmedUrl : '',
    });
  };

  const handleClear = () => {
    setText('');
    setArticleUrl('');
  };

  return (
    <form onSubmit={handleSubmit} className="d-flex flex-column gap-3">
      <div>
        <label htmlFor="news-url" className="form-label text-secondary fw-semibold mb-1">
          Article URL <span className="text-muted fw-normal">(optional)</span>
        </label>
        <div className="input-group">
          <span
            className="input-group-text form-control-custom bg-secondary border-end-0 text-muted"
            style={{ borderTopRightRadius: 0, borderBottomRightRadius: 0 }}
          >
            <i className="bi bi-link-45deg"></i>
          </span>
          <input
            id="news-url"
            type="text"
            className="form-control form-control-custom border-start-0"
            style={{ borderTopLeftRadius: 0, borderBottomLeftRadius: 0 }}
            value={articleUrl}
            onChange={(e) => setArticleUrl(e.target.value)}
            placeholder="e.g. https://example.com/news/article — we'll auto-extract the article"
            disabled={loading}
          />
        </div>
        {urlProvided && !isUrlValid && (
          <div className="text-warning small mt-1">
            That doesn't look like a valid URL. Leave it blank or fix the format.
          </div>
        )}
      </div>

      <div className="d-flex justify-content-between align-items-center">
        <label htmlFor="news-text" className="form-label text-secondary fw-semibold mb-0">
          Paste News Article Content{' '}
          {urlProvided && (
            <span className="text-muted fw-normal">(optional — a URL was provided)</span>
          )}
        </label>
        <span className={`small ${hasEnoughText || urlProvided ? 'text-success' : 'text-warning'}`}>
          {trimmedText.length} chars (Min: {minCharCount})
        </span>
      </div>

      <textarea
        id="news-text"
        className="form-control form-control-custom"
        rows="8"
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Copy and paste the full body text of the article here, or just supply a URL above..."
        disabled={loading}
      />

      <div className="d-flex gap-2 justify-content-end">
        <button
          type="button"
          className="btn btn-outline-secondary px-4 py-2"
          onClick={handleClear}
          disabled={loading || (!text && !articleUrl)}
          style={{ borderRadius: '10px' }}
        >
          Clear
        </button>
        <button
          type="submit"
          className="btn btn-cyber d-flex align-items-center gap-2"
          disabled={loading || !canSubmit}
        >
          {loading ? (
            <>
              <span className="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>
              Analyzing Article...
            </>
          ) : (
            <>
              <i className="bi bi-shield-check"></i>
              Run Detection
            </>
          )}
        </button>
      </div>
    </form>
  );
}