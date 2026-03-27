import pytest
from unittest.mock import patch, MagicMock
import json
from app.constants import JobType


def test_merge_pdfs_missing_job_id(client, auth_headers):
    """Test merge PDFs endpoint with missing client_job_id"""
    response = client.post(
        "/api/v1/merge-pdfs",
        headers=auth_headers,
        json={"document_urls": ["https://example.com/doc1.pdf"]},
    )

    assert response.status_code == 400
    assert "client_job_id is required" in response.json["error"]["message"]


def test_merge_pdfs_missing_document_urls(client, auth_headers):
    """Test merge PDFs endpoint with missing document_urls"""
    response = client.post(
        "/api/v1/merge-pdfs",
        headers=auth_headers,
        json={"client_job_id": "test-123"},
    )

    assert response.status_code == 400
    assert "document_urls" in response.json["error"]["message"]


def test_merge_pdfs_empty_document_urls(client, auth_headers):
    """Test merge PDFs endpoint with empty document_urls array"""
    response = client.post(
        "/api/v1/merge-pdfs",
        headers=auth_headers,
        json={"client_job_id": "test-123", "document_urls": []},
    )

    assert response.status_code == 400
    assert "document_urls" in response.json["error"]["message"]


def test_merge_pdfs_invalid_url_format(client, auth_headers):
    """Test merge PDFs endpoint with invalid URL format"""
    response = client.post(
        "/api/v1/merge-pdfs",
        headers=auth_headers,
        json={
            "client_job_id": "test-123",
            "document_urls": ["not-a-valid-url", "https://example.com/doc.pdf"],
        },
    )

    assert response.status_code == 400
    assert "must start with http" in response.json["error"]["message"]


def test_merge_pdfs_invalid_url_type(client, auth_headers):
    """Test merge PDFs endpoint with non-string URL"""
    response = client.post(
        "/api/v1/merge-pdfs",
        headers=auth_headers,
        json={
            "client_job_id": "test-123",
            "document_urls": [123, "https://example.com/doc.pdf"],
        },
    )

    assert response.status_code == 400
    assert "Invalid URL" in response.json["error"]["message"]


@patch("app.api.merge_pdf.merge_pdfs_task")
def test_merge_pdfs_success(mock_merge_task, client, auth_headers):
    """Test successful merge PDFs request"""
    # Mock the Celery task
    mock_task = MagicMock()
    mock_task.id = "test-task-123"
    mock_merge_task.delay.return_value = mock_task

    response = client.post(
        "/api/v1/merge-pdfs",
        headers=auth_headers,
        json={
            "client_job_id": "merge-test-001",
            "document_urls": [
                "https://example.com/doc1.pdf",
                "https://example.com/doc2.pdf",
                "https://example.com/image.png",
            ],
        },
    )

    assert response.status_code == 200
    assert response.json["client_job_id"] == "merge-test-001"
    assert response.json["task_id"] == "test-task-123"
    assert response.json["status"] == "queued"
    assert "started_at" in response.json

    # Verify the task was called with correct parameters
    mock_merge_task.delay.assert_called_once()
    call_kwargs = mock_merge_task.delay.call_args[1]
    assert call_kwargs["client_job_id"] == "merge-test-001"
    assert len(call_kwargs["document_urls"]) == 3
    assert (
        call_kwargs["output_filename"] == "merge-test-001"
    )  # Default to client_job_id


@patch("app.api.merge_pdf.merge_pdfs_task")
def test_merge_pdfs_with_custom_filename(mock_merge_task, client, auth_headers):
    """Test merge PDFs with custom output filename"""
    mock_task = MagicMock()
    mock_task.id = "test-task-456"
    mock_merge_task.delay.return_value = mock_task

    response = client.post(
        "/api/v1/merge-pdfs",
        headers=auth_headers,
        json={
            "client_job_id": "merge-test-002",
            "document_urls": [
                "https://example.com/doc1.pdf",
                "https://example.com/doc2.pdf",
            ],
            "output_filename": "my-custom-output",
        },
    )

    assert response.status_code == 200

    # Verify custom filename was passed
    call_kwargs = mock_merge_task.delay.call_args[1]
    assert call_kwargs["output_filename"] == "my-custom-output"


@patch("app.api.merge_pdf.merge_pdfs_task")
def test_merge_pdfs_with_webhook(mock_merge_task, client, auth_headers):
    """Test merge PDFs with webhook URL"""
    mock_task = MagicMock()
    mock_task.id = "test-task-789"
    mock_merge_task.delay.return_value = mock_task

    response = client.post(
        "/api/v1/merge-pdfs",
        headers=auth_headers,
        json={
            "client_job_id": "merge-test-003",
            "document_urls": ["https://example.com/doc1.pdf"],
            "webhook": "https://webhook.site/test-123",
        },
    )

    assert response.status_code == 200

    # Verify webhook was passed
    call_kwargs = mock_merge_task.delay.call_args[1]
    assert call_kwargs["webhook_url"] == "https://webhook.site/test-123"


@patch("app.api.merge_pdf.merge_pdfs_task")
def test_merge_pdfs_with_file_upload_url(mock_merge_task, client, auth_headers):
    """Test merge PDFs with custom file upload URL"""
    mock_task = MagicMock()
    mock_task.id = "test-task-101"
    mock_merge_task.delay.return_value = mock_task

    response = client.post(
        "/api/v1/merge-pdfs",
        headers=auth_headers,
        json={
            "client_job_id": "merge-test-004",
            "document_urls": ["https://example.com/doc1.pdf"],
            "file_upload_url": "https://s3.amazonaws.com/presigned-url",
        },
    )

    assert response.status_code == 200

    # Verify file_upload_url was passed
    call_kwargs = mock_merge_task.delay.call_args[1]
    assert (
        call_kwargs["file_upload_url"]
        == "https://s3.amazonaws.com/presigned-url"
    )


@patch("app.api.merge_pdf.merge_pdfs_task")
def test_merge_pdfs_with_metadata(mock_merge_task, client, auth_headers):
    """Test merge PDFs with custom metadata"""
    mock_task = MagicMock()
    mock_task.id = "test-task-202"
    mock_merge_task.delay.return_value = mock_task

    metadata = {
        "project": "test-project",
        "user": "john-doe",
        "category": "contracts",
    }

    response = client.post(
        "/api/v1/merge-pdfs",
        headers=auth_headers,
        json={
            "client_job_id": "merge-test-005",
            "document_urls": ["https://example.com/doc1.pdf"],
            "meta_data": metadata,
        },
    )

    assert response.status_code == 200
    assert response.json["meta_data"] == metadata

    # Verify metadata was passed
    call_kwargs = mock_merge_task.delay.call_args[1]
    assert call_kwargs["meta_data"] == metadata


def test_merge_pdfs_unauthorized(client):
    """Test merge PDFs endpoint without authentication"""
    response = client.post(
        "/api/v1/merge-pdfs",
        json={
            "client_job_id": "test-123",
            "document_urls": ["https://example.com/doc1.pdf"],
        },
    )

    assert response.status_code == 401


def test_get_merge_status_missing_job_id(client, auth_headers):
    """Test get merge status without job_id parameter"""
    response = client.get("/api/v1/merge-pdfs/status", headers=auth_headers)

    assert response.status_code == 400
    assert "job_id" in response.json["error"]["message"]


def test_get_merge_status_not_found(client, auth_headers):
    """Test get merge status for non-existent job"""
    response = client.get(
        "/api/v1/merge-pdfs/status?job_id=non-existent-job-id",
        headers=auth_headers,
    )

    assert response.status_code == 404


@patch("app.api.merge_pdf.merge_pdfs_task")
def test_get_merge_status_success(mock_merge_task, client, auth_headers):
    """Test get merge status for existing job"""
    # First create a job
    mock_task = MagicMock()
    mock_task.id = "test-task-303"
    mock_merge_task.delay.return_value = mock_task

    create_response = client.post(
        "/api/v1/merge-pdfs",
        headers=auth_headers,
        json={
            "client_job_id": "merge-status-test-001",
            "document_urls": ["https://example.com/doc1.pdf"],
        },
    )

    assert create_response.status_code == 200
    job_id = create_response.json["job_id"]

    # Now get status using job_id
    status_response = client.get(
        f"/api/v1/merge-pdfs/status?job_id={job_id}", headers=auth_headers
    )

    assert status_response.status_code == 200
    assert status_response.json["job_id"] == job_id
    assert status_response.json["client_job_id"] == "merge-status-test-001"
    assert status_response.json["task_id"] == "test-task-303"
    assert status_response.json["status"] == "queued"


@patch("app.api.merge_pdf.merge_pdfs_task")
def test_get_merge_status_wrong_job_type(mock_merge_task, client, auth_headers):
    """Test get merge status for a job that is not a merge job"""
    from app.database import log_request
    from app import app as flask_app

    # Create a split job instead of merge using new schema
    with flask_app.app_context():
        documents = [
            {
                "url": "https://example.com/doc.pdf",
                "type": JobType.SPLIT,
                "status": "PENDING",
            }
        ]

        job = log_request(
            client_job_id="split-job-001",
            job_type=JobType.SPLIT,
            documents=documents,
            task_id="task-999",
        )
        job_id = job.id

    # Try to get merge status for split job using job_id
    response = client.get(
        f"/api/v1/merge-pdfs/status?job_id={job_id}", headers=auth_headers
    )

    assert response.status_code == 400
    assert "not a merge job" in response.json["error"]["message"]


def test_merge_pdfs_unauthorized_status(client):
    """Test get merge status without authentication"""
    response = client.get("/api/v1/merge-pdfs/status?job_id=test-job-id-123")

    assert response.status_code == 401


@patch("app.api.merge_pdf.get_job_info_by_id")
def test_get_merge_status_response_structure(
    mock_get_job, client, auth_headers
):
    """Test that merge status response has correct document structure"""
    # Mock job info with documents array
    mock_get_job.return_value = {
        "job_id": "test-job-id-structure",
        "client_job_id": "merge-test-structure",
        "task_id": "test-task-structure",
        "status": "completed",
        "job_type": JobType.MERGE,
        "created_at": "2025-10-07T10:15:30Z",
        "ended_at": "2025-10-07T10:15:45Z",
        "processing_time": 15.2,
        "meta_data": {"project": "Q4-2025"},
        "download_url": "https://s3.amazonaws.com/bucket/merged/merge-test.pdf",
        "documents": [
            {
                "type": "url",
                "document_url": "https://example.com/cover.pdf",
                "status": "SUCCESS",
                "processing_time": 2.1,
                "meta_data": {},
            },
            {
                "type": "url",
                "document_url": "https://example.com/logo.png",
                "status": "SUCCESS",
                "processing_time": 1.8,
                "meta_data": {},
            },
            {
                "type": "url",
                "document_url": "https://example.com/content.pdf",
                "status": "SUCCESS",
                "processing_time": 3.2,
                "meta_data": {},
            },
        ],
    }

    response = client.get(
        "/api/v1/merge-pdfs/status?job_id=test-job-id-structure",
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json

    # Verify job-level fields
    assert data["job_id"] == "test-job-id-structure"
    assert data["client_job_id"] == "merge-test-structure"
    assert data["task_id"] == "test-task-structure"
    assert data["status"] == "completed"
    assert data["started_at"] == "2025-10-07T10:15:30Z"
    assert data["ended_at"] == "2025-10-07T10:15:45Z"
    assert data["processing_time"] == "15.20"  # 2-decimal format
    assert data["meta_data"] == {"project": "Q4-2025"}
    assert (
        data["download_url"]
        == "https://s3.amazonaws.com/bucket/merged/merge-test.pdf"
    )

    # Verify documents array - merge_pdf.py line 177 includes documents directly
    assert "documents" in data
    assert len(data["documents"]) == 3

    # Check structure of each document
    for doc in data["documents"]:
        assert "type" in doc
        assert "document_url" in doc
        assert "status" in doc
        assert "processing_time" in doc
        # meta_data is included (even if empty)
        assert "meta_data" in doc


# ===== Download Limit Tests =====


@patch("app.api.merge_pdf.merge_pdfs_task")
def test_merge_pdfs_download_count_within_limit(
    mock_merge_task, client, auth_headers
):
    """Test merge PDFs with document count within limit"""
    from app import app as flask_app

    # Set limit to 5
    flask_app.config["MAX_DOWNLOADS_PER_JOB"] = 5

    mock_task = MagicMock()
    mock_task.id = "test-task-limit-ok"
    mock_merge_task.delay.return_value = mock_task

    response = client.post(
        "/api/v1/merge-pdfs",
        headers=auth_headers,
        json={
            "client_job_id": "limit-test-001",
            "document_urls": [
                "https://example.com/doc1.pdf",
                "https://example.com/doc2.pdf",
                "https://example.com/doc3.pdf",
            ],
        },
    )

    assert response.status_code == 200
    assert response.json["status"] == "queued"


@patch("app.api.merge_pdf.merge_pdfs_task")
def test_merge_pdfs_download_count_at_limit(
    mock_merge_task, client, auth_headers
):
    """Test merge PDFs with document count exactly at limit"""
    from app import app as flask_app

    # Set limit to 3
    flask_app.config["MAX_DOWNLOADS_PER_JOB"] = 3

    mock_task = MagicMock()
    mock_task.id = "test-task-limit-exact"
    mock_merge_task.delay.return_value = mock_task

    response = client.post(
        "/api/v1/merge-pdfs",
        headers=auth_headers,
        json={
            "client_job_id": "limit-test-002",
            "document_urls": [
                "https://example.com/doc1.pdf",
                "https://example.com/doc2.pdf",
                "https://example.com/doc3.pdf",
            ],
        },
    )

    assert response.status_code == 200
    assert response.json["status"] == "queued"


def test_merge_pdfs_download_count_exceeds_limit(client, auth_headers):
    """Test merge PDFs with document count exceeding limit"""
    from app import app as flask_app

    # Set limit to 2
    flask_app.config["MAX_DOWNLOADS_PER_JOB"] = 2

    response = client.post(
        "/api/v1/merge-pdfs",
        headers=auth_headers,
        json={
            "client_job_id": "limit-test-003",
            "document_urls": [
                "https://example.com/doc1.pdf",
                "https://example.com/doc2.pdf",
                "https://example.com/doc3.pdf",
            ],
        },
    )

    assert response.status_code == 400
    assert "Too many documents" in response.json["error"]["message"]
    assert "Maximum 2 downloads allowed" in response.json["error"]["message"]
    assert "3 requested" in response.json["error"]["message"]


def test_merge_pdfs_download_count_limit_one(client, auth_headers):
    """Test merge PDFs with limit of 1 document"""
    from app import app as flask_app

    # Set limit to 1
    flask_app.config["MAX_DOWNLOADS_PER_JOB"] = 1

    response = client.post(
        "/api/v1/merge-pdfs",
        headers=auth_headers,
        json={
            "client_job_id": "limit-test-004",
            "document_urls": [
                "https://example.com/doc1.pdf",
                "https://example.com/doc2.pdf",
            ],
        },
    )

    assert response.status_code == 400
    assert "Maximum 1 downloads allowed" in response.json["error"]["message"]
    assert "2 requested" in response.json["error"]["message"]


@patch("app.api.merge_pdf.merge_pdfs_task")
def test_merge_pdfs_download_count_limit_one_success(
    mock_merge_task, client, auth_headers
):
    """Test merge PDFs succeeds with exactly 1 document when limit is 1"""
    from app import app as flask_app

    # Set limit to 1
    flask_app.config["MAX_DOWNLOADS_PER_JOB"] = 1

    mock_task = MagicMock()
    mock_task.id = "test-task-one-doc"
    mock_merge_task.delay.return_value = mock_task

    response = client.post(
        "/api/v1/merge-pdfs",
        headers=auth_headers,
        json={
            "client_job_id": "limit-test-005",
            "document_urls": ["https://example.com/doc1.pdf"],
        },
    )

    assert response.status_code == 200
    assert response.json["status"] == "queued"


def test_merge_pdfs_download_count_validates_before_queueing(
    client, auth_headers
):
    """Test that download count validation happens before job is queued"""
    from app import app as flask_app

    # Set a low limit
    flask_app.config["MAX_DOWNLOADS_PER_JOB"] = 1

    response = client.post(
        "/api/v1/merge-pdfs",
        headers=auth_headers,
        json={
            "client_job_id": "limit-test-006",
            "document_urls": [
                "https://example.com/doc1.pdf",
                "https://example.com/doc2.pdf",
                "https://example.com/doc3.pdf",
                "https://example.com/doc4.pdf",
                "https://example.com/doc5.pdf",
            ],
        },
    )

    # Should fail immediately with 400, not queue the job
    assert response.status_code == 400
    assert "Too many documents" in response.json["error"]["message"]

    # Job should not have been created in database
    # (it returns 400 before log_request is called)
