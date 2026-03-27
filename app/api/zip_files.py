from flask import Blueprint, request, jsonify, g, current_app
from datetime import datetime, timezone
from app.database import log_request, get_job_info_by_id
from app.middleware.auth import require_jwt_token
from app.workers.celery_worker import create_zip_task
from app.constants import Status, JobType
from app.services.request_audit import store_audit_data
from app.services.limit_validator import validate_download_count
from app.utils.priority_helper import validate_priority, invoke_task_with_priority

zip_files_bp = Blueprint("zip_files", __name__)


@zip_files_bp.route("/api/v1/create-zip", methods=["POST"])
@require_jwt_token
def create_zip_route():
    """
    Create a ZIP archive from multiple files of any type.

    Request Body:
    {
        "client_job_id": "1234",
        "document_urls": ["https://url1.com/file.pdf", "https://url2.com/image.png"],
        "output_filename": "my-archive",  # optional
        "webhook": "https://test-webhook-url.com/1234",  # optional
        "file_upload_url": "https://signed-aws-s3-storage-link.com/12345",  # optional
        "meta_data": {}  # optional
    }

    Response:
    {
        "client_job_id": "1234",
        "task_id": "12345",
        "status": "Queued",
        "started_at": "2025-10-07T10:00:00Z",
        "status_code": 200,
        "meta_data": {}
    }
    """
    data = request.json
    user_id = g.current_user["id"]

    # Validate required fields
    client_job_id = data.get("client_job_id")
    document_urls = data.get("document_urls", [])

    if not client_job_id:
        return jsonify(
            {
                "status": "Bad Request",
                "error": {"message": "client_job_id is required"},
            }
        ), 400

    if (
        not document_urls
        or not isinstance(document_urls, list)
        or len(document_urls) == 0
    ):
        return jsonify(
            {
                "status": "Bad Request",
                "error": {
                    "message": "document_urls array is required and must not be empty"
                },
            }
        ), 400

    # Validate document URLs
    for idx, url in enumerate(document_urls):
        if not isinstance(url, str) or not url.strip():
            return jsonify(
                {
                    "status": "Bad Request",
                    "error": {"message": f"Invalid URL at index {idx}"},
                }
            ), 400

        # Basic URL validation
        if not url.startswith(("http://", "https://")):
            return jsonify(
                {
                    "status": "Bad Request",
                    "error": {
                        "message": f"URL at index {idx} must start with http:// or https://"
                    },
                }
            ), 400

    # Validate download count limit
    max_downloads = current_app.config["MAX_DOWNLOADS_PER_JOB"]
    is_valid, error_message = validate_download_count(
        len(document_urls), max_downloads
    )
    if not is_valid:
        return jsonify(
            {"status": "Bad Request", "error": {"message": error_message}}
        ), 400

    # Optional fields
    output_filename = data.get("output_filename") or client_job_id
    webhook_url = data.get("webhook")
    file_upload_url = data.get("file_upload_url")
    meta_data = data.get("meta_data", {})
    priority = data.get("priority")  # Optional: 0=High, 1=Medium, 2=Low

    # Validate priority if provided
    is_valid, error_msg = validate_priority(priority)
    if not is_valid:
        return jsonify({"error": error_msg}), 400

    # Prepare documents array with only processing metadata (no URLs)
    documents = []
    for idx in range(len(document_urls)):
        documents.append(
            {
                "type": "url",
                "status": Status.QUEUED,
                "started_at": None,
                "ended_at": None,
                "processing_time": None,
                "error": None,
                "meta_data": {},
            }
        )

    # Log request to database FIRST (before queueing task)
    job = log_request(
        client_job_id=client_job_id,
        job_type=JobType.ZIP,
        documents=documents,
        output_filename=output_filename,
        webhook_url=webhook_url,
        meta_data=meta_data,
        request_audit_s3_key=None,  # Will update after storing to S3
        task_id=None,  # Will update after task is created
    )

    # Store full request data to S3 for audit/compliance
    audit_s3_key = store_audit_data(job_id=str(job.id), request_data=data)

    # Update job with audit S3 key if successful
    if audit_s3_key:
        job.request_audit_s3_key = audit_s3_key
        from app.models import db

        db.session.commit()

    # Queue the create ZIP task with job_id
    task = invoke_task_with_priority(
        create_zip_task,
        priority=priority,
        job_id=str(job.id),  # Pass UUID job_id
        client_job_id=client_job_id,
        document_urls=document_urls,
        output_filename=output_filename,
        webhook_url=webhook_url,
        file_upload_url=file_upload_url,
        meta_data=meta_data,
        user_id=user_id,
    )

    # Update task_id in database
    from app.database import update_job_task_id_by_id

    update_job_task_id_by_id(str(job.id), task.id)

    # Return response
    return jsonify(
        {
            "job_id": job.id,
            "client_job_id": client_job_id,
            "task_id": task.id,
            "status": Status.QUEUED,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "meta_data": meta_data,
        }
    ), 200


@zip_files_bp.route("/api/v1/create-zip/status", methods=["GET"])
@require_jwt_token
def get_zip_status():
    """
    Get the status of a ZIP creation job.

    Query Parameters:
    - job_id: Job identifier

    Response:
    {
        "job_id": "550e8400-e29b-41d4-a716-446655440000",
        "client_job_id": "123",
        "task_id": "12345",
        "status": "queued|running|completed|failed",
        "started_at": "2025-10-07T10:00:00Z",
        "ended_at": "2025-10-07T10:05:30Z",
        "processing_time": "5.6",
        "meta_data": {},
        "download_url": "https://..."
    }
    """
    job_id = request.args.get("job_id")

    if not job_id:
        return jsonify(
            {
                "status": "Bad Request",
                "error": {"message": "job_id query parameter is required"},
            }
        ), 400

    # Get job info
    job_info = get_job_info_by_id(job_id)

    if not job_info:
        return jsonify(
            {"status": "Not Found", "error": {"message": f"Job not found"}}
        ), 404

    # Check if job is zip type
    if job_info.get("job_type") != JobType.ZIP:
        return jsonify(
            {
                "status": "Bad Request",
                "error": {"message": f"Job is not a ZIP creation job"},
            }
        ), 400

    # Filter out internal fields from documents (file_path is server-internal)
    documents = job_info.get("documents", [])
    filtered_documents = []
    for doc in documents:
        # Create a copy without file_path
        filtered_doc = {k: v for k, v in doc.items() if k != "file_path"}
        filtered_documents.append(filtered_doc)

    # Build response
    response = {
        "job_id": job_info.get("job_id"),
        "client_job_id": job_info["client_job_id"],
        "task_id": job_info["task_id"],
        "status": job_info["status"],
        "started_at": job_info.get("created_at"),
        "ended_at": job_info.get("ended_at"),
        "processing_time": f"{job_info.get('processing_time'):.2f}"
        if job_info.get("processing_time")
        else None,
        "meta_data": job_info.get("meta_data", {}),
        "documents": filtered_documents,
        "download_url": job_info.get("download_url"),
    }

    # Add error if failed
    if job_info["status"] == Status.FAILED:
        response["error"] = job_info.get("error")

    return jsonify(response), 200
