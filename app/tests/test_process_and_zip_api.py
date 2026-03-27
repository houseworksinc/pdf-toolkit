import pytest
from unittest.mock import patch, MagicMock
import json
from app.constants import JobType


def test_process_and_zip_missing_job_id(client, auth_headers):
    """Test process-and-zip endpoint with missing client_job_id"""
    response = client.post(
        "/api/v1/process-and-zip",
        headers=auth_headers,
        json={
            "documents": [
                {"type": "url", "document_url": "https://example.com/doc.pdf"}
            ]
        },
    )

    assert response.status_code == 400
    assert response.json["error"]["message"] == "client_job_id is required"


def test_process_and_zip_missing_documents(client, auth_headers):
    """Test process-and-zip endpoint with missing documents"""
    response = client.post(
        "/api/v1/process-and-zip",
        headers=auth_headers,
        json={"client_job_id": "test-123"},
    )

    assert response.status_code == 400
    assert (
        response.json["error"]["message"]
        == "documents array is required and must not be empty"
    )


def test_process_and_zip_empty_documents(client, auth_headers):
    """Test process-and-zip endpoint with empty documents array"""
    response = client.post(
        "/api/v1/process-and-zip",
        headers=auth_headers,
        json={"client_job_id": "test-123", "documents": []},
    )

    assert response.status_code == 400
    assert (
        response.json["error"]["message"]
        == "documents array is required and must not be empty"
    )


def test_process_and_zip_missing_document_type(client, auth_headers):
    """Test process-and-zip endpoint with missing document type"""
    response = client.post(
        "/api/v1/process-and-zip",
        headers=auth_headers,
        json={
            "client_job_id": "test-123",
            "documents": [{"document_url": "https://example.com/doc.pdf"}],
        },
    )

    assert response.status_code == 400
    assert (
        response.json["error"]["message"]
        == "Document at index 0: 'type' is required"
    )


def test_process_and_zip_invalid_document_type(client, auth_headers):
    """Test process-and-zip endpoint with invalid document type"""
    response = client.post(
        "/api/v1/process-and-zip",
        headers=auth_headers,
        json={
            "client_job_id": "test-123",
            "documents": [
                {
                    "type": "invalid",
                    "document_url": "https://example.com/doc.pdf",
                }
            ],
        },
    )

    assert response.status_code == 400
    assert (
        response.json["error"]["message"]
        == f"Document at index 0: 'type' must be 'url' or '{JobType.GENERATE}', got 'invalid'"
    )


def test_process_and_zip_url_missing_document_url(client, auth_headers):
    """Test process-and-zip endpoint with type=url but missing document_url"""
    response = client.post(
        "/api/v1/process-and-zip",
        headers=auth_headers,
        json={"client_job_id": "test-123", "documents": [{"type": "url"}]},
    )

    assert response.status_code == 400
    assert (
        response.json["error"]["message"]
        == "Document at index 0: 'document_url' is required for type='url'"
    )


def test_process_and_zip_generate_missing_template_url(client, auth_headers):
    """Test process-and-zip endpoint with type=generate but missing template_url"""
    response = client.post(
        "/api/v1/process-and-zip",
        headers=auth_headers,
        json={
            "client_job_id": "test-123",
            "documents": [{"type": JobType.GENERATE, "data": {}}],
        },
    )

    assert response.status_code == 400
    assert (
        response.json["error"]["message"]
        == "Document at index 0: 'template_url' is required for static mode"
    )


def test_process_and_zip_generate_missing_data(client, auth_headers):
    """Test process-and-zip endpoint with type=generate but missing data"""
    response = client.post(
        "/api/v1/process-and-zip",
        headers=auth_headers,
        json={
            "client_job_id": "test-123",
            "documents": [
                {
                    "type": JobType.GENERATE,
                    "template_url": "https://example.com/template.docx",
                }
            ],
        },
    )

    assert response.status_code == 400
    assert (
        response.json["error"]["message"]
        == "Document at index 0: 'data' is required and must be an object for type='generate'"
    )


def test_process_and_zip_generate_invalid_mode(client, auth_headers):
    """Test process-and-zip endpoint with invalid generation mode"""
    response = client.post(
        "/api/v1/process-and-zip",
        headers=auth_headers,
        json={
            "client_job_id": "test-123",
            "documents": [
                {
                    "type": JobType.GENERATE,
                    "template_url": "https://example.com/template.docx",
                    "data": {
                        "test": "data"
                    },  # Add valid data so mode validation runs
                    "mode": "invalid",
                }
            ],
        },
    )

    assert response.status_code == 400
    assert (
        response.json["error"]["message"]
        == "Document at index 0: 'mode' must be 'static' or 'dynamic'"
    )


@patch("app.api.process_and_zip.process_and_zip_task")
def test_process_and_zip_success_mixed_documents(
    mock_zip_task, client, auth_headers
):
    """Test successful process-and-zip request with mixed document types"""
    mock_task = MagicMock()
    mock_task.id = "test-task-123"
    mock_zip_task.delay.return_value = mock_task

    response = client.post(
        "/api/v1/process-and-zip",
        headers=auth_headers,
        json={
            "client_job_id": "proc-zip-test-001",
            "documents": [
                {
                    "type": "url",
                    "document_url": "https://example.com/cover.pdf",
                    "meta_data": {"label": "Cover Page"},
                },
                {
                    "type": JobType.GENERATE,
                    "mode": "static",
                    "template_url": "https://example.com/invoice.docx",
                    "data": {"invoice_number": "INV-001", "total": 1500.00},
                    "meta_data": {"label": "Invoice"},
                },
                {
                    "type": JobType.GENERATE,
                    "mode": "dynamic",
                    "template_url": "https://example.com/report.docx",
                    "output_filename": "quarterly_report",
                    "data": {"report_title": "Q3 Report"},
                    "meta_data": {"label": "Report"},
                },
            ],
            "output_filename": "complete-package",
            "meta_data": {"project": "Q3-2025"},
        },
    )

    assert response.status_code == 200
    assert response.json["client_job_id"] == "proc-zip-test-001"
    assert response.json["task_id"] == "test-task-123"
    assert response.json["status"] == "queued"
    assert "started_at" in response.json
    assert response.json["meta_data"] == {"project": "Q3-2025"}
    # Documents array should NOT be in initial response
    assert "documents" not in response.json

    # Verify the task was called with correct parameters
    mock_zip_task.delay.assert_called_once()
    call_kwargs = mock_zip_task.delay.call_args[1]
    assert call_kwargs["client_job_id"] == "proc-zip-test-001"
    assert len(call_kwargs["documents"]) == 3
    assert call_kwargs["output_filename"] == "complete-package"
    assert call_kwargs["documents"][0]["type"] == "url"
    assert call_kwargs["documents"][1]["type"] == JobType.GENERATE
    assert call_kwargs["documents"][1]["mode"] == "static"
    assert call_kwargs["documents"][2]["type"] == JobType.GENERATE
    assert call_kwargs["documents"][2]["mode"] == "dynamic"


@patch("app.api.process_and_zip.process_and_zip_task")
def test_process_and_zip_with_webhook(mock_zip_task, client, auth_headers):
    """Test process-and-zip with webhook URL"""
    mock_task = MagicMock()
    mock_task.id = "test-task-456"
    mock_zip_task.delay.return_value = mock_task

    response = client.post(
        "/api/v1/process-and-zip",
        headers=auth_headers,
        json={
            "client_job_id": "proc-zip-test-002",
            "documents": [
                {"type": "url", "document_url": "https://example.com/doc.pdf"}
            ],
            "webhook": "https://webhook.site/test-123",
        },
    )

    assert response.status_code == 200

    # Verify webhook was passed
    call_kwargs = mock_zip_task.delay.call_args[1]
    assert call_kwargs["webhook_url"] == "https://webhook.site/test-123"


@patch("app.api.process_and_zip.process_and_zip_task")
def test_process_and_zip_with_file_upload_url(
    mock_zip_task, client, auth_headers
):
    """Test process-and-zip with custom file upload URL"""
    mock_task = MagicMock()
    mock_task.id = "test-task-789"
    mock_zip_task.delay.return_value = mock_task

    response = client.post(
        "/api/v1/process-and-zip",
        headers=auth_headers,
        json={
            "client_job_id": "proc-zip-test-003",
            "documents": [
                {"type": "url", "document_url": "https://example.com/doc.pdf"}
            ],
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


@patch("app.api.process_and_zip.process_and_zip_task")
def test_process_and_zip_default_output_filename(
    mock_zip_task, client, auth_headers
):
    """Test process-and-zip defaults output_filename to client_job_id"""
    mock_task = MagicMock()
    mock_task.id = "test-task-101"
    mock_zip_task.delay.return_value = mock_task

    response = client.post(
        "/api/v1/process-and-zip",
        headers=auth_headers,
        json={
            "client_job_id": "proc-zip-test-004",
            "documents": [
                {"type": "url", "document_url": "https://example.com/doc.pdf"}
            ],
        },
    )

    assert response.status_code == 200

    # Verify output_filename defaults to client_job_id
    call_kwargs = mock_zip_task.delay.call_args[1]
    assert call_kwargs["output_filename"] == "proc-zip-test-004"


def test_process_and_zip_unauthorized(client):
    """Test process-and-zip endpoint without authentication"""
    response = client.post(
        "/api/v1/process-and-zip",
        json={
            "client_job_id": "test-123",
            "documents": [
                {"type": "url", "document_url": "https://example.com/doc.pdf"}
            ],
        },
    )

    assert response.status_code == 401


def test_get_process_and_zip_status_missing_job_id(client, auth_headers):
    """Test get process-and-zip status without job_id parameter"""
    response = client.get(
        "/api/v1/process-and-zip/status", headers=auth_headers
    )

    assert response.status_code == 400
    assert "job_id" in response.json["error"]["message"]


def test_get_process_and_zip_status_not_found(client, auth_headers):
    """Test get process-and-zip status for non-existent job"""
    response = client.get(
        "/api/v1/process-and-zip/status?job_id=non-existent-job-id",
        headers=auth_headers,
    )

    assert response.status_code == 404


@patch("app.api.process_and_zip.process_and_zip_task")
def test_get_process_and_zip_status_success(
    mock_zip_task, client, auth_headers
):
    """Test get process-and-zip status for existing job"""
    # First create a job
    mock_task = MagicMock()
    mock_task.id = "test-task-202"
    mock_zip_task.delay.return_value = mock_task

    create_response = client.post(
        "/api/v1/process-and-zip",
        headers=auth_headers,
        json={
            "client_job_id": "proc-zip-status-test-001",
            "documents": [
                {"type": "url", "document_url": "https://example.com/doc.pdf"}
            ],
        },
    )

    assert create_response.status_code == 200
    job_id = create_response.json["job_id"]

    # Now get status using job_id
    status_response = client.get(
        f"/api/v1/process-and-zip/status?job_id={job_id}", headers=auth_headers
    )

    assert status_response.status_code == 200
    assert status_response.json["job_id"] == job_id
    assert status_response.json["client_job_id"] == "proc-zip-status-test-001"
    assert status_response.json["task_id"] == "test-task-202"
    assert status_response.json["status"] == "queued"


@patch("app.api.process_and_zip.process_and_zip_task")
def test_get_process_and_zip_status_wrong_job_type(
    mock_zip_task, client, auth_headers
):
    """Test get process-and-zip status for a job that is not a process-and-zip job"""
    from app.database import log_request
    from app import app as flask_app

    # Create a merge job instead of process-and-zip
    with flask_app.app_context():
        documents = [
            {
                "url": "https://example.com/doc.pdf",
                "type": "url",
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

    # Try to get process-and-zip status for merge job using job_id
    response = client.get(
        f"/api/v1/process-and-zip/status?job_id={job_id}", headers=auth_headers
    )

    assert response.status_code == 400
    assert (
        response.json["error"]["message"]
        == f"Job is not a {JobType.PROCESS_AND_ZIP} job"
    )


def test_process_and_zip_unauthorized_status(client):
    """Test get process-and-zip status without authentication"""
    response = client.get(
        "/api/v1/process-and-zip/status?job_id=test-job-id-123"
    )

    assert response.status_code == 401


@patch("app.database.get_document_stats_by_id")
@patch("app.database.get_job_info_by_id")
def test_get_process_and_zip_status_response_structure(
    mock_get_job, mock_get_stats, client, auth_headers
):
    """Test that process-and-zip status response has correct document structure"""
    # Mock job info with documents that have various statuses
    mock_get_job.return_value = {
        "job_id": "test-job-id-structure",
        "client_job_id": "proc-zip-test-structure",
        "task_id": "test-task-structure",
        "status": "running",
        "job_type": JobType.PROCESS_AND_ZIP,
        "created_at": "2025-10-10T10:00:00Z",
        "started_at": "2025-10-10T10:00:00Z",
        "completed_at": None,
        "processing_time": None,
        "meta_data": {"project": "test"},
        "download_url": None,
        "documents": [
            {
                "type": "url",
                "document_url": "https://example.com/doc1.pdf",
                "status": "completed",
                "started_at": "2025-10-10T10:00:01Z",  # This should be filtered out
                "ended_at": "2025-10-10T10:00:03Z",  # This should be filtered out
                "processing_time": 2.1,
                "error": None,
                "meta_data": {"label": "Document 1"},
                "data": {"sensitive": "data"},  # This should be filtered out
                "index": 0,  # This should be filtered out
            },
            {
                "type": "generate",
                "mode": "static",
                "template_url": "https://example.com/template.docx",
                "status": "running",
                "started_at": "2025-10-10T10:00:03Z",  # This should be filtered out
                "ended_at": None,
                "processing_time": None,
                "error": None,
                "meta_data": {"label": "Generated Doc"},
                "data": {"sensitive": "data"},  # This should be filtered out
                "index": 1,  # This should be filtered out
            },
            {
                "type": "url",
                "document_url": "https://example.com/doc3.pdf",
                "status": "failed",
                "started_at": "2025-10-10T10:00:05Z",  # This should be filtered out
                "ended_at": "2025-10-10T10:00:06Z",  # This should be filtered out
                "processing_time": 1.0,
                "error": "Download failed",
                "meta_data": {"label": "Document 3"},
                "data": None,  # This should be filtered out
                "index": 2,  # This should be filtered out
            },
        ],
    }

    # Mock document stats
    mock_get_stats.return_value = {
        "total": 3,
        "completed": 1,
        "failed": 1,
        "pending": 0,
        "processing": 1,
    }

    response = client.get(
        "/api/v1/process-and-zip/status?job_id=test-job-id-structure",
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json

    # Verify job-level fields
    assert data["job_id"] == "test-job-id-structure"
    assert data["client_job_id"] == "proc-zip-test-structure"
    assert data["task_id"] == "test-task-structure"
    assert data["status"] == "running"
    assert data["started_at"] == "2025-10-10T10:00:00Z"
    assert data["ended_at"] is None
    assert data["processing_time"] is None
    assert data["meta_data"] == {"project": "test"}
    assert data["download_url"] is None
    assert "progress" in data
    # New fields added in webhook fixes
    assert data["documents_completed"] == 1
    assert data["documents_failed"] == 1

    # Verify documents array structure
    assert "documents" in data
    assert len(data["documents"]) == 3

    # Document 1: completed status
    doc1 = data["documents"][0]
    assert doc1["type"] == "url"
    assert doc1["status"] == "completed"
    assert doc1["processing_time"] == 2.1
    assert doc1["meta_data"] == {"label": "Document 1"}
    # These fields should NOT be present (filtered out per process_and_zip.py:311-323)
    assert "started_at" not in doc1
    assert "ended_at" not in doc1
    assert "document_url" not in doc1
    assert "data" not in doc1
    assert "index" not in doc1
    assert "template_url" not in doc1
    # error field should not be present when None
    assert "error" not in doc1

    # Document 2: running status
    doc2 = data["documents"][1]
    assert doc2["type"] == "generate"
    assert doc2["status"] == "running"
    assert "processing_time" not in doc2  # None values are filtered out
    assert doc2["meta_data"] == {"label": "Generated Doc"}
    # These fields should NOT be present
    assert "started_at" not in doc2
    assert "ended_at" not in doc2
    assert "mode" not in doc2
    assert "template_url" not in doc2
    assert "data" not in doc2
    assert "index" not in doc2
    assert "error" not in doc2  # None values are filtered out

    # Document 3: failed status with error
    doc3 = data["documents"][2]
    assert doc3["type"] == "url"
    assert doc3["status"] == "failed"
    assert doc3["processing_time"] == 1.0
    assert doc3["error"] == "Download failed"
    assert doc3["meta_data"] == {"label": "Document 3"}
    # These fields should NOT be present
    assert "started_at" not in doc3
    assert "ended_at" not in doc3
    assert "document_url" not in doc3
    assert "data" not in doc3
    assert "index" not in doc3
