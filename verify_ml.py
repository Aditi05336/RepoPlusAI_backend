"""
verify_ml.py

Runtime verification and audit script for ML Commit Forecast module.
Executes live ML forecasting on specified GitHub repositories and logs
commit data collection, week aggregation, scikit-learn LinearRegression fit,
predicted next week commits, trend direction, and fallback triggers.
"""

import sys
import logging
from typing import Dict, Any
import github_api
import ml_forecast
from utils import aggregate_weekly_commits

logging.basicConfig(level=logging.INFO)

TARGET_REPOS = [
    ("facebook", "react"),
    ("tensorflow", "tensorflow"),
    ("microsoft", "vscode"),
    ("pallets", "flask"),
    ("3107Alok", "DocMind-AI"),
]


def audit_ml_for_repo(owner: str, repo: str) -> Dict[str, Any]:
    print("\n" + "=" * 60)
    print(f"AUDITING ML FORECAST FOR: {owner}/{repo}")
    print("=" * 60)

    # Step 1: Fetch commit history
    print("1. Fetching commit history from GitHub REST API...")
    raw_commits = github_api.get_commits(owner, repo, max_pages=2)
    total_commits = len(raw_commits)
    print(f"   - Total commits fetched: {total_commits}")

    # Step 2: Parse commit dates
    parsed_dates = [c["date_parsed"] for c in raw_commits if c.get("date_parsed")]
    print(f"   - Valid commit dates parsed: {len(parsed_dates)} / {total_commits}")

    # Step 3: Aggregate weekly commits
    weekly = aggregate_weekly_commits(parsed_dates)
    total_weeks = len(weekly)
    print(f"   - Total weekly buckets generated: {total_weeks}")
    print("   - Weekly breakdown:")
    for w in weekly:
        print(f"       Week {w['week_start']}: {w['commit_count']} commits")

    # Step 4: Execute ML forecast model
    print("\n2. Executing predict_commit_trend()...")
    forecast_result = ml_forecast.predict_commit_trend(raw_commits)

    method = forecast_result.get("method")
    trend = forecast_result.get("trend")
    predicted_commits = forecast_result.get("predicted_next_week_commits")

    print(f"   - Forecast Method: '{method}'")
    print(f"   - Predicted Next Week Commits: {predicted_commits}")
    print(f"   - Trend Direction: '{trend}'")

    # Fallback condition check
    min_required = ml_forecast.MIN_WEEKS_FOR_REGRESSION
    fallback_triggered = method == "fallback"
    fallback_reason = "N/A"

    if total_weeks == 0:
        fallback_reason = "No commit history found (total_weeks = 0)"
    elif total_weeks < min_required:
        fallback_reason = f"Insufficient weekly history ({total_weeks} weeks available < {min_required} required)"

    if fallback_triggered:
        print(f"   - Fallback Triggered: YES (Reason: {fallback_reason})")
    else:
        print("   - Fallback Triggered: NO (scikit-learn LinearRegression model fitted successfully!)")

    return {
        "repo": f"{owner}/{repo}",
        "total_commits": total_commits,
        "total_weeks": total_weeks,
        "required_weeks": min_required,
        "method": method,
        "predicted_commits": predicted_commits,
        "trend": trend,
        "fallback_triggered": fallback_triggered,
        "fallback_reason": fallback_reason,
    }


def main():
    results = []
    for owner, repo in TARGET_REPOS:
        res = audit_ml_for_repo(owner, repo)
        results.append(res)

    print("\n" + "=" * 60)
    print("SUMMARY ML AUDIT REPORT")
    print("=" * 60)
    print(f"{'Repository':<25} | {'Commits':<8} | {'Weeks':<6} | {'Method':<18} | {'Predicted':<10} | {'Trend':<12}")
    print("-" * 85)
    for r in results:
        print(f"{r['repo']:<25} | {r['total_commits']:<8} | {r['total_weeks']:<6} | {r['method']:<18} | {r['predicted_commits']:<10} | {r['trend']:<12}")
    print("=" * 60)


if __name__ == "__main__":
    main()
