from flask import Blueprint, request, jsonify, g
from datetime import datetime, timezone
from app.database import log_request, log_split_outputs_by_id
from app.middleware.auth import require_jwt_token
from app.workers.celery_worker import split_pdf_task
from app.constants import Status, JobType
from app.services.request_audit import store_audit_data
from app.utils.priority_helper import validate_priority, invoke_task_with_priority

split_pdf_bp = Blueprint("split_pdf", __name__)


@split_pdf_bp.route("/api/v1/split-pdf", methods=["POST"])
@require_jwt_token
def split_pdf_route():
    """
    Split a PDF into multiple files based on page numbers or labels.

    Request Body:
    {
        "client_job_id": "1234",
        "document_url": "https://sample-document-url.com/123",
        "webhook": "https://test-webhook-url.com/1234",  # optional
        "meta_data": {},  # optional
        "splits": [
            {
                "output_filename": "file-1",
                "pages": [1, 4, 5, 10],  # OR "labels": ["i", "ii", "iv"]
                "file_upload_url": "https://signed-aws-s3-storage-link.com/12345",  # optional
                "meta_data": {}  # optional
            }
        ]
    }

    Response:
    {
        "client_job_id": "1234",
        "task_id": "12345",
        "status": "Queued",
        "started_at": "2025-10-03T10:00:00Z",
        "status_code": 200,
        "meta_data": {},
        "splits": []
    }
    """
    data = request.json
    user_id = g.current_user["id"]

    # Validate required fields
    client_job_id = data.get("client_job_id")
    document_url = data.get("document_url")
    splits = data.get("splits", [])

    if not client_job_id:
        return jsonify(
            {
                "status": "Bad Request",
                "error": {"message": "client_job_id is required"},
            }
        ), 400

    if not document_url:
        return jsonify(
            {
                "status": "Bad Request",
                "error": {"message": "document_url is required"},
            }
        ), 400

    if not splits or not isinstance(splits, list) or len(splits) == 0:
        return jsonify(
            {
                "status": "Bad Request",
                "error": {
                    "message": "splits array is required and must not be empty"
                },
            }
        ), 400

    # Validate each split
    for idx, split in enumerate(splits):
        output_filename = split.get("output_filename")
        if not output_filename:
            return jsonify(
                {
                    "status": "Bad Request",
                    "error": {
                        "message": f"Split at index {idx} is missing 'output_filename'"
                    },
                }
            ), 400

        has_pages = "pages" in split
        has_labels = "labels" in split

        if not has_pages and not has_labels:
            return jsonify(
                {
                    "status": "Bad Request",
                    "error": {
                        "message": f"Split '{output_filename}' must have either 'pages' or 'labels'"
                    },
                }
            ), 400

        if has_pages and has_labels:
            return jsonify(
                {
                    "status": "Bad Request",
                    "error": {
                        "message": f"Split '{output_filename}' cannot have both 'pages' and 'labels'"
                    },
                }
            ), 400

        if has_pages:
            if not isinstance(split["pages"], list) or len(split["pages"]) == 0:
                return jsonify(
                    {
                        "status": "Bad Request",
                        "error": {
                            "message": f"Split '{output_filename}' has invalid 'pages' - must be a non-empty list"
                        },
                    }
                ), 400

        if has_labels:
            if (
                not isinstance(split["labels"], list)
                or len(split["labels"]) == 0
            ):
                return jsonify(
                    {
                        "status": "Bad Request",
                        "error": {
                            "message": f"Split '{output_filename}' has invalid 'labels' - must be a non-empty list"
                        },
                    }
                ), 400

    # Optional fields
    webhook_url = data.get("webhook")
    meta_data = data.get("meta_data", {})
    priority = data.get("priority")  # Optional: 0=High, 1=Medium, 2=Low

    # Validate priority if provided
    is_valid, error_msg = validate_priority(priority)
    if not is_valid:
        return jsonify({"error": error_msg}), 400

    # Create documents array with only processing metadata (no URLs)
    documents = [
        {
            "type": "url",
            "status": Status.QUEUED,
            "started_at": None,
            "ended_at": None,
            "processing_time": None,
            "error": None,
            "meta_data": {},
        }
    ]

    # Log request to database FIRST (before queueing task)
    job = log_request(
        client_job_id=client_job_id,
        job_type=JobType.SPLIT,
        documents=documents,
        output_filename=None,  # Split jobs don't have a single output file
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

    # Log split outputs to database
    log_split_outputs_by_id(str(job.id), splits)

    # Queue the split PDF task with job_id
    task = invoke_task_with_priority(
        split_pdf_task,
        priority=priority,
        job_id=str(job.id),  # Pass UUID job_id
        client_job_id=client_job_id,
        document_url=document_url,
        splits=splits,
        webhook_url=webhook_url,
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
            "splits": [],
        }
    ), 200


@split_pdf_bp.route("/api/v1/split-pdf/status", methods=["GET"])
@require_jwt_token
def get_split_pdf_status():
    """
    Get the status of a split PDF job.

    Query Parameters:
    - job_id: Job identifier (required)

    Response:
    {
        "job_id": "550e8400-e29b-41d4-a716-446655440000",
        "client_job_id": "123",
        "task_id": "12345",
        "status": "queued|running|completed|failed",
        "started_at": "2025-10-03T10:00:00Z",
        "ended_at": "2025-10-03T10:05:30Z",
        "processing_time": "5.6",
        "progress": 100,
        "meta_data": {},
        "splits": [
            {
                "output_filename": "file-1",
                "pages": [1, 4, 5, 10],
                "labels": null,
                "status": "completed",
                "status_remark": "Completed",
                "download_url": "https://...",
                "file_size": 123456,
                "processing_time": 2.3,
                "meta_data": {}
            }
        ]
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

    # Get job with splits
    from app.database import get_job_with_splits_by_id

    job_with_splits = get_job_with_splits_by_id(job_id)

    if not job_with_splits:
        return jsonify(
            {"status": "Not Found", "error": {"message": f"Job not found"}}
        ), 404

    # Calculate progress from splits
    splits = job_with_splits.get("splits", [])
    if splits:
        total = len(splits)
        completed = sum(
            1
            for s in splits
            if s["status"] in [Status.COMPLETED, Status.FAILED]
        )
        progress = int((completed / total) * 100) if total > 0 else 0
    else:
        progress = 0 if job_with_splits["status"] == Status.QUEUED else 100

    # Format splits for response
    formatted_splits = []
    for split in splits:
        status_remark = (
            split.get("error")
            if split["status"] == Status.FAILED
            else "Completed"
        )

        formatted_splits.append(
            {
                "output_filename": split["file_name"],
                "pages": split["pages"],
                "labels": split.get("labels"),
                "status": split["status"],
                "status_remark": status_remark,
                "download_url": split.get("download_url"),
                "file_size": split.get("file_size"),
                "processing_time": split.get("processing_time"),
                "meta_data": split.get("meta_data", {}),
            }
        )

    # Build response
    response = {
        "job_id": job_with_splits.get("job_id"),
        "client_job_id": job_with_splits["client_job_id"],
        "task_id": job_with_splits["task_id"],
        "status": job_with_splits["status"],
        "started_at": job_with_splits.get("created_at"),
        "ended_at": job_with_splits.get("ended_at"),
        "processing_time": f"{job_with_splits.get('processing_time'):.2f}"
        if job_with_splits.get("processing_time")
        else None,
        "progress": progress,
        "meta_data": job_with_splits.get("meta_data", {}),
        "documents": job_with_splits.get("documents", []),
        "splits": formatted_splits,
    }

    return jsonify(response), 200
