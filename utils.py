"""
utils.py

Reusable helper functions shared across the backend:
- GitHub GET wrapper with retry logic
- Pagination helper
- Date parsing
- Weekly commit aggregation
- Standard response helpers

This module should NOT contain business/scoring logic — that belongs in analytics.py.
"""

import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import requests

from config import config


class GitHubAPIError(Exception):
    """Raised when a GitHub API request fails after all retries."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


def github_get(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
) -> requests.Response:
    """
    Wrapper around requests.get with retry logic for GitHub API calls.

    Retries on network errors and on 5xx responses. Does NOT retry on 4xx
    (those are usually not-found / rate-limit / auth issues that retries
    won't fix) except for secondary rate limit signals.

    Raises GitHubAPIError if the request ultimately fails.
    """
    last_error = None

    for attempt in range(1, config.MAX_RETRIES + 1):
        try:
            response = requests.get(
                url,
                headers=headers,
                params=params,
                timeout=config.REQUEST_TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            last_error = exc
            _backoff(attempt)
            continue

        if response.status_code == 403 and _is_rate_limited(response):
            # Respect GitHub's Retry-After / reset headers where possible.
            wait_seconds = _seconds_until_rate_limit_reset(response)
            if attempt < config.MAX_RETRIES:
                time.sleep(min(wait_seconds, 30))
                continue
            raise GitHubAPIError(
                "GitHub API rate limit exceeded.", status_code=403
            )

        if response.status_code >= 500:
            last_error = f"Server error {response.status_code}"
            _backoff(attempt)
            continue

        # 2xx, 3xx, or a "final" 4xx (404, 401, etc.) — return as-is.
        return response

    raise GitHubAPIError(f"GitHub request failed after retries: {last_error}")


def _is_rate_limited(response: requests.Response) -> bool:
    remaining = response.headers.get("X-RateLimit-Remaining")
    return remaining is not None and remaining == "0"


def _seconds_until_rate_limit_reset(response: requests.Response) -> int:
    reset_epoch = response.headers.get("X-RateLimit-Reset")
    if not reset_epoch:
        return 5
    try:
        reset_time = int(reset_epoch)
        now = int(time.time())
        return max(reset_time - now, 1)
    except ValueError:
        return 5


def _backoff(attempt: int) -> None:
    """Simple exponential backoff: 1s, 2s, 4s..."""
    time.sleep(2 ** (attempt - 1))


def github_get_paginated(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    max_pages: int = 5,
    per_page: int = 100,
) -> List[Dict[str, Any]]:
    """
    Fetch all pages (up to max_pages) of a paginated GitHub REST endpoint
    and return the combined list of items.
    """
    params = dict(params or {})
    params["per_page"] = per_page

    all_items: List[Dict[str, Any]] = []
    page = 1

    while page <= max_pages:
        params["page"] = page
        response = github_get(url, headers=headers, params=params)

        if response.status_code != 200:
            break

        page_items = response.json()
        if not isinstance(page_items, list) or not page_items:
            break

        all_items.extend(page_items)

        if len(page_items) < per_page:
            # Last page reached.
            break

        page += 1

    return all_items


def parse_github_date(date_str: Optional[str]) -> Optional[datetime]:
    """
    Parse a GitHub ISO-8601 date string (e.g. '2024-05-01T12:34:56Z')
    into a timezone-aware datetime. Returns None if parsing fails.
    """
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return None


def aggregate_weekly_commits(commit_dates: List[datetime]) -> List[Dict[str, Any]]:
    """
    Aggregate a list of commit datetimes into weekly buckets.

    Returns a list of dicts sorted chronologically, e.g.:
        [{"week_start": "2024-04-29", "commit_count": 12}, ...]

    Weeks are bucketed by ISO year/week (Monday start).
    """
    if not commit_dates:
        return []

    buckets: Dict[str, int] = {}
    week_start_lookup: Dict[str, datetime] = {}

    for dt in commit_dates:
        if dt is None:
            continue
        iso_year, iso_week, _ = dt.isocalendar()
        key = f"{iso_year}-W{iso_week:02d}"
        buckets[key] = buckets.get(key, 0) + 1

        if key not in week_start_lookup:
            # Compute the Monday of this ISO week for a friendly label.
            monday = dt - timedelta(days=dt.weekday())
            week_start_lookup[key] = monday

    sorted_keys = sorted(buckets.keys())

    result = [
        {
            "week_start": week_start_lookup[key].strftime("%Y-%m-%d"),
            "commit_count": buckets[key],
        }
        for key in sorted_keys
    ]
    return result


def success_response(data: Dict[str, Any], status_code: int = 200):
    """Standard success envelope for API responses."""
    return {"success": True, "data": data}, status_code


def error_response(message: str, status_code: int = 400, details: Optional[Any] = None):
    """Standard error envelope for API responses."""
    payload = {"success": False, "error": message}
    if details is not None:
        payload["details"] = details
    return payload, status_code