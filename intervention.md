# Intervention System Implementation

## Overview
Added a Word2Vec-based intervention system to measure divergence before, during, and after AI suggestions.

## Key Components

### Backend (app.py)
- **Intervention Parameters**: Turns 7-13 (configurable via INTERVENTION_START/END)
- **find_similar_words()**: Finds words with cosine similarity 0.4-0.6 from Word2Vec
- **Suggestion Logic**: Provides one AI suggestion when entering intervention phase
- **Tracking**: Records responses during intervention for analysis

### Frontend (app.js)
- Displays suggestion box showing both previous word and AI suggestion
- User writes a word related to BOTH the previous word and the suggestion
- Visual feedback distinguishes intervention turns in results

### Results Dashboard
- Shows overall divergence score
- Breaks down metrics: Before/During/After intervention
- Highlights intervention phase responses with asterisk

## Endpoints
- `/api/start`: Returns intervention_start/end parameters
- `/api/respond`: Returns suggestion when entering intervention phase
- `/api/suggest`: Gets fresh suggestions for any word
- `/api/summary`: Returns before/during/after divergence analysis

## How It Works
1. Turns 1-6: Normal game, no suggestions (measures baseline divergence)
2. Turns 7-13: AI shows suggestion based on previous word (cosine sim 0.4-0.6)
3. Turns 14+: Normal game again, no suggestions (measures post-intervention)
4. Results compare all three phases
