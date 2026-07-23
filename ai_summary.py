"""
ai_summary.py

Communicates with the Groq API to turn already-computed metrics into
a human-readable summary. This module receives ONLY summarized metrics —
never raw GitHub data — and the LLM never calculates repository health.

If the AI service is unavailable or misconfigured, this module returns a
graceful, template-based fallback so the API never hard-fails on Groq
being down.
"""

import json
import os
import re
from typing import Any, Dict

import requests

from config import config

PROMPT_TEMPLATE_PATH = os.path.join(
    os.path.dirname(__file__), "prompts", "repo_summary.txt"
)


def _load_prompt_template() -> str:
    with open(PROMPT_TEMPLATE_PATH, "r", encoding="utf-8") as f:
        return f.read()


def _build_prompt(metrics: Dict[str, Any]) -> str:
    template = _load_prompt_template()
    return template.format(
        repo_full_name=metrics.get("repo_full_name", "unknown/unknown"),
        overall_health=metrics.get("overall_health", 0),
        activity_score=metrics.get("activity_score", 0),
        issue_score=metrics.get("issue_score", 0),
        contributor_score=metrics.get("contributor_score", 0),
        bus_factor=metrics.get("bus_factor", 0),
        documentation_score=metrics.get("documentation_score", 0),
        release_score=metrics.get("release_score", 0),
        commit_quality_score=metrics.get("commit_quality_score", 0),
        forecast_trend=metrics.get("forecast_trend", "unknown"),
        predicted_next_week_commits=metrics.get("predicted_next_week_commits", 0),
    )


def _fallback_summary(metrics: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deterministic, template-based summary used when Groq is unavailable
    (missing API key, network failure, timeout, or bad response). Ensures
    the API always returns a usable AI-insight section, even offline.
    """
    overall = metrics.get("overall_health", 0)
    bus_factor = metrics.get("bus_factor", 0)
    trend = metrics.get("forecast_trend", "unknown")

    if overall >= 75:
        overall_desc = "in strong overall health"
    elif overall >= 50:
        overall_desc = "in moderate health with room to improve"
    else:
        overall_desc = "showing signs of concern across several metrics"

    if bus_factor <= 1:
        risk_level = "High"
    elif bus_factor == 2:
        risk_level = "Medium"
    else:
        risk_level = "Low"

    return {
        "overall_summary": (
            f"This repository is {overall_desc}, with an overall health "
            f"score of {overall}/100. Commit activity is currently {trend}."
        ),
        "strengths": [
            f"Activity score of {metrics.get('activity_score', 0)}/100",
            f"Issue resolution score of {metrics.get('issue_score', 0)}/100",
        ],
        "weaknesses": [
            f"Bus factor of {bus_factor} indicates knowledge concentration risk"
            if bus_factor <= 2
            else "No major weaknesses detected in fallback mode",
        ],
        "risk_level": risk_level,
        "recommendations": [
            "Encourage more contributors to reduce bus factor risk.",
            "Keep documentation sections (installation, usage, license) up to date.",
            "Maintain a regular release cadence.",
        ],
        "source": "fallback",
    }


def _extract_json(text: str) -> Dict[str, Any]:
    """
    Best-effort extraction of a JSON object from the model's raw text
    response, stripping markdown code fences if present.
    """
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()

    return json.loads(cleaned)


def generate_ai_summary(metrics: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sends computed metrics to the Groq API and returns a structured summary:
        {
            "overall_summary": str,
            "strengths": [str, ...],
            "weaknesses": [str, ...],
            "risk_level": "Low" | "Medium" | "High",
            "recommendations": [str, ...],
            "source": "groq" | "fallback"
        }
    """
    api_key = config.GROQ_API_KEY or config.GROK_API_KEY
    if not api_key:
        return _fallback_summary(metrics)

    prompt = _build_prompt(metrics)

    payload = {
        "model": config.GROQ_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You explain pre-computed repository metrics. You never "
                    "calculate scores yourself. You always respond with "
                    "valid JSON only, matching the requested schema exactly."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.4,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(
            config.GROQ_API_URL,
            json=payload,
            headers=headers,
            timeout=config.GROQ_TIMEOUT_SECONDS,
        )
    except requests.RequestException:
        return _fallback_summary(metrics)

    if response.status_code != 200:
        return _fallback_summary(metrics)

    try:
        body = response.json()
        raw_text = body["choices"][0]["message"]["content"]
        parsed = _extract_json(raw_text)
    except (KeyError, IndexError, ValueError, json.JSONDecodeError):
        return _fallback_summary(metrics)

    # Validate the shape minimally; fall back if Groq didn't follow the schema.
    required_keys = {"overall_summary", "strengths", "weaknesses", "risk_level", "recommendations"}
    if not required_keys.issubset(parsed.keys()):
        return _fallback_summary(metrics)

    parsed["source"] = "groq"
    return parsed