import jwt from 'jsonwebtoken';
import db from '../db/index.js';

const JWT_SECRET = process.env.JWT_SECRET || 'dev-secret-change-me';

// Required auth — blocks the request if not logged in.
export const requireAuth = (req, res, next) => {
  const header = req.headers.authorization || '';
  const token = header.startsWith('Bearer ') ? header.slice(7) : null;
  if (!token) return res.status(401).json({ error: { message: 'Login required.' } });

  try {
    const payload = jwt.verify(token, JWT_SECRET);
    req.userId = payload.userId;
    next();
  } catch {
    return res.status(401).json({ error: { message: 'Invalid or expired session.' } });
  }
};

// Optional auth — attaches userId if present, but doesn't block guests.
// This preserves the existing "works without login" behavior.
export const optionalAuth = (req, res, next) => {
  const header = req.headers.authorization || '';
  const token = header.startsWith('Bearer ') ? header.slice(7) : null;
  if (token) {
    try {
      const payload = jwt.verify(token, JWT_SECRET);
      req.userId = payload.userId;
    } catch { /* ignore invalid token, treat as guest */ }
  }
  next();
};

// Token accounting — 1 "token" per analysis call. Blocks only logged-in
// users who exceed their quota; guests are unaffected (existing behavior).
export const trackTokenUsage = (req, res, next) => {
  if (!req.userId) return next();

  const user = db.prepare('SELECT tokens_used, token_limit FROM users WHERE id = ?').get(req.userId);
  if (user && user.tokens_used >= user.token_limit) {
    return res.status(429).json({ error: { message: 'Token quota exceeded. Try again later or add your own Gemini key.' } });
  }

  db.prepare('UPDATE users SET tokens_used = tokens_used + 1 WHERE id = ?').run(req.userId);
  next();
};