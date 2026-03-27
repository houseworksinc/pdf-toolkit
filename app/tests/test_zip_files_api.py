import pytest
from unittest.mock import patch, MagicMock
import json
from app.constants import JobType


def test_create_zip_missing_job_id(client, auth_headers):
    """Test create ZIP endpoint with missing client_job_id"""
    response = client.post(
        "/api/v1/create-zip",
        headers=auth_headers,
        json={"document_urls": ["https://example.com/file1.pdf"]},
    )

    assert response.status_code == 400
    assert "client_job_id is required" in response.json["error"]["message"]


def test_create_zip_missing_document_urls(client, auth_headers):
    """Test create ZIP endpoint with missing document_urls"""
    response = client.post(
        "/api/v1/create-zip",
        headers=auth_headers,
        json={"client_job_id": "test-123"},
    )

    assert response.status_code == 400
    assert "document_urls" in response.json["error"]["message"]


def test_create_zip_empty_document_urls(client, auth_headers):
    """Test create ZIP endpoint with empty document_urls array"""
    response = client.post(
        "/api/v1/create-zip",
        headers=auth_headers,
        json={"client_job_id": "test-123", "document_urls": []},
    )

    assert response.status_code == 400
    assert "document_urls" in response.json["error"]["message"]


def test_create_zip_invalid_url_format(client, auth_headers):
    """Test create ZIP endpoint with invalid URL format"""
    response = client.post(
        "/api/v1/create-zip",
        headers=auth_headers,
        json={
            "client_job_id": "test-123",
            "document_urls": [
                "not-a-valid-url",
                "https://example.com/file.pdf",
            ],
        },
    )

    assert response.status_code == 400
    assert "must start with http" in response.json["error"]["message"]


def test_create_zip_invalid_url_type(client, auth_headers):
    """Test create ZIP endpoint with non-string URL"""
    response = client.post(
        "/api/v1/create-zip",
        headers=auth_headers,
        json={
            "client_job_id": "test-123",
            "document_urls": [123, "https://example.com/file.pdf"],
        },
    )

    assert response.status_code == 400
    assert "Invalid URL" in response.json["error"]["message"]


@patch("app.api.zip_files.create_zip_task")
def test_create_zip_success(mock_zip_task, client, auth_headers):
    """Test successful ZIP creation request"""
    # Mock the Celery task
    mock_task = MagicMock()
    mock_task.id = "test-task-123"
    mock_zip_task.delay.return_value = mock_task

    response = client.post(
        "/api/v1/create-zip",
        headers=auth_headers,
        json={
            "client_job_id": "zip-test-001",
            "document_urls": [
                "https://example.com/doc1.pdf",
                "https://example.com/image.png",
                "https://example.com/doc2.docx",
                "https://example.com/data.xlsx",
            ],
        },
    )

    assert response.status_code == 200
    assert response.json["client_job_id"] == "zip-test-001"
    assert response.json["task_id"] == "test-task-123"
    assert response.json["status"] == "queued"
    assert "started_at" in response.json

    # Verify the task was called with correct parameters
    mock_zip_task.delay.assert_called_once()
    call_kwargs = mock_zip_task.delay.call_args[1]
    assert call_kwargs["client_job_id"] == "zip-test-001"
    assert len(call_kwargs["document_urls"]) == 4
    assert (
        call_kwargs["output_filename"] == "zip-test-001"
    )  # Default to client_job_id


@patch("app.api.zip_files.create_zip_task")
def test_create_zip_with_custom_filename(mock_zip_task, client, auth_headers):
    """Test ZIP creation with custom output filename"""
    mock_task = MagicMock()
    mock_task.id = "test-task-456"
    mock_zip_task.delay.return_value = mock_task

    response = client.post(
        "/api/v1/create-zip",
        headers=auth_headers,
        json={
            "client_job_id": "zip-test-002",
            "document_urls": [
                "https://example.com/file1.pdf",
                "https://example.com/file2.txt",
            ],
            "output_filename": "my-custom-archive",
        },
    )

    assert response.status_code == 200

    # Verify custom filename was passed
    call_kwargs = mock_zip_task.delay.call_args[1]
    assert call_kwargs["output_filename"] == "my-custom-archive"


@patch("app.api.zip_files.create_zip_task")
def test_create_zip_with_webhook(mock_zip_task, client, auth_headers):
    """Test ZIP creation with webhook URL"""
    mock_task = MagicMock()
    mock_task.id = "test-task-789"
    mock_zip_task.delay.return_value = mock_task

    response = client.post(
        "/api/v1/create-zip",
        headers=auth_headers,
        json={
            "client_job_id": "zip-test-003",
            "document_urls": ["https://example.com/file1.pdf"],
            "webhook": "https://webhook.site/test-123",
        },
    )

    assert response.status_code == 200

    # Verify webhook was passed
    call_kwargs = mock_zip_task.delay.call_args[1]
    assert call_kwargs["webhook_url"] == "https://webhook.site/test-123"


@patch("app.api.zip_files.create_zip_task")
def test_create_zip_with_file_upload_url(mock_zip_task, client, auth_headers):
    """Test ZIP creation with custom file upload URL"""
    mock_task = MagicMock()
    mock_task.id = "test-task-101"
    mock_zip_task.delay.return_value = mock_task

    response = client.post(
        "/api/v1/create-zip",
        headers=auth_headers,
        json={
            "client_job_id": "zip-test-004",
            "document_urls": ["https://example.com/file1.pdf"],
            "file_upload_url": "https://s3.amazonaws.com/presigned-url",
        },
    )

    assert response.status_code == 200

    # Verify file_upload_url was passed
    call_kwargs = mock_zip_task.delay.call_args[1]
    assert (
        call_kwargs["file_upload_url"]
        == "https://s3.amazonaws.com/presigned-url"
    )


@patch("app.api.zip_files.create_zip_task")
def test_create_zip_with_metadata(mock_zip_task, client, auth_headers):
    """Test ZIP creation with custom metadata"""
    mock_task = MagicMock()
    mock_task.id = "test-task-202"
    mock_zip_task.delay.return_value = mock_task

    metadata = {
        "project": "test-project",
        "user": "john-doe",
        "category": "documents",
    }

    response = client.post(
        "/api/v1/create-zip",
        headers=auth_headers,
        json={
            "client_job_id": "zip-test-005",
            "document_urls": ["https://example.com/file1.pdf"],
            "meta_data": metadata,
        },
    )

    assert response.status_code == 200
    assert response.json["meta_data"] == metadata

    # Verify metadata was passed
    call_kwargs = mock_zip_task.delay.call_args[1]
    assert call_kwargs["meta_data"] == metadata


@patch("app.api.zip_files.create_zip_task")
def test_create_zip_with_mixed_file_types(mock_zip_task, client, auth_headers):
    """Test ZIP creation with various file types (any type should work)"""
    mock_task = MagicMock()
    mock_task.id = "test-task-303"
    mock_zip_task.delay.return_value = mock_task

    response = client.post(
        "/api/v1/create-zip",
        headers=auth_headers,
        json={
            "client_job_id": "zip-test-006",
            "document_urls": [
                "https://example.com/document.pdf",
                "https://example.com/image.jpg",
                "https://example.com/spreadsheet.xlsx",
                "https://example.com/presentation.pptx",
                "https://example.com/video.mp4",
                "https://example.com/audio.mp3",
                "https://example.com/data.json",
                "https://example.com/code.py",
            ],
        },
    )

    assert response.status_code == 200
    # ZIP should accept any file type
    call_kwargs = mock_zip_task.delay.call_args[1]
    assert len(call_kwargs["document_urls"]) == 8


def test_create_zip_unauthorized(client):
    """Test create ZIP endpoint without authentication"""
    response = client.post(
        "/api/v1/create-zip",
        json={
            "client_job_id": "test-123",
            "document_urls": ["https://example.com/file1.pdf"],
        },
    )

    assert response.status_code == 401


def test_get_zip_status_missing_job_id(client, auth_headers):
    """Test get ZIP status without job_id parameter"""
    response = client.get("/api/v1/create-zip/status", headers=auth_headers)

    assert response.status_code == 400
    assert "job_id" in response.json["error"]["message"]


def test_get_zip_status_not_found(client, auth_headers):
    """Test get ZIP status for non-existent job"""
    response = client.get(
        "/api/v1/create-zip/status?job_id=non-existent-job-id",
        headers=auth_headers,
    )

    assert response.status_code == 404


@patch("app.api.zip_files.create_zip_task")
def test_get_zip_status_success(mock_zip_task, client, auth_headers):
    """Test get ZIP status for existing job"""
    # First create a job
    mock_task = MagicMock()
    mock_task.id = "test-task-404"
    mock_zip_task.delay.return_value = mock_task

    create_response = client.post(
        "/api/v1/create-zip",
        headers=auth_headers,
        json={
            "client_job_id": "zip-status-test-001",
            "document_urls": ["https://example.com/file1.pdf"],
        },
    )

    assert create_response.status_code == 200
    job_id = create_response.json["job_id"]

    # Now get status using job_id
    status_response = client.get(
        f"/api/v1/create-zip/status?job_id={job_id}", headers=auth_headers
    )

    assert status_response.status_code == 200
    assert status_response.json["job_id"] == job_id
    assert status_response.json["client_job_id"] == "zip-status-test-001"
    assert status_response.json["task_id"] == "test-task-404"
    assert status_response.json["status"] == "queued"


@patch("app.api.zip_files.create_zip_task")
def test_get_zip_status_wrong_job_type(mock_zip_task, client, auth_headers):
    """Test get ZIP status for a job that is not a ZIP job"""
    from app.database import log_request
    from app import app as flask_app

    # Create a merge job instead of ZIP using new schema
    with flask_app.app_context():
        documents = [
            {
                "url": "https://example.com/doc.pdf",
                "type": JobType.MERGE,
                "status": "PENDING",
            }
        ]

        job = log_request(
            client_job_id="merge-job-001",
            job_type=JobType.MERGE,
            documents=documents,
            task_id="task-999",
        )
        job_id = job.id

    # Try to get ZIP status for merge job using job_id
    response = client.get(
        f"/api/v1/create-zip/status?job_id={job_id}", headers=auth_headers
    )

    assert response.status_code == 400
    assert "not a ZIP creation job" in response.json["error"]["message"]


def test_create_zip_unauthorized_status(client):
    """Test get ZIP status without authentication"""
    response = client.get("/api/v1/create-zip/status?job_id=test-job-id-123")

    assert response.status_code == 401


@patch("app.api.zip_files.get_job_info_by_id")
def test_get_zip_status_response_structure(mock_get_job, client, auth_headers):
    """Test that ZIP status response has correct document structure"""
    # Mock job info with documents array
    mock_get_job.return_value = {
        "job_id": "test-job-id-structure",
        "client_job_id": "zip-test-structure",
        "task_id": "test-task-structure",
        "status": "completed",
        "job_type": JobType.ZIP,
        "created_at": "2025-10-07T10:15:30Z",
        "ended_at": "2025-10-07T10:15:42Z",
        "processing_time": 12.3,
        "meta_data": {"project": "Q4-2025", "department": "Engineering"},
        "download_url": "https://s3.amazonaws.com/bucket/zips/zip-test.zip",
        "documents": [
            {
                "type": "url",
                "document_url": "https://example.com/report.pdf",
                "status": "SUCCESS",
                "processing_time": 2.1,
                "meta_data": {},
            },
            {
                "type": "url",
                "document_url": "https://example.com/data.xlsx",
                "status": "SUCCESS",
                "processing_time": 1.5,
                "meta_data": {},
            },
            {
                "type": "url",
                "document_url": "https://example.com/presentation.pptx",
                "status": "SUCCESS",
                "processing_time": 3.2,
                "meta_data": {},
            },
        ],
    }

    response = client.get(
        "/api/v1/create-zip/status?job_id=test-job-id-structure",
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json

    # Verify job-level fields
    assert data["job_id"] == "test-job-id-structure"
    assert data["client_job_id"] == "zip-test-structure"
    assert data["task_id"] == "test-task-structure"
    assert data["status"] == "completed"
    assert data["started_at"] == "2025-10-07T10:15:30Z"
    assert data["ended_at"] == "2025-10-07T10:15:42Z"
    assert data["processing_time"] == "12.30"  # 2-decimal format
    assert data["meta_data"] == {
        "project": "Q4-2025",
        "department": "Engineering",
    }
    assert (
        data["download_url"]
        == "https://s3.amazonaws.com/bucket/zips/zip-test.zip"
    )

    # Verify documents array structure
    assert "documents" in data
    assert len(data["documents"]) == 3

    # Check structure of each document
    for doc in data["documents"]:
        assert "type" in doc
        assert "document_url" in doc
        assert "status" in doc
        assert "processing_time" in doc
        assert "meta_data" in doc
