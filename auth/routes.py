"""
routes.py

Flask API routes for authentication (Signup, Login, Logout, Profile verification).
"""

from flask import Blueprint, jsonify, request
from auth.services import authenticate_user_service, get_user_profile_service, register_user_service, update_username_service
from auth.utils import jwt_required, decode_jwt_token

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


@auth_bp.route("/signup", methods=["POST"])
def signup():
    """
    Register a new user account.
    Payload: { name, email, github_username, password }
    """
    payload = request.get_json(silent=True) or {}
    success, result, status_code = register_user_service(payload)

    if success:
        return jsonify({"success": True, "message": "Account created successfully.", **result}), status_code
    else:
        return jsonify({"success": False, "error": result}), status_code


@auth_bp.route("/login", methods=["POST"])
def login():
    """
    Authenticate an existing user.
    Payload: { email, password }
    """
    payload = request.get_json(silent=True) or {}
    success, result, status_code = authenticate_user_service(payload)

    if success:
        return jsonify({"success": True, "message": "Logged in successfully.", **result}), status_code
    else:
        return jsonify({"success": False, "error": result}), status_code


@auth_bp.route("/logout", methods=["POST"])
def logout():
    """Logout endpoint for user session cleanup."""
    return jsonify({"success": True, "message": "Logged out successfully."}), 200


@auth_bp.route("/me", methods=["GET"])
@jwt_required
def get_current_user():
    """Get authenticated user profile."""
    user_id = int(request.user_token_payload.get("sub"))
    success, result, status_code = get_user_profile_service(user_id)

    if success:
        return jsonify({"success": True, **result}), status_code
    else:
        return jsonify({"success": False, "error": result}), status_code


@auth_bp.route("/username", methods=["PUT", "POST"])
@jwt_required
def update_username():
    """
    Update authenticated user's username.
    Payload: { "username": "new_username" } or { "github_username": "new_username" }
    """
    user_id = int(request.user_token_payload.get("sub"))
    payload = request.get_json(silent=True) or {}
    new_username = payload.get("username") or payload.get("github_username") or payload.get("new_username")

    success, result, status_code = update_username_service(user_id, new_username)

    if success:
        return jsonify({"success": True, **result}), status_code
    else:
        return jsonify({"success": False, "error": result}), status_code

