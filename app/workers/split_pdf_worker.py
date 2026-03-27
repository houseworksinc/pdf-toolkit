"""Celery worker for PDF splitting operations"""

import time
from datetime import datetime, timezone

from app import app
from app.constants import Status, CeleryState
from app.services.pdf_splitter import split_pdf_from_url, split_pdf_by_pages
from app.services.pdf_orchestrator import download_document_from_url
from app.services.limit_validator import DownloadLimitExceeded
from app.services.upload_handler import upload_split_file
from app.services.webhook_notifier import (
    send_webhook_notification,
    build_webhook_payload,
)
from app.database import (
    update_job_status_by_id,
    update_split_output_status_by_id,
    is_split_job_complete_by_id,
    get_split_outputs_by_id,
    get_job_info_by_id,
)
from app.models import User
import tempfile


def register_split_pdf_task(celery_app):
    """Register the split_pdf_task with the Celery app"""

    @celery_app.task(name="split_pdf_task", bind=True)
    def split_pdf_task(
        self,
        job_id,
        client_job_id,
        document_url,
        splits,
        webhook_url=None,
        meta_data=None,
        user_id=None,
    ):
        """
        Celery task to split a PDF and upload split files.

        Args:
            job_id: Job UUID (primary key)
            client_job_id: Unique job identifier
            document_url: URL to download the source PDF from
            splits: List of split configurations
            webhook_url: Optional webhook URL for notifications
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
                meta={"client_job_id": client_job_id, "progress": 0},
            )

            with app.app_context():
                from app.database import update_document_status_by_id

                update_job_status_by_id(job_id, Status.PROCESSING)
                # Update source document status to PROCESSING
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
                    progress=0,
                    meta_data=meta_data,
                    splits=[],
                    documents=job_info.get("documents", []),
                )
                send_webhook_notification(webhook_url, payload, webhook_secret)

            # Create temporary directory for split files
            with tempfile.TemporaryDirectory() as tmpdir:
                # Download PDF with size validation
                max_download_bytes = (
                    app.config["MAX_DOWNLOAD_SIZE_MB"] * 1024 * 1024
                )

                download_result = download_document_from_url(
                    document_url,
                    tmpdir,
                    total_downloaded_bytes=0,  # Single PDF download
                    max_download_bytes=max_download_bytes,
                )

                if not download_result["success"]:
                    raise Exception(download_result["error"])

                pdf_path = download_result["file_path"]

                # Split the downloaded PDF
                split_results = split_pdf_by_pages(
                    pdf_path, splits, output_dir=tmpdir
                )

                # Process each split result
                total_splits = len(split_results)
                completed_splits = 0

                for idx, split_result in enumerate(split_results):
                    file_name = split_result["file_name"]
                    split_start_time = time.time()

                    with app.app_context():
                        # Update split status to PROCESSING
                        update_split_output_status_by_id(
                            job_id, file_name, Status.PROCESSING
                        )

                    if split_result["success"]:
                        # Upload the split file
                        split_config = splits[idx]
                        file_upload_url = split_config.get("file_upload_url")

                        upload_result = upload_split_file(
                            file_path=split_result["file_path"],
                            output_filename=file_name,
                            job_id=job_id,
                            split_index=idx,
                            file_upload_url=file_upload_url,
                        )

                        split_processing_time = time.time() - split_start_time

                        with app.app_context():
                            if upload_result["success"]:
                                # Update split status to SUCCESS
                                update_split_output_status_by_id(
                                    job_id=job_id,
                                    file_name=file_name,
                                    status=Status.COMPLETED,
                                    s3_key=upload_result.get("s3_key"),
                                    download_url=upload_result.get(
                                        "download_url"
                                    ),
                                    processing_time=split_processing_time,
                                    file_size=upload_result.get("file_size", 0),
                                )
                                completed_splits += 1
                            else:
                                # Update split status to FAILURE
                                error_msg = upload_result.get(
                                    "error", "Upload failed"
                                )
                                update_split_output_status_by_id(
                                    job_id=job_id,
                                    file_name=file_name,
                                    status=Status.FAILED,
                                    error=error_msg,
                                    processing_time=split_processing_time,
                                )
                    else:
                        # Split creation failed
                        split_processing_time = time.time() - split_start_time
                        error_msg = split_result.get("error", "Split failed")

                        with app.app_context():
                            update_split_output_status_by_id(
                                job_id=job_id,
                                file_name=file_name,
                                status=Status.FAILED,
                                error=error_msg,
                                processing_time=split_processing_time,
                            )

                    # Calculate progress
                    progress = int(((idx + 1) / total_splits) * 100)
                    self.update_state(
                        state=CeleryState.PROCESSING,
                        meta={
                            "client_job_id": client_job_id,
                            "progress": progress,
                        },
                    )

                    # Send webhook notification with progress
                    if webhook_url and webhook_secret:
                        with app.app_context():
                            current_splits = get_split_outputs_by_id(job_id)
                            # Map splits to webhook format
                            webhook_splits = []
                            for split in current_splits:
                                webhook_splits.append(
                                    {
                                        "output_filename": split["file_name"],
                                        "pages": split["pages"],
                                        "labels": split.get("labels"),
                                        "status": split["status"],
                                        "status_remark": split.get("error")
                                        or "Completed"
                                        if split["status"] == Status.COMPLETED
                                        else split.get("error", ""),
                                        "download_url": split.get(
                                            "download_url"
                                        ),
                                        "file_size": split.get("file_size"),
                                        "processing_time": split.get(
                                            "processing_time"
                                        ),
                                        "meta_data": split.get("meta_data", {}),
                                    }
                                )

                            payload = build_webhook_payload(
                                client_job_id=client_job_id,
                                task_id=self.request.id,
                                status=Status.PROCESSING,
                                job_id=job_id,
                                started_at=job_info["created_at"]
                                if job_info
                                else datetime.now(timezone.utc).isoformat(),
                                progress=progress,
                                meta_data=meta_data,
                                splits=webhook_splits,
                                documents=job_info.get("documents", []),
                            )
                            send_webhook_notification(
                                webhook_url, payload, webhook_secret
                            )

                # Check if all splits are complete and determine final status
                with app.app_context():
                    from app.database import update_document_status_by_id

                    _, final_status = is_split_job_complete_by_id(job_id)
                    total_time = time.time() - start_time

                    # Update job status
                    update_job_status_by_id(
                        job_id=job_id,
                        status=final_status,
                        processing_time=total_time,
                    )

                    # Update source document status to COMPLETED
                    update_document_status_by_id(
                        job_id=job_id,
                        document_index=0,
                        status=Status.COMPLETED,
                        ended_at=datetime.now(timezone.utc),
                        processing_time=total_time,
                    )

                    # Get final splits for response
                    final_splits = get_split_outputs_by_id(job_id)

                    # Map final splits to webhook format
                    webhook_splits = []
                    for split in final_splits:
                        webhook_splits.append(
                            {
                                "output_filename": split["file_name"],
                                "pages": split["pages"],
                                "labels": split.get("labels"),
                                "status": split["status"],
                                "status_remark": split.get("error")
                                or "Completed"
                                if split["status"] == Status.COMPLETED
                                else split.get("error", ""),
                                "download_url": split.get("download_url"),
                                "file_size": split.get("file_size"),
                                "processing_time": split.get("processing_time"),
                                "meta_data": split.get("meta_data", {}),
                            }
                        )

                # Send final webhook notification
                if webhook_url and webhook_secret:
                    payload = build_webhook_payload(
                        client_job_id=client_job_id,
                        task_id=self.request.id,
                        status=final_status,
                        job_id=job_id,
                        started_at=job_info["created_at"]
                        if job_info
                        else datetime.now(timezone.utc).isoformat(),
                        ended_at=datetime.now(timezone.utc).isoformat(),
                        processing_time=total_time,
                        progress=100,
                        meta_data=meta_data,
                        splits=webhook_splits,
                        documents=job_info.get("documents", []),
                    )
                    send_webhook_notification(
                        webhook_url, payload, webhook_secret
                    )

                return {
                    "status": final_status,
                    "client_job_id": client_job_id,
                    "splits": webhook_splits,
                    "processing_time": total_time,
                }

        except DownloadLimitExceeded as e:
            # Download limit exceeded - handle specifically
            error_msg = str(e)
            error_type = "DownloadLimitExceeded"

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
                from app.database import update_document_status_by_id

                update_job_status_by_id(
                    job_id=job_id,
                    status=Status.FAILED,
                    error=error_msg,
                    exception_type=error_type,
                    processing_time=time.time() - start_time,
                )
                # Update source document status to FAILED
                update_document_status_by_id(
                    job_id=job_id,
                    document_index=0,
                    status=Status.FAILED,
                    ended_at=datetime.now(timezone.utc),
                    error=error_msg,
                )

            # Send failure webhook
            if webhook_url and webhook_secret:
                with app.app_context():
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
                    progress=0,
                    meta_data=meta_data,
                    error=error_msg,
                    splits=[],
                    documents=updated_job_info.get("documents", [])
                    if updated_job_info
                    else [],
                )
                send_webhook_notification(webhook_url, payload, webhook_secret)

            raise

        except Exception as e:
            # Log error and update task status
            self.update_state(
                state=CeleryState.FAILURE,
                meta={
                    "client_job_id": client_job_id,
                    "error": str(e),
                    "exc_type": type(e).__name__,
                },
            )

            # Update database
            with app.app_context():
                from app.database import update_document_status_by_id

                update_job_status_by_id(
                    job_id=job_id,
                    status=Status.FAILED,
                    error=str(e),
                    exception_type=type(e).__name__,
                    processing_time=time.time() - start_time,
                )
                # Update source document status to FAILED
                update_document_status_by_id(
                    job_id=job_id,
                    document_index=0,
                    status=Status.FAILED,
                    ended_at=datetime.now(timezone.utc),
                    error=str(e),
                )

            # Send failure webhook
            if webhook_url and webhook_secret:
                # Get updated job info
                with app.app_context():
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
                    progress=0,
                    meta_data=meta_data,
                    splits=[],
                    error=str(e),
                    documents=updated_job_info.get("documents", [])
                    if updated_job_info
                    else [],
                )
                send_webhook_notification(webhook_url, payload, webhook_secret)

            raise

    return split_pdf_task
