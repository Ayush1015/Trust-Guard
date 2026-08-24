import test from 'node:test';
import assert from 'node:assert';
import { analyzeNews } from '../src/controllers/analyzeController.js';

// Setup environment variables for tests
process.env.PYTHON_ML_SERVICE_URL = 'http://mock-ml-service';

const makeMockRes = () => {
  return {
    statusCode: 200,
    jsonData: null,
    status(code) {
      this.statusCode = code;
      return this;
    },
    json(data) {
      this.jsonData = data;
      return this;
    }
  };
};

test('analyzeNews tests suite', async (t) => {
  const originalFetch = globalThis.fetch;

  t.afterEach(() => {
    globalThis.fetch = originalFetch;
    delete process.env.FACT_CHECK_API_KEY;
  });

  await t.test('API key missing - falls back to local ML model', async () => {
    // FACT_CHECK_API_KEY is not set
    delete process.env.FACT_CHECK_API_KEY;

    // Mock ML service call to succeed
    globalThis.fetch = async (url, options) => {
      if (url.includes('/analyze/news')) {
        return {
          ok: true,
          json: async () => ({
            label: 'Real',
            confidence: 88.5,
            badgeClass: 'success',
            metrics: {
              linguisticStyleMatch: 90.0,
              aiTextProbability: 10.0
            },
            explanation: 'Looks real.'
          })
        };
      }
      return { ok: false, status: 404 };
    };

    const req = {
      body: { text: 'This is a test news article that is long enough to pass validation.' }
    };
    const res = makeMockRes();

    await analyzeNews(req, res);

    assert.strictEqual(res.statusCode, 200);
    assert.strictEqual(res.jsonData.success, true);
    assert.strictEqual(res.jsonData.factCheckStatus, 'unavailable');
    assert.strictEqual(res.jsonData.source, 'local_ml_model');
    assert.strictEqual(res.jsonData.label, 'Real');
    assert.strictEqual(res.jsonData.confidence, 88.5);
  });

  await t.test('Successful fact-check match', async () => {
    process.env.FACT_CHECK_API_KEY = 'test_key';

    globalThis.fetch = async (url, options) => {
      // Mock Google Fact Check API
      if (url.includes('factchecktools.googleapis.com')) {
        return {
          ok: true,
          json: async () => ({
            claims: [
              {
                text: 'The earth is flat',
                claimReview: [
                  {
                    publisher: { name: 'Science Check' },
                    url: 'https://sciencecheck.org/earth',
                    reviewDate: '2026-08-18',
                    textualRating: 'False'
                  }
                ]
              }
            ]
          })
        };
      }
      // Mock local ML
      if (url.includes('/analyze/news')) {
        return {
          ok: true,
          json: async () => ({
            label: 'Fake',
            confidence: 90.0,
            badgeClass: 'danger',
            metrics: {
              linguisticStyleMatch: 40.0,
              aiTextProbability: 80.0
            },
            explanation: 'ML thinks it is fake.'
          })
        };
      }
      return { ok: false, status: 404 };
    };

    const req = {
      body: { text: 'The earth is flat and we have been lied to for generations.' }
    };
    const res = makeMockRes();

    await analyzeNews(req, res);

    assert.strictEqual(res.statusCode, 200);
    assert.strictEqual(res.jsonData.success, true);
    assert.strictEqual(res.jsonData.factCheckStatus, 'match_found');
    assert.strictEqual(res.jsonData.source, 'google_fact_check_api');
    assert.strictEqual(res.jsonData.label, 'Fake');
    assert.strictEqual(res.jsonData.confidence, 99.0);
    assert.strictEqual(res.jsonData.factChecks.length, 1);
    assert.strictEqual(res.jsonData.factChecks[0].publisher, 'Science Check');
    assert.strictEqual(res.jsonData.factChecks[0].rating, 'False');
  });

  await t.test('No fact-check match - falls back to local ML model', async () => {
    process.env.FACT_CHECK_API_KEY = 'test_key';

    globalThis.fetch = async (url, options) => {
      // Mock Google Fact Check API returning empty claims
      if (url.includes('factchecktools.googleapis.com')) {
        return {
          ok: true,
          json: async () => ({ claims: [] })
        };
      }
      // Mock local ML
      if (url.includes('/analyze/news')) {
        return {
          ok: true,
          json: async () => ({
            label: 'Real',
            confidence: 85.0,
            badgeClass: 'success',
            metrics: {
              linguisticStyleMatch: 95.0,
              aiTextProbability: 5.0
            },
            explanation: 'ML thinks it is real.'
          })
        };
      }
      return { ok: false, status: 404 };
    };

    const req = {
      body: { text: 'A completely normal news article with zero matches.' }
    };
    const res = makeMockRes();

    await analyzeNews(req, res);

    assert.strictEqual(res.statusCode, 200);
    assert.strictEqual(res.jsonData.success, true);
    assert.strictEqual(res.jsonData.factCheckStatus, 'no_match');
    assert.strictEqual(res.jsonData.source, 'local_ml_model');
    assert.strictEqual(res.jsonData.label, 'Real');
    assert.strictEqual(res.jsonData.confidence, 85.0);
    assert.match(res.jsonData.explanation, /No matching published fact check was found/);
  });

  await t.test('Google API timeout/error - falls back to local ML model', async () => {
    process.env.FACT_CHECK_API_KEY = 'test_key';

    globalThis.fetch = async (url, options) => {
      // Mock Google Fact Check API failure / timeout
      if (url.includes('factchecktools.googleapis.com')) {
        throw new Error('Timeout or network error');
      }
      // Mock local ML
      if (url.includes('/analyze/news')) {
        return {
          ok: true,
          json: async () => ({
            label: 'Real',
            confidence: 85.0,
            badgeClass: 'success',
            metrics: {
              linguisticStyleMatch: 95.0,
              aiTextProbability: 5.0
            },
            explanation: 'ML works.'
          })
        };
      }
      return { ok: false, status: 404 };
    };

    const req = {
      body: { text: 'A news article that causes Google API to throw an error.' }
    };
    const res = makeMockRes();

    await analyzeNews(req, res);

    assert.strictEqual(res.statusCode, 200);
    assert.strictEqual(res.jsonData.success, true);
    assert.strictEqual(res.jsonData.factCheckStatus, 'unavailable');
    assert.strictEqual(res.jsonData.source, 'local_ml_model');
    assert.strictEqual(res.jsonData.label, 'Real');
    assert.strictEqual(res.jsonData.confidence, 85.0);
  });
});
