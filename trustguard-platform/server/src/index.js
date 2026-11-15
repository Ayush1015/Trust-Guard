import express from 'express';
import cors from 'cors';
import dotenv from 'dotenv';
import apiRouter from './routes/api.js';
import path from 'path';
import { fileURLToPath } from 'url';

// Load environment variables
dotenv.config();

const app = express();
const PORT = process.env.PORT || 5000;

// Middleware
// The TrustGuard browser extension calls this gateway from a
// chrome-extension:// / moz-extension:// origin, and background
// service-worker fetches sometimes send no Origin header at all.
// Both are allowed here in addition to the local Vite dev server.
const ALLOWED_ORIGINS = [
  'http://localhost:5173',
  'http://127.0.0.1:5173',
];

app.use(cors({
  origin: (origin, callback) => {
    if (
      !origin || // extension service workers / curl / same-origin
      ALLOWED_ORIGINS.includes(origin) ||
      /^chrome-extension:\/\//.test(origin) ||
      /^moz-extension:\/\//.test(origin) ||
      /^extension:\/\//.test(origin) // Safari web extensions
    ) {
      return callback(null, true);
    }
    return callback(new Error(`CORS blocked for origin: ${origin}`));
  },
  credentials: true
}));
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// Health check endpoint
app.get('/health', (req, res) => {
  res.status(200).json({
    status: 'UP',
    timestamp: new Date().toISOString(),
    service: 'TrustGuard Gateway API'
  });
});

// Free hosted demo never accepts accounts into ephemeral storage.
if (process.env.PUBLIC_DEMO === 'true') {
  app.use('/api/v1/auth', (req, res) => res.status(503).json({
    error: { message: 'Accounts and saved history are disabled on this temporary public demo.' }
  }));
}
// API Routes
app.use('/api/v1', apiRouter);

if (process.env.PUBLIC_DEMO === 'true') {
  const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../client/dist');
  app.use(express.static(root));
  app.get('*', (req, res) => res.sendFile(path.join(root, 'index.html')));
}

// Global Error Handler
app.use((err, req, res, next) => {
  console.error('Unhandled Error:', err);
  res.status(err.status || 500).json({
    error: {
      message: err.message || 'Internal Server Error',
      status: err.status || 500
    }
  });
});

// Start Server
const server = app.listen(PORT, () => {
  console.log(`🚀 TrustGuard API Gateway running on http://localhost:${PORT}`);
});
// Real news analysis (web search + article fetch + NLI) routinely runs
// 3-5 minutes. Node's default requestTimeout (300s) silently destroyed
// long SSE streams and slow normal requests, surfacing as client
// failures after minutes of apparently-fine progress. Budget both to
// match measured end-to-end latency; the ML service has its own guards.
server.requestTimeout = 660000;
server.headersTimeout = 70000;
