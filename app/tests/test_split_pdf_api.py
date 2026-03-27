import pytest
from unittest.mock import patch, MagicMock


def test_split_pdf_requires_auth(client):
    """Test that split PDF endpoint requires authentication"""
    response = client.post("/api/v1/split-pdf", json={})
    assert response.status_code == 401


def test_split_pdf_missing_job_id(test_user_headers, client):
    """Test split PDF with missing client_job_id"""
    response = client.post(
        "/api/v1/split-pdf",
        headers=test_user_headers,
        json={"document_url": "https://example.com/doc.pdf", "splits": []},
    )

    assert response.status_code == 400
    data = response.json
    assert "client_job_id" in data["error"]["message"]


def test_split_pdf_missing_document_url(test_user_headers, client):
    """Test split PDF with missing document_url"""
    response = client.post(
        "/api/v1/split-pdf",
        headers=test_user_headers,
        json={"client_job_id": "test-123", "splits": []},
    )

    assert response.status_code == 400
    data = response.json
    assert "document_url" in data["error"]["message"]


def test_split_pdf_empty_splits(test_user_headers, client):
    """Test split PDF with empty splits array"""
    response = client.post(
        "/api/v1/split-pdf",
        headers=test_user_headers,
        json={
            "client_job_id": "test-123",
            "document_url": "https://example.com/doc.pdf",
            "splits": [],
        },
    )

    assert response.status_code == 400
    data = response.json
    assert "splits" in data["error"]["message"]


def test_split_pdf_missing_output_filename(test_user_headers, client):
    """Test split PDF with split missing output_filename"""
    response = client.post(
        "/api/v1/split-pdf",
        headers=test_user_headers,
        json={
            "client_job_id": "test-123",
            "document_url": "https://example.com/doc.pdf",
            "splits": [{"pages": [1, 2, 3]}],
        },
    )

    assert response.status_code == 400
    data = response.json
    assert "output_filename" in data["error"]["message"]


def test_split_pdf_missing_pages_and_labels(test_user_headers, client):
    """Test split PDF with split missing both pages and labels"""
    response = client.post(
        "/api/v1/split-pdf",
        headers=test_user_headers,
        json={
            "client_job_id": "test-123",
            "document_url": "https://example.com/doc.pdf",
            "splits": [{"output_filename": "test-file"}],
        },
    )

    assert response.status_code == 400
    data = response.json
    assert (
        "pages" in data["error"]["message"]
        or "labels" in data["error"]["message"]
    )


def test_split_pdf_both_pages_and_labels(test_user_headers, client):
    """Test split PDF with split having both pages and labels"""
    response = client.post(
        "/api/v1/split-pdf",
        headers=test_user_headers,
        json={
            "client_job_id": "test-123",
            "document_url": "https://example.com/doc.pdf",
            "splits": [
                {
                    "output_filename": "test-file",
                    "pages": [1, 2, 3],
                    "labels": ["i", "ii", "iii"],
                }
            ],
        },
    )

    assert response.status_code == 400
    data = response.json
    assert "cannot have both" in data["error"]["message"]


def test_split_pdf_valid_request_with_pages(test_user_headers, client):
    """Test split PDF with valid request using pages"""
    with patch("app.api.split_pdf.split_pdf_task") as mock_task:
        mock_task.delay.return_value = MagicMock(id="task-123")

        response = client.post(
            "/api/v1/split-pdf",
            headers=test_user_headers,
            json={
                "client_job_id": "test-123",
                "document_url": "https://example.com/doc.pdf",
                "splits": [{"output_filename": "file-1", "pages": [1, 2, 3]}],
            },
        )

        assert response.status_code == 200
        data = response.json
        assert data["client_job_id"] == "test-123"
        assert data["task_id"] == "task-123"
        assert data["status"] == "queued"
        assert "started_at" in data
        assert mock_task.delay.called


def test_split_pdf_valid_request_with_labels(test_user_headers, client):
    """Test split PDF with valid request using labels"""
    with patch("app.api.split_pdf.split_pdf_task") as mock_task:
        mock_task.delay.return_value = MagicMock(id="task-456")

        response = client.post(
            "/api/v1/split-pdf",
            headers=test_user_headers,
            json={
                "client_job_id": "test-456",
                "document_url": "https://example.com/doc.pdf",
                "splits": [
                    {"output_filename": "file-2", "labels": ["i", "ii", "iii"]}
                ],
            },
        )

        assert response.status_code == 200
        data = response.json
        assert data["client_job_id"] == "test-456"
        assert data["task_id"] == "task-456"


def test_split_pdf_with_webhook_and_metadata(test_user_headers, client):
    """Test split PDF with webhook URL and metadata"""
    with patch("app.api.split_pdf.split_pdf_task") as mock_task:
        mock_task.delay.return_value = MagicMock(id="task-789")

        response = client.post(
            "/api/v1/split-pdf",
            headers=test_user_headers,
            json={
                "client_job_id": "test-789",
                "document_url": "https://example.com/doc.pdf",
                "webhook": "https://example.com/webhook",
                "meta_data": {"client": "test"},
                "splits": [
                    {
                        "output_filename": "file-3",
                        "pages": [1],
                        "file_upload_url": "https://s3.amazonaws.com/presigned-url",
                        "meta_data": {"section": "intro"},
                    }
                ],
            },
        )

        assert response.status_code == 200
        data = response.json
        assert data["meta_data"] == {"client": "test"}

        # Verify task was called with correct parameters
        call_args = mock_task.delay.call_args
        assert call_args[1]["webhook_url"] == "https://example.com/webhook"
        assert call_args[1]["meta_data"] == {"client": "test"}


def test_get_split_pdf_status_requires_auth(client):
    """Test that status endpoint requires authentication"""
    response = client.get("/api/v1/split-pdf/status?job_id=test-job-id-123")
    assert response.status_code == 401


def test_get_split_pdf_status_missing_job_id(test_user_headers, client):
    """Test status endpoint with missing job_id"""
    response = client.get("/api/v1/split-pdf/status", headers=test_user_headers)

    assert response.status_code == 400
    data = response.json
    assert "job_id" in data["error"]["message"]


def test_get_split_pdf_status_job_not_found(test_user_headers, client):
    """Test status endpoint with non-existent job"""
    response = client.get(
        "/api/v1/split-pdf/status?job_id=nonexistent", headers=test_user_headers
    )

    assert response.status_code == 404
    data = response.json
    assert "not found" in data["error"]["message"]


def test_get_split_pdf_status_success(test_user_headers, client):
    """Test getting status of a completed split job"""
    # First create a split job
    with patch("app.api.split_pdf.split_pdf_task") as mock_task:
        mock_task.delay.return_value = MagicMock(id="task-status-test")

        create_response = client.post(
            "/api/v1/split-pdf",
            headers=test_user_headers,
            json={
                "client_job_id": "status-test-123",
                "document_url": "https://example.com/doc.pdf",
                "splits": [{"output_filename": "file-status", "pages": [1, 2]}],
            },
        )

        assert create_response.status_code == 200
        # Extract job_id from creation response for status check
        job_id = create_response.json["job_id"]

    # Now get status using job_id
    status_response = client.get(
        f"/api/v1/split-pdf/status?job_id={job_id}", headers=test_user_headers
    )

    assert status_response.status_code == 200
    data = status_response.json
    assert data["job_id"] == job_id
    assert data["client_job_id"] == "status-test-123"
    assert "status" in data
    assert "splits" in data
    assert isinstance(data["splits"], list)


def test_split_pdf_multiple_splits(test_user_headers, client):
    """Test split PDF with multiple splits"""
    with patch("app.api.split_pdf.split_pdf_task") as mock_task:
        mock_task.delay.return_value = MagicMock(id="task-multi")

        response = client.post(
            "/api/v1/split-pdf",
            headers=test_user_headers,
            json={
                "client_job_id": "multi-split-123",
                "document_url": "https://example.com/doc.pdf",
                "splits": [
                    {"output_filename": "intro", "pages": [1, 2, 3]},
                    {"output_filename": "chapter1", "labels": ["1", "2", "3"]},
                    {"output_filename": "appendix", "pages": [50, 51, 52]},
                ],
            },
        )

        assert response.status_code == 200
        data = response.json
        assert data["client_job_id"] == "multi-split-123"

        # Verify all splits were passed to the task
        call_args = mock_task.delay.call_args
        assert len(call_args[1]["splits"]) == 3
