/**
 * TrustGuard Analysis Gateway
 *
 * Node/Express API
 *        ↓
 * Python FastAPI ML Service
 *        ↓
 * ┌──────────────┬──────────────┬──────────────┐
 * │ Local Models │ Kaggle Models│ Gemini/Web   │
 * └──────────────┴──────────────┴──────────────┘
 *                       ↓
 *                  MODEL POLL
 *                       ↓
 *                  FINAL RESULT
 *
 * IMPORTANT:
 * This gateway does NOT create fake fallback predictions.
 * If the ML service is unavailable, it returns an error.
 *
 * UPGRADE NOTE (auth):
 * All existing behavior for anonymous/guest requests is unchanged.
 * When req.userId is present (see middleware/auth.js optionalAuth), the
 * result is additionally saved to analysis_history and, for the news
 * endpoint, an automatic translation/summary is attached in the user's
 * saved preferred_language.
 */

import db from '../db/index.js';

// ============================================================
// HELPERS
// ============================================================

const getMLServiceUrl = () => {
  return (
    process.env.PYTHON_ML_SERVICE_URL ||
    'http://127.0.0.1:8000'
  );
};

/**
 * Safely call Python ML service.
 */
const callMLService = async (
  endpoint,
  payload,
  options = {}
) => {

  const mlServiceUrl = getMLServiceUrl();

  const controller = new AbortController();

  const timeout = setTimeout(() => {
    controller.abort();
  }, options.timeout || 60000);

  try {

    const response = await fetch(
      `${mlServiceUrl}${endpoint}`,
      {
        method: 'POST',

        headers: {
          'Content-Type': 'application/json',
          ...(options.headers || {})
        },

        body: JSON.stringify(
          payload
        ),

        signal:
          controller.signal
      }
    );

    const contentType = (response.headers && typeof response.headers.get === 'function')
      ? (response.headers.get('content-type') || '')
      : 'application/json';

    let data;

    if (
      contentType.includes(
        'application/json'
      )
    ) {

      data =
        await response.json();

    } else {

      data =
        await response.text();
    }

    if (!response.ok) {

      const message =
        typeof data === 'object'
          ? data.detail ||
            data.error?.message ||
            'ML service returned an error.'
          : data ||
            'ML service returned an error.';

      const error =
        new Error(message);

      error.status =
        response.status;

      throw error;
    }

    return data;

  } finally {

    clearTimeout(
      timeout
    );
  }
};

/** Best-effort user context lookup. Never throws — history/translation
 *  are enhancements, not required for the core analysis to succeed. */
const getUserContext = (userId) => {
  if (!userId) return null;
  try {
    return db
      .prepare('SELECT preferred_language, gemini_api_key FROM users WHERE id = ?')
      .get(userId);
  } catch (err) {
    console.warn('getUserContext failed:', err.message);
    return null;
  }
};

const saveHistory = (userId, type, inputSummary, result) => {
  if (!userId) return;
  try {
    db.prepare(
      `INSERT INTO analysis_history
        (user_id, type, input_summary, result_label, confidence, raw_result)
       VALUES (?, ?, ?, ?, ?, ?)`
    ).run(
      userId,
      type,
      String(inputSummary || '').slice(0, 300),
      result?.label ?? result?.poll?.winner ?? null,
      result?.confidence ?? result?.poll?.confidence ?? null,
      JSON.stringify(result)
    );
  } catch (err) {
    // History is a convenience feature — never fail the analysis over it.
    console.warn('saveHistory failed:', err.message);
  }
};


// ============================================================
// NEWS
// ============================================================

/**
 * POST /api/v1/analyze/news
 */
export const analyzeNews = async (
  req,
  res
) => {

  try {

    const {
      text = '',
      headline = '',
      article_url = '',
      article_text = '',
      mode = 'auto'
    } = req.body || {};


    // --------------------------------------------------------
    // Normalize input
    // --------------------------------------------------------

    const legacyText =
      typeof text === 'string'
        ? text.trim()
        : '';

    const newsHeadline =
      typeof headline === 'string'
        ? headline.trim()
        : '';

    const articleUrl =
      typeof article_url === 'string'
        ? article_url.trim()
        : '';

    const articleText =
      typeof article_text === 'string'
        ? article_text.trim()
        : '';

    const finalHeadline =
      newsHeadline ||
      legacyText;


    if (
      !finalHeadline &&
      !articleUrl &&
      !articleText
    ) {

      return res.status(
        400
      ).json({

        error: {
          message:
            'Provide a headline, article URL, or article text.'
        }

      });
    }

    const totalInputLength =
      (
        finalHeadline +
        articleUrl +
        articleText
      ).trim().length;

    if (
      totalInputLength < 15
    ) {

      return res.status(
        400
      ).json({

        error: {
          message:
            'News input must contain at least 15 characters.'
        }

      });
    }


    // --------------------------------------------------------
    // Build Python payload
    // --------------------------------------------------------

    const payload = {

      text:
        finalHeadline,

      headline:
        finalHeadline,

      article_url:
        articleUrl,

      article_text:
        articleText,

      mode:
        mode || 'auto'
    };

    if (req.userId) {
      payload.user_id = req.userId;
    }


    // --------------------------------------------------------
    // Optional per-user Gemini key + internal auth header
    // --------------------------------------------------------

    const userContext = getUserContext(req.userId);

    const headers = {};

    if (
      process.env.ML_SERVICE_TOKEN
    ) {

      headers[
        'X-ML-Service-Token'
      ] =
        process.env.ML_SERVICE_TOKEN;
    }

    // A saved per-user Gemini key takes precedence over the server default,
    // matching the existing X-Gemini-API-Key header the client already sends
    // for anonymous sessions.
    const geminiKeyHeader = req.headers ? req.headers['x-gemini-api-key'] : undefined;
    if (userContext?.gemini_api_key && !geminiKeyHeader) {
      headers['X-Gemini-API-Key'] = userContext.gemini_api_key;
    } else if (geminiKeyHeader) {
      headers['X-Gemini-API-Key'] = geminiKeyHeader;
    }


    // --------------------------------------------------------
    // Call Python ensemble
    // --------------------------------------------------------

    const mlData =
      await callMLService(
        '/analyze/news',
        payload,
        {
          timeout:
            90000,

          headers
        }
      );


    // --------------------------------------------------------
    // Auto-translate/summarize into the user's saved language
    // (additive — failure here never breaks the main result)
    // --------------------------------------------------------

    if (
      userContext?.preferred_language &&
      userContext.preferred_language !== 'English' &&
      (articleText || finalHeadline)
    ) {
      try {
        mlData.autoSummary = await callMLService(
          '/analyze/news/summary',
          {
            text: articleText || finalHeadline,
            language: userContext.preferred_language,
          },
          { timeout: 30000, headers }
        );
      } catch (translateErr) {
        console.warn('Auto-translate summary failed:', translateErr.message);
      }
    }


    // --------------------------------------------------------
    // Save history for logged-in users (additive)
    // --------------------------------------------------------

    saveHistory(req.userId, 'news', finalHeadline || articleUrl, mlData);


    // --------------------------------------------------------
    // Return exactly what Python generated (+ optional autoSummary)
    // --------------------------------------------------------

    return res.status(
      200
    ).json(
      mlData
    );


  } catch (error) {

    console.error(
      'Error in analyzeNews:',
      error
    );

    if (
      error.name ===
      'AbortError'
    ) {

      return res.status(
        504
      ).json({

        error: {
          message:
            'News analysis timed out. Please try again.'
        }

      });
    }

    if (
      error.status
    ) {

      return res.status(
        error.status >= 400 &&
        error.status < 600
          ? error.status
          : 502
      ).json({

        error: {
          message:
            error.message
        }

      });
    }

    return res.status(
      503
    ).json({

      error: {
        message:
          'TrustGuard ML service is unavailable.'
      }

    });
  }
};


// ============================================================
// REVIEW
// ============================================================

/**
 * POST /api/v1/analyze/review
 */
export const analyzeReview = async (
  req,
  res
) => {

  try {

    const {
      text
    } = req.body || {};

    if (
      typeof text !== 'string' ||
      text.trim().length < 10
    ) {

      return res.status(
        400
      ).json({

        error: {
          message:
            'Review text must be at least 10 characters long.'
        }

      });
    }

    const headers = {};

    if (
      process.env.ML_SERVICE_TOKEN
    ) {

      headers[
        'X-ML-Service-Token'
      ] =
        process.env.ML_SERVICE_TOKEN;
    }

    const mlData =
      await callMLService(
        '/analyze/review',
        {
          text:
            text.trim()
        },
        {
          timeout:
            60000,

          headers
        }
      );

    saveHistory(req.userId, 'review', text.trim(), mlData);

    return res.status(
      200
    ).json(
      mlData
    );


  } catch (error) {

    console.error(
      'Error in analyzeReview:',
      error
    );

    if (
      error.name ===
      'AbortError'
    ) {

      return res.status(
        504
      ).json({

        error: {
          message:
            'Review analysis timed out.'
        }

      });
    }

    if (
      error.status
    ) {

      return res.status(
        error.status >= 400 &&
        error.status < 600
          ? error.status
          : 502
      ).json({

        error: {
          message:
            error.message
        }

      });
    }

    return res.status(
      503
    ).json({

      error: {
        message:
          'TrustGuard ML service is unavailable.'
      }

    });
  }
};


// ============================================================
// REVIEW — FULL PAGE (extension-style: many reviews + ratings at once)
// ============================================================

/**
 * POST /api/v1/analyze/review/page
 *
 * Payload:
 * {
 *   "reviews": ["text1", "text2", ...],
 *   "ratings": [5, 5, 1, 4, ...],
 *   "url": "https://..."
 * }
 */
export const analyzeReviewPage = async (req, res) => {
  try {
    const { reviews, ratings, url } = req.body || {};

    if (!Array.isArray(reviews) || reviews.length === 0) {
      return res.status(400).json({ error: { message: 'At least one review is required.' } });
    }

    const headers = {};
    if (process.env.ML_SERVICE_TOKEN) {
      headers['X-ML-Service-Token'] = process.env.ML_SERVICE_TOKEN;
    }

    const mlData = await callMLService(
      '/analyze/review/page',
      { reviews: reviews.slice(0, 100), ratings: Array.isArray(ratings) ? ratings.slice(0, 100) : [] },
      { timeout: 90000, headers }
    );

    saveHistory(req.userId, 'review_page', url || `${reviews.length} reviews`, {
      label: mlData.verdict,
      confidence: mlData.fakeReviewRatio,
      ...mlData,
    });

    return res.status(200).json(mlData);
  } catch (error) {
    console.error('Error in analyzeReviewPage:', error);
    if (error.status) {
      return res.status(error.status >= 400 && error.status < 600 ? error.status : 502).json({
        error: { message: error.message },
      });
    }
    return res.status(503).json({ error: { message: 'TrustGuard ML service is unavailable.' } });
  }
};


// ============================================================
// PHISHING
// ============================================================

/**
 * POST /api/v1/analyze/phishing
 */
export const analyzePhishing = async (
  req,
  res
) => {

  try {

    const {
      url
    } = req.body || {};

    if (
      typeof url !== 'string' ||
      !url.trim()
    ) {

      return res.status(
        400
      ).json({

        error: {
          message:
            'A URL is required.'
        }

      });
    }

    const normalizedUrl =
      url.trim();

    let parsedUrl;

    try {

      const candidate =
        normalizedUrl.match(
          /^https?:\/\//i
        )
          ? normalizedUrl
          : `https://${normalizedUrl}`;

      parsedUrl =
        new URL(
          candidate
        );

    } catch {

      return res.status(
        400
      ).json({

        error: {
          message:
            'A valid HTTP or HTTPS URL is required.'
        }

      });
    }

    if (
      ![
        'http:',
        'https:'
      ].includes(
        parsedUrl.protocol
      )
    ) {

      return res.status(
        400
      ).json({

        error: {
          message:
            'Only HTTP and HTTPS URLs are supported.'
        }

      });
    }

    const headers = {};

    if (
      process.env.ML_SERVICE_TOKEN
    ) {

      headers[
        'X-ML-Service-Token'
      ] =
        process.env.ML_SERVICE_TOKEN;
    }

    const mlData =
      await callMLService(
        '/analyze/phishing',
        {
          url:
            parsedUrl.toString()
        },
        {
          timeout:
            60000,

          headers
        }
      );

    saveHistory(req.userId, 'phishing', parsedUrl.toString(), mlData);

    return res.status(
      200
    ).json(
      mlData
    );


  } catch (error) {

    console.error(
      'Error in analyzePhishing:',
      error
    );

    if (
      error.name ===
      'AbortError'
    ) {

      return res.status(
        504
      ).json({

        error: {
          message:
            'Phishing analysis timed out.'
        }

      });
    }

    if (
      error.status
    ) {

      return res.status(
        error.status >= 400 &&
        error.status < 600
          ? error.status
          : 502
      ).json({

        error: {
          message:
            error.message
        }

      });
    }

    return res.status(
      503
    ).json({

      error: {
        message:
          'TrustGuard ML service is unavailable.'
      }

    });
  }
};


// ============================================================
// NEWS TRANSLATION
// ============================================================

export const translateNews = async (
  req,
  res
) => {

  try {

    const {
      text,
      language
    } = req.body || {};

    if (
      typeof text !== 'string' ||
      text.trim().length < 1
    ) {

      return res.status(
        400
      ).json({

        error: {
          message:
            'Text is required.'
        }

      });
    }

    if (
      typeof language !== 'string' ||
      !language.trim()
    ) {

      return res.status(
        400
      ).json({

        error: {
          message:
            'Target language is required.'
        }

      });
    }

    const headers = {};

    if (
      process.env.ML_SERVICE_TOKEN
    ) {

      headers[
        'X-ML-Service-Token'
      ] =
        process.env.ML_SERVICE_TOKEN;
    }

    const mlData =
      await callMLService(
        '/analyze/news/translate',
        {
          text:
            text.trim(),

          language:
            language.trim()
        },
        {
          timeout:
            90000,

          headers
        }
      );

    return res.status(
      200
    ).json(
      mlData
    );


  } catch (error) {

    console.error(
      'Error in translateNews:',
      error
    );

    return res.status(
      error.status || 503
    ).json({

      error: {
        message:
          error.message ||
          'Translation service unavailable.'
      }

    });
  }
};


// ============================================================
// NEWS SUMMARY
// ============================================================

export const summarizeNews = async (
  req,
  res
) => {

  try {

    const {
      text,
      language = 'English'
    } = req.body || {};

    if (
      typeof text !== 'string' ||
      !text.trim()
    ) {

      return res.status(
        400
      ).json({

        error: {
          message:
            'Text is required.'
        }

      });
    }

    const headers = {};

    if (
      process.env.ML_SERVICE_TOKEN
    ) {

      headers[
        'X-ML-Service-Token'
      ] =
        process.env.ML_SERVICE_TOKEN;
    }

    const mlData =
      await callMLService(
        '/analyze/news/summary',
        {
          text:
            text.trim(),

          language:
            typeof language === 'string'
              ? language.trim()
              : 'English'
        },
        {
          timeout:
            90000,

          headers
        }
      );

    return res.status(
      200
    ).json(
      mlData
    );


  } catch (error) {

    console.error(
      'Error in summarizeNews:',
      error
    );

    return res.status(
      error.status || 503
    ).json({

      error: {
        message:
          error.message ||
          'Summary service unavailable.'
      }

    });
  }
};


// ============================================================
// HEALTH CHECK
// ============================================================

export const analysisHealth = async (
  req,
  res
) => {

  try {

    const mlServiceUrl =
      getMLServiceUrl();

    const response =
      await fetch(
        `${mlServiceUrl}/health`,
        {
          method: 'GET',
          signal:
            AbortSignal.timeout(
              5000
            )
        }
      );

    const data =
      await response.json();

    return res.status(
      response.ok
        ? 200
        : 503
    ).json({

      success:
        response.ok,

      gateway:
        'online',

      mlService:
        data
    });


  } catch (error) {

    return res.status(
      503
    ).json({

      success:
        false,

      gateway:
        'online',

      mlService: {
        status:
          'offline'
      },

      error: {
        message:
          'Python ML service is unavailable.'
      }
    });
  }
};

export const analyzeNewsStream = async (req, res) => {
  const mlServiceUrl = getMLServiceUrl();
  try {
    const upstream = await fetch(`${mlServiceUrl}/analyze/news/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(process.env.ML_SERVICE_TOKEN ? { 'X-ML-Service-Token': process.env.ML_SERVICE_TOKEN } : {}),
      },
      body: JSON.stringify(req.body || {}),
    });

    res.status(upstream.status);
    res.setHeader('Content-Type', 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache');
    res.setHeader('Connection', 'keep-alive');
    res.flushHeaders?.();

    if (!upstream.body) { res.end(); return; }

    const reader = upstream.body.getReader();
    const decoder = new TextDecoder();
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      res.write(decoder.decode(value, { stream: true }));
    }
    res.end();
  } catch (error) {
    console.error('Error in analyzeNewsStream:', error);
    if (!res.headersSent) {
      res.status(503).json({ error: { message: 'TrustGuard ML service is unavailable.' } });
    } else {
      res.end();
    }
  }
};