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

// Fake News
router.post(
  '/analyze/news',
  analyzeNews
);


// Fake Reviews
router.post(
  '/analyze/review',
  analyzeReview
);


// Phishing URL
router.post(
  '/analyze/phishing',
  analyzePhishing
);


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