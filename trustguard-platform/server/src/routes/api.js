import express from 'express';

import {
  analyzeNews,
  analyzeReview,
  analyzeReviewPage,
  analyzePhishing,
  translateNews,
  summarizeNews,
  analysisHealth,
  analyzeNewsStream
} from '../controllers/analyzeController.js';

import {
  signup,
  login,
  me,
  history,
  historyDetail,
  updatePreferences
} from '../controllers/authController.js';

import { requireAuth, optionalAuth, trackTokenUsage } from '../middleware/auth.js';

const router = express.Router();


// ============================================================
// AUTH ROUTES (new — additive, does not affect existing routes)
// ============================================================

router.post('/auth/signup', signup);
router.post('/auth/login', login);
router.get('/auth/me', requireAuth, me);
router.get('/auth/history', requireAuth, history);
router.get('/auth/history/:id', requireAuth, historyDetail);
router.patch('/auth/preferences', requireAuth, updatePreferences);


// ============================================================
// ANALYSIS ROUTES
// ============================================================
//
// optionalAuth: attaches req.userId when a valid token is sent, but never
// blocks guests — existing anonymous usage keeps working exactly as before.
//
// trackTokenUsage: only enforces a quota for logged-in users; guests are
// unaffected (existing behavior preserved).

// Fake News
router.post(
  '/analyze/news',
  optionalAuth,
  trackTokenUsage,
  analyzeNews
);


// Fake Reviews
router.post(
  '/analyze/review',
  optionalAuth,
  trackTokenUsage,
  analyzeReview
);

// Fake Reviews — full page / extension bulk mode
router.post(
  '/analyze/review/page',
  optionalAuth,
  trackTokenUsage,
  analyzeReviewPage
);


// Phishing URL
router.post(
  '/analyze/phishing',
  optionalAuth,
  trackTokenUsage,
  analyzePhishing
);


// News Translation
router.post(
  '/analyze/news/translate',
  optionalAuth,
  translateNews
);


// News Summary
router.post(
  '/analyze/news/summary',
  optionalAuth,
  summarizeNews
);


// Analysis service health
router.get(
  '/analyze/health',
  analysisHealth
);

router.post('/analyze/news/stream', analyzeNewsStream);
export default router;
