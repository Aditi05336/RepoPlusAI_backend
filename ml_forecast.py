"""
ml_forecast.py

Machine Learning module: predicts next week's commit count and determines
whether repository activity is increasing, stable, or declining.

Input: weekly commit history (from utils.aggregate_weekly_commits).
Library: scikit-learn LinearRegression.

This module ONLY handles forecasting — no scoring/health logic lives here.
"""

from typing import Any, Dict, List

import numpy as np
from sklearn.linear_model import LinearRegression

from utils import aggregate_weekly_commits

MIN_WEEKS_FOR_REGRESSION = 4  # Below this, regression is unreliable — use a fallback.
TREND_STABLE_THRESHOLD = 0.5  # Slope magnitude below this counts as "stable".


def _fallback_trend(weekly_counts: List[int]) -> Dict[str, Any]:
    """
    Simple moving-average-based fallback for repos with too little history
    for a meaningful regression fit (e.g. brand-new repos).

    Compares the most recent count to the average of prior weeks.
    """
    if not weekly_counts:
        return {
            "predicted_next_week_commits": 0,
            "trend": "insufficient_data",
            "method": "fallback",
        }

    if len(weekly_counts) == 1:
        return {
            "predicted_next_week_commits": weekly_counts[-1],
            "trend": "insufficient_data",
            "method": "fallback",
        }

    recent = weekly_counts[-1]
    prior_avg = sum(weekly_counts[:-1]) / len(weekly_counts[:-1])

    predicted_next_week = round((recent + prior_avg) / 2)

    if recent > prior_avg * 1.15:
        trend = "increasing"
    elif recent < prior_avg * 0.85:
        trend = "declining"
    else:
        trend = "stable"

    return {
        "predicted_next_week_commits": max(0, predicted_next_week),
        "trend": trend,
        "method": "fallback",
    }


def predict_commit_trend(commits: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Prepares weekly commit data, fits a LinearRegression model, and predicts
    next week's commit count + overall trend direction.

    Returns:
        {
            "predicted_next_week_commits": int,
            "trend": "increasing" | "stable" | "declining" | "insufficient_data",
            "method": "linear_regression" | "fallback",
            "weekly_commit_history": [{"week_start": ..., "commit_count": ...}, ...]
        }
    """
    commit_dates = [c["date_parsed"] for c in commits if c.get("date_parsed")]
    weekly = aggregate_weekly_commits(commit_dates)

    if not weekly:
        return {
            "predicted_next_week_commits": 0,
            "trend": "insufficient_data",
            "method": "fallback",
            "weekly_commit_history": [],
        }

    weekly_counts = [w["commit_count"] for w in weekly]

    if len(weekly) < MIN_WEEKS_FOR_REGRESSION:
        result = _fallback_trend(weekly_counts)
        result["weekly_commit_history"] = weekly
        return result

    # Smooth the series with a 2-period rolling average to reduce noise
    # before fitting, per the known limitation that raw weekly commit
    # counts are noisy.
    smoothed = _rolling_average(weekly_counts, window=2)

    X = np.arange(len(smoothed)).reshape(-1, 1)
    y = np.array(smoothed)

    model = LinearRegression()
    model.fit(X, y)

    next_week_index = np.array([[len(smoothed)]])
    predicted = model.predict(next_week_index)[0]
    predicted_next_week = max(0, round(float(predicted)))

    slope = float(model.coef_[0])

    if abs(slope) < TREND_STABLE_THRESHOLD:
        trend = "stable"
    elif slope > 0:
        trend = "increasing"
    else:
        trend = "declining"

    return {
        "predicted_next_week_commits": predicted_next_week,
        "trend": trend,
        "method": "linear_regression",
        "weekly_commit_history": weekly,
    }


def _rolling_average(values: List[int], window: int = 2) -> List[float]:
    """Simple centered-ish trailing rolling average to smooth noisy series."""
    if window <= 1 or len(values) <= window:
        return [float(v) for v in values]

    smoothed = []
    for i in range(len(values)):
        start = max(0, i - window + 1)
        chunk = values[start : i + 1]
        smoothed.append(sum(chunk) / len(chunk))
    return smoothed