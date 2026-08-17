import { useState } from 'react';
import Navbar from './components/Navbar';
import TabNavigation from './components/TabNavigation';
import NewsInput from './components/NewsInput';
import ReviewInput from './components/ReviewInput';
import PhishingInput from './components/PhishingInput';
import ResultCard from './components/ResultCard';

function App() {
  const [activeTab, setActiveTab] = useState('news');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  // Clear previous results and errors when switching modules
  const handleTabChange = (tab) => {
    setActiveTab(tab);
    setResult(null);
    setError(null);
  };

  const handleAnalysisSubmit = async (payload) => {
    setLoading(true);
    setResult(null);
    setError(null);

    const apiPath = `http://localhost:5000/api/v1/analyze/${activeTab}`;

    try {
      const response = await fetch(apiPath, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error?.message || 'Verification request failed. Please check inputs and try again.');
      }

      setResult(data);
    } catch (err) {
      console.error('API Error:', err);
      setError(err.message || 'Unable to connect to the TrustGuard security gateway.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="d-flex flex-column min-vh-100">
      {/* Brand Header */}
      <Navbar />

      <main className="container flex-grow-1 py-4">
        <div className="text-center mb-5">
          <h2 className="display-5 fw-extrabold text-white tracking-tight mb-2">
            Verifiable Digital Intelligence
          </h2>
          <p className="lead text-secondary mx-auto" style={{ maxWidth: '600px', fontSize: '1.1rem' }}>
            Identify machine-generated text, linguistic fraud, sensationalized claims, and web security risks with unified telemetry models.
          </p>
        </div>

        {/* Tab Selector */}
        <TabNavigation activeTab={activeTab} setActiveTab={handleTabChange} />

        {/* Content Panel */}
        <div className="row justify-content-center">
          <div className="col-lg-8">
            <div className="glass-card p-4 p-md-5 border-light-subtle shadow-lg">
              {activeTab === 'news' && (
                <NewsInput onSubmit={handleAnalysisSubmit} loading={loading} />
              )}
              {activeTab === 'review' && (
                <ReviewInput onSubmit={handleAnalysisSubmit} loading={loading} />
              )}
              {activeTab === 'phishing' && (
                <PhishingInput onSubmit={handleAnalysisSubmit} loading={loading} />
              )}
            </div>

            {/* Status alerts */}
            {error && (
              <div className="alert alert-danger d-flex align-items-center mt-4 border-0 badge-glow-danger text-danger bg-opacity-10 py-3" role="alert" style={{ borderRadius: '12px' }}>
                <i className="bi bi-exclamation-triangle-fill fs-5 me-3"></i>
                <div>
                  <strong className="text-white">Analysis Halt:</strong> {error}
                </div>
              </div>
            )}

            {/* Inference Result Card */}
            {result && !error && (
              <ResultCard result={result} type={activeTab} />
            )}
          </div>
        </div>
      </main>

      <footer className="py-4 text-center mt-5 border-top border-light-subtle bg-dark bg-opacity-20 text-muted small">
        <div className="container">
          <p className="m-0">© 2026 TrustGuard Digital Forensics. All rights reserved.</p>
          <p className="m-0 mt-1" style={{ fontSize: '0.75rem' }}>
            Node.js API Gateway <i className="bi bi-arrow-left-right mx-1 text-info"></i> Python ML Engine Pre-wiring Active
          </p>
        </div>
      </footer>
    </div>
  );
}

export default App;
