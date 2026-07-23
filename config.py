"""
config.py

Centralizes all configuration for the RepoPulse AI backend.
Loads environment variables and exposes them as simple constants/attributes.

This file contains NO business logic. It only reads and organizes configuration.
"""

import os
from dotenv import load_dotenv

# Load variables from a .env file (if present) into the process environment.
load_dotenv()


def _get_bool(env_var: str, default: bool = False) -> bool:
    """Parse an environment variable as a boolean."""
    value = os.getenv(env_var)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _get_int(env_var: str, default: int) -> int:
    """Parse an environment variable as an integer, falling back to a default."""
    value = os.getenv(env_var)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


class Config:
    """Application configuration, dynamically populated from environment variables."""

    @property
    def GITHUB_TOKEN(self) -> str:
        load_dotenv()
        return os.getenv("GITHUB_TOKEN", "")

    @property
    def GITHUB_API_BASE_URL(self) -> str:
        return os.getenv("GITHUB_API_BASE_URL", "https://api.github.com")

    @property
    def GROQ_API_KEY(self) -> str:
        load_dotenv()
        return os.getenv("GROQ_API_KEY", "") or os.getenv("GROK_API_KEY", "")

    @property
    def GROQ_API_URL(self) -> str:
        return os.getenv("GROQ_API_URL", "https://api.groq.com/openai/v1/chat/completions")

    @property
    def GROQ_MODEL(self) -> str:
        return os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")

    @property
    def GROQ_TIMEOUT_SECONDS(self) -> int:
        return _get_int("GROQ_TIMEOUT_SECONDS", 20)

    # Backward compatibility aliases
    @property
    def GROK_API_KEY(self) -> str:
        return self.GROQ_API_KEY

    @property
    def GROK_API_URL(self) -> str:
        return self.GROQ_API_URL

    @property
    def GROK_MODEL(self) -> str:
        return self.GROQ_MODEL

    @property
    def GROK_TIMEOUT_SECONDS(self) -> int:
        return self.GROQ_TIMEOUT_SECONDS

    @property
    def CACHE_TTL_SECONDS(self) -> int:
        return _get_int("CACHE_TTL_SECONDS", 900)  # 15 minutes default

    @property
    def CORS_ORIGIN(self):
        val = os.getenv("CORS_ORIGIN", "*")
        if not val or val.strip() == "*":
            return "*"
        if "," in val:
            return [v.strip() for v in val.split(",") if v.strip()]
        return val.strip()

    @property
    def DATABASE_URL(self) -> str:
        load_dotenv()
        return os.getenv("DATABASE_URL", "sqlite:///repopulse.db")

    @property
    def JWT_SECRET_KEY(self) -> str:
        load_dotenv()
        return os.getenv("JWT_SECRET_KEY", "dev-secret-key-change-in-production")

    @property
    def JWT_EXPIRATION_HOURS(self) -> int:
        return _get_int("JWT_EXPIRATION_HOURS", 24)

    @property
    def FLASK_ENV(self) -> str:
        return os.getenv("FLASK_ENV", "development")

    @property
    def DEBUG(self) -> bool:
        return _get_bool("FLASK_DEBUG", self.FLASK_ENV == "development")

    @property
    def PORT(self) -> int:
        return _get_int("PORT", 5000)

    @property
    def REQUEST_TIMEOUT_SECONDS(self) -> int:
        return _get_int("REQUEST_TIMEOUT_SECONDS", 15)

    @property
    def MAX_RETRIES(self) -> int:
        return _get_int("MAX_RETRIES", 3)

    @property
    def COMMIT_HISTORY_WEEKS(self) -> int:
        return _get_int("COMMIT_HISTORY_WEEKS", 12)

    def validate(self):
        """
        Perform light validation on startup and return a list of warnings.
        Does not raise — the app should still run (e.g. with degraded AI
        features) even if optional keys are missing.
        """
        warnings = []
        if not self.GITHUB_TOKEN:
            warnings.append(
                "GITHUB_TOKEN is not set — GitHub API rate limits will be very low (60/hr)."
            )
        if not self.GROQ_API_KEY:
            warnings.append(
                "GROQ_API_KEY is not set — AI summaries will use the fallback response."
            )
        return warnings


config = Config()