import { useState } from 'react';

export default function ReviewInput({ onSubmit, loading }) {
  const [text, setText] = useState('');
  const minCharCount = 10;

  const handleSubmit = (e) => {
    e.preventDefault();
    if (text.trim().length >= minCharCount) {
      onSubmit({ text });
    }
  };

  const handleClear = () => {
    setText('');
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

      <div className="d-flex gap-2 justify-content-end">
        <button
          type="button"
          className="btn btn-outline-secondary px-4 py-2"
          onClick={handleClear}
          disabled={loading || !text}
          style={{ borderRadius: '10px' }}
        >
          Clear
        </button>
        <button
          type="submit"
          className="btn btn-cyber d-flex align-items-center gap-2"
          disabled={loading || text.trim().length < minCharCount}
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
