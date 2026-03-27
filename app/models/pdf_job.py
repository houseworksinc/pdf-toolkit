from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import CheckConstraint, Enum as SQLEnum
import uuid
from app.constants import JobType, Status

db = SQLAlchemy()


class PdfJob(db.Model):
    __tablename__ = "pdf_jobs"

    # Primary Keys & Identifiers
    id = db.Column(
        db.String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    client_job_id = db.Column(db.String(255), nullable=False, index=True)
    task_id = db.Column(db.String(255), nullable=True, index=True)
    user_id = db.Column(db.String(255), nullable=True, index=True)

    # Job Classification
    job_type = db.Column(
        SQLEnum(
            JobType.GENERATE,
            JobType.SPLIT,
            JobType.MERGE,
            JobType.ZIP,
            JobType.PARSE,
            JobType.PROCESS_AND_MERGE,
            JobType.PROCESS_AND_ZIP,
            JobType.CONVERT,
            name="job_type_enum",
        ),
        nullable=False,
        index=True,
    )

    # NEW: Unified documents array - stores array of document objects with status, metadata, etc.
    # This is mutable and gets updated during processing
    documents = db.Column(db.JSON, nullable=True)

    # Job-level metadata and configuration
    meta_data = db.Column(db.JSON, nullable=True)
    output_filename = db.Column(db.String(255), nullable=True)
    webhook_url = db.Column(db.String(2048), nullable=True)

    # Audit trail - S3 reference to original API request (stored in S3 for compliance)
    request_audit_s3_key = db.Column(db.String(1024), nullable=True)

    # Status Tracking
    status = db.Column(
        SQLEnum(
            Status.QUEUED,
            Status.PROCESSING,
            Status.COMPLETED,
            Status.FAILED,
            Status.PARTIAL_COMPLETED,
            Status.CANCELLED,
            name="status_enum",
        ),
        default=Status.QUEUED,
        nullable=False,
        index=True,
    )

    # Output
    s3_key = db.Column(db.String(1024), nullable=True)
    download_url = db.Column(db.String(2048), nullable=True)
    file_size = db.Column(db.BigInteger, nullable=True)

    # Error Tracking
    error = db.Column(db.Text, nullable=True)
    exception_type = db.Column(db.String(255), nullable=True)

    # Performance Metrics
    processing_time = db.Column(db.Float, nullable=True)

    # Timestamps
    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    started_at = db.Column(db.DateTime, nullable=True)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    ended_at = db.Column(db.DateTime, nullable=True)

    # Relationships
    splits = db.relationship(
        "PdfSplitOutput", back_populates="job", cascade="all, delete-orphan"
    )

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "length(client_job_id) <= 255", name="check_client_job_id_length"
        ),
        CheckConstraint("length(task_id) <= 255", name="check_task_id_length"),
        CheckConstraint(
            "length(output_filename) <= 255",
            name="check_output_filename_length",
        ),
        CheckConstraint(
            "length(webhook_url) <= 2048", name="check_webhook_url_length"
        ),
        CheckConstraint("length(s3_key) <= 1024", name="check_s3_key_length"),
        CheckConstraint(
            "length(request_audit_s3_key) <= 1024",
            name="check_request_audit_s3_key_length",
        ),
        CheckConstraint(
            "length(download_url) <= 2048", name="check_download_url_length"
        ),
        CheckConstraint(
            "length(exception_type) <= 255", name="check_exception_type_length"
        ),
        # Removed PostgreSQL-specific ::text cast for SQLite compatibility
        # Meta data length validation is handled at application level
        CheckConstraint(
            "processing_time >= 0", name="check_processing_time_positive"
        ),
        CheckConstraint("file_size >= 0", name="check_file_size_positive"),
    )

    def __repr__(self):
        return f"<PdfJob {self.client_job_id} ({self.job_type})>"


class PdfSplitOutput(db.Model):
    __tablename__ = "pdf_split_outputs"

    # Primary Key
    id = db.Column(
        db.String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )

    # Foreign Key - references the primary key (id) of pdf_jobs table
    pdf_job_id = db.Column(
        db.String(36),
        db.ForeignKey("pdf_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Split Configuration
    file_name = db.Column(db.String(255), nullable=False)
    pages = db.Column(db.Text, nullable=False)  # JSON array stored as text
    labels = db.Column(db.Text, nullable=True)  # JSON array stored as text

    # Per-split metadata
    meta_data = db.Column(db.Text, nullable=True)  # JSON stored as text

    # Output Locations
    file_upload_url = db.Column(db.String(2048), nullable=True)
    s3_key = db.Column(db.String(1024), nullable=True)
    download_url = db.Column(db.String(2048), nullable=True)

    # Status Tracking
    status = db.Column(
        SQLEnum(
            "PENDING",
            "PROCESSING",
            "SUCCESS",
            "FAILURE",
            name="split_status_enum",
        ),
        default="PENDING",
        nullable=False,
    )
    error = db.Column(db.String(2048), nullable=True)

    # Performance
    processing_time = db.Column(db.Float, nullable=True)
    file_size = db.Column(db.Integer, nullable=True)

    # Timestamps
    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    ended_at = db.Column(db.DateTime, nullable=True)

    # Relationships
    job = db.relationship("PdfJob", back_populates="splits")

    # Constraints
    __table_args__ = (
        CheckConstraint(
            "length(pdf_job_id) <= 36", name="check_split_pdf_job_id_length"
        ),
        CheckConstraint(
            "length(file_name) > 0 AND length(file_name) <= 255",
            name="check_file_name_length",
        ),
        CheckConstraint("length(pages) <= 10240", name="check_pages_length"),
        CheckConstraint("length(labels) <= 10240", name="check_labels_length"),
        CheckConstraint(
            "length(meta_data) <= 10240", name="check_split_meta_data_length"
        ),
        CheckConstraint(
            "length(file_upload_url) <= 2048",
            name="check_file_upload_url_length",
        ),
        CheckConstraint(
            "length(s3_key) <= 1024", name="check_split_s3_key_length"
        ),
        CheckConstraint(
            "length(download_url) <= 2048",
            name="check_split_download_url_length",
        ),
        CheckConstraint(
            "length(error) <= 2048", name="check_split_error_length"
        ),
        CheckConstraint(
            "processing_time >= 0", name="check_split_processing_time_positive"
        ),
        CheckConstraint("file_size >= 0", name="check_file_size_positive"),
        db.Index("idx_split_pdf_job_id", "pdf_job_id"),
        db.Index("idx_split_status", "status"),
    )

    def __repr__(self):
        return f"<PdfSplitOutput {self.file_name} for job {self.pdf_job_id}>"
