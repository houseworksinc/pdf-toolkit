from unittest.mock import patch


def test_pdf_generation(client, auth_headers):
    """Test PDF generation with JWT authentication"""
    with patch("app.api.pdf_generation.generate_pdf_task") as mock_task, patch(
        "app.api.pdf_generation.log_request"
    ) as mock_log:
        # Configure mocks
        mock_task.delay.return_value.id = "mock_task_id"

        # Configure mock_log to return a job object with an id
        from unittest.mock import MagicMock

        mock_job = MagicMock()
        mock_job.id = "test-job-uuid-api"
        mock_log.return_value = mock_job

        payload = {
            "client_job_id": "test123",
            "template_url": "https://example.com/sample_template.docx",
            "data": {"name": "John Doe", "address": "123 Main St"},
        }
        response = client.post(
            "/api/v1/generate-pdf", json=payload, headers=auth_headers
        )

        assert response.status_code == 202
        assert response.headers["Content-Type"] == "application/json"
        assert response.json["status"] == "queued"
        assert response.json["client_job_id"] == "test123"
        assert response.json["job_id"] == "test-job-uuid-api"

        # Verify task was called with keyword arguments
        call_kwargs = mock_task.delay.call_args[1]
        assert call_kwargs["job_id"] == "test-job-uuid-api"
        assert call_kwargs["client_job_id"] == "test123"
        assert (
            call_kwargs["template_url"]
            == "https://example.com/sample_template.docx"
        )
        assert call_kwargs["json_data"] == {
            "name": "John Doe",
            "address": "123 Main St",
        }
        assert call_kwargs["output_filename"] is None
        assert "user_id" in call_kwargs  # user_id is added by the endpoint


def test_pdf_generation_no_auth(client):
    """Test PDF generation without authentication fails"""
    payload = {
        "client_job_id": "test123",
        "template_url": "https://example.com/sample_template.docx",
        "data": {"name": "John Doe", "address": "123 Main St"},
    }
    response = client.post("/api/v1/generate-pdf", json=payload)

    assert response.status_code == 401
    assert "Token is missing" in response.json["error"]


def test_pdf_generation_invalid_token(client):
    """Test PDF generation with invalid token fails"""
    headers = {
        "Authorization": "Bearer invalid.token.here",
        "Content-Type": "application/json",
    }

    payload = {
        "client_job_id": "test123",
        "template_url": "https://example.com/sample_template.docx",
        "data": {"name": "John Doe", "address": "123 Main St"},
    }
    response = client.post(
        "/api/v1/generate-pdf", json=payload, headers=headers
    )

    assert response.status_code == 401
    assert "Token is invalid or expired" in response.json["error"]
