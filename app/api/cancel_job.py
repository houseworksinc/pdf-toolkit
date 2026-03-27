from flask import Blueprint, jsonify
from app.middleware.auth import require_jwt_token
from app.database import get_job_info_by_id, update_job_status_by_id
from app.constants import Status
from app.models.pdf_job import db, PdfJob
from app.models import User
from app.services.webhook_notifier import send_webhook_notification, build_webhook_payload
from sqlalchemy.orm.attributes import flag_modified
from celery.result import AsyncResult
import logging

cancel_job_bp = Blueprint("cancel_job", __name__)
logger = logging.getLogger(__name__)

FINAL_STATUSES = [Status.COMPLETED, Status.FAILED, Status.PARTIAL_COMPLETED, Status.CANCELLED]


@cancel_job_bp.route("/api/v1/jobs/<job_id>/cancel", methods=["POST"])
@require_jwt_token
def cancel_job_route(job_id):
    """
    Cancel an in-progress job.

    Path Parameters:
        job_id: The job UUID to cancel

    Response (200):
        {
            "job_id": "uuid",
            "client_job_id": "client-123",
            "status": "cancelled",
            "message": "Job cancelled successfully"
        }

    Error Responses:
        400: Job already in final state
        404: Job not found
    """
    # Look up job
    job_info = get_job_info_by_id(job_id)
    if not job_info:
        return jsonify({"error": "Job not found", "job_id": job_id}), 404

    current_status = job_info.get("status")

    # Validate job is in a cancellable state
    if current_status in FINAL_STATUSES:
        return jsonify({
            "error": f"Job is already in final state: {current_status}",
            "job_id": job_id,
            "client_job_id": job_info.get("client_job_id"),
            "status": current_status,
        }), 400

    # Revoke Celery task if task_id exists
    task_id = job_info.get("task_id")
    if task_id:
        try:
            result = AsyncResult(task_id)
            result.revoke(terminate=True, signal="SIGTERM")
            logger.info(f"Revoked Celery task {task_id} for job {job_id}")
        except Exception as e:
            logger.warning(f"Failed to revoke Celery task {task_id} for job {job_id}: {e}")

    # Update job status to CANCELLED
    update_job_status_by_id(
        job_id=job_id,
        status=Status.CANCELLED,
        error="Job cancelled by user",
    )

    # Update all non-completed document statuses to cancelled
    job = PdfJob.query.filter_by(id=job_id).first()
    if job and job.documents:
        modified = False
        for doc in job.documents:
            doc_status = doc.get("status")
            if doc_status not in [Status.COMPLETED, Status.FAILED]:
                doc["status"] = Status.CANCELLED
                modified = True
        if modified:
            flag_modified(job, "documents")
            db.session.commit()

    logger.info(f"Job {job_id} cancelled successfully")

    # Send webhook notification if configured
    if job_info.get("webhook_url"):
        webhook_url = job_info["webhook_url"]
        webhook_secret = None
        if job and job.user_id:
            user = User.query.get(job.user_id)
            if user and user.webhook_secret:
                webhook_secret = user.webhook_secret

        if webhook_secret:
            try:
                # Re-fetch job to get updated ended_at and documents
                updated_job_info = get_job_info_by_id(job_id)
                payload = build_webhook_payload(
                    client_job_id=job_info.get("client_job_id", ""),
                    task_id=job_info.get("task_id", ""),
                    status=Status.CANCELLED,
                    job_id=job_id,
                    ended_at=updated_job_info.get("ended_at") if updated_job_info else None,
                    documents=updated_job_info.get("documents", []) if updated_job_info else [],
                    error="Job cancelled by user",
                )
                send_webhook_notification(webhook_url, payload, webhook_secret)
            except Exception as e:
                logger.warning(f"Failed to send cancellation webhook for job {job_id}: {e}")

    return jsonify({
        "job_id": job_id,
        "client_job_id": job_info.get("client_job_id"),
        "status": Status.CANCELLED,
        "message": "Job cancelled successfully",
    }), 200
