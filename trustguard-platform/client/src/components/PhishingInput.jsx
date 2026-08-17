import { useState } from 'react';

export default function PhishingInput({ onSubmit, loading }) {
  const [url, setUrl] = useState('');
  
  // Simple URL validation regex
  const urlRegex = /^(https?:\/\/)?([\da-z.-]+)\.([a-z.]{2,6})([/\w .-]*)*\/?$/;

  const isValidUrl = urlRegex.test(url.trim());

  const handleSubmit = (e) => {
    e.preventDefault();
    if (isValidUrl) {
      onSubmit({ url: url.trim() });
    }
  };

  const handleClear = () => {
    setUrl('');
  };

  return (
    <form onSubmit={handleSubmit} className="d-flex flex-column gap-3">
      <div>
        <label htmlFor="target-url" className="form-label text-secondary fw-semibold mb-1">
          Scan Destination URL
        </label>
        <div className="input-group">
          <span className="input-group-text form-control-custom bg-secondary border-end-0 text-muted" style={{ borderTopRightRadius: 0, borderBottomRightRadius: 0 }}>
            <i className="bi bi-link-45deg"></i>
          </span>
          <input
            id="target-url"
            type="text"
            className="form-control form-control-custom border-start-0"
            style={{ borderTopLeftRadius: 0, borderBottomLeftRadius: 0 }}
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="e.g. https://secure-login.paypal-verification.xyz or google.com"
            disabled={loading}
          />
        </div>
        {url && !isValidUrl && (
          <div className="text-warning small mt-1">
            Please enter a valid URL syntax (e.g. site.com or https://site.com)
          </div>
        )}
      </div>

      <div className="d-flex gap-2 justify-content-end">
        <button
          type="button"
          className="btn btn-outline-secondary px-4 py-2"
          onClick={handleClear}
          disabled={loading || !url}
          style={{ borderRadius: '10px' }}
        >
          Clear
        </button>
        <button
          type="submit"
          className="btn btn-cyber d-flex align-items-center gap-2"
          disabled={loading || !isValidUrl}
        >
          {loading ? (
            <>
              <span className="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>
              Inspecting Domain...
            </>
          ) : (
            <>
              <i className="bi bi-shield-slash"></i>
              Scan URL
            </>
          )}
        </button>
      </div>
    </form>
  );
}
