"""
services.py

Business logic for user registration, authentication, and JWT generation.
Interacts with the PostgreSQL database via SQLAlchemy ORM.
"""

import logging
from sqlalchemy.exc import IntegrityError
from auth.models import User, db
from auth.utils import (
    generate_jwt_token,
    normalize_email,
    normalize_github_username,
    validate_email,
    validate_github_username,
    validate_name,
    validate_password,
)

logger = logging.getLogger("repopulse.auth")


def register_user_service(data: dict) -> tuple[bool, dict | str, int]:
    """
    Validate user input and create a new account in PostgreSQL.
    Returns (success, response_payload, status_code).
    """
    raw_name = data.get("name") or data.get("fullName") or ""
    raw_email = data.get("email") or ""
    raw_password = data.get("password") or ""
    raw_github = data.get("github_username") or data.get("githubUsername") or ""

    # Validate inputs
    valid_name, err = validate_name(raw_name)
    if not valid_name:
        return False, err, 400

    valid_email, err = validate_email(raw_email)
    if not valid_email:
        return False, err, 400

    valid_github, err = validate_github_username(raw_github)
    if not valid_github:
        return False, err, 400

    valid_pass, err = validate_password(raw_password)
    if not valid_pass:
        return False, err, 400

    clean_email = normalize_email(raw_email)
    clean_github = normalize_github_username(raw_github)
    clean_name = raw_name.strip()

    # Check for duplicate email
    existing_email = User.query.filter_by(email=clean_email).first()
    if existing_email:
        return False, "An account with this email address already exists.", 409

    # Check for duplicate GitHub username
    existing_github = User.query.filter_by(github_username=clean_github).first()
    if existing_github:
        return False, "This GitHub username is already registered.", 409

    # Create new User
    try:
        user = User(
            name=clean_name,
            email=clean_email,
            github_username=clean_github,
            username=clean_github,
        )
        user.set_password(raw_password)

        db.session.add(user)
        db.session.commit()

        token = generate_jwt_token(user.id, user.email)
        logger.info("New user registered successfully: id=%s, email=%s", user.id, user.email)

        return True, {"user": user.to_dict(), "token": token}, 201
    except IntegrityError as exc:
        db.session.rollback()
        logger.warning("IntegrityError during user registration: %s", exc)
        return False, "Registration failed due to a duplicate constraint.", 409
    except Exception as exc:
        db.session.rollback()
        logger.exception("Database error during registration")
        return False, "Internal error creating user account. Please try again later.", 500


def authenticate_user_service(data: dict) -> tuple[bool, dict | str, int]:
    """
    Authenticate user credentials against PostgreSQL database.
    Returns (success, response_payload, status_code).
    """
    raw_email = data.get("email") or ""
    raw_password = data.get("password") or ""

    clean_email = normalize_email(raw_email)

    if not clean_email or not raw_password:
        return False, "Email and password are required.", 400

    user = User.query.filter_by(email=clean_email).first()

    # Generic error message to prevent user enumeration attacks
    if not user or not user.check_password(raw_password):
        return False, "Invalid email or password.", 401

    token = generate_jwt_token(user.id, user.email)
    logger.info("User authenticated successfully: id=%s, email=%s", user.id, user.email)

    return True, {"user": user.to_dict(), "token": token}, 200


def get_user_profile_service(user_id: int) -> tuple[bool, dict | str, int]:
    """Fetch user profile by user ID."""
    user = db.session.get(User, user_id) if hasattr(db.session, 'get') else User.query.get(user_id)
    if not user:
        return False, "User not found.", 404
    return True, {"user": user.to_dict()}, 200


def update_username_service(user_id: int, new_username: str) -> tuple[bool, dict | str, int]:
    """
    Update the authenticated user's application username in PostgreSQL DB.
    Validates format, checks uniqueness, and saves to DB.
    Only user.username is updated; user.github_username and user.name remain untouched.
    """
    raw_username = (new_username or "").strip()
    if not raw_username:
        return False, "Username is required.", 400

    clean_username = normalize_github_username(raw_username)
    valid, err = validate_github_username(clean_username)
    if not valid:
        return False, err, 400

    user = db.session.get(User, user_id) if hasattr(db.session, 'get') else User.query.get(user_id)
    if not user:
        return False, "User not found.", 404

    # Current username
    current_username = user.username or user.github_username
    if current_username == clean_username:
        return True, {"user": user.to_dict(), "message": "Username updated successfully."}, 200

    # Check for duplicate application username among other users
    existing_user = User.query.filter(User.username == clean_username, User.id != user_id).first()
    if existing_user:
        return False, "Username is already taken.", 409

    try:
        user.username = clean_username
        db.session.commit()
        logger.info("Updated username for user id=%s to '%s' (github_username remains '%s')", user_id, clean_username, user.github_username)
        return True, {"user": user.to_dict(), "message": "Username updated successfully."}, 200
    except IntegrityError:
        db.session.rollback()
        return False, "Username is already taken.", 409
    except Exception as exc:
        db.session.rollback()
        logger.exception("Failed to update username")
        return False, "Internal server error while updating username.", 500


