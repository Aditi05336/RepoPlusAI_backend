"""
analytics.py

The core analytics engine. Computes all repository health metrics
deterministically in Python. The LLM (Groq) never performs these
calculations — it only explains them (see ai_summary.py).

Each score function accepts raw GitHub data (as returned by github_api.py)
and returns a numeric score, generally on a 0-100 scale.
"""

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from utils import aggregate_weekly_commits

# Weights for the overall health formula, per the project spec:
# Overall Health = Activity*0.30 + Issues*0.20 + Contributors*0.20
#                  + Documentation*0.15 + Releases*0.15
#
# NOTE: The spec's weights sum to 1.00 and explicitly omit Commit Quality
# from the weighted formula (it's listed separately in section 7/10).
# We keep Commit Quality as its own reported score, not folded into
# Overall Health, to match the spec exactly.
WEIGHTS = {
    "activity": 0.30,
    "issues": 0.20,
    "contributors": 0.20,
    "documentation": 0.15,
    "releases": 0.15,
}


# ---------------------------------------------------------------------------
# Activity Score
# ---------------------------------------------------------------------------
def calculate_activity_score(commits: List[Dict[str, Any]]) -> int:
    """
    Score based on average commits per week over the available commit
    history, per the spec's thresholds:
        >30 commits/week  -> 100
        20-30              -> 85
        10-20               -> 70
        <10                 -> 40
    """
    weekly = aggregate_weekly_commits(
        [c["date_parsed"] for c in commits if c.get("date_parsed")]
    )

    if not weekly:
        return 0

    avg_commits_per_week = sum(w["commit_count"] for w in weekly) / len(weekly)

    if avg_commits_per_week > 30:
        return 100
    elif avg_commits_per_week >= 20:
        return 85
    elif avg_commits_per_week >= 10:
        return 70
    else:
        return 40


# ---------------------------------------------------------------------------
# Issue Resolution Score
# ---------------------------------------------------------------------------
def calculate_issue_score(issues: Dict[str, List[Dict[str, Any]]]) -> int:
    """
    Score = closed / (open + closed) * 100

    Edge case: a repo with zero issues total is treated as a perfect score
    (nothing outstanding, no evidence of poor issue hygiene) rather than
    dividing by zero.
    """
    open_count = len(issues.get("open", []))
    closed_count = len(issues.get("closed", []))
    total = open_count + closed_count

    if total == 0:
        return 100

    return round((closed_count / total) * 100)


# ---------------------------------------------------------------------------
# Contributor Score & Bus Factor
# ---------------------------------------------------------------------------
def calculate_bus_factor(contributors: List[Dict[str, Any]]) -> int:
    """
    Bus Factor: the minimum number of contributors whose combined commits
    account for at least 50% of total contributions. A bus factor of 1
    means a single contributor could "leave" and take half the project's
    institutional knowledge with them — high risk.
    """
    if not contributors:
        return 0

    sorted_contribs = sorted(
        contributors, key=lambda c: c.get("contributions", 0), reverse=True
    )
    total_contributions = sum(c.get("contributions", 0) for c in sorted_contribs)

    if total_contributions == 0:
        return 0

    running_total = 0
    bus_factor = 0
    for contributor in sorted_contribs:
        running_total += contributor.get("contributions", 0)
        bus_factor += 1
        if running_total >= total_contributions * 0.5:
            break

    return bus_factor


def calculate_contributor_score(contributors: List[Dict[str, Any]]) -> int:
    """
    Score based on contributor diversity and bus factor.

    Approach:
    - More total contributors -> higher baseline score (capped).
    - Higher bus factor (relative to contributor count) -> less
      single-point-of-failure risk -> higher score.

    This is a heuristic blend, not a formal spec formula, since the
    project spec only says "measure contributor diversity and bus factor."
    """
    if not contributors:
        return 0

    contributor_count = len(contributors)
    bus_factor = calculate_bus_factor(contributors)

    # Baseline from raw contributor count: 1 -> 20, 5 -> ~60, 10+ -> 100.
    count_score = min(100, 20 + (contributor_count - 1) * 9)

    # Bus factor ratio: how much of the "50% of work" is spread out,
    # relative to total contributor count.
    bus_factor_ratio = bus_factor / contributor_count if contributor_count else 0
    bus_factor_score = min(100, bus_factor_ratio * 150)  # scaled up, capped at 100

    # Weighted blend: raw headcount matters, but distribution matters more.
    final_score = (count_score * 0.4) + (bus_factor_score * 0.6)
    return round(final_score)


# ---------------------------------------------------------------------------
# Documentation Score
# ---------------------------------------------------------------------------
DOC_SECTION_PATTERNS = {
    "installation": r"#+\s*(installation|install|getting started|setup)\b",
    "usage": r"#+\s*(usage|how to use|quick start|quickstart)\b",
    "license": r"#+\s*(license|licence)\b",
    "contributing": r"#+\s*(contributing|contribution)\b",
    "api_docs": r"#+\s*(api|api reference|documentation)\b",
}


def calculate_documentation_score(readme: Optional[str]) -> int:
    """
    Checks the README for the presence of key sections: Installation,
    Usage, License, Contributing, API docs. Each present section
    contributes 20 points, for a max of 100.

    Detection is done via case-insensitive regex against markdown-style
    headers (#, ##, ###) — a lightweight approach that avoids needing a
    full markdown parser.
    """
    if not readme:
        return 0

    text = readme.lower()
    score = 0

    for _section, pattern in DOC_SECTION_PATTERNS.items():
        if re.search(pattern, text, re.IGNORECASE | re.MULTILINE):
            score += 20

    return score


# ---------------------------------------------------------------------------
# Release Score
# ---------------------------------------------------------------------------
def calculate_release_score(releases: List[Dict[str, Any]]) -> int:
    """
    Rewards recent and regular releases.

    - No releases -> 0
    - Recency: most recent release within 90 days -> up to 50 points
    - Regularity: releases spaced consistently over time -> up to 50 points
      (measured via average gap between releases; more releases with
      tighter, consistent spacing scores higher)
    """
    published = [r for r in releases if r.get("published_at")]
    if not published:
        return 0

    dates = sorted(
        [
            datetime.strptime(r["published_at"], "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=timezone.utc
            )
            for r in published
        ]
    )

    now = datetime.now(timezone.utc)
    most_recent = dates[-1]
    days_since_last = (now - most_recent).days

    # Recency component (0-50): full marks within 90 days, tapering to 0 by 365 days.
    if days_since_last <= 90:
        recency_score = 50
    elif days_since_last >= 365:
        recency_score = 0
    else:
        recency_score = round(50 * (1 - (days_since_last - 90) / (365 - 90)))

    # Regularity component (0-50): based on number of releases and consistency of gaps.
    if len(dates) == 1:
        regularity_score = 10  # A single release shows minimal cadence.
    else:
        gaps_days = [
            (dates[i] - dates[i - 1]).days for i in range(1, len(dates))
        ]
        avg_gap = sum(gaps_days) / len(gaps_days)
        # Reward frequent-ish releases (e.g. every ~30-60 days) over sparse ones.
        if avg_gap <= 60:
            regularity_score = 50
        elif avg_gap >= 365:
            regularity_score = 10
        else:
            regularity_score = round(50 - ((avg_gap - 60) / (365 - 60)) * 40)

    return round(recency_score + regularity_score)


# ---------------------------------------------------------------------------
# Commit Quality Score
# ---------------------------------------------------------------------------
VAGUE_MESSAGES = {"fix", "update", "wip", "misc", "stuff", "test", "changes", "minor fix"}


def calculate_commit_quality(commits: List[Dict[str, Any]]) -> int:
    """
    Rewards descriptive commit messages. Heuristics:
    - Length: longer, more descriptive messages score higher (up to a point).
    - Not a generic/vague placeholder message ("fix", "update", "wip", etc).
    - Bonus for conventional-commit-style prefixes (feat:, fix:, chore:, etc.)
      which signal structured commit hygiene.
    """
    if not commits:
        return 0

    conventional_prefix = re.compile(
        r"^(feat|fix|chore|docs|style|refactor|test|perf|build|ci)(\(.+\))?:\s"
    )

    scores = []
    for commit in commits:
        message = (commit.get("message") or "").strip()
        first_line = message.split("\n")[0].strip()
        lowered = first_line.lower()

        if not first_line:
            scores.append(0)
            continue

        if lowered in VAGUE_MESSAGES or len(first_line) < 6:
            scores.append(20)
            continue

        length_score = min(60, len(first_line))  # up to 60 pts from length/detail
        conventional_bonus = 25 if conventional_prefix.match(first_line) else 0
        multi_line_bonus = 15 if "\n" in message.strip() else 0

        commit_score = min(100, length_score + conventional_bonus + multi_line_bonus)
        scores.append(commit_score)

    return round(sum(scores) / len(scores))


# ---------------------------------------------------------------------------
# Overall Health
# ---------------------------------------------------------------------------
def calculate_overall_health(
    activity_score: int,
    issue_score: int,
    contributor_score: int,
    documentation_score: int,
    release_score: int,
) -> int:
    """
    Weighted overall health score, per the spec's formula:
        Overall Health = Activity*0.30 + Issues*0.20 + Contributors*0.20
                         + Documentation*0.15 + Releases*0.15
    """
    weighted_sum = (
        activity_score * WEIGHTS["activity"]
        + issue_score * WEIGHTS["issues"]
        + contributor_score * WEIGHTS["contributors"]
        + documentation_score * WEIGHTS["documentation"]
        + release_score * WEIGHTS["releases"]
    )
    return round(weighted_sum)


def run_full_analysis(repo_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Orchestrates all scoring functions against a full repo_data payload
    (as returned by github_api.fetch_full_repository_data) and returns a
    single dict of all computed metrics. This is what app.py should call.
    """
    commits = repo_data.get("commits", [])
    contributors = repo_data.get("contributors", [])
    issues = repo_data.get("issues", {"open": [], "closed": []})
    releases = repo_data.get("releases", [])
    readme = repo_data.get("readme")

    activity_score = calculate_activity_score(commits)
    issue_score = calculate_issue_score(issues)
    contributor_score = calculate_contributor_score(contributors)
    bus_factor = calculate_bus_factor(contributors)
    documentation_score = calculate_documentation_score(readme)
    release_score = calculate_release_score(releases)
    commit_quality_score = calculate_commit_quality(commits)

    overall_health = calculate_overall_health(
        activity_score=activity_score,
        issue_score=issue_score,
        contributor_score=contributor_score,
        documentation_score=documentation_score,
        release_score=release_score,
    )

    return {
        "overall_health": overall_health,
        "activity_score": activity_score,
        "issue_score": issue_score,
        "contributor_score": contributor_score,
        "bus_factor": bus_factor,
        "documentation_score": documentation_score,
        "release_score": release_score,
        "commit_quality_score": commit_quality_score,
    }