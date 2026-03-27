"""
Process and ZIP Worker

This module contains the Celery task for processing and zipping files.
It handles both PDF generation from templates and downloading existing documents,
then creates a ZIP archive with all processed files.
"""

import os
import tempfile
import time
from datetime import datetime, timezone

from app import app
from app.workers.celery_worker import celery, s3_client, s3_bucket
from app.models import User
from app.constants import Status
from app.database import (
    update_job_status_by_id,
    update_document_status_by_id,
    get_document_stats_by_id,
    get_job_info_by_id,
)
from app.services.pdf_orchestrator import (
    download_template,
    generate_single_pdf,
    download_document_from_url,
    convert_image_to_pdf_page,
    resize_pdf_to_page_size,
    SUPPORTED_FORMATS,
)
from app.services.limit_validator import DownloadLimitExceeded
from app.services.zip_creator import create_zip_from_local_files
from app.services.webhook_notifier import send_webhook_notification
from app.services.upload_handler import generate_s3_presigned_url
import requests


def build_process_zip_webhook_payload(
    client_job_id,
    task_id,
    status,
    started_at,
    job_id=None,
    ended_at=None,
    processing_time=None,
    progress=None,
    documents=None,
    meta_data=None,
    download_url=None,
    error=None,
    doc_stats=None,
):
    """Build webhook payload for process-and-zip jobs."""
    payload = {
        "client_job_id": client_job_id,
        "task_id": task_id,
        "status": status,
        "started_at": started_at,
    }

    if job_id:
        payload["job_id"] = job_id
    if ended_at:
        payload["ended_at"] = ended_at
    if processing_time is not None:
        payload["processing_time"] = f"{processing_time:.2f}"
    if progress is not None:
        payload["progress"] = progress
    if documents:
        payload["documents"] = documents
    if meta_data:
        payload["meta_data"] = meta_data
    if download_url:
        payload["download_url"] = download_url
    if error:
        payload["error"] = error
    if doc_stats:
        payload["documents_completed"] = doc_stats["completed"]
        payload["documents_failed"] = doc_stats["failed"]

    return payload


@celery.task(name="process_and_zip_task", bind=True)
def process_and_zip_task(
    self,
    job_id,
    client_job_id,
    documents,
    output_filename,
    webhook_url=None,
    file_upload_url=None,
    meta_data=None,
    user_id=None,
):
    """
    Celery task to process and zip multiple documents.

    This task:
    1. Downloads templates and generates PDFs (for type='generate')
    2. Downloads existing documents (for type='url')
    3. Creates a ZIP archive with all documents
    4. Uploads the final ZIP file
    5. Sends webhook notifications at each step

    Args:
        job_id: Job UUID (primary key)
        client_job_id: Unique job identifier
        documents: List of document configurations with status tracking
        output_filename: Name for the final ZIP file
        webhook_url: Optional webhook URL for notifications
        file_upload_url: Optional custom URL to upload the result
        meta_data: Optional metadata for the job
        user_id: User ID for webhook secret lookup
    """
    start_time = time.time()
    webhook_secret = None
    job_info = None

    try:
        # Get webhook secret from user if user_id provided
        if user_id and webhook_url:
            with app.app_context():
                user = User.query.get(user_id)
                if user and user.webhook_secret:
                    webhook_secret = user.webhook_secret

        # Update task status to PROCESSING
        self.update_state(
            state="PROCESSING",
            meta={"client_job_id": client_job_id, "progress": 0},
        )

        with app.app_context():
            update_job_status_by_id(
                job_id, Status.PROCESSING, started_at=datetime.now(timezone.utc)
            )
            job_info = get_job_info_by_id(job_id)

        # Send initial webhook notification (job started)
        if webhook_url and webhook_secret:
            with app.app_context():
                doc_stats = get_document_stats_by_id(job_id)
            payload = build_process_zip_webhook_payload(
                client_job_id=client_job_id,
                task_id=self.request.id,
                status=Status.PROCESSING,
                started_at=job_info["started_at"]
                if job_info
                else datetime.now(timezone.utc).isoformat(),
                job_id=job_id,
                progress=0,
                documents=documents,
                meta_data=meta_data,
                doc_stats=doc_stats,
            )
            send_webhook_notification(webhook_url, payload, webhook_secret)

        # Create temporary directory for all operations
        with tempfile.TemporaryDirectory() as tmpdir:
            generated_files = []  # Track all generated/downloaded files for zipping
            original_filenames = []  # Track original filenames for ZIP naming
            total_documents = len(documents)

            # Initialize download tracking for size limits
            total_downloaded_bytes = 0
            max_download_bytes = (
                app.config["MAX_DOWNLOAD_SIZE_MB"] * 1024 * 1024
            )
            download_limit_exceeded = False
            download_limit_error_msg = None

            # Process each document
            for idx, doc in enumerate(documents):
                doc_type = doc["type"]
                doc_start_time = time.time()

                # Update document status to PROCESSING
                with app.app_context():
                    update_document_status_by_id(
                        job_id=job_id,
                        document_index=idx,
                        status=Status.PROCESSING,
                        started_at=datetime.now(timezone.utc),
                    )

                try:
                    if doc_type == "url":
                        # Download existing document with size validation
                        document_url = doc["document_url"]
                        download_result = download_document_from_url(
                            document_url,
                            tmpdir,
                            total_downloaded_bytes=total_downloaded_bytes,
                            max_download_bytes=max_download_bytes,
                        )

                        if not download_result["success"]:
                            raise Exception(download_result["error"])

                        file_path = download_result["file_path"]
                        file_size = download_result.get("file_size", 0)

                        # Apply page sizing to images and PDFs
                        from pathlib import Path as _Path
                        file_ext = _Path(file_path).suffix.lower()
                        if file_ext in SUPPORTED_FORMATS.get("image", []):
                            file_path = convert_image_to_pdf_page(
                                file_path, page_size=page_size
                            )
                            file_size = os.path.getsize(file_path)
                        elif file_ext in SUPPORTED_FORMATS.get("pdf", []):
                            resize_pdf_to_page_size(file_path, page_size)
                            file_size = os.path.getsize(file_path)

                        generated_files.append(file_path)
                        doc_output_filename = doc.get("output_filename")
                        if doc_output_filename:
                            _, downloaded_ext = os.path.splitext(file_path)
                            if not os.path.splitext(doc_output_filename)[1]:
                                doc_output_filename = f"{doc_output_filename}{downloaded_ext}"
                            original_filenames.append(doc_output_filename)
                        else:
                            original_filenames.append(download_result.get("original_filename"))

                        # Update cumulative bytes counter
                        total_downloaded_bytes += file_size

                        # Update document status to SUCCESS
                        doc_processing_time = time.time() - doc_start_time
                        with app.app_context():
                            update_document_status_by_id(
                                job_id=job_id,
                                document_index=idx,
                                status=Status.COMPLETED,
                                ended_at=datetime.now(timezone.utc),
                                processing_time=doc_processing_time,
                                file_path=file_path,
                                file_size=download_result.get("file_size"),
                            )

                    elif doc_type == "generate":
                        # Generate PDF from template
                        template_url = doc.get("template_url")
                        json_data = doc["data"]
                        mode = doc.get("mode", "static")
                        use_empty_template = doc.get(
                            "use_empty_template", False
                        )
                        doc_output_filename = doc.get("output_filename")
                        template_hash = doc.get("template_hash")

                        # Download template or create empty one (with caching if template_hash provided)
                        template_path = download_template(
                            template_url=template_url,
                            output_dir=tmpdir,
                            use_empty_template=use_empty_template,
                            template_hash=template_hash,
                            enable_cache=True,
                        )

                        # Generate PDF
                        gen_result = generate_single_pdf(
                            template_path=template_path,
                            data=json_data,
                            mode=mode,
                            output_dir=tmpdir,
                            output_filename=doc_output_filename,
                        )

                        if not gen_result["success"]:
                            raise Exception(gen_result["error"])

                        pdf_path = gen_result["pdf_path"]
                        generated_files.append(pdf_path)
                        # For generated PDFs, use the output filename if provided
                        if doc_output_filename:
                            pdf_name = f"{doc_output_filename}.pdf" if not doc_output_filename.endswith(".pdf") else doc_output_filename
                            original_filenames.append(pdf_name)
                        else:
                            original_filenames.append(None)

                        # Get file size
                        file_size = os.path.getsize(pdf_path)

                        # Update document status to SUCCESS
                        doc_processing_time = time.time() - doc_start_time
                        with app.app_context():
                            update_document_status_by_id(
                                job_id=job_id,
                                document_index=idx,
                                status=Status.COMPLETED,
                                ended_at=datetime.now(timezone.utc),
                                processing_time=doc_processing_time,
                                file_path=pdf_path,
                                file_size=file_size,
                            )

                except DownloadLimitExceeded as e:
                    # Download limit exceeded - abort entire job immediately
                    error_msg = str(e)
                    doc_processing_time = time.time() - doc_start_time

                    with app.app_context():
                        update_document_status_by_id(
                            job_id=job_id,
                            document_index=idx,
                            status=Status.FAILED,
                            ended_at=datetime.now(timezone.utc),
                            processing_time=doc_processing_time,
                            error=error_msg,
                        )

                    # Set flag and break loop
                    download_limit_exceeded = True
                    download_limit_error_msg = error_msg
                    break

                except Exception as e:
                    # Document processing failed
                    error_msg = str(e)
                    doc_processing_time = time.time() - doc_start_time

                    with app.app_context():
                        update_document_status_by_id(
                            job_id=job_id,
                            document_index=idx,
                            status=Status.FAILED,
                            ended_at=datetime.now(timezone.utc),
                            processing_time=doc_processing_time,
                            error=error_msg,
                        )

                # Calculate progress (0-90% for document processing)
                progress = int(((idx + 1) / total_documents) * 90)
                self.update_state(
                    state="PROCESSING",
                    meta={"client_job_id": client_job_id, "progress": progress},
                )

                # Send webhook notification with progress
                if webhook_url and webhook_secret:
                    with app.app_context():
                        # Get updated documents and stats
                        updated_job_info = get_job_info_by_id(job_id)
                        doc_stats = get_document_stats_by_id(job_id)

                        # Map document status for webhook - exclude 'index' and 'data' fields
                        webhook_documents = []
                        for doc in updated_job_info.get("documents", []):
                            webhook_doc = {
                                "type": doc["type"],
                                "status": doc.get("status"),
                                "processing_time": doc.get("processing_time"),
                                "error": doc.get("error"),
                                "meta_data": doc.get("meta_data", {}),
                            }
                            # Only include non-None values
                            webhook_doc = {
                                k: v
                                for k, v in webhook_doc.items()
                                if v is not None
                            }
                            webhook_documents.append(webhook_doc)

                        payload = build_process_zip_webhook_payload(
                            client_job_id=client_job_id,
                            task_id=self.request.id,
                            status=Status.PROCESSING,
                            started_at=updated_job_info["started_at"],
                            job_id=job_id,
                            progress=progress,
                            documents=webhook_documents,
                            meta_data=meta_data,
                            doc_stats=doc_stats,
                        )
                        send_webhook_notification(
                            webhook_url, payload, webhook_secret
                        )

            # Check if download limit was exceeded
            if download_limit_exceeded:
                raise Exception(download_limit_error_msg)

            # Check if we have any files to zip
            with app.app_context():
                doc_stats = get_document_stats_by_id(job_id)

            if doc_stats["completed"] == 0:
                # All documents failed
                raise Exception("All documents failed to process")

            if len(generated_files) == 0:
                raise Exception("No files available for zipping")

            # Update progress to zipping phase (90%)
            self.update_state(
                state="PROCESSING",
                meta={"client_job_id": client_job_id, "progress": 90},
            )

            # Create ZIP archive with all documents
            zip_result = create_zip_from_local_files(
                file_paths=generated_files,
                output_filename=output_filename,
                output_dir=tmpdir,
                original_filenames=original_filenames,
            )

            if not zip_result["success"]:
                raise Exception(zip_result["error"])

            zip_path = zip_result["zip_path"]
            file_size = zip_result["file_size"]

            # Upload the ZIP file
            if file_upload_url:
                # Upload to custom URL (PUT request)
                try:
                    with open(zip_path, "rb") as f:
                        response = requests.put(
                            file_upload_url, data=f, timeout=60
                        )
                        response.raise_for_status()

                    download_url = file_upload_url.split("?")[
                        0
                    ]  # Remove query params
                    s3_key = None
                except Exception as e:
                    raise Exception(f"Failed to upload to custom URL: {str(e)}")
            else:
                # Upload to S3
                if output_filename:
                    s3_key = f"zips/{output_filename}.zip"
                else:
                    s3_key = f"zips/{job_id}.zip"
                try:
                    s3_client.upload_file(zip_path, s3_bucket, s3_key)

                    # Generate presigned URL with application/zip content type
                    download_url = generate_s3_presigned_url(
                        s3_key, bucket=s3_bucket, content_type="application/zip"
                    )
                except Exception as e:
                    raise Exception(f"Failed to upload to S3: {str(e)}")

            # Calculate total processing time
            total_time = time.time() - start_time

            # Determine final status based on document stats
            if doc_stats["failed"] > 0 and doc_stats["completed"] > 0:
                final_status = Status.PARTIAL_COMPLETED
            elif doc_stats["failed"] > 0:
                final_status = Status.FAILED
            else:
                final_status = Status.COMPLETED

            # Update database with final status
            with app.app_context():
                update_job_status_by_id(
                    job_id=job_id,
                    status=final_status,
                    s3_key=s3_key,
                    download_url=download_url,
                    processing_time=total_time,
                    file_size=file_size,
                    ended_at=datetime.now(timezone.utc),
                )

                # Get final job info for webhook
                final_job_info = get_job_info_by_id(job_id)

            # Send final webhook notification (job completed)
            if webhook_url and webhook_secret:
                with app.app_context():
                    doc_stats = get_document_stats_by_id(job_id)

                    # Map document status for webhook - exclude 'index' and 'data' fields
                    webhook_documents = []
                    for doc in final_job_info.get("documents", []):
                        webhook_doc = {
                            "type": doc["type"],
                            "status": doc.get("status"),
                            "processing_time": doc.get("processing_time"),
                            "error": doc.get("error"),
                            "meta_data": doc.get("meta_data", {}),
                        }
                        # Only include non-None values
                        webhook_doc = {
                            k: v
                            for k, v in webhook_doc.items()
                            if v is not None
                        }
                        webhook_documents.append(webhook_doc)

                    payload = build_process_zip_webhook_payload(
                        client_job_id=client_job_id,
                        task_id=self.request.id,
                        status=final_status,
                        started_at=final_job_info["started_at"],
                        job_id=job_id,
                        ended_at=datetime.now(timezone.utc).isoformat(),
                        processing_time=total_time,
                        progress=100,
                        documents=webhook_documents,
                        meta_data=meta_data,
                        download_url=download_url,
                        doc_stats=doc_stats,
                    )
                    send_webhook_notification(
                        webhook_url, payload, webhook_secret
                    )

            return {
                "status": final_status,
                "client_job_id": client_job_id,
                "download_url": download_url,
                "processing_time": total_time,
                "file_size": file_size,
                "documents_completed": doc_stats["completed"],
                "documents_failed": doc_stats["failed"],
            }

    except Exception as e:
        # Log error and update task status
        error_msg = str(e)
        error_type = type(e).__name__

        self.update_state(
            state="FAILURE",
            meta={
                "client_job_id": client_job_id,
                "error": error_msg,
                "exc_type": error_type,
            },
        )

        # Update database
        with app.app_context():
            update_job_status_by_id(
                job_id=job_id,
                status=Status.FAILED,
                error=error_msg,
                exception_type=error_type,
                processing_time=time.time() - start_time,
                ended_at=datetime.now(timezone.utc),
            )

            # Get final doc stats
            doc_stats = get_document_stats_by_id(job_id)

            # Get documents for webhook
            final_job_info = get_job_info_by_id(job_id)

        # Send failure webhook
        if webhook_url and webhook_secret:
            with app.app_context():
                # Map document status for webhook - exclude 'index' and 'data' fields
                webhook_documents = []
                if final_job_info:
                    for doc in final_job_info.get("documents", []):
                        webhook_doc = {
                            "type": doc["type"],
                            "status": doc.get("status"),
                            "processing_time": doc.get("processing_time"),
                            "error": doc.get("error"),
                            "meta_data": doc.get("meta_data", {}),
                        }
                        # Only include non-None values
                        webhook_doc = {
                            k: v
                            for k, v in webhook_doc.items()
                            if v is not None
                        }
                        webhook_documents.append(webhook_doc)

                payload = build_process_zip_webhook_payload(
                    client_job_id=client_job_id,
                    task_id=self.request.id,
                    status=Status.FAILED,
                    started_at=job_info["started_at"]
                    if job_info
                    else datetime.now(timezone.utc).isoformat(),
                    job_id=job_id,
                    ended_at=datetime.now(timezone.utc).isoformat(),
                    processing_time=time.time() - start_time,
                    progress=0,
                    documents=webhook_documents,
                    meta_data=meta_data,
                    error=error_msg,
                    doc_stats=doc_stats,
                )
                send_webhook_notification(webhook_url, payload, webhook_secret)

        raise
