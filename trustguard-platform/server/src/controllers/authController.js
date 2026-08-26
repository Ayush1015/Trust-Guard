import bcrypt from 'bcryptjs';
import jwt from 'jsonwebtoken';
import db from '../db/index.js';

const JWT_SECRET = process.env.JWT_SECRET || 'dev-only-insecure-secret-change-me';
const TOKEN_EXPIRY = '7d';
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export const signup = async (req, res) => {
  try {
    const { email, password } = req.body || {};

    if (typeof email !== 'string' || !EMAIL_RE.test(email.trim())) {
      return res.status(400).json({ error: { message: 'A valid email address is required.' } });
    }
    if (typeof password !== 'string' || password.length < 8) {
      return res.status(400).json({ error: { message: 'Password must be at least 8 characters.' } });
    }

    const normalizedEmail = email.trim().toLowerCase();
    const existing = db.prepare('SELECT id FROM users WHERE email = ?').get(normalizedEmail);
    if (existing) {
      return res.status(409).json({ error: { message: 'An account with this email already exists.' } });
    }

    const passwordHash = await bcrypt.hash(password, 12);
    const info = db
      .prepare('INSERT INTO users (email, password_hash) VALUES (?, ?)')
      .run(normalizedEmail, passwordHash);

    const token = jwt.sign({ userId: info.lastInsertRowid }, JWT_SECRET, { expiresIn: TOKEN_EXPIRY });

    return res.status(201).json({
      success: true,
      token,
      user: {
        id: info.lastInsertRowid,
        email: normalizedEmail,
        preferredLanguage: 'English',
        tokensUsed: 0,
        tokenLimit: 200,
      },
    });
  } catch (err) {
    console.error('signup error:', err);
    return res.status(500).json({ error: { message: 'Signup failed. Please try again.' } });
  }
};

export const login = async (req, res) => {
  try {
    const { email, password } = req.body || {};
    if (typeof email !== 'string' || typeof password !== 'string') {
      return res.status(400).json({ error: { message: 'Email and password are required.' } });
    }

    const user = db.prepare('SELECT * FROM users WHERE email = ?').get(email.trim().toLowerCase());
    const valid = user ? await bcrypt.compare(password, user.password_hash) : false;

    if (!user || !valid) {
      return res.status(401).json({ error: { message: 'Invalid email or password.' } });
    }

    const token = jwt.sign({ userId: user.id }, JWT_SECRET, { expiresIn: TOKEN_EXPIRY });

    return res.json({
      success: true,
      token,
      user: {
        id: user.id,
        email: user.email,
        preferredLanguage: user.preferred_language,
        tokensUsed: user.tokens_used,
        tokenLimit: user.token_limit,
      },
    });
  } catch (err) {
    console.error('login error:', err);
    return res.status(500).json({ error: { message: 'Login failed. Please try again.' } });
  }
};

export const me = (req, res) => {
  const user = db
    .prepare('SELECT id, email, preferred_language, tokens_used, token_limit FROM users WHERE id = ?')
    .get(req.userId);

  if (!user) return res.status(404).json({ error: { message: 'User not found.' } });

  return res.json({
    success: true,
    user: {
      id: user.id,
      email: user.email,
      preferredLanguage: user.preferred_language,
      tokensUsed: user.tokens_used,
      tokenLimit: user.token_limit,
    },
  });
};

export const history = (req, res) => {
  const rows = db
    .prepare(
      `SELECT id, type, input_summary, result_label, confidence, created_at
       FROM analysis_history WHERE user_id = ? ORDER BY id DESC LIMIT 100`
    )
    .all(req.userId);

  return res.json({ success: true, history: rows });
};

export const historyDetail = (req, res) => {
  const row = db
    .prepare('SELECT * FROM analysis_history WHERE id = ? AND user_id = ?')
    .get(req.params.id, req.userId);

  if (!row) return res.status(404).json({ error: { message: 'History entry not found.' } });

  let raw = null;
  try {
    raw = JSON.parse(row.raw_result);
  } catch {
    raw = null;
  }

  return res.json({ success: true, entry: { ...row, raw_result: raw } });
};

export const updatePreferences = (req, res) => {
  const { preferredLanguage, geminiApiKey } = req.body || {};

  if (preferredLanguage !== undefined && typeof preferredLanguage !== 'string') {
    return res.status(400).json({ error: { message: 'preferredLanguage must be a string.' } });
  }
  if (geminiApiKey !== undefined && typeof geminiApiKey !== 'string') {
    return res.status(400).json({ error: { message: 'geminiApiKey must be a string.' } });
  }

  db.prepare(
    `UPDATE users
     SET preferred_language = COALESCE(?, preferred_language),
         gemini_api_key = COALESCE(?, gemini_api_key)
     WHERE id = ?`
  ).run(preferredLanguage ?? null, geminiApiKey ?? null, req.userId);

  return res.json({ success: true });
};
