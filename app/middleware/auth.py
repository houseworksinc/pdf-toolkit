from functools import wraps
from flask import request, jsonify, current_app, g
import jwt
import datetime
from app.database import get_user_by_id


def generate_jwt_token(user_id, username):
    """Generate a JWT token for the user"""
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "user_id": user_id,
        "username": username,
        "exp": now
        + datetime.timedelta(
            seconds=current_app.config["JWT_ACCESS_TOKEN_EXPIRES"]
        ),
        "iat": now,
    }

    return jwt.encode(
        payload, current_app.config["JWT_SECRET_KEY"], algorithm="HS256"
    )


def decode_jwt_token(token):
    """Decode and validate a JWT token"""
    try:
        payload = jwt.decode(
            token, current_app.config["JWT_SECRET_KEY"], algorithms=["HS256"]
        )
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def require_jwt_token(f):
    """Decorator to require JWT authentication"""

    @wraps(f)
    def decorated(*args, **kwargs):
        token = None

        # Check for token in Authorization header (Bearer token)
        auth_header = request.headers.get("Authorization")
        if auth_header:
            try:
                token = auth_header.split(" ")[1]  # Bearer <token>
            except IndexError:
                return jsonify(
                    {
                        "error": "Invalid authorization header format. Use 'Bearer <token>'"
                    }
                ), 401

        # Check for token in x-access-token header (alternative)
        if not token:
            token = request.headers.get("x-access-token")

        if not token:
            return jsonify({"error": "Token is missing"}), 401

        # Decode the token
        payload = decode_jwt_token(token)
        if not payload:
            return jsonify({"error": "Token is invalid or expired"}), 401

        # Verify user still exists and is active
        user = get_user_by_id(payload["user_id"])
        if not user:
            return jsonify({"error": "User not found or inactive"}), 401

        # Store user info in Flask's g object for use in the route
        g.current_user = user

        return f(*args, **kwargs)

    return decorated
