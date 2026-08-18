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
 */


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

          // Forward authenticated user information
          // if your auth middleware provides it.
          ...(options.headers || {})
        },

        body: JSON.stringify(
          payload
        ),

        signal:
          controller.signal
      }
    );

    const contentType =
      response.headers.get(
        'content-type'
      ) || '';

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


// ============================================================
// NEWS
// ============================================================

/**
 * POST /api/v1/analyze/news
 *
 * Supports:
 *
 * {
 *   "text": "headline..."
 * }
 *
 * OR
 *
 * {
 *   "headline": "headline...",
 *   "article_url": "https://..."
 * }
 *
 * OR
 *
 * {
 *   "headline": "...",
 *   "article_url": "...",
 *   "article_text": "..."
 * }
 *
 * Gemini:
 *
 * - User Gemini authorization can be forwarded
 *   by your authentication layer.
 *
 * - If the user has no Gemini authorization,
 *   Python can use the TrustGuard server Gemini
 *   configuration.
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


    // --------------------------------------------------------
    // Backward compatibility
    //
    // Existing frontend:
    //
    // { text: "..." }
    //
    // continues to work.
    // --------------------------------------------------------

    const finalHeadline =
      newsHeadline ||
      legacyText;


    // --------------------------------------------------------
    // Validate
    // --------------------------------------------------------

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


    // --------------------------------------------------------
    // Validate minimum content
    // --------------------------------------------------------

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

      // Legacy compatibility
      text:
        finalHeadline,

      // New functionality
      headline:
        finalHeadline,

      article_url:
        articleUrl,

      article_text:
        articleText,

      mode:
        mode || 'auto'
    };


    // --------------------------------------------------------
    // Optional user authentication context
    // --------------------------------------------------------
    //
    // DO NOT send raw OAuth secrets from the browser.
    //
    // If your authentication middleware has already
    // authenticated the user, use a server-side identifier
    // or secure credential reference.
    //
    // Example:
    //
    // req.user.id
    //
    // The Python service can then resolve the user's
    // authorized Gemini credentials.
    // --------------------------------------------------------

    if (req.user) {

      payload.user_id =
        req.user.id;
    }


    // --------------------------------------------------------
    // Optional internal auth
    // --------------------------------------------------------

    const headers = {};

    if (
      process.env.ML_SERVICE_TOKEN
    ) {

      headers[
        'X-ML-Service-Token'
      ] =
        process.env.ML_SERVICE_TOKEN;
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
    // Return exactly what Python generated
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


    // --------------------------------------------------------
    // Timeout
    // --------------------------------------------------------

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


    // --------------------------------------------------------
    // Python service error
    // --------------------------------------------------------

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


    // --------------------------------------------------------
    // Service unavailable
    // --------------------------------------------------------

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
 *
 * Payload:
 *
 * {
 *   "text": "This product is amazing..."
 * }
 */
export const analyzeReview = async (
  req,
  res
) => {

  try {

    const {
      text
    } = req.body || {};


    // --------------------------------------------------------
    // Validate
    // --------------------------------------------------------

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


    // --------------------------------------------------------
    // Call Python
    // --------------------------------------------------------

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


    // --------------------------------------------------------
    // Return ensemble result
    // --------------------------------------------------------

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
// PHISHING
// ============================================================

/**
 * POST /api/v1/analyze/phishing
 *
 * Payload:
 *
 * {
 *   "url": "https://example.com"
 * }
 */
export const analyzePhishing = async (
  req,
  res
) => {

  try {

    const {
      url
    } = req.body || {};


    // --------------------------------------------------------
    // Validate URL
    // --------------------------------------------------------

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


    // --------------------------------------------------------
    // More reliable URL validation
    //
    // Do NOT use the old regex.
    // It rejects many legitimate URLs and can behave badly
    // with complex URLs.
    // --------------------------------------------------------

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


    // --------------------------------------------------------
    // Call Python phishing ensemble
    // --------------------------------------------------------

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


    // --------------------------------------------------------
    // Return ensemble result
    // --------------------------------------------------------

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

/**
 * POST /api/v1/analyze/news/translate
 *
 * Payload:
 *
 * {
 *   "text": "...",
 *   "language": "Hindi"
 * }
 */
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

/**
 * POST /api/v1/analyze/news/summary
 *
 * Payload:
 *
 * {
 *   "text": "...",
 *   "language": "English"
 * }
 */
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

/**
 * GET /api/v1/analyze/health
 */
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