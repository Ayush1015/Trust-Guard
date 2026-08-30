import { useState } from 'react';

export default function ReviewInput({ onSubmit, loading }) {
  const [text, setText] = useState('');
  const [productUrl, setProductUrl] = useState('');
  const minCharCount = 10;

  const urlRegex = /^(https?:\/\/)?([\da-z.-]+)\.([a-z.]{2,6})([/\w .-]*)*\/?$/;
  const trimmedUrl = productUrl.trim();
  const isUrlValid = !trimmedUrl || urlRegex.test(trimmedUrl);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (text.trim().length >= minCharCount && isUrlValid) {
      onSubmit({ text, product_url: trimmedUrl });
    }
  };

  const handleClear = () => {
    setText('');
    setProductUrl('');
  };

  return (
    <form onSubmit={handleSubmit} className="d-flex flex-column gap-3">
      <div className="d-flex justify-content-between align-items-center">
        <label htmlFor="review-text" className="form-label text-secondary fw-semibold mb-0">
          Paste Product / Service Review
        </label>
        <span className={`small ${text.trim().length < minCharCount ? 'text-warning' : 'text-success'}`}>
          {text.trim().length} chars (Min: {minCharCount})
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

      <div>
        <label htmlFor="product-url" className="form-label text-secondary fw-semibold mb-1">
          Product / Seller URL <span className="text-muted fw-normal">(optional)</span>
        </label>
        <input
          id="product-url"
          type="text"
          className="form-control form-control-custom"
          value={productUrl}
          onChange={(e) => setProductUrl(e.target.value)}
          placeholder="e.g. https://www.amazon.com/dp/XXXXXXX or the seller's storefront link"
          disabled={loading}
        />
        {!isUrlValid && (
          <div className="text-warning small mt-1">
            Please enter a valid URL syntax (e.g. site.com or https://site.com), or leave this blank.
          </div>
        )}
        <div className="text-secondary small mt-1">
          We'll flag whether the linked product/seller page looks legitimate or matches known scam patterns.
        </div>
      </div>

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
          disabled={loading || text.trim().length < minCharCount || !isUrlValid}
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