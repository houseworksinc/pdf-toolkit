from flask import Blueprint, request, jsonify, g
from app.middleware.auth import require_jwt_token
from app.models import User, db
from datetime import datetime, timezone
import secrets

webhook_bp = Blueprint("webhook", __name__)


@webhook_bp.route("/api/v1/webhook/regenerate-secret", methods=["POST"])
@require_jwt_token
def regenerate_webhook_secret():
    """
    Regenerate webhook secret for authenticated user.
    User must be logged in with valid JWT token.

    Returns:
        JSON response with new webhook secret (shown only once)
    """
    user_id = g.current_user["id"]
    user = User.query.get(user_id)

    if not user:
        return jsonify({"error": "User not found"}), 404

    # Generate new secret
    new_secret = secrets.token_urlsafe(32)

    # Update user record
    old_secret_preview = (
        f"****...{user.webhook_secret[-4:]}" if user.webhook_secret else "None"
    )
    user.webhook_secret = new_secret
    user.webhook_secret_created_at = datetime.now(timezone.utc)
    db.session.commit()

    return jsonify(
        {
            "message": "Webhook secret regenerated successfully",
            "webhook_secret": new_secret,
            "created_at": user.webhook_secret_created_at.isoformat(),
            "previous_secret": old_secret_preview,
            "warning": "⚠️ Save this secret securely - it won't be shown again!",
        }
    ), 200


@webhook_bp.route("/api/v1/webhook/secret-info", methods=["GET"])
@require_jwt_token
def get_webhook_secret_info():
    """
    Get webhook secret info (masked) for authenticated user.
    Shows last 4 characters only.

    Returns:
        JSON response with masked secret and metadata
    """
    user_id = g.current_user["id"]
    user = User.query.get(user_id)

    if not user:
        return jsonify({"error": "User not found"}), 404

    if not user.webhook_secret:
        return jsonify(
            {
                "message": "No webhook secret configured",
                "has_secret": False,
                "help": "Use POST /api/v1/webhook/regenerate-secret to create one",
            }
        ), 200

    # Mask secret, show only last 4 chars
    masked_secret = f"****...{user.webhook_secret[-4:]}"

    return jsonify(
        {
            "has_secret": True,
            "webhook_secret": masked_secret,
            "created_at": user.webhook_secret_created_at.isoformat()
            if user.webhook_secret_created_at
            else None,
            "help": "Use POST /api/v1/webhook/regenerate-secret to generate a new secret",
        }
    ), 200


@webhook_bp.route("/api/v1/webhook/test", methods=["POST"])
@require_jwt_token
def test_webhook():
    """
    Test webhook endpoint by sending a test notification.

    Request Body:
        {
            "webhook_url": "https://your-server.com/webhook"
        }

    Returns:
        JSON response with test result
    """
    from app.services.webhook_notifier import send_webhook_notification

    user_id = g.current_user["id"]
    user = User.query.get(user_id)

    if not user:
        return jsonify({"error": "User not found"}), 404

    if not user.webhook_secret:
        return jsonify(
            {
                "error": "No webhook secret configured",
                "help": "Use POST /api/v1/webhook/regenerate-secret to create one",
            }
        ), 400

    data = request.json
    webhook_url = data.get("webhook_url")

    if not webhook_url:
        return jsonify({"error": "webhook_url is required"}), 400

    # Build test payload
    test_payload = {
        "client_job_id": "test-webhook-123",
        "task_id": "test-task-456",
        "status": "test",
        "message": "This is a test webhook notification",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user": user.username,
    }

    # Send webhook
    result = send_webhook_notification(
        webhook_url=webhook_url,
        payload=test_payload,
        webhook_secret=user.webhook_secret,
    )

    if result["success"]:
        return jsonify(
            {
                "message": "Test webhook sent successfully",
                "webhook_url": webhook_url,
                "result": result,
            }
        ), 200
    else:
        return jsonify(
            {
                "message": "Test webhook failed",
                "webhook_url": webhook_url,
                "error": result.get("error"),
                "result": result,
            }
        ), 500
