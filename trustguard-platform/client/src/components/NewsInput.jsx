import { useState } from 'react';

export default function NewsInput({ onSubmit, loading }) {
  const [text, setText] = useState('');
  const minCharCount = 15;

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
        <label htmlFor="news-text" className="form-label text-secondary fw-semibold mb-0">
          Paste News Article Content
        </label>
        <span className={`small ${text.trim().length < minCharCount ? 'text-warning' : 'text-success'}`}>
          {text.trim().length} chars (Min: {minCharCount})
        </span>
      </div>
      
      <div className="textarea-wrapper">
        <textarea
          id="news-text"
          className="form-control form-control-custom"
          rows="8"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Copy and paste the full body text of the article you want to analyze here..."
          disabled={loading}
        />
        <div className="scanline"></div>
      </div>

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
              <span className="scanner-loader" role="status" aria-hidden="true"></span>
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
