import bcrypt from 'bcryptjs';
import jwt from 'jsonwebtoken';
import db from '../db/index.js';

const JWT_SECRET = process.env.JWT_SECRET || 'dev-secret-change-me';
const TOKEN_EXPIRY = '7d';

export const signup = async (req, res) => {
  try {
    const { email, password } = req.body || {};
    if (!email || !password || password.length < 8) {
      return res.status(400).json({ error: { message: 'Valid email and password (min 8 chars) required.' } });
    }

    const existing = db.prepare('SELECT id FROM users WHERE email = ?').get(email.toLowerCase());
    if (existing) {
      return res.status(409).json({ error: { message: 'Account already exists.' } });
    }

    const hash = await bcrypt.hash(password, 12);
    const info = db.prepare(
      'INSERT INTO users (email, password_hash) VALUES (?, ?)'
    ).run(email.toLowerCase(), hash);

    const token = jwt.sign({ userId: info.lastInsertRowid }, JWT_SECRET, { expiresIn: TOKEN_EXPIRY });
    return res.status(201).json({ success: true, token, user: { id: info.lastInsertRowid, email } });
  } catch (err) {
    console.error('signup error:', err);
    return res.status(500).json({ error: { message: 'Signup failed.' } });
  }
};

export const login = async (req, res) => {
  try {
    const { email, password } = req.body || {};
    const user = db.prepare('SELECT * FROM users WHERE email = ?').get((email || '').toLowerCase());
    if (!user || !(await bcrypt.compare(password || '', user.password_hash))) {
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
        tokenLimit: user.token_limit
      }
    });
  } catch (err) {
    console.error('login error:', err);
    return res.status(500).json({ error: { message: 'Login failed.' } });
  }
};

export const me = (req, res) => {
  const user = db.prepare(
    'SELECT id, email, preferred_language, tokens_used, token_limit FROM users WHERE id = ?'
  ).get(req.userId);
  if (!user) return res.status(404).json({ error: { message: 'User not found.' } });
  res.json({ success: true, user });
};

export const history = (req, res) => {
  const rows = db.prepare(
    'SELECT id, type, input_summary, result_label, confidence, created_at FROM analysis_history WHERE user_id = ? ORDER BY id DESC LIMIT 100'
  ).all(req.userId);
  res.json({ success: true, history: rows });
};

export const updatePreferences = (req, res) => {
  const { preferredLanguage, geminiApiKey } = req.body || {};
  db.prepare(
    'UPDATE users SET preferred_language = COALESCE(?, preferred_language), gemini_api_key = COALESCE(?, gemini_api_key) WHERE id = ?'
  ).run(preferredLanguage || null, geminiApiKey || null, req.userId);
  res.json({ success: true });
};