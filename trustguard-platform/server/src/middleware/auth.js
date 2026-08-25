import jwt from 'jsonwebtoken';
import db from '../db/index.js';

const JWT_SECRET = process.env.JWT_SECRET;

if (!JWT_SECRET) {
  // Fail loudly in production rather than silently signing tokens with a
  // guessable default secret. In dev, a warning is enough to keep moving.
  if (process.env.NODE_ENV === 'production') {
    throw new Error('JWT_SECRET environment variable is required in production.');
  }
  console.warn(
    '[auth] JWT_SECRET is not set. Using an insecure dev-only fallback. ' +
    'Set JWT_SECRET in your .env before deploying.'
  );
}

const SECRET = JWT_SECRET || 'dev-only-insecure-secret-change-me';

/** Blocks the request unless a valid Bearer token is present. */
export const requireAuth = (req, res, next) => {
  const header = req.headers.authorization || '';
  const token = header.startsWith('Bearer ') ? header.slice(7) : null;
  if (!token) {
    return res.status(401).json({ error: { message: 'Login required.' } });
  }

  try {
    const payload = jwt.verify(token, SECRET);
    req.userId = payload.userId;
    next();
  } catch {
    return res.status(401).json({ error: { message: 'Invalid or expired session.' } });
  }
};

/**
 * Attaches req.userId when a valid token is present, but never blocks the
 * request. This preserves the app's existing "works fine for guests"
 * behavior while enabling history/token-tracking for logged-in users.
 */
export const optionalAuth = (req, res, next) => {
  const header = req.headers.authorization || '';
  const token = header.startsWith('Bearer ') ? header.slice(7) : null;
  if (token) {
    try {
      const payload = jwt.verify(token, SECRET);
      req.userId = payload.userId;
    } catch {
      // Invalid/expired token from a logged-in-looking client: treat as
      // guest rather than erroring, so a stale token never blocks analysis.
    }
  }
  next();
};

/**
 * Counts one analysis call against the logged-in user's quota. Guests are
 * never rate-limited by this middleware (existing behavior preserved).
 */
export const trackTokenUsage = (req, res, next) => {
  if (!req.userId) return next();

  const user = db.prepare('SELECT tokens_used, token_limit FROM users WHERE id = ?').get(req.userId);
  if (!user) return next();

  if (user.tokens_used >= user.token_limit) {
    return res.status(429).json({
      error: {
        message:
          'You have used all your free analysis tokens for this period. ' +
          'Add your own Gemini API key in settings to continue without limits.',
      },
    });
  }

  db.prepare('UPDATE users SET tokens_used = tokens_used + 1 WHERE id = ?').run(req.userId);
  next();
};

export { SECRET as JWT_SECRET_FOR_TESTS_ONLY };
