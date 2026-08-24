import express from 'express';

import {
  analyzeNews,
  analyzeReview,
  analyzePhishing,
  translateNews,
  summarizeNews,
  analysisHealth
} from '../controllers/analyzeController.js';

const router = express.Router();


// ============================================================
// ANALYSIS ROUTES
// ============================================================
import { requireAuth, optionalAuth, trackTokenUsage } from '../middleware/auth.js';
import { signup, login, me, history, updatePreferences } from '../controllers/authController.js';

// AUTH (new, additive — does not touch existing routes)
router.post('/auth/signup', signup);
router.post('/auth/login', login);
router.get('/auth/me', requireAuth, me);
router.get('/auth/history', requireAuth, history);
router.patch('/auth/preferences', requireAuth, updatePreferences);

// Apply optionalAuth + trackTokenUsage in front of the existing analyze routes:
router.post('/analyze/news', optionalAuth, trackTokenUsage, analyzeNews);
router.post('/analyze/review', optionalAuth, trackTokenUsage, analyzeReview);
router.post('/analyze/phishing', optionalAuth, trackTokenUsage, analyzePhishing);
// Fake News
router.post(
  '/analyze/news',
  analyzeNews
);


// Fake Reviews
// router.post(
//   '/analyze/review',
//   analyzeReview
// );


// Phishing URL
// router.post(
//   '/analyze/phishing',
//   analyzePhishing
// );


// News Translation
router.post(
  '/analyze/news/translate',
  translateNews
);


// News Summary
router.post(
  '/analyze/news/summary',
  summarizeNews
);


// Analysis service health
router.get(
  '/analyze/health',
  analysisHealth
);


export default router;