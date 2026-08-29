import { useState } from 'react';

const urlRegex = /^(https?:\/\/)?([\da-z.-]+)\.([a-z.]{2,6})([/\w .-]*)*\/?$/;

export default function ReviewInput({ onSubmit, loading }) {
  const [text, setText] = useState('');
  const [productUrl, setProductUrl] = useState('');
  const minCharCount = 10;

  const trimmedText = text.trim();
  const trimmedUrl = productUrl.trim();
  const urlProvided = trimmedUrl.length > 0;
  const isUrlValid = !urlProvided || urlRegex.test(trimmedUrl);
  const canSubmit = trimmedText.length >= minCharCount && isUrlValid;

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!canSubmit) return;
    onSubmit({
      text: trimmedText,
      product_url: urlProvided ? trimmedUrl : '',
    });
  };

  const handleClear = () => {
    setText('');
    setProductUrl('');
  };

  return (
    <form onSubmit={handleSubmit} className="d-flex flex-column gap-3">
      <div>

        <label htmlFor="review-url" className="form-label text-secondary fw-semibold mb-1">
          Product / Listing URL <span className="text-muted fw-normal">(optional, for your reference)</span>
        </label>
        <div className="input-group">
          <span
            className="input-group-text form-control-custom bg-secondary border-end-0 text-muted"
            style={{ borderTopRightRadius: 0, borderBottomRightRadius: 0 }}
          >
            <i className="bi bi-link-45deg"></i>
          </span>
          <input
            id="review-url"
            type="text"
            className="form-control form-control-custom border-start-0"
            style={{ borderTopLeftRadius: 0, borderBottomLeftRadius: 0 }}
            value={productUrl}
            onChange={(e) => setProductUrl(e.target.value)}
            placeholder="e.g. https://store.example.com/product/123"
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
        <label htmlFor="review-text" className="form-label text-secondary fw-semibold mb-0">
          Paste Product / Service Review
        </label>

        <span className={`small ${trimmedText.length < minCharCount ? 'text-warning' : 'text-success'}`}>
          {trimmedText.length} chars (Min: {minCharCount})
        </span>
      </div>

      <textarea
        id="review-text"
        className="form-control form-control-custom"
        rows="6"
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Paste a suspicious e-commerce, hotel, or product review to check for spam patterns or astroturfing..."
        disabled={loading}
      />

      <div className="d-flex gap-2 justify-content-end">
        <button
          type="button"
          className="btn btn-outline-secondary px-4 py-2"
          onClick={handleClear}
          disabled={loading || (!text && !productUrl)}
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
              Analyzing Review...
            </>
          ) : (
            <>
              <i className="bi bi-star-half"></i>
              Analyze Review
            </>
          )}
        </button>
      </div>
    </form>
  );
}