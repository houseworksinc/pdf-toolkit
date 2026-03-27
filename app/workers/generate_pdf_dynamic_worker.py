"""Celery worker for dynamic PDF generation"""

import os
import time
import logging
import requests
import tempfile
from datetime import datetime, timezone
from zipfile import BadZipFile

logger = logging.getLogger(__name__)

from app import app
from app.constants import Status, CeleryState
from app.services.pdf_generator import generate_pdf_dynamic
from app.services.pdf_orchestrator import download_template, optimize_pdf
from app.services.limit_validator import DownloadLimitExceeded
from app.services.webhook_notifier import (
    send_webhook_notification,
    build_webhook_payload,
)
from app.services.upload_handler import generate_s3_presigned_url
from app.database import update_job_status_by_id, get_job_info_by_id
from app.models import User


def register_generate_pdf_dynamic_task(celery_app, s3_client, s3_bucket):
    """Register the generate_pdf_dynamic_task with the Celery app"""

    @celery_app.task(name="generate_pdf_dynamic_task", bind=True)
    def generate_pdf_dynamic_task(
        self,
        job_id,
        client_job_id,
        template_url,
        json_data,
        output_filename="output",
        use_empty_template=False,
        webhook_url=None,
        meta_data=None,
        user_id=None,
        template_hash=None,
    ):
        """
        Celery task to generate PDF using dynamic content processing and upload to S3

        Args:
            job_id: Job UUID (primary key)
            client_job_id: Unique job identifier
            template_url: URL to download the template from (optional if use_empty_template is True)
            json_data: Data to populate the template with
            output_filename: Output filename (without extension)
            use_empty_template: If True, create an empty template instead of downloading
            webhook_url: Optional webhook URL for notifications
            meta_data: Optional metadata for the job
            user_id: User ID for webhook secret lookup
            template_hash: Optional hash for template caching (caching enabled only if provided)
        """
        start_time = time.time()
        webhook_secret = None

        try:
            # Get webhook secret from user if user_id provided
            if user_id and webhook_url:
                with app.app_context():
                    user = User.query.get(user_id)
                    if user and user.webhook_secret:
                        webhook_secret = user.webhook_secret

            # Update task status in both Celery and database
            self.update_state(
                state=CeleryState.PROCESSING,
                meta={"client_job_id": client_job_id},
            )

            # Use the imported app's context
            with app.app_context():
                from app.database import update_document_status_by_id

                update_job_status_by_id(job_id, Status.PROCESSING)
                # Update document status to PROCESSING
                update_document_status_by_id(
                    job_id=job_id,
                    document_index=0,
                    status=Status.PROCESSING,
                    started_at=datetime.now(timezone.utc),
                )
                job_info = get_job_info_by_id(job_id)

            # Send initial webhook notification (job started)
            if webhook_url and webhook_secret:
                payload = build_webhook_payload(
                    client_job_id=client_job_id,
                    task_id=self.request.id,
                    status=Status.PROCESSING,
                    job_id=job_id,
                    started_at=datetime.now(timezone.utc).isoformat(),
                    meta_data=meta_data,
                    documents=job_info.get("documents", []),
                )
                send_webhook_notification(webhook_url, payload, webhook_secret)

            # Create temporary directory
            with tempfile.TemporaryDirectory() as tmpdir:
                # Download template (with caching if template_hash provided)
                # or create empty one based on use_empty_template flag
                template_path = download_template(
                    template_url=template_url,
                    output_dir=tmpdir,
                    use_empty_template=use_empty_template or not template_url,
                    template_hash=template_hash,
                    enable_cache=True,
                )

                logger.info("Task ID: %s", self.request.id)
                # Generate PDF using dynamic function
                try:
                    result = generate_pdf_dynamic(
                        template_path, json_data, tmpdir, output_filename
                    )
                except BadZipFile:
                    raise Exception(
                        f"Invalid template file: The URL '{template_url}' did not return a valid DOCX file. Please check the template URL and ensure it points to a valid Word document."
                    )
                except Exception as e:
                    if "BadZipFile" in str(e) or "not a zip file" in str(e):
                        raise Exception(
                            f"Invalid template file: The URL '{template_url}' did not return a valid DOCX file. Please check the template URL and ensure it points to a valid Word document."
                        )
                    raise

                if not result["success"]:
                    raise Exception(f"PDF generation failed: {result['error']}")

                pdf_path = result["pdf_path"]

                # Optimize PDF to reduce file size before upload
                optimize_pdf(pdf_path)

                # Upload to S3
                if output_filename:
                    s3_key = f"pdfs/{output_filename}.pdf"
                else:
                    s3_key = f"pdfs/{job_id}.pdf"
                s3_client.upload_file(pdf_path, s3_bucket, s3_key)

                # Generate presigned URL
                presigned_url = generate_s3_presigned_url(
                    s3_key, bucket=s3_bucket
                )

                # Update database with success status
                processing_time = time.time() - start_time
                with app.app_context():
                    from app.database import update_document_status_by_id

                    update_job_status_by_id(
                        job_id,
                        Status.COMPLETED,
                        s3_key=s3_key,
                        download_url=presigned_url,
                        processing_time=processing_time,
                    )
                    # Update document status to COMPLETED
                    update_document_status_by_id(
                        job_id=job_id,
                        document_index=0,
                        status=Status.COMPLETED,
                        ended_at=datetime.now(timezone.utc),
                        processing_time=result.get("processing_time", 0),
                    )
                    # Get updated job info for webhook
                    updated_job_info = get_job_info_by_id(job_id)

                # Send success webhook notification
                if webhook_url and webhook_secret:
                    payload = build_webhook_payload(
                        client_job_id=client_job_id,
                        task_id=self.request.id,
                        status=Status.COMPLETED,
                        job_id=job_id,
                        started_at=updated_job_info.get("started_at")
                        or datetime.now(timezone.utc).isoformat(),
                        ended_at=datetime.now(timezone.utc).isoformat(),
                        processing_time=processing_time,
                        meta_data=meta_data,
                        download_url=presigned_url,
                        documents=updated_job_info.get("documents", []),
                    )
                    send_webhook_notification(
                        webhook_url, payload, webhook_secret
                    )

                return {
                    "status": CeleryState.SUCCESS,
                    "client_job_id": client_job_id,
                    "download_url": presigned_url,
                    "processing_time": result.get("processing_time", 0),
                }

        except DownloadLimitExceeded as e:
            # Download limit exceeded - handle specifically
            error_msg = str(e)
            error_type = "DownloadLimitExceeded"
            processing_time = time.time() - start_time

            self.update_state(
                state=CeleryState.FAILURE,
                meta={
                    "client_job_id": client_job_id,
                    "job_id": job_id,
                    "error": error_msg,
                    "exc_type": error_type,
                },
            )

            with app.app_context():
                from app.database import update_document_status_by_id

                update_job_status_by_id(
                    job_id,
                    Status.FAILED,
                    error=error_msg,
                    exception_type=error_type,
                    processing_time=processing_time,
                )
                update_document_status_by_id(
                    job_id=job_id,
                    document_index=0,
                    status=Status.FAILED,
                    ended_at=datetime.now(timezone.utc),
                    error=error_msg,
                )
                updated_job_info = get_job_info_by_id(job_id)

            if webhook_url and webhook_secret:
                payload = build_webhook_payload(
                    client_job_id=client_job_id,
                    task_id=self.request.id,
                    status=Status.FAILED,
                    job_id=job_id,
                    started_at=updated_job_info.get("started_at")
                    or datetime.now(timezone.utc).isoformat(),
                    ended_at=datetime.now(timezone.utc).isoformat(),
                    processing_time=processing_time,
                    meta_data=meta_data,
                    error=error_msg,
                    documents=updated_job_info.get("documents", []),
                )
                send_webhook_notification(webhook_url, payload, webhook_secret)

            raise

        except Exception as e:
            # Log error and update task status in both Celery and database
            error_msg = str(e)
            processing_time = time.time() - start_time

            self.update_state(
                state=CeleryState.FAILURE,
                meta={
                    "client_job_id": client_job_id,
                    "job_id": job_id,
                    "error": error_msg,
                    "exc_type": type(e).__name__,
                },
            )

            # Use the imported app's context for database updates
            with app.app_context():
                from app.database import update_document_status_by_id

                update_job_status_by_id(
                    job_id,
                    Status.FAILED,
                    error=error_msg,
                    exception_type=type(e).__name__,
                    processing_time=processing_time,
                )
                # Update document status to FAILED
                update_document_status_by_id(
                    job_id=job_id,
                    document_index=0,
                    status=Status.FAILED,
                    ended_at=datetime.now(timezone.utc),
                    error=error_msg,
                )
                # Get updated job info for webhook
                updated_job_info = get_job_info_by_id(job_id)

            # Send failure webhook notification
            if webhook_url and webhook_secret:
                payload = build_webhook_payload(
                    client_job_id=client_job_id,
                    task_id=self.request.id,
                    status=Status.FAILED,
                    job_id=job_id,
                    started_at=updated_job_info.get("started_at")
                    or datetime.now(timezone.utc).isoformat(),
                    ended_at=datetime.now(timezone.utc).isoformat(),
                    processing_time=processing_time,
                    meta_data=meta_data,
                    error=error_msg,
                    documents=updated_job_info.get("documents", []),
                )
                send_webhook_notification(webhook_url, payload, webhook_secret)

            raise

    return generate_pdf_dynamic_task
