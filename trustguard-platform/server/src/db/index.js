import Database from 'better-sqlite3';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const db = new Database(path.join(__dirname, 'trustguard.db'));

db.pragma('journal_mode = WAL');

db.exec(`
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  preferred_language TEXT DEFAULT 'English',
  gemini_api_key TEXT,
  tokens_used INTEGER DEFAULT 0,
  token_limit INTEGER DEFAULT 200,
  created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS analysis_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  type TEXT NOT NULL,          -- news | review | phishing
  input_summary TEXT,
  result_label TEXT,
  confidence REAL,
  raw_result TEXT,             -- JSON blob of the full analysis result
  created_at TEXT DEFAULT (datetime('now')),
  FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_history_user ON analysis_history(user_id, created_at DESC);
`);

/**
 * Reset any user's token counter. Intended to be called from a daily/monthly
 * cron (e.g. node-cron in index.js) so quotas refill instead of permanently
 * locking users out.
 */
export function resetAllTokenUsage() {
  db.prepare('UPDATE users SET tokens_used = 0').run();
}

export default db;
