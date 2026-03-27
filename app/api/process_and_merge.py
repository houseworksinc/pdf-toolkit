"""
Process and Merge PDFs API

This module provides endpoints for generating PDFs from templates and merging them
with existing documents in a single atomic operation.
"""

from flask import Blueprint, request, jsonify, g, current_app
from datetime import datetime, timezone
from app.database import log_request
from app.middleware.auth import require_jwt_token
from app.workers.process_and_merge_worker import process_and_merge_task
from app.constants import Status, JobType
from app.services.request_audit import store_audit_data
from app.services.limit_validator import validate_download_count
from app.utils.priority_helper import validate_priority, invoke_task_with_priority
import copy

process_and_merge_bp = Blueprint("process_and_merge", __name__)


@process_and_merge_bp.route("/api/v1/process-and-merge-pdfs", methods=["POST"])
@require_jwt_token
def process_and_merge_route():
    """
    Process and merge multiple documents into a single PDF.

    This endpoint can:
    1. Generate PDFs from templates (static or dynamic mode)
    2. Download existing documents from URLs
    3. Merge all documents in the specified order

    Request Body:
    {
        "client_job_id": "PROC-001",
        "documents": [
            {
                "type": "url",
                "document_url": "https://...",
                "meta_data": {"label": "Cover Page"}
            },
            {
                "type": "JobType.GENERATE",
                "mode": "static",
                "template_url": "https://...",
                "data": {...},
                "meta_data": {"label": "Invoice"}
            }
        ],
        "output_filename": "final-package",  # optional
        "webhook": "https://...",  # optional
        "file_upload_url": "https://...",  # optional
        "meta_data": {}  # optional job-level metadata
    }

    Response (200 OK):
    {
        "client_job_id": "PROC-001",
        "task_id": "abc123...",
        "status": "queued",
        "started_at": "2025-10-09T10:00:00Z",
        "meta_data": {}
    }
    """
    data = request.json
    user_id = g.current_user["id"]

    # Validate required fields
    client_job_id = data.get("client_job_id")
    documents = data.get("documents", [])

    if not client_job_id:
        return jsonify(
            {
                "status": "Bad Request",
                "status_code": 400,
                "error": {"message": "client_job_id is required"},
            }
        ), 400

    if not documents or not isinstance(documents, list) or len(documents) == 0:
        return jsonify(
            {
                "status": "Bad Request",
                "status_code": 400,
                "error": {
                    "message": "documents array is required and must not be empty"
                },
            }
        ), 400

    # Validate and prepare each document
    prepared_documents = []

    for idx, doc in enumerate(documents):
        doc_type = doc.get("type")

        if not doc_type:
            return jsonify(
                {
                    "status": "Bad Request",
                    "status_code": 400,
                    "error": {
                        "message": f"Document at index {idx}: 'type' is required"
                    },
                }
            ), 400

        # Initialize document with common fields
        prepared_doc = {
            "type": doc_type,
            "status": Status.QUEUED,
            "started_at": None,
            "completed_at": None,
            "processing_time": None,
            "error": None,
            "meta_data": doc.get("meta_data", {}),
        }

        if doc_type == "url":
            # Validate URL document
            document_url = doc.get("document_url")
            if not document_url:
                return jsonify(
                    {
                        "status": "Bad Request",
                        "status_code": 400,
                        "error": {
                            "message": f"Document at index {idx}: 'document_url' is required for type='url'"
                        },
                    }
                ), 400

            if not isinstance(document_url, str) or not document_url.startswith(
                ("http://", "https://")
            ):
                return jsonify(
                    {
                        "status": "Bad Request",
                        "status_code": 400,
                        "error": {
                            "message": f"Document at index {idx}: 'document_url' must be a valid HTTP/HTTPS URL"
                        },
                    }
                ), 400

            prepared_doc["document_url"] = document_url

        elif doc_type == JobType.GENERATE:
            # Validate generate document
            template_url = doc.get("template_url")
            json_data = doc.get("data")
            mode = doc.get("mode", "static")
            use_empty_template = doc.get("use_empty_template", False)

            # Validate use_empty_template flag
            if not isinstance(use_empty_template, bool):
                return jsonify(
                    {
                        "status": "Bad Request",
                        "status_code": 400,
                        "error": {
                            "message": f"Document at index {idx}: 'use_empty_template' must be a boolean"
                        },
                    }
                ), 400

            # Validate mode
            if mode not in ["static", "dynamic"]:
                return jsonify(
                    {
                        "status": "Bad Request",
                        "status_code": 400,
                        "error": {
                            "message": f"Document at index {idx}: 'mode' must be 'static' or 'dynamic'"
                        },
                    }
                ), 400

            # Static mode: template_url is ALWAYS required
            if mode == "static":
                if not template_url:
                    return jsonify(
                        {
                            "status": "Bad Request",
                            "status_code": 400,
                            "error": {
                                "message": f"Document at index {idx}: 'template_url' is required for static mode"
                            },
                        }
                    ), 400
                if not isinstance(
                    template_url, str
                ) or not template_url.startswith(("http://", "https://")):
                    return jsonify(
                        {
                            "status": "Bad Request",
                            "status_code": 400,
                            "error": {
                                "message": f"Document at index {idx}: 'template_url' must be a valid HTTP/HTTPS URL"
                            },
                        }
                    ), 400

            # Dynamic mode: template_url is required unless use_empty_template is true
            elif mode == "dynamic":
                if not use_empty_template and not template_url:
                    return jsonify(
                        {
                            "status": "Bad Request",
                            "status_code": 400,
                            "error": {
                                "message": f"Document at index {idx}: 'template_url' is required for dynamic mode unless 'use_empty_template' is true"
                            },
                        }
                    ), 400
                if template_url and (
                    not isinstance(template_url, str)
                    or not template_url.startswith(("http://", "https://"))
                ):
                    return jsonify(
                        {
                            "status": "Bad Request",
                            "status_code": 400,
                            "error": {
                                "message": f"Document at index {idx}: 'template_url' must be a valid HTTP/HTTPS URL when provided"
                            },
                        }
                    ), 400

            if not json_data or not isinstance(json_data, dict):
                return jsonify(
                    {
                        "status": "Bad Request",
                        "status_code": 400,
                        "error": {
                            "message": f"Document at index {idx}: 'data' is required and must be an object for type='generate'"
                        },
                    }
                ), 400

            prepared_doc["template_url"] = template_url
            prepared_doc["data"] = json_data
            prepared_doc["mode"] = mode
            prepared_doc["use_empty_template"] = use_empty_template
            prepared_doc["output_filename"] = doc.get(
                "output_filename"
            )  # Optional for dynamic generation
            prepared_doc["template_hash"] = doc.get(
                "template_hash"
            )  # Optional for caching

        else:
            return jsonify(
                {
                    "status": "Bad Request",
                    "status_code": 400,
                    "error": {
                        "message": f"Document at index {idx}: 'type' must be 'url' or '{JobType.GENERATE}', got '{doc_type}'"
                    },
                }
            ), 400

        prepared_documents.append(prepared_doc)

    # Validate download count limit (only count documents with type="url")
    url_documents_count = sum(
        1 for doc in prepared_documents if doc.get("type") == "url"
    )
    if url_documents_count > 0:
        max_downloads = current_app.config["MAX_DOWNLOADS_PER_JOB"]
        is_valid, error_message = validate_download_count(
            url_documents_count, max_downloads
        )
        if not is_valid:
            return jsonify(
                {
                    "status": "Bad Request",
                    "status_code": 400,
                    "error": {"message": error_message},
                }
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

    # Create sanitized documents for database (remove large data fields)
    documents_for_db = copy.deepcopy(prepared_documents)
    for doc in documents_for_db:
        # Remove large fields to reduce database size
        doc.pop("document_url", None)
        doc.pop("template_url", None)
        doc.pop("data", None)

    # Log request to database FIRST (before queueing task)
    job = log_request(
        client_job_id=client_job_id,
        job_type=JobType.PROCESS_AND_MERGE,
        documents=documents_for_db,
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

    # Queue the process and merge task with job_id
    task = invoke_task_with_priority(
        process_and_merge_task,
        priority=priority,
        job_id=str(job.id),  # Pass UUID job_id
        client_job_id=client_job_id,
        documents=prepared_documents,
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


@process_and_merge_bp.route(
    "/api/v1/process-and-merge-pdfs/status", methods=["GET"]
)
@require_jwt_token
def get_process_and_merge_status():
    """
    Get the status of a process-and-merge job.

    Query Parameters:
    - job_id: Job identifier (required)

    Response:
    {
        "job_id": "550e8400-e29b-41d4-a716-446655440000",
        "client_job_id": "PROC-001",
        "task_id": "abc123...",
        "status": "queued|running|completed|failed",
        "started_at": "2025-10-09T10:00:00Z",
        "ended_at": "2025-10-09T10:05:30Z",
        "processing_time": "5.6",
        "progress": 75,
        "documents": [...],
        "meta_data": {},
        "download_url": "https://..."
    }
    """
    job_id = request.args.get("job_id")

    if not job_id:
        return jsonify(
            {
                "status": "Bad Request",
                "status_code": 400,
                "error": {"message": "job_id query parameter is required"},
            }
        ), 400

    # Get job info
    from app.database import get_job_info_by_id, get_document_stats_by_id

    job_info = get_job_info_by_id(job_id)

    if not job_info:
        return jsonify(
            {
                "status": "Not Found",
                "status_code": 404,
                "error": {"message": f"Job not found"},
            }
        ), 404

    # Check if job is process_and_merge type
    if job_info.get("job_type") != JobType.PROCESS_AND_MERGE:
        return jsonify(
            {
                "status": "Bad Request",
                "status_code": 400,
                "error": {
                    "message": f"Job is not a {JobType.PROCESS_AND_MERGE} job"
                },
            }
        ), 400

    # Get document statistics
    doc_stats = get_document_stats_by_id(job_id)

    # Calculate progress percentage
    total = doc_stats["total"]
    completed = doc_stats["completed"]
    failed = doc_stats["failed"]

    if total > 0:
        # Progress: 0-90% for document processing, 90-100% for merging
        doc_progress = int((completed + failed) / total * 90)

        # If all documents done and job is COMPLETED, we're at 100%
        if job_info["status"] == Status.COMPLETED:
            progress = 100
        elif job_info["status"] in [Status.FAILED, Status.PARTIAL_COMPLETED]:
            progress = doc_progress
        else:
            progress = doc_progress
    else:
        progress = 0

    # Filter documents - remove 'data' and 'index' fields
    filtered_documents = []
    for doc in job_info.get("documents", []):
        filtered_doc = {
            "type": doc.get("type"),
            "status": doc.get("status"),
            "processing_time": doc.get("processing_time"),
            "error": doc.get("error"),
            "meta_data": doc.get("meta_data", {}),
        }
        # Only include non-None values
        filtered_doc = {k: v for k, v in filtered_doc.items() if v is not None}
        filtered_documents.append(filtered_doc)

    # Build response
    response = {
        "job_id": job_info.get("job_id"),
        "client_job_id": job_info["client_job_id"],
        "task_id": job_info["task_id"],
        "status": job_info["status"],
        "started_at": job_info.get("started_at"),
        "ended_at": job_info.get("completed_at"),
        "processing_time": f"{job_info.get('processing_time'):.2f}"
        if job_info.get("processing_time")
        else None,
        "progress": progress,
        "documents": filtered_documents,
        "documents_completed": completed,
        "documents_failed": failed,
        "meta_data": job_info.get("meta_data", {}),
        "download_url": job_info.get("download_url"),
    }

    # Add error if failed
    if job_info["status"] in [Status.FAILED, Status.PARTIAL_COMPLETED]:
        response["error"] = job_info.get("error")

    return jsonify(response), 200
