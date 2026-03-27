import os
from flask import Blueprint, request, jsonify, g
from app.database import create_user, verify_user, update_user_metadata, update_user_password
from app.middleware.auth import require_jwt_token, generate_jwt_token

auth_bp = Blueprint("auth", __name__, url_prefix="/api/v1/auth")


@auth_bp.route("/register", methods=["POST"])
@require_jwt_token
def register():
    """Register a new user (Master user only)"""
    # Check if the requesting user is the master user
    master_username = os.environ.get("MASTER_USERNAME")
    if not master_username:
        return jsonify({"error": "Master username not configured"}), 500

    if g.current_user["username"] != master_username:
        return jsonify(
            {"error": "Only master user can register new users"}
        ), 403

    data = request.json

    if not data or not data.get("username") or not data.get("password"):
        return jsonify({"error": "Username and password are required"}), 400

    username = data["username"].strip()
    password = data["password"]
    meta_data = data.get("meta_data")  # Optional metadata

    # Basic validation
    if len(username) < 3:
        return jsonify(
            {"error": "Username must be at least 3 characters long"}
        ), 400

    if len(password) < 8:
        return jsonify(
            {"error": "Password must be at least 8 characters long"}
        ), 400

    # Create user with optional metadata
    user_info = create_user(username, password, meta_data)
    if user_info:
        return jsonify(
            {
                "message": "User registered successfully",
                "username": username,
                "user_id": user_info["id"],
                "webhook_secret": user_info["webhook_secret"],
                "warning": "⚠️ Save the webhook_secret securely - it won't be shown again!",
            }
        ), 201
    else:
        return jsonify({"error": "Username already exists"}), 409


@auth_bp.route("/login", methods=["POST"])
def login():
    """Login user and return JWT token"""
    data = request.json

    if not data or not data.get("username") or not data.get("password"):
        return jsonify({"error": "Username and password are required"}), 400

    username = data["username"].strip()
    password = data["password"]

    # Verify user credentials
    user = verify_user(username, password)
    if user:
        # Generate JWT token
        token = generate_jwt_token(user["id"], user["username"])

        return jsonify(
            {
                "message": "Login successful",
                "token": token,
                "user": {"id": user["id"], "username": user["username"]},
            }
        ), 200
    else:
        return jsonify({"error": "Invalid username or password"}), 401


@auth_bp.route("/authenticate", methods=["GET"])
@require_jwt_token
def authenticate():
    """Verify JWT token and return user info"""
    return jsonify(
        {
            "message": "Token is valid",
            "user": {
                "id": g.current_user["id"],
                "username": g.current_user["username"],
            },
        }
    ), 200


@auth_bp.route("/update-user-metadata", methods=["PUT"])
@require_jwt_token
def update_user_metadata_route():
    """Update user metadata"""
    data = request.json

    if not data or "meta_data" not in data:
        return jsonify({"error": "meta_data field is required"}), 400

    user_id = g.current_user["id"]
    meta_data = data["meta_data"]

    if update_user_metadata(user_id, meta_data):
        return jsonify(
            {"message": "Metadata updated successfully", "meta_data": meta_data}
        ), 200
    else:
        return jsonify({"error": "Failed to update metadata"}), 500


@auth_bp.route("/reset-password", methods=["POST"])
@require_jwt_token
def reset_password():
    """Reset a user's password (Master user only)"""
    # Check if the requesting user is the master user
    master_username = os.environ.get("MASTER_USERNAME")
    if not master_username:
        return jsonify({"error": "Master username not configured"}), 500

    if g.current_user["username"] != master_username:
        return jsonify(
            {"error": "Only master user can reset passwords"}
        ), 403

    data = request.json

    if not data or not data.get("username") or not data.get("new_password"):
        return jsonify({"error": "Username and new_password are required"}), 400

    username = data["username"].strip()
    new_password = data["new_password"]

    # Validate password length
    if len(new_password) < 8:
        return jsonify(
            {"error": "Password must be at least 8 characters long"}
        ), 400

    # Update password
    if update_user_password(username, new_password):
        return jsonify(
            {"message": f"Password reset successfully for user: {username}"}
        ), 200
    else:
        return jsonify({"error": "User not found or inactive"}), 404
