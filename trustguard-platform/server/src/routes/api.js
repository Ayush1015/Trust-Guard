import express from 'express';
import {
  analyzeNews,
  analyzeReview,
  analyzePhishing
} from '../controllers/analyzeController.js';

const router = express.Router();

// Define router endpoints mapping to analyzeController methods
router.post('/analyze/news', analyzeNews);
router.post('/analyze/review', analyzeReview);
router.post('/analyze/phishing', analyzePhishing);

export default router;
