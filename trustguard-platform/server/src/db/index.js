import { DatabaseSync } from 'node:sqlite';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Create native SQLite DatabaseSync instance
const rawDb = new DatabaseSync(path.join(__dirname, 'trustguard.db'));

// Compatibility wrapper for better-sqlite3
const db = {
  pragma(str) {
    if (str.includes('=')) {
      rawDb.exec(`PRAGMA ${str}`);
    } else {
      return rawDb.prepare(`PRAGMA ${str}`).get();
    }
  },

  exec(sql) {
    return rawDb.exec(sql);
  },

  prepare(sql) {
    const stmt = rawDb.prepare(sql);
    return {
      run(...args) {
        const result = stmt.run(...args);
        return {
          changes: result.changes,
          lastInsertRowid: typeof result.lastInsertRowid === 'bigint'
            ? Number(result.lastInsertRowid)
            : result.lastInsertRowid
        };
      },
      get(...args) {
        return stmt.get(...args);
      },
      all(...args) {
        return stmt.all(...args);
      }
    };
  }
};

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
