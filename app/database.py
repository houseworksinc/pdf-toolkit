import os
import json
import secrets
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple
from app.models import db, PdfJob, PdfSplitOutput, User
from app.constants import Status
from sqlalchemy.exc import IntegrityError, DatabaseError
from sqlalchemy.orm.attributes import flag_modified
from app.models import JobType

logger = logging.getLogger(__name__)


def init_db():
    """Initialize the database and create all tables"""
    from app import app

    with app.app_context():
        # Create all tables
        db.create_all()

        # Create master admin user if it doesn't exist
        master_username = os.environ.get("MASTER_USERNAME")
        master_password = os.environ.get("MASTER_PASSWORD")

        if not master_username or not master_password:
            raise ValueError(
                "MASTER_USERNAME and MASTER_PASSWORD environment variables are required"
            )

        existing_user = User.query.filter_by(username=master_username).first()

        if not existing_user:
            admin = User(username=master_username)
            admin.set_password(master_password)
            # Generate webhook secret for master admin
            admin.webhook_secret = secrets.token_urlsafe(32)
            admin.webhook_secret_created_at = datetime.now(timezone.utc)
            db.session.add(admin)
            db.session.commit()
            logger.info("Master admin user created successfully.")
        else:
            # If existing admin doesn't have webhook secret, generate one
            if not existing_user.webhook_secret:
                existing_user.webhook_secret = secrets.token_urlsafe(32)
                existing_user.webhook_secret_created_at = datetime.now(
                    timezone.utc
                )
                db.session.commit()
                logger.info("Webhook secret generated for existing admin user.")


def close_db(e=None):
    """Close database connection (for Flask teardown)"""
    # SQLAlchemy handles connection pooling, no explicit close needed
    pass


# ===== PDF Jobs Functions =====


def log_request(
    client_job_id: str,
    job_type: str = JobType.GENERATE,
    documents: Optional[List[Dict[str, Any]]] = None,
    output_filename: Optional[str] = None,
    webhook_url: Optional[str] = None,
    meta_data: Optional[Dict[str, Any]] = None,
    request_audit_s3_key: Optional[str] = None,
    task_id: Optional[str] = None,
) -> PdfJob:
    """
    Log a PDF job request with unified documents array.

    Args:
        client_job_id: Client's unique job identifier
        job_type: Type of job (JobType.GENERATE, JobType.MERGE, JobType.SPLIT, JobType.ZIP, JobType.PROCESS_AND_MERGE)
        documents: Array of document objects with status, metadata, etc.
        output_filename: Optional output filename
        webhook_url: Optional webhook URL for notifications
        meta_data: Job-level metadata
        request_audit_s3_key: S3 key reference to original API request stored in S3 for compliance
        task_id: Celery task ID

    Raises:
        IntegrityError: If constraint violation occurs
        DatabaseError: For other database-related errors
    """
    try:
        job = PdfJob(
            client_job_id=client_job_id,
            job_type=job_type,
            documents=documents,
            output_filename=output_filename,
            webhook_url=webhook_url,
            meta_data=meta_data,
            request_audit_s3_key=request_audit_s3_key,
            task_id=task_id,
        )

        db.session.add(job)
        db.session.commit()

        return job

    except IntegrityError as e:
        db.session.rollback()
        logger.error(
            f"Failed to log request for client_job_id {client_job_id}: {str(e)}"
        )
        raise
    except DatabaseError as e:
        db.session.rollback()
        logger.error(
            f"Database error while logging request for client_job_id {client_job_id}: {str(e)}"
        )
        raise


def update_job_status_by_id(
    job_id: str,
    status: str,
    s3_key: Optional[str] = None,
    download_url: Optional[str] = None,
    file_size: Optional[int] = None,
    error: Optional[str] = None,
    exception_type: Optional[str] = None,
    processing_time: Optional[float] = None,
    started_at: Optional[datetime] = None,
    ended_at: Optional[datetime] = None,
):
    """Update the status of a PDF job by job_id (UUID)"""
    job = PdfJob.query.filter_by(id=job_id).first()

    if job:
        job.status = status
        job.updated_at = datetime.now(timezone.utc)

        # Set started_at if provided or if moving to PROCESSING
        if started_at:
            job.started_at = started_at
        elif status == Status.PROCESSING and not job.started_at:
            job.started_at = datetime.now(timezone.utc)

        # Set ended_at if provided or if moving to final status
        if ended_at:
            job.ended_at = ended_at
        elif (
            status
            in [Status.COMPLETED, Status.FAILED, Status.PARTIAL_COMPLETED, Status.CANCELLED]
            and not job.ended_at
        ):
            job.ended_at = datetime.now(timezone.utc)

        if status == Status.COMPLETED:
            job.s3_key = s3_key
            job.download_url = download_url
            job.file_size = file_size
            job.processing_time = processing_time
        elif status == Status.CANCELLED:
            job.error = error
        elif status in [Status.FAILED, Status.PARTIAL_COMPLETED]:
            job.error = error
            job.exception_type = exception_type
            job.processing_time = processing_time
            # Also update s3_key and download_url for PARTIAL_COMPLETED
            if status == Status.PARTIAL_COMPLETED:
                job.s3_key = s3_key
                job.download_url = download_url
                job.file_size = file_size

        db.session.commit()


def update_job_task_id_by_id(job_id: str, task_id: str):
    """Update the task_id for a job by job_id (UUID)"""
    job = PdfJob.query.filter_by(id=job_id).first()

    if job:
        job.task_id = task_id
        job.updated_at = datetime.now(timezone.utc)
        db.session.commit()


def get_job_info_by_id(job_id: str) -> Optional[Dict[str, Any]]:
    """Get job information by UUID job_id (primary key)"""
    job = PdfJob.query.filter_by(id=job_id).first()

    if not job:
        return None

    job_dict = {
        "id": job.id,
        "job_id": job.id,  # UUID primary key for status lookups
        "client_job_id": job.client_job_id,
        "task_id": job.task_id,
        "job_type": job.job_type,
        "documents": job.documents,
        "output_filename": job.output_filename,
        "webhook_url": job.webhook_url,
        "meta_data": job.meta_data,
        "request_audit_s3_key": job.request_audit_s3_key,
        "status": job.status,
        "s3_key": job.s3_key,
        "download_url": job.download_url,
        "file_size": job.file_size,
        "error": job.error,
        "exception_type": job.exception_type,
        "processing_time": job.processing_time,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
        "ended_at": job.ended_at.isoformat() if job.ended_at else None,
    }

    return job_dict


def get_all_jobs(
    limit: int = 100,
    offset: int = 0,
    status: Optional[str] = None,
    client_job_id: Optional[str] = None,
    job_type: Optional[str] = None,
    user_id: Optional[str] = None,
    job_id: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Get all job logs with optional filtering"""
    query = PdfJob.query

    # Add filters
    if status:
        query = query.filter_by(status=status)
    if client_job_id:
        query = query.filter_by(client_job_id=client_job_id)
    if job_type:
        query = query.filter_by(job_type=job_type)
    if user_id:
        query = query.filter_by(user_id=user_id)
    if job_id:
        query = query.filter_by(id=job_id)
    if date_from:
        query = query.filter(PdfJob.created_at >= date_from)
    if date_to:
        query = query.filter(PdfJob.created_at <= date_to)

    # Order and paginate
    jobs = (
        query.order_by(PdfJob.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    # Convert to dictionaries
    result = []
    for job in jobs:
        job_dict = {
            "id": job.id,
            "client_job_id": job.client_job_id,
            "task_id": job.task_id,
            "job_type": job.job_type,
            "documents": job.documents,
            "output_filename": job.output_filename,
            "webhook_url": job.webhook_url,
            "meta_data": job.meta_data,
            "request_audit_s3_key": job.request_audit_s3_key,
            "status": job.status,
            "s3_key": job.s3_key,
            "download_url": job.download_url,
            "file_size": job.file_size,
            "error": job.error,
            "exception_type": job.exception_type,
            "processing_time": job.processing_time,
            "created_at": job.created_at.isoformat()
            if job.created_at
            else None,
            "started_at": job.started_at.isoformat()
            if job.started_at
            else None,
            "updated_at": job.updated_at.isoformat()
            if job.updated_at
            else None,
            "ended_at": job.ended_at.isoformat() if job.ended_at else None,
        }
        result.append(job_dict)

    return result


def get_document_stats_by_id(job_id: str) -> Dict[str, int]:
    """
    Get aggregate statistics about documents in a job by job_id (UUID).

    Args:
        job_id: Job UUID (primary key)

    Returns:
        Dictionary with counts: total, pending, processing, completed, failed
    """
    job = PdfJob.query.filter_by(id=job_id).first()

    if not job or not job.documents:
        return {
            "total": 0,
            "pending": 0,
            "processing": 0,
            "completed": 0,
            "failed": 0,
        }

    stats = {
        "total": len(job.documents),
        "pending": 0,
        "processing": 0,
        "completed": 0,
        "failed": 0,
    }

    for doc in job.documents:
        status = doc.get("status", Status.QUEUED)
        if status == Status.QUEUED:
            stats["pending"] += 1
        elif status == Status.PROCESSING:
            stats["processing"] += 1
        elif status == Status.COMPLETED:
            stats["completed"] += 1
        elif status == Status.FAILED:
            stats["failed"] += 1

    return stats


def update_document_status_by_id(
    job_id: str,
    document_index: int,
    status: str,
    started_at: Optional[datetime] = None,
    ended_at: Optional[datetime] = None,
    processing_time: Optional[float] = None,
    error: Optional[str] = None,
    **kwargs,
):
    """
    Update the status of a specific document in the documents array by job_id.

    Args:
        job_id: Job UUID (primary key)
        document_index: Index of the document in the documents array
        status: New status ('PENDING', 'PROCESSING', 'SUCCESS', 'FAILURE')
        started_at: When processing started
        ended_at: When processing ended
        processing_time: Time taken to process (seconds)
        error: Error message if failed
        **kwargs: Additional fields to update in the document object
    """
    job = PdfJob.query.filter_by(id=job_id).first()

    if not job or not job.documents:
        logger.warning(f"Job {job_id} not found or has no documents")
        return

    if document_index < 0 or document_index >= len(job.documents):
        logger.warning(
            f"Document index {document_index} out of range for job {job_id}"
        )
        return

    # Update document status
    job.documents[document_index]["status"] = status

    if started_at:
        job.documents[document_index]["started_at"] = started_at.isoformat()

    if ended_at:
        job.documents[document_index]["ended_at"] = ended_at.isoformat()

    if processing_time is not None:
        job.documents[document_index]["processing_time"] = processing_time

    if error:
        job.documents[document_index]["error"] = error

    # Update any additional fields
    for key, value in kwargs.items():
        job.documents[document_index][key] = value

    # Mark the documents column as modified (required for JSON columns)
    flag_modified(job, "documents")
    job.updated_at = datetime.now(timezone.utc)

    db.session.commit()


def get_document_status_by_id(
    job_id: str, document_index: int
) -> Optional[Dict[str, Any]]:
    """
    Get the status of a specific document by job_id.

    Args:
        job_id: Job UUID (primary key)
        document_index: Index of the document in the documents array

    Returns:
        Document object or None if not found
    """
    job = PdfJob.query.filter_by(id=job_id).first()

    if not job or not job.documents:
        return None

    if document_index < 0 or document_index >= len(job.documents):
        return None

    return job.documents[document_index]


def get_all_documents_by_id(job_id: str) -> List[Dict[str, Any]]:
    """
    Get all documents for a job by job_id.

    Args:
        job_id: Job UUID (primary key)

    Returns:
        List of document objects
    """
    job = PdfJob.query.filter_by(id=job_id).first()

    if not job or not job.documents:
        return []

    return job.documents


# ===== Split Outputs Functions =====


def get_job_with_splits_by_id(job_id: str) -> Optional[Dict[str, Any]]:
    """Get job info along with all split outputs by job_id (UUID)"""
    job_info = get_job_info_by_id(job_id)

    if not job_info:
        return None

    if job_info["job_type"] == JobType.SPLIT:
        # Get splits using job_id
        job_info["splits"] = get_split_outputs_by_id(job_id)

    return job_info


def log_split_outputs_by_id(job_id: str, splits: List[Dict[str, Any]]):
    """
    Insert split output records for a job by job_id.

    Args:
        job_id: Job UUID (primary key)
        splits: List of split configurations

    Raises:
        IntegrityError: If constraint violation occurs
        DatabaseError: For other database-related errors
        ValueError: If job_id not found
    """
    try:
        # Verify job exists
        job = PdfJob.query.filter_by(id=job_id).first()
        if not job:
            raise ValueError(f"Job not found: {job_id}")

        for split in splits:
            # Handle splits with either 'pages' or 'labels'
            pages = split.get("pages", [])
            labels = split.get("labels")

            split_output = PdfSplitOutput(
                pdf_job_id=job_id,  # Use UUID primary key
                file_name=split.get("output_filename") or split.get("file_name"),  # Support both for backward compatibility
                pages=json.dumps(pages),
                labels=json.dumps(labels) if labels else None,
                meta_data=json.dumps(split.get("meta_data"))
                if split.get("meta_data")
                else None,
                file_upload_url=split.get("file_upload_url"),
            )
            db.session.add(split_output)

        db.session.commit()

    except IntegrityError as e:
        db.session.rollback()
        logger.error(
            f"Failed to log split outputs for job_id {job_id}: {str(e)}"
        )
        raise
    except DatabaseError as e:
        db.session.rollback()
        logger.error(
            f"Database error while logging split outputs for job_id {job_id}: {str(e)}"
        )
        raise


def get_split_outputs_by_id(job_id: str) -> List[Dict[str, Any]]:
    """Get all split outputs for a job by job_id"""
    # Query splits using job_id
    splits = (
        PdfSplitOutput.query.filter_by(pdf_job_id=job_id)
        .order_by(PdfSplitOutput.id)
        .all()
    )

    result = []
    for split in splits:
        split_dict = {
            "id": split.id,
            "job_id": job_id,
            "file_name": split.file_name,
            "pages": json.loads(split.pages) if split.pages else [],
            "labels": json.loads(split.labels) if split.labels else None,
            "meta_data": json.loads(split.meta_data)
            if split.meta_data
            else None,
            "file_upload_url": split.file_upload_url,
            "s3_key": split.s3_key,
            "download_url": split.download_url,
            "status": split.status,
            "error": split.error,
            "processing_time": split.processing_time,
            "file_size": split.file_size,
            "created_at": split.created_at.isoformat()
            if split.created_at
            else None,
            "ended_at": split.ended_at.isoformat() if split.ended_at else None,
        }
        result.append(split_dict)

    return result


def update_split_output_status_by_id(
    job_id: str,
    file_name: str,
    status: str,
    s3_key: Optional[str] = None,
    download_url: Optional[str] = None,
    error: Optional[str] = None,
    processing_time: Optional[float] = None,
    file_size: Optional[int] = None,
):
    """Update the status of a specific split output by job_id"""
    # Query split using job_id
    split = PdfSplitOutput.query.filter_by(
        pdf_job_id=job_id, file_name=file_name
    ).first()

    if split:
        split.status = status

        if status in [Status.COMPLETED, Status.FAILED]:
            split.ended_at = datetime.now(timezone.utc)

        if status == Status.COMPLETED:
            split.s3_key = s3_key
            split.download_url = download_url
            split.processing_time = processing_time
            split.file_size = file_size
        elif status == Status.FAILED:
            split.error = error

        db.session.commit()


def is_split_job_complete_by_id(job_id: str) -> Tuple[bool, str]:
    """Check if all splits for a job are complete by job_id"""
    # Query splits using job_id
    splits = PdfSplitOutput.query.filter_by(pdf_job_id=job_id).all()

    if not splits:
        return False, Status.QUEUED

    total = len(splits)
    completed = sum(1 for s in splits if s.status == Status.COMPLETED)
    failed = sum(1 for s in splits if s.status == Status.FAILED)

    if completed == total:
        return True, Status.COMPLETED
    elif failed > 0 and (completed + failed) == total:
        return (
            True,
            Status.PARTIAL_COMPLETED if completed > 0 else Status.FAILED,
        )
    else:
        return False, Status.PROCESSING


# ===== User Management Functions =====


def create_user(
    username: str, password: str, meta_data: Optional[Dict[str, Any]] = None
) -> Optional[Dict[str, Any]]:
    """
    Create a new user with hashed password and webhook secret.

    Returns:
        User dict if successful, None if username exists

    Raises:
        IntegrityError: If constraint violation occurs
        DatabaseError: For other database-related errors
    """
    try:
        existing_user = User.query.filter_by(username=username).first()

        if existing_user:
            return None  # Username already exists

        user = User(username=username)
        user.set_password(password)

        # Generate webhook secret
        webhook_secret = secrets.token_urlsafe(32)
        user.webhook_secret = webhook_secret
        user.webhook_secret_created_at = datetime.now(timezone.utc)

        if meta_data:
            user.meta_data = json.dumps(meta_data)

        db.session.add(user)
        db.session.commit()

        return {
            "id": user.id,
            "username": user.username,
            "webhook_secret": webhook_secret,
        }

    except IntegrityError as e:
        db.session.rollback()
        logger.error(f"Failed to create user {username}: {str(e)}")
        raise
    except DatabaseError as e:
        db.session.rollback()
        logger.error(f"Database error while creating user {username}: {str(e)}")
        raise


def verify_user(username: str, password: str) -> Optional[Dict[str, Any]]:
    """Verify user credentials and return user info if valid"""
    user = User.query.filter_by(username=username, is_active=True).first()

    if user and user.check_password(password):
        return {
            "id": user.id,
            "username": user.username,
            "is_active": user.is_active,
            "meta_data": json.loads(user.meta_data) if user.meta_data else None,
        }

    return None


def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    """Get user by ID for JWT token validation"""
    user = User.query.filter_by(id=user_id, is_active=True).first()

    if user:
        return {
            "id": user.id,
            "username": user.username,
            "is_active": user.is_active,
            "meta_data": json.loads(user.meta_data) if user.meta_data else None,
        }

    return None


def update_user_metadata(user_id: str, meta_data: Dict[str, Any]) -> bool:
    """Update user metadata"""
    user = User.query.filter_by(id=user_id, is_active=True).first()

    if not user:
        return False

    user.meta_data = json.dumps(meta_data) if meta_data else None
    db.session.commit()

    return True


def update_user_password(username: str, new_password: str) -> bool:
    """
    Update a user's password.

    Args:
        username: The username of the user to update
        new_password: The new password (will be hashed)

    Returns:
        True if successful, False if user not found
    """
    user = User.query.filter_by(username=username, is_active=True).first()

    if not user:
        return False

    user.set_password(new_password)
    db.session.commit()

    return True
