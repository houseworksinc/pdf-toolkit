from app.database import (
    log_request,
    update_job_status_by_id,
    get_job_info_by_id,
)
from app import app
from app.constants import JobType, Status
import pytest
import sqlite3
import os


def test_log_request(client):
    # Run the test within the application context
    with app.app_context():
        # Log a request to the database with new schema
        documents = [
            {
                "url": "https://example.com/template.docx",
                "type": "template",
                "status": "PENDING",
            }
        ]

        job = log_request(
            client_job_id="test_job_123",
            job_type=JobType.GENERATE,
            documents=documents,
            task_id="task_123",
        )

        # Get the job information using job_id
        job_info = get_job_info_by_id(str(job.id))

        # Verify the job was stored correctly
        assert job_info is not None
        assert job_info["client_job_id"] == "test_job_123"
        assert job_info["job_type"] == JobType.GENERATE
        assert job_info["documents"] == documents
        assert job_info["task_id"] == "task_123"
        assert job_info["status"] == Status.QUEUED


def test_update_job_status_success(client):
    # Run the test within the application context
    with app.app_context():
        # First create a job
        documents = [
            {
                "url": "https://example.com/template.docx",
                "type": "template",
                "status": "PENDING",
            }
        ]

        job = log_request(
            client_job_id="test_success_job",
            job_type=JobType.GENERATE,
            documents=documents,
            task_id="task_success",
        )

        # Update the job status to success using job_id
        update_job_status_by_id(
            str(job.id), Status.COMPLETED, s3_key="pdfs/test_success_job.pdf"
        )

        # Get the updated job information using job_id
        job_info = get_job_info_by_id(str(job.id))

        # Verify the status was updated correctly
        assert job_info["status"] == Status.COMPLETED
        assert job_info["s3_key"] == "pdfs/test_success_job.pdf"
        assert job_info["ended_at"] is not None


def test_update_job_status_failure(client):
    # Run the test within the application context
    with app.app_context():
        # First create a job
        documents = [
            {
                "url": "https://example.com/template.docx",
                "type": "template",
                "status": "PENDING",
            }
        ]

        job = log_request(
            client_job_id="test_failure_job",
            job_type=JobType.GENERATE,
            documents=documents,
            task_id="task_failure",
        )

        # Update the job status to failure using job_id
        update_job_status_by_id(
            str(job.id),
            Status.FAILED,
            error="PDF generation failed",
            exception_type="RuntimeError",
        )

        # Get the updated job information using job_id
        job_info = get_job_info_by_id(str(job.id))

        # Verify the status was updated correctly
        assert job_info["status"] == Status.FAILED
        assert job_info["error"] == "PDF generation failed"
        assert job_info["exception_type"] == "RuntimeError"
        assert job_info["ended_at"] is not None  # FAILURE status sets ended_at
