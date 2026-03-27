from flask import Blueprint, request, jsonify, g
from app.database import log_request
from app.middleware.auth import require_jwt_token
from app.workers.celery_worker import (
    generate_pdf_task,
    generate_pdf_dynamic_task,
)
from app.constants import Status, CeleryState, JobType
from app.services.request_audit import store_audit_data
from app.utils.priority_helper import validate_priority, invoke_task_with_priority

pdf_bp = Blueprint("pdf", __name__, url_prefix="/api/v1")


@pdf_bp.route("/generate-pdf", methods=["POST"])
@require_jwt_token
def generate_pdf_route():
    """Generate PDF from template (static mode)"""
    data = request.json
    user_id = g.current_user["id"]

    client_job_id = data.get("client_job_id")
    template_url = data.get("template_url")
    json_data = data.get("data")
    output_filename = data.get("output_filename")
    webhook_url = data.get("webhook")  # Optional webhook URL
    meta_data = data.get("meta_data", {})  # Optional metadata
    template_hash = data.get("template_hash")  # Optional template hash for caching
    priority = data.get("priority")  # Optional: 0=High, 1=Medium, 2=Low

    # Validate priority if provided
    is_valid, error_msg = validate_priority(priority)
    if not is_valid:
        return jsonify({"error": error_msg}), 400

    # Validate the request - static mode ALWAYS requires template_url
    if not all([client_job_id, template_url, json_data]):
        return jsonify(
            {
                "error": "Missing required parameters: client_job_id, template_url, and data are required for static mode"
            }
        ), 400

    # Validate template_url is a proper URL
    if not isinstance(template_url, str) or not template_url.startswith(
        ("http://", "https://")
    ):
        return jsonify(
            {"error": "template_url must be a valid HTTP/HTTPS URL"}
        ), 400

    # Log request to database FIRST (before queueing task)
    # Documents array only stores processing metadata (no large data payloads)
    job = log_request(
        client_job_id=client_job_id,
        job_type=JobType.GENERATE,
        documents=[
            {
                "type": JobType.GENERATE,
                "mode": "static",
                "status": Status.QUEUED,
                "started_at": None,
                "ended_at": None,
                "processing_time": None,
                "error": None,
                "meta_data": {},
            }
        ],
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

    # Queue the PDF generation task with job_id
    task = invoke_task_with_priority(
        generate_pdf_task,
        priority=priority,
        job_id=str(job.id),  # Pass UUID job_id
        client_job_id=client_job_id,
        template_url=template_url,
        json_data=json_data,
        output_filename=output_filename,
        webhook_url=webhook_url,
        meta_data=meta_data,
        user_id=user_id,
        template_hash=template_hash,
    )

    # Update task_id in database
    from app.database import update_job_task_id_by_id

    update_job_task_id_by_id(str(job.id), task.id)

    response_data = {
        "status": Status.QUEUED,
        "job_id": job.id,
        "client_job_id": client_job_id,
        "task_id": task.id,
    }

    # Add output_filename to response if provided
    if output_filename:
        response_data["output_filename"] = output_filename

    return jsonify(response_data), 202  # 202 Accepted


@pdf_bp.route("/generate-pdf/dynamic", methods=["POST"])
@require_jwt_token
def generate_pdf_dynamic_route():
    """Generate PDF with dynamic content"""
    data = request.json
    user_id = g.current_user["id"]

    client_job_id = data.get("client_job_id")
    template_url = data.get("template_url")
    json_data = data.get("data")
    output_filename = data.get("output_filename", "output")
    use_empty_template = data.get("use_empty_template", False)
    webhook_url = data.get("webhook")  # Optional webhook URL
    meta_data = data.get("meta_data", {})  # Optional metadata
    template_hash = data.get("template_hash")  # Optional template hash for caching
    priority = data.get("priority")  # Optional: 0=High, 1=Medium, 2=Low

    # Validate priority if provided
    is_valid, error_msg = validate_priority(priority)
    if not is_valid:
        return jsonify({"error": error_msg}), 400

    # Validate the request
    if not client_job_id or not json_data:
        return jsonify(
            {
                "error": "Missing required parameters: client_job_id and data are required"
            }
        ), 400

    # Validate use_empty_template flag
    if not isinstance(use_empty_template, bool):
        return jsonify({"error": "use_empty_template must be a boolean"}), 400

    # Dynamic mode: template_url is required unless use_empty_template is true
    if not use_empty_template and not template_url:
        return jsonify(
            {
                "error": "template_url is required for dynamic mode unless use_empty_template is true"
            }
        ), 400

    # If template_url is provided, validate it's a proper URL
    if template_url and (
        not isinstance(template_url, str)
        or not template_url.startswith(("http://", "https://"))
    ):
        return jsonify(
            {
                "error": "template_url must be a valid HTTP/HTTPS URL when provided"
            }
        ), 400

    # Log request to database FIRST (before queueing task)
    # Documents array only stores processing metadata (no large data payloads)
    job = log_request(
        client_job_id=client_job_id,
        job_type=JobType.GENERATE,
        documents=[
            {
                "type": JobType.GENERATE,
                "mode": "dynamic",
                "status": Status.QUEUED,
                "started_at": None,
                "ended_at": None,
                "processing_time": None,
                "error": None,
                "meta_data": {},
            }
        ],
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

    # Queue the PDF generation task with job_id
    task = invoke_task_with_priority(
        generate_pdf_dynamic_task,
        priority=priority,
        job_id=str(job.id),  # Pass UUID job_id
        client_job_id=client_job_id,
        template_url=template_url,
        json_data=json_data,
        output_filename=output_filename,
        use_empty_template=use_empty_template,
        webhook_url=webhook_url,
        meta_data=meta_data,
        user_id=user_id,
        template_hash=template_hash,
    )

    # Update task_id in database
    from app.database import update_job_task_id_by_id

    update_job_task_id_by_id(str(job.id), task.id)

    return jsonify(
        {
            "status": Status.QUEUED,
            "job_id": job.id,
            "client_job_id": client_job_id,
            "task_id": task.id,
            "output_filename": output_filename,
        }
    ), 202  # 202 Accepted


@pdf_bp.route("/generate-pdf/status", methods=["GET"])
@require_jwt_token
def check_status():
    """Check the status of a PDF generation task"""
    job_id = request.args.get("job_id")

    # Validate job_id parameter
    if not job_id:
        return jsonify({"error": "job_id query parameter is required"}), 400

    # Get job from database by job_id
    from app.database import get_job_info_by_id
    from celery.result import AsyncResult

    job_info = get_job_info_by_id(job_id)

    if not job_info:
        return jsonify({"error": "Job not found"}), 404

    task_id = job_info.get("task_id")

    if not task_id:
        return jsonify({"error": "Task ID not found for this job"}), 404

    # Use AsyncResult which works for all task types
    task = AsyncResult(task_id)

    # Filter documents - remove 'data' and 'index' fields, include timing
    filtered_documents = []
    for doc in job_info.get("documents", []):
        filtered_doc = {
            "type": doc.get("type"),
            "status": doc.get("status"),
            "started_at": doc.get("started_at"),
            "ended_at": doc.get("ended_at"),
            "processing_time": doc.get("processing_time"),
            "error": doc.get("error"),
            "meta_data": doc.get("meta_data", {}),
        }
        # Only include non-None values
        filtered_doc = {k: v for k, v in filtered_doc.items() if v is not None}
        filtered_documents.append(filtered_doc)

    response = {
        "job_id": job_info.get("job_id"),
        "client_job_id": job_info.get("client_job_id"),
        "task_id": task_id,
        "status": task.status,
        "documents": filtered_documents,  # Include filtered documents array from database
    }

    if task.state == CeleryState.PENDING:
        response["status"] = CeleryState.PENDING
    elif task.state == CeleryState.FAILURE:
        response["status"] = CeleryState.FAILURE
        # Handle case where task.info is an exception object
        if hasattr(task.info, "get"):
            response["error"] = str(task.info.get("error", "Unknown error"))
        else:
            # If task.info is an exception, use it directly
            response["error"] = str(task.info)
    elif task.state == CeleryState.SUCCESS:
        response["status"] = CeleryState.SUCCESS
        if task.info and isinstance(task.info, dict):
            # Flatten the structure - extract fields from task.info directly
            for key, value in task.info.items():
                if key not in [
                    "status",
                    "s3_key",
                ]:  # Avoid overwriting the status and exclude s3_key
                    response[key] = value
    else:
        # STARTED, RETRY, or custom state (like PROCESSING)
        response["status"] = task.state

    return jsonify(response)
