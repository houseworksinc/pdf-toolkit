from flask import Blueprint, request, jsonify, g
from app.database import get_all_jobs
from app.middleware.auth import require_jwt_token
from app.services.request_audit import get_audit_data
from datetime import datetime
import logging
import os

logs_bp = Blueprint("logs", __name__, url_prefix="/api/v1")
logger = logging.getLogger(__name__)


@logs_bp.route("/logs", methods=["GET"])
@require_jwt_token
def get_logs():
    """
    Get PDF generation job logs with optional filtering.

    Query Parameters:
    - limit: Number of logs to return (default: 100)
    - offset: Offset for pagination (default: 0)
    - status: Filter by job status (optional)
    - client_job_id: Filter by client job ID (optional)
    - job_type: Filter by job type (optional)
    - job_id: Filter by specific job ID (optional)
    - date_from: Filter jobs created after this date (ISO format, optional)
    - date_to: Filter jobs created before this date (ISO format, optional)
    - include_request_data: Include full request data from S3 (default: false)

    Response:
    {
        "total": 10,
        "offset": 0,
        "limit": 100,
        "logs": [
            {
                "id": "...",
                "client_job_id": "...",
                "status": "...",
                "request_data": {  # Only if include_request_data=true
                    "documents": [...],
                    "template_url": "...",
                    "data": {...},
                    ...
                },
                ...
            }
        ]
    }
    """
    # Parse query parameters
    limit = request.args.get("limit", 100, type=int)
    offset = request.args.get("offset", 0, type=int)
    status = request.args.get("status")
    client_job_id = request.args.get("client_job_id")
    job_type = request.args.get("job_type")
    job_id = request.args.get("job_id")
    date_from_str = request.args.get("date_from")
    date_to_str = request.args.get("date_to")
    include_request_data = (
        request.args.get("include_request_data", "false").lower() == "true"
    )

    # Parse date filters
    date_from = None
    date_to = None
    try:
        if date_from_str:
            date_from = datetime.fromisoformat(date_from_str.replace("Z", "+00:00"))
        if date_to_str:
            date_to = datetime.fromisoformat(date_to_str.replace("Z", "+00:00"))
    except ValueError as e:
        return jsonify({"error": f"Invalid date format: {str(e)}. Use ISO format (e.g., 2025-01-01T00:00:00Z)"}), 400

    # Check if the current user is the master user
    # Master user can see all logs, regular users can only see their own
    master_username = os.environ.get("MASTER_USERNAME")
    is_master = g.current_user["username"] == master_username

    # Get user_id filter - master sees all, others see only their own
    user_id = None if is_master else g.current_user.get("id")

    # Get logs from database
    logs = get_all_jobs(
        limit=limit,
        offset=offset,
        status=status,
        client_job_id=client_job_id,
        job_type=job_type,
        user_id=user_id,
        job_id=job_id,
        date_from=date_from,
        date_to=date_to,
    )

    # Optionally fetch full request data from S3
    if include_request_data:
        for log in logs:
            job_id = log.get("id")
            request_audit_s3_key = log.get("request_audit_s3_key")

            if job_id and request_audit_s3_key:
                try:
                    audit_data = get_audit_data(job_id)
                    if audit_data:
                        log["request_data"] = audit_data
                    else:
                        log["request_data"] = None
                        log["request_data_error"] = (
                            "Failed to retrieve audit data from S3"
                        )
                except Exception as e:
                    logger.error(
                        f"Error fetching audit data for job {job_id}: {str(e)}"
                    )
                    log["request_data"] = None
                    log["request_data_error"] = str(e)
            else:
                log["request_data"] = None

    return jsonify(
        {"total": len(logs), "offset": offset, "limit": limit, "logs": logs}
    )
