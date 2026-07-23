# RepoPulse AI — Backend

Flask backend for RepoPulse AI, an AI-powered GitHub Repository Health Analyzer.

Python deterministically computes every repository metric and health score.
Machine Learning (scikit-learn) forecasts future commit activity. Groq
only explains the already-computed metrics in natural language —
it never calculates the health score itself.

## Folder Structure

```
backend/
├── app.py              # Flask controller: routes + workflow orchestration only
├── config.py           # Centralized environment/config loading
├── github_api.py        # GitHub REST API data fetching (no scoring)
├── analytics.py          # Core scoring engine (all health metrics)
├── ml_forecast.py         # Linear Regression commit forecasting
├── ai_summary.py           # Groq API integration + fallback summary
├── utils.py                 # Shared helpers (retries, pagination, dates, etc.)
├── cache.py                   # In-memory TTL cache (Redis-swappable)
├── prompts/
│   └── repo_summary.txt         # Groq prompt template
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

## Installation

```bash
cd backend
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Environment Setup

```bash
cp .env.example .env
```

Then fill in:
- `GITHUB_TOKEN` — a GitHub personal access token. Without it you're capped
  at 60 requests/hour; with it, 5,000/hour. Needed for anything beyond
  the smallest test repos.
- `GROQ_API_KEY` — your GroqCloud API key. If omitted, `/api/analyze` still
  works — `ai_summary.py` returns a deterministic fallback summary instead
  of calling Groq.

## Running Locally

```bash
python app.py
```

The server starts on `http://localhost:5000` (configurable via `PORT`).

For production-like local testing:

```bash
gunicorn app:app --bind 0.0.0.0:5000
```

## API Endpoints

### `GET /api/health`

Liveness check.

```json
{ "success": true, "data": { "status": "ok" } }
```

### `POST /api/analyze`

Analyzes a public GitHub repository end-to-end.

**Request body:**
```json
{
  "owner": "facebook",
  "repository": "react"
}
```

**Response body (200):**
```json
{
  "success": true,
  "cached": false,
  "data": {
    "repository": { "full_name": "facebook/react", "stars": 12345, "...": "..." },
    "scores": {
      "overall_health": 82,
      "activity_score": 100,
      "issue_score": 76,
      "contributor_score": 91,
      "bus_factor": 4,
      "documentation_score": 100,
      "release_score": 85,
      "commit_quality_score": 68
    },
    "forecast": {
      "predicted_next_week_commits": 42,
      "trend": "stable",
      "method": "linear_regression",
      "weekly_commit_history": [ { "week_start": "2026-06-01", "commit_count": 38 } ]
    },
    "contributors": [ { "login": "gaearon", "contributions": 1500 } ],
    "languages": { "JavaScript": 900000, "TypeScript": 300000 },
    "ai_insights": {
      "overall_summary": "...",
      "strengths": ["..."],
      "weaknesses": ["..."],
      "risk_level": "Low",
      "recommendations": ["..."],
      "source": "groq"
    }
  }
}
```

**Error response (4xx/5xx):**
```json
{ "success": false, "error": "Repository 'owner/repo' not found." }
```

Results are cached in-memory per `owner/repository` for `CACHE_TTL_SECONDS`
(default 900s / 15 min) to avoid redundant GitHub API calls.

## Deployment

### Backend (Render)

1. Push this `backend/` folder to a GitHub repo.
2. Create a new Web Service on Render, pointing at the repo.
3. Build command: `pip install -r requirements.txt`
4. Start command: `gunicorn app:app --bind 0.0.0.0:$PORT`
5. Add environment variables from `.env.example` in Render's dashboard.

**Note:** Render's free tier spins down after inactivity — the first
request after idle can take 10-30 seconds while the instance cold-starts.
This is expected, not a bug.

### Frontend (Vercel)

Point the frontend's API base URL at your deployed Render backend URL and
set `CORS_ORIGIN` on the backend to your Vercel deployment's origin.

## Notes on Design Decisions

- **Caching is in-memory, not Redis**, for simplicity in the initial build.
  `cache.py` is written with a small `get/set/delete/clear` interface
  specifically so a `RedisCache` class can be dropped in later without
  touching any call sites.
- **ML forecasting falls back to a moving-average heuristic** for repos
  with fewer than 4 weeks of commit history, since linear regression on
  that little data is unreliable.
- **Groq failures never break the API.** If the Groq API key is missing,
  the request times out, or the response isn't valid JSON, `ai_summary.py`
  returns a deterministic, template-based summary instead.