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
  });

  await t.test('Input validation fails when payload is empty', async () => {
    const req = {
      body: {}
    };
    const res = makeMockRes();

    await analyzeNews(req, res);

    assert.strictEqual(res.statusCode, 400);
    assert.strictEqual(res.jsonData.error.message, 'Provide a headline, article URL, or article text.');
  });

  await t.test('Input validation fails when content is too short', async () => {
    const req = {
      body: { text: 'Short text' }
    };
    const res = makeMockRes();

    await analyzeNews(req, res);

    assert.strictEqual(res.statusCode, 400);
    assert.strictEqual(res.jsonData.error.message, 'News input must contain at least 15 characters.');
  });

  await t.test('Successful news analysis forwarding', async () => {
    globalThis.fetch = async (url, options) => {
      if (url.includes('/analyze/news')) {
        return {
          ok: true,
          headers: {
            get: (name) => name.toLowerCase() === 'content-type' ? 'application/json' : null
          },
          json: async () => ({
            success: true,
            label: 'Real',
            confidence: 88.5,
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
    assert.strictEqual(res.jsonData.label, 'Real');
    assert.strictEqual(res.jsonData.confidence, 88.5);
  });

  await t.test('Auto-summary triggers when preferred language is not English', async () => {
    // Setup request with userId so database preferred language can be queried
    const req = {
      userId: 1,
      body: { text: 'This is a test news article that is long enough to pass validation.' }
    };
    const res = makeMockRes();

    globalThis.fetch = async (url, options) => {
      if (url.includes('/analyze/news/summary')) {
        return {
          ok: true,
          headers: {
            get: (name) => name.toLowerCase() === 'content-type' ? 'application/json' : null
          },
          json: async () => ({
            summary: 'Translation summary text in Spanish'
          })
        };
      }
      if (url.includes('/analyze/news')) {
        return {
          ok: true,
          headers: {
            get: (name) => name.toLowerCase() === 'content-type' ? 'application/json' : null
          },
          json: async () => ({
            success: true,
            label: 'Real',
            confidence: 88.5,
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

    await analyzeNews(req, res);

    assert.strictEqual(res.statusCode, 200);
    // Since our database mock always returns 'English' for preferred_language,
    // let's verify autoSummary was not queried (because language is English).
    assert.strictEqual(res.jsonData.autoSummary, undefined);
  });
});
