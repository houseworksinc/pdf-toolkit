"""Celery worker for PDF merging operations"""

import time
import requests
import tempfile
from datetime import datetime, timezone

from app import app
from app.constants import Status, CeleryState
from app.services.pdf_merger import (
    MergeError,
    UnsupportedFormatError,
    DocumentNotFoundError,
)
from app.services.limit_validator import DownloadLimitExceeded
from app.services.webhook_notifier import (
    send_webhook_notification,
    build_webhook_payload,
)
from app.services.upload_handler import generate_s3_presigned_url
from app.database import update_job_status_by_id, get_job_info_by_id
from app.models import User


def register_merge_pdfs_task(celery_app, s3_client, s3_bucket):
    """Register the merge_pdfs_task with the Celery app"""

    @celery_app.task(name="merge_pdfs_task", bind=True)
    def merge_pdfs_task(
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
        Celery task to merge multiple PDFs/images and upload the result.

        Args:
            job_id: UUID job identifier (primary key)
            client_job_id: Client-provided job identifier
            document_urls: List of URLs to documents to merge
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

                update_job_status_by_id(
                    job_id,
                    Status.PROCESSING,
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

            # Create temporary directory for merge operation
            with tempfile.TemporaryDirectory() as tmpdir:
                # Use client_job_id as output filename if not provided
                if not output_filename:
                    output_filename = client_job_id

                # Import download and merge functions
                from app.services.pdf_orchestrator import (
                    download_document_from_url,
                    merge_local_pdfs,
                    optimize_pdf,
                )

                # Initialize download tracking
                downloaded_files = []
                document_tracking = []  # Track download success/failure per document
                total_downloaded_bytes = 0
                max_download_bytes = (
                    app.config["MAX_DOWNLOAD_SIZE_MB"] * 1024 * 1024
                )
                download_limit_exceeded = False  # Track if limit was hit
                download_limit_error_msg = None  # Store the error message

                for idx, url in enumerate(document_urls):
                    doc_start_time = time.time()

                    # Update document status to PROCESSING
                    with app.app_context():
                        from app.database import update_document_status_by_id

                        update_document_status_by_id(
                            job_id=job_id,
                            document_index=idx,
                            status=Status.PROCESSING,
                            started_at=datetime.now(timezone.utc),
                        )

                    try:
                        # Download document with size validation
                        download_result = download_document_from_url(
                            url,
                            tmpdir,
                            total_downloaded_bytes=total_downloaded_bytes,
                            max_download_bytes=max_download_bytes,
                        )

                        if not download_result["success"]:
                            raise Exception(download_result["error"])

                        file_path = download_result["file_path"]
                        file_size = download_result.get("file_size", 0)
                        downloaded_files.append(file_path)

                        # Update cumulative bytes counter
                        total_downloaded_bytes += file_size

                        # Track successful download (keep status as PROCESSING until merge completes)
                        document_tracking.append(
                            {
                                "index": idx,
                                "status": "downloaded",
                                "file_path": file_path,
                                "file_size": file_size,
                                "download_time": time.time() - doc_start_time,
                            }
                        )

                    except DownloadLimitExceeded as e:
                        # Download limit exceeded - abort entire job immediately
                        error_msg = str(e)
                        doc_processing_time = time.time() - doc_start_time

                        # Mark current document as FAILED
                        with app.app_context():
                            from app.database import (
                                update_document_status_by_id,
                            )

                            update_document_status_by_id(
                                job_id=job_id,
                                document_index=idx,
                                status=Status.FAILED,
                                ended_at=datetime.now(timezone.utc),
                                processing_time=doc_processing_time,
                                error=error_msg,
                            )

                        # Clean up any already-downloaded files
                        for file_path in downloaded_files:
                            try:
                                if (
                                    file_path
                                    and tempfile.gettempdir() in file_path
                                ):
                                    import os

                                    if os.path.exists(file_path):
                                        os.remove(file_path)
                            except Exception:
                                pass  # Best effort cleanup

                        # Set flag and break out of loop
                        download_limit_exceeded = True
                        download_limit_error_msg = error_msg
                        break

                    except Exception as e:
                        # Document download failed
                        error_msg = str(e)
                        doc_processing_time = time.time() - doc_start_time

                        # Mark document as FAILED immediately
                        with app.app_context():
                            from app.database import (
                                update_document_status_by_id,
                            )

                            update_document_status_by_id(
                                job_id=job_id,
                                document_index=idx,
                                status=Status.FAILED,
                                ended_at=datetime.now(timezone.utc),
                                processing_time=doc_processing_time,
                                error=error_msg,
                            )

                        # Track failed download
                        document_tracking.append(
                            {
                                "index": idx,
                                "status": "failed",
                                "error": error_msg,
                            }
                        )

                # Check if download limit was exceeded
                if download_limit_exceeded:
                    raise MergeError(download_limit_error_msg)

                # Check if we have any files to merge
                if len(downloaded_files) == 0:
                    raise MergeError("All documents failed to download")

                # Merge all downloaded documents
                merge_result = merge_local_pdfs(
                    pdf_paths=downloaded_files,
                    output_filename=output_filename,
                    output_dir=tmpdir,
                )

                if not merge_result["success"]:
                    raise MergeError(merge_result.get("error", "Merge failed"))

                # Merge successful - now mark all successfully downloaded documents as COMPLETED
                with app.app_context():
                    from app.database import update_document_status_by_id

                    for doc_info in document_tracking:
                        if doc_info["status"] == "downloaded":
                            # Calculate total processing time (download + merge)
                            total_processing_time = doc_info["download_time"]

                            update_document_status_by_id(
                                job_id=job_id,
                                document_index=doc_info["index"],
                                status=Status.COMPLETED,
                                ended_at=datetime.now(timezone.utc),
                                processing_time=total_processing_time,
                                file_path=doc_info["file_path"],
                                file_size=doc_info["file_size"],
                            )

                pdf_path = merge_result["pdf_path"]
                
                # Optimize the merged PDF
                optimize_pdf(pdf_path)
                
                file_size = os.path.getsize(pdf_path)

                # Upload the merged PDF
                if file_upload_url:
                    # Upload to custom URL (PUT request)
                    try:
                        with open(pdf_path, "rb") as f:
                            response = requests.put(
                                file_upload_url, data=f, timeout=60
                            )
                            response.raise_for_status()

                        download_url = file_upload_url.split("?")[
                            0
                        ]  # Remove query params
                        s3_key = None
                    except Exception as e:
                        raise MergeError(
                            f"Failed to upload to custom URL: {str(e)}"
                        )
                else:
                    # Upload to S3
                    if output_filename:
                        s3_key = f"pdfs/merged/{output_filename}.pdf"
                    else:
                        s3_key = f"pdfs/merged/{job_id}.pdf"
                    try:
                        s3_client.upload_file(pdf_path, s3_bucket, s3_key)

                        # Generate presigned URL
                        download_url = generate_s3_presigned_url(
                            s3_key, bucket=s3_bucket
                        )
                    except Exception as e:
                        raise MergeError(f"Failed to upload to S3: {str(e)}")

                # Calculate processing time
                processing_time = time.time() - start_time

                # Update database with success status
                with app.app_context():
                    from app.database import update_job_status_by_id

                    update_job_status_by_id(
                        job_id=job_id,
                        status=Status.COMPLETED,
                        s3_key=s3_key,
                        download_url=download_url,
                        processing_time=processing_time,
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
                    "num_documents": merge_result.get(
                        "num_documents", len(document_urls)
                    ),
                }

        except (MergeError, UnsupportedFormatError, DocumentNotFoundError) as e:
            # Handle merge-specific errors
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
                from app.database import update_job_status_by_id

                update_job_status_by_id(
                    job_id=job_id,
                    status=Status.FAILED,
                    error=error_msg,
                    exception_type=error_type,
                    processing_time=time.time() - start_time,
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
                    "error": error_msg,
                    "exc_type": error_type,
                },
            )

            # Update database
            with app.app_context():
                from app.database import update_job_status_by_id

                update_job_status_by_id(
                    job_id=job_id,
                    status=Status.FAILED,
                    error=error_msg,
                    exception_type=error_type,
                    processing_time=time.time() - start_time,
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

    return merge_pdfs_task
