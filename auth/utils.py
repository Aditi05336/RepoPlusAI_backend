"""
utils.py

Validation and JWT security helpers for RepoPulse AI authentication.
"""

from functools import wraps
import re
from datetime import datetime, timedelta, timezone
import jwt
from flask import request, jsonify
from config import config


def normalize_email(email: str) -> str:
    """Trim whitespace and convert email to lowercase."""
    return (email or "").strip().lower()


def normalize_github_username(username: str) -> str:
    """Trim whitespace and clean GitHub username."""
    return (username or "").strip()


def validate_name(name: str) -> tuple[bool, str]:
    """Validate user name."""
    trimmed = (name or "").strip()
    if not trimmed:
        return False, "Full name is required."
    if len(trimmed) < 2:
        return False, "Name must be at least 2 characters long."
    if len(trimmed) > 100:
        return False, "Name must not exceed 100 characters."
    return True, ""


def validate_email(email: str) -> tuple[bool, str]:
    """Validate email address format."""
    normalized = normalize_email(email)
    if not normalized:
        return False, "Email address is required."
    
    # Standard RFC 5322 pattern check
    pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
    if not re.match(pattern, normalized):
        return False, "Invalid email address format."
    return True, ""


def validate_password(password: str) -> tuple[bool, str]:
    """
    Validate password strength and complexity:
    - Minimum 8 characters
    - Must contain at least one uppercase letter, one lowercase letter, one digit, and one special character.
    """
    if not password:
        return False, "Password is required."
    if len(password) < 8:
        return False, "Password must be at least 8 characters long."
    if len(password) > 128:
        return False, "Password must not exceed 128 characters."
    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter."
    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter."
    if not re.search(r"[0-9]", password):
        return False, "Password must contain at least one digit."
    if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?]", password):
        return False, "Password must contain at least one special character (!@#$%^&*)."
    return True, ""


def validate_github_username(username: str) -> tuple[bool, str]:
    """
    Validate GitHub username format according to GitHub standards:
    - 1 to 39 characters
    - Alphanumeric characters or single hyphens
    - Cannot begin or end with a hyphen
    """
    cleaned = normalize_github_username(username)
    if not cleaned:
        return False, "GitHub username is required."
    
    pattern = r"^[a-zA-Z0-9](?:[a-zA-Z0-9]|-(?=[a-zA-Z0-9])){0,38}$"
    if not re.match(pattern, cleaned):
        return False, "Invalid GitHub username format."
    return True, ""


def generate_jwt_token(user_id: int, email: str) -> str:
    """Generate a signed JWT token containing user details and expiration."""
    now = datetime.now(timezone.utc)
    expiration = now + timedelta(hours=config.JWT_EXPIRATION_HOURS)
    payload = {
        "sub": str(user_id),
        "email": email,
        "iat": int(now.timestamp()),
        "exp": int(expiration.timestamp()),
    }
    return jwt.encode(payload, config.JWT_SECRET_KEY, algorithm="HS256")


def decode_jwt_token(token: str) -> tuple[bool, dict | str]:
    """Decode and verify a signed JWT token."""
    try:
        payload = jwt.decode(token, config.JWT_SECRET_KEY, algorithms=["HS256"])
        return True, payload
    except jwt.ExpiredSignatureError:
        return False, "Authentication token has expired. Please log in again."
    except jwt.InvalidTokenError:
        return False, "Invalid authentication token."


def jwt_required(f):
    """Decorator to enforce valid JWT token in Request Authorization Header."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"success": False, "error": "Missing or malformed Authorization header."}), 401
        
        token = auth_header.split(" ", 1)[1].strip()
        is_valid, result = decode_jwt_token(token)
        if not is_valid:
            return jsonify({"success": False, "error": result}), 401
        
        request.user_token_payload = result
        return f(*args, **kwargs)
    return decorated_function
