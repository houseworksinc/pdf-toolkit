from flask import Blueprint, request, jsonify, g
from datetime import datetime, timezone
import tempfile
import shutil
import os
import time
import logging

from app.middleware.auth import require_jwt_token
from app.services.unoserver_converter import UnoServerConverter
from app.services.pdf_orchestrator import download_document_from_url
from app.services.upload_handler import upload_to_s3, upload_to_presigned_url
from app.database import log_request, update_job_status_by_id
from app.constants import Status, JobType

logger = logging.getLogger(__name__)

convert_docx_bp = Blueprint("convert_docx", __name__)

# Configuration
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB limit


@convert_docx_bp.route("/api/v1/convert-docx-to-pdf", methods=["POST"])
@require_jwt_token
def convert_docx_to_pdf():
    """
    Synchronously convert DOCX to PDF.

    Request Body:
    {
        "docx_url": "https://example.com/document.docx",
        "output_filename": "my-document",         // optional
        "client_job_id": "client-123",            // optional
        "file_upload_url": "https://s3-presigned..." // optional
    }

    Returns:
        200: Conversion successful with download URL
        400: Invalid request parameters
        500: Conversion or upload failed
        503: UnoServer unavailable
    """
    start_time = time.time()
    data = request.json
    temp_dir = None
    job_id = None

    try:
        # 1. VALIDATE REQUEST
        docx_url = data.get("docx_url")
        output_filename = data.get("output_filename")
        client_job_id = data.get("client_job_id")
        file_upload_url = data.get("file_upload_url")
        user_id = g.current_user["id"]

        # Validate required fields
        if not docx_url:
            return jsonify({"error": "docx_url is required"}), 400

        if not isinstance(docx_url, str) or not docx_url.startswith(("http://", "https://")):
            return jsonify({"error": "docx_url must be a valid HTTP/HTTPS URL"}), 400

        # Validate output_filename if provided
        if output_filename and not isinstance(output_filename, str):
            return jsonify({"error": "output_filename must be a string"}), 400

        if output_filename and len(output_filename) > 255:
            return jsonify({"error": "output_filename too long (max 255 chars)"}), 400

        # 2. LOG REQUEST TO DATABASE
        job = log_request(
            client_job_id=client_job_id or f"sync-convert-{int(time.time())}",
            job_type=JobType.CONVERT,
            documents=[{
                "type": "docx",
                "status": Status.PROCESSING,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "ended_at": None,
                "processing_time": None,
                "error": None,
                "meta_data": {"docx_url": docx_url}
            }],
            output_filename=output_filename,
            webhook_url=None,  # No webhooks for sync endpoint
            meta_data={"sync": True, "user_id": user_id},
            request_audit_s3_key=None,
            task_id=None  # No Celery task for sync operation
        )

        job_id = str(job.id)

        # Update job status to PROCESSING
        update_job_status_by_id(
            job_id=job_id,
            status=Status.PROCESSING,
            started_at=datetime.now(timezone.utc)
        )

        logger.info(f"Job {job_id}: Starting DOCX to PDF conversion")

        # 3. CREATE TEMP DIRECTORY
        temp_dir = tempfile.mkdtemp()
        logger.info(f"Job {job_id}: Created temp directory {temp_dir}")

        # 4. CHECK UNOSERVER AVAILABILITY
        converter = UnoServerConverter()
        if not converter.is_available():
            error_msg = "PDF conversion service unavailable"
            logger.error(f"Job {job_id}: {error_msg}")

            update_job_status_by_id(
                job_id=job_id,
                status=Status.FAILED,
                error=error_msg,
                ended_at=datetime.now(timezone.utc),
                processing_time=time.time() - start_time
            )

            return jsonify({"error": error_msg}), 503

        # 5. DOWNLOAD DOCX FILE
        logger.info(f"Job {job_id}: Downloading DOCX from {docx_url}")

        download_result = download_document_from_url(
            url=docx_url,
            output_dir=temp_dir,
            total_downloaded_bytes=0,
            max_download_bytes=MAX_FILE_SIZE
        )

        if not download_result["success"]:
            error_msg = f"Download failed: {download_result['error']}"
            logger.error(f"Job {job_id}: {error_msg}")

            update_job_status_by_id(
                job_id=job_id,
                status=Status.FAILED,
                error=error_msg,
                ended_at=datetime.now(timezone.utc),
                processing_time=time.time() - start_time
            )

            return jsonify({"error": error_msg}), 500

        docx_path = download_result["file_path"]
        logger.info(f"Job {job_id}: Downloaded {download_result['file_size']} bytes")

        # 6. VALIDATE FILE TYPE
        if not docx_path.lower().endswith('.docx'):
            error_msg = "File must be a DOCX document"
            logger.error(f"Job {job_id}: {error_msg}")

            update_job_status_by_id(
                job_id=job_id,
                status=Status.FAILED,
                error=error_msg,
                ended_at=datetime.now(timezone.utc),
                processing_time=time.time() - start_time
            )

            return jsonify({"error": error_msg}), 400

        # 7. CONVERT TO PDF
        logger.info(f"Job {job_id}: Converting DOCX to PDF")

        try:
            pdf_path = converter.convert_to_pdf(
                input_path=docx_path,
                output_dir=temp_dir
            )

            logger.info(f"Job {job_id}: Conversion successful - {pdf_path}")
        except Exception as e:
            error_msg = f"Conversion failed: {str(e)}"
            logger.error(f"Job {job_id}: {error_msg}")

            update_job_status_by_id(
                job_id=job_id,
                status=Status.FAILED,
                error=error_msg,
                ended_at=datetime.now(timezone.utc),
                processing_time=time.time() - start_time
            )

            return jsonify({"error": error_msg}), 500

        # 8. UPLOAD PDF
        if file_upload_url:
            # Upload to client-provided presigned URL
            logger.info(f"Job {job_id}: Uploading to presigned URL")

            upload_result = upload_to_presigned_url(pdf_path, file_upload_url)

            if not upload_result["success"]:
                error_msg = f"Upload to presigned URL failed: {upload_result['error']}"
                logger.error(f"Job {job_id}: {error_msg}")

                update_job_status_by_id(
                    job_id=job_id,
                    status=Status.FAILED,
                    error=error_msg,
                    ended_at=datetime.now(timezone.utc),
                    processing_time=time.time() - start_time
                )

                return jsonify({"error": error_msg}), 500

            download_url = file_upload_url
            s3_key = None
            file_size = upload_result["file_size"]

            logger.info(f"Job {job_id}: Upload to presigned URL successful")
        else:
            # Upload to our S3 bucket
            s3_key = f"pdfs/convert/{job_id}.pdf"
            logger.info(f"Job {job_id}: Uploading to S3: {s3_key}")

            upload_result = upload_to_s3(
                file_path=pdf_path,
                s3_key=s3_key,
                generate_presigned_url=True
            )

            if not upload_result["success"]:
                error_msg = f"S3 upload failed: {upload_result['error']}"
                logger.error(f"Job {job_id}: {error_msg}")

                update_job_status_by_id(
                    job_id=job_id,
                    status=Status.FAILED,
                    error=error_msg,
                    ended_at=datetime.now(timezone.utc),
                    processing_time=time.time() - start_time
                )

                return jsonify({"error": error_msg}), 500

            download_url = upload_result["download_url"]
            s3_key = upload_result["s3_key"]
            file_size = upload_result["file_size"]

            logger.info(f"Job {job_id}: S3 upload successful")

        # 9. UPDATE JOB STATUS
        processing_time = time.time() - start_time

        update_job_status_by_id(
            job_id=job_id,
            status=Status.COMPLETED,
            s3_key=s3_key,
            download_url=download_url,
            file_size=file_size,
            ended_at=datetime.now(timezone.utc),
            processing_time=processing_time
        )

        logger.info(f"Job {job_id}: Completed in {processing_time:.2f}s")

        # 10. RETURN SUCCESS RESPONSE
        return jsonify({
            "status": Status.COMPLETED,
            "job_id": job_id,
            "client_job_id": client_job_id,
            "download_url": download_url,
            "s3_key": s3_key,
            "file_size": file_size,
            "processing_time": round(processing_time, 2),
            "output_filename": output_filename or f"{job_id}.pdf"
        }), 200

    except Exception as e:
        # Handle any unexpected errors
        error_msg = f"Unexpected error: {str(e)}"
        logger.error(f"Job {job_id if job_id else 'unknown'}: {error_msg}", exc_info=True)

        if job_id:
            update_job_status_by_id(
                job_id=job_id,
                status=Status.FAILED,
                error=error_msg,
                ended_at=datetime.now(timezone.utc),
                processing_time=time.time() - start_time
            )

        return jsonify({"error": error_msg}), 500

    finally:
        # ALWAYS cleanup temporary directory
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
                logger.info(f"Cleaned up temp directory: {temp_dir}")
            except Exception as e:
                logger.warning(f"Failed to cleanup temp directory: {e}")
