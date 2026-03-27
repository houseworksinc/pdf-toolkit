"""Celery worker for ZIP file creation operations"""

import time
import requests
import tempfile
from datetime import datetime, timezone

from app import app
from app.constants import Status, CeleryState
from app.services.zip_creator import create_zip_from_urls, ZipCreationError
from app.services.pdf_merger import DocumentNotFoundError
from app.services.limit_validator import DownloadLimitExceeded
from app.services.webhook_notifier import (
    send_webhook_notification,
    build_webhook_payload,
)
from app.services.upload_handler import generate_s3_presigned_url
from app.database import update_job_status_by_id, get_job_info_by_id
from app.models import User


def register_create_zip_task(celery_app, s3_client, s3_bucket):
    """Register the create_zip_task with the Celery app"""

    @celery_app.task(name="create_zip_task", bind=True)
    def create_zip_task(
        self,
        job_id,
        client_job_id,
        document_urls,
        output_filename=None,
        webhook_url=None,
        file_upload_url=None,
        meta_data=None,
        user_id=None,
    ):
        """
        Celery task to create a ZIP archive from multiple files and upload the result.

        Args:
            job_id: UUID job identifier (primary key)
            client_job_id: Client-provided job identifier
            document_urls: List of URLs to files to include in ZIP
            output_filename: Optional output filename (default: client_job_id)
            webhook_url: Optional webhook URL for notifications
            file_upload_url: Optional custom URL to upload the result
            meta_data: Optional metadata for the job
            user_id: User ID for webhook secret lookup
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
                meta={"client_job_id": client_job_id, "job_id": job_id},
            )

            with app.app_context():
                from app.database import (
                    update_job_status_by_id,
                    get_job_info_by_id,
                    update_document_status_by_id,
                )

                update_job_status_by_id(job_id, Status.PROCESSING)
                job_info = get_job_info_by_id(job_id)

                # Mark all documents as PROCESSING
                num_documents = len(job_info.get("documents", []))
                for idx in range(num_documents):
                    update_document_status_by_id(
                        job_id=job_id,
                        document_index=idx,
                        status=Status.PROCESSING,
                        started_at=datetime.now(timezone.utc),
                    )

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

            # Create temporary directory for ZIP operation
            with tempfile.TemporaryDirectory() as tmpdir:
                # Use client_job_id as output filename if not provided
                if not output_filename:
                    output_filename = client_job_id

                # Initialize download size limit
                max_download_bytes = (
                    app.config["MAX_DOWNLOAD_SIZE_MB"] * 1024 * 1024
                )

                # Create ZIP archive with size limits
                zip_result = create_zip_from_urls(
                    document_urls=document_urls,
                    output_filename=output_filename,
                    output_dir=tmpdir,
                    max_download_bytes=max_download_bytes,
                )

                if not zip_result["success"]:
                    raise ZipCreationError(
                        zip_result.get("error", "ZIP creation failed")
                    )

                zip_path = zip_result["zip_path"]
                file_size = zip_result.get("file_size", 0)

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
                        raise ZipCreationError(
                            f"Failed to upload to custom URL: {str(e)}"
                        )
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
                            s3_key,
                            bucket=s3_bucket,
                            content_type="application/zip",
                        )
                    except Exception as e:
                        raise ZipCreationError(
                            f"Failed to upload to S3: {str(e)}"
                        )

                # Calculate processing time
                processing_time = time.time() - start_time

                # Update database with success status
                with app.app_context():
                    from app.database import (
                        update_job_status_by_id,
                        update_document_status_by_id,
                    )

                    update_job_status_by_id(
                        job_id=job_id,
                        status=Status.COMPLETED,
                        s3_key=s3_key,
                        download_url=download_url,
                        processing_time=processing_time,
                    )

                    # Mark all documents as COMPLETED
                    num_documents = len(document_urls)
                    for idx in range(num_documents):
                        update_document_status_by_id(
                            job_id=job_id,
                            document_index=idx,
                            status=Status.COMPLETED,
                            ended_at=datetime.now(timezone.utc),
                            processing_time=processing_time
                            / num_documents,  # Distribute time across documents
                        )

                # Send final webhook notification (job completed)
                if webhook_url and webhook_secret:
                    # Get updated job info with latest documents status
                    with app.app_context():
                        from app.database import get_job_info_by_id

                        updated_job_info = get_job_info_by_id(job_id)

                    payload = build_webhook_payload(
                        client_job_id=client_job_id,
                        task_id=self.request.id,
                        status=Status.COMPLETED,
                        job_id=job_id,
                        started_at=job_info["created_at"]
                        if job_info
                        else datetime.now(timezone.utc).isoformat(),
                        ended_at=datetime.now(timezone.utc).isoformat(),
                        processing_time=processing_time,
                        meta_data=meta_data,
                        download_url=download_url,
                        documents=updated_job_info.get("documents", []),
                    )
                    send_webhook_notification(
                        webhook_url, payload, webhook_secret
                    )

                return {
                    "status": CeleryState.SUCCESS,
                    "client_job_id": client_job_id,
                    "download_url": download_url,
                    "processing_time": processing_time,
                    "file_size": file_size,
                    "num_files": zip_result.get(
                        "num_files", len(document_urls)
                    ),
                }

        except DownloadLimitExceeded as e:
            # Handle download limit exceeded errors separately
            error_msg = str(e)
            error_type = "DownloadLimitExceeded"

            self.update_state(
                state=CeleryState.FAILURE,
                meta={
                    "client_job_id": client_job_id,
                    "job_id": job_id,
                    "error": error_msg,
                    "exc_type": error_type,
                },
            )

            # Update database
            with app.app_context():
                from app.database import (
                    update_job_status_by_id,
                    update_document_status_by_id,
                )

                update_job_status_by_id(
                    job_id=job_id,
                    status=Status.FAILED,
                    error=error_msg,
                    exception_type=error_type,
                    processing_time=time.time() - start_time,
                )

                # Mark all documents as FAILED
                num_documents = len(document_urls)
                for idx in range(num_documents):
                    update_document_status_by_id(
                        job_id=job_id,
                        document_index=idx,
                        status=Status.FAILED,
                        ended_at=datetime.now(timezone.utc),
                        error=error_msg,
                    )

            # Send failure webhook
            if webhook_url and webhook_secret:
                # Get updated job info
                with app.app_context():
                    from app.database import get_job_info_by_id

                    updated_job_info = get_job_info_by_id(job_id)

                payload = build_webhook_payload(
                    client_job_id=client_job_id,
                    task_id=self.request.id,
                    status=Status.FAILED,
                    job_id=job_id,
                    started_at=job_info["created_at"]
                    if job_info
                    else datetime.now(timezone.utc).isoformat(),
                    ended_at=datetime.now(timezone.utc).isoformat(),
                    processing_time=time.time() - start_time,
                    meta_data=meta_data,
                    error=error_msg,
                    documents=updated_job_info.get("documents", [])
                    if updated_job_info
                    else [],
                )
                send_webhook_notification(webhook_url, payload, webhook_secret)

            raise

        except (ZipCreationError, DocumentNotFoundError) as e:
            # Handle ZIP-specific errors
            error_type = type(e).__name__
            error_msg = str(e)

            self.update_state(
                state=CeleryState.FAILURE,
                meta={
                    "client_job_id": client_job_id,
                    "job_id": job_id,
                    "error": error_msg,
                    "exc_type": error_type,
                },
            )

            # Update database
            with app.app_context():
                from app.database import (
                    update_job_status_by_id,
                    update_document_status_by_id,
                )

                update_job_status_by_id(
                    job_id=job_id,
                    status=Status.FAILED,
                    error=error_msg,
                    exception_type=error_type,
                    processing_time=time.time() - start_time,
                )

                # Mark all documents as FAILED
                num_documents = len(document_urls)
                for idx in range(num_documents):
                    update_document_status_by_id(
                        job_id=job_id,
                        document_index=idx,
                        status=Status.FAILED,
                        ended_at=datetime.now(timezone.utc),
                        error=error_msg,
                    )

            # Send failure webhook
            if webhook_url and webhook_secret:
                # Get updated job info
                with app.app_context():
                    from app.database import get_job_info_by_id

                    updated_job_info = get_job_info_by_id(job_id)

                payload = build_webhook_payload(
                    client_job_id=client_job_id,
                    task_id=self.request.id,
                    status=Status.FAILED,
                    job_id=job_id,
                    started_at=job_info["created_at"]
                    if job_info
                    else datetime.now(timezone.utc).isoformat(),
                    ended_at=datetime.now(timezone.utc).isoformat(),
                    processing_time=time.time() - start_time,
                    meta_data=meta_data,
                    error=error_msg,
                    documents=updated_job_info.get("documents", [])
                    if updated_job_info
                    else [],
                )
                send_webhook_notification(webhook_url, payload, webhook_secret)

            raise

        except Exception as e:
            # Handle unexpected errors
            error_msg = str(e)
            error_type = type(e).__name__

            self.update_state(
                state=CeleryState.FAILURE,
                meta={
                    "client_job_id": client_job_id,
                    "job_id": job_id,
                    "error": error_msg,
                    "exc_type": error_type,
                },
            )

            # Update database
            with app.app_context():
                from app.database import (
                    update_job_status_by_id,
                    update_document_status_by_id,
                )

                update_job_status_by_id(
                    job_id=job_id,
                    status=Status.FAILED,
                    error=error_msg,
                    exception_type=error_type,
                    processing_time=time.time() - start_time,
                )

                # Mark all documents as FAILED
                num_documents = len(document_urls)
                for idx in range(num_documents):
                    update_document_status_by_id(
                        job_id=job_id,
                        document_index=idx,
                        status=Status.FAILED,
                        ended_at=datetime.now(timezone.utc),
                        error=error_msg,
                    )

            # Send failure webhook
            if webhook_url and webhook_secret:
                # Get updated job info
                with app.app_context():
                    from app.database import get_job_info_by_id

                    updated_job_info = get_job_info_by_id(job_id)

                payload = build_webhook_payload(
                    client_job_id=client_job_id,
                    task_id=self.request.id,
                    status=Status.FAILED,
                    job_id=job_id,
                    started_at=job_info["created_at"]
                    if job_info
                    else datetime.now(timezone.utc).isoformat(),
                    ended_at=datetime.now(timezone.utc).isoformat(),
                    processing_time=time.time() - start_time,
                    meta_data=meta_data,
                    error=error_msg,
                    documents=updated_job_info.get("documents", [])
                    if updated_job_info
                    else [],
                )
                send_webhook_notification(webhook_url, payload, webhook_secret)

            raise

    return create_zip_task
