from unittest.mock import patch, MagicMock
from app.main import app


def test_hello_world(client):
    response = client.get("/")  # Use the test client to make a GET request
    assert response.status_code == 200  # Check the response status
    assert response.json == {
        "message": "Hello, World!"
    }  # Check the response data


def test_generate_pdf_route_missing_params(client, auth_headers):
    response = client.post(
        "/api/v1/generate-pdf", json={}, headers=auth_headers
    )
    assert response.status_code == 400
    assert response.json == {
        "error": "Missing required parameters: client_job_id, template_url, and data are required for static mode"
    }


# Test the root endpoint (no auth required)
def test_hello_world_no_auth_required(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json == {"message": "Hello, World!"}


# Test PDF generation missing parameters
def test_generate_pdf_missing_params(client, auth_headers):
    response = client.post(
        "/api/v1/generate-pdf", headers=auth_headers, json={}
    )
    assert response.status_code == 400
    assert response.json == {
        "error": "Missing required parameters: client_job_id, template_url, and data are required for static mode"
    }


# Test PDF generation missing partial parameters
def test_generate_pdf_partial_params(client, auth_headers):
    response = client.post(
        "/api/v1/generate-pdf",
        headers=auth_headers,
        json={"client_job_id": "test123"},
    )
    assert response.status_code == 400
    assert response.json == {
        "error": "Missing required parameters: client_job_id, template_url, and data are required for static mode"
    }


# Test PDF generation with all parameters
@patch("app.api.pdf_generation.generate_pdf_task")
@patch("app.api.pdf_generation.log_request")
def test_generate_pdf_valid_params(
    mock_log_request, mock_generate_pdf_task, client, auth_headers
):
    # Configure the mock to return a task with an ID
    mock_task = MagicMock()
    mock_task.id = "mock_task_id"
    mock_generate_pdf_task.delay.return_value = mock_task

    # Configure mock_log_request to return a job object with an id
    mock_job = MagicMock()
    mock_job.id = "test-job-uuid-123"
    mock_log_request.return_value = mock_job

    # Test data
    job_data = {
        "client_job_id": "test123",
        "template_url": "https://example.com/template.docx",
        "data": {"name": "Test User"},
    }

    # Make the request
    response = client.post(
        "/api/v1/generate-pdf", headers=auth_headers, json=job_data
    )

    # Verify response
    assert response.status_code == 202
    assert response.json["status"] == "queued"
    assert response.json["client_job_id"] == "test123"
    assert response.json["job_id"] == "test-job-uuid-123"

    # Get the actual task_id from the response instead of comparing it to mock_task_id
    assert "task_id" in response.json
    task_id = response.json["task_id"]

    # Verify the task was called with keyword arguments
    call_kwargs = mock_generate_pdf_task.delay.call_args[1]
    assert call_kwargs["job_id"] == "test-job-uuid-123"
    assert call_kwargs["client_job_id"] == "test123"
    assert call_kwargs["template_url"] == "https://example.com/template.docx"
    assert call_kwargs["json_data"] == {"name": "Test User"}
    assert call_kwargs["output_filename"] is None
    assert "user_id" in call_kwargs  # user_id is added by the endpoint

    # Verify logging was called correctly
    # Extract the actual call to check the documents array structure
    call_args = mock_log_request.call_args
    assert call_args[1]["client_job_id"] == "test123"
    assert call_args[1]["job_type"] == "generate"
    assert "documents" in call_args[1]
    assert len(call_args[1]["documents"]) == 1
    # Documents array should NOT contain template_url or data (stored in S3 instead)
    assert "template_url" not in call_args[1]["documents"][0]
    assert "data" not in call_args[1]["documents"][0]
    # But should contain processing metadata
    assert call_args[1]["documents"][0]["type"] == "generate"
    assert call_args[1]["documents"][0]["mode"] == "static"
    assert call_args[1]["documents"][0]["status"] == "queued"
    # request_data is replaced with request_audit_s3_key (will be None initially, then updated)
    assert "request_audit_s3_key" in call_args[1]
    # task_id is None during initial log_request, then updated via update_job_task_id_by_id
    assert call_args[1]["task_id"] is None


# Test PDF status endpoint - pending status
@patch("app.database.get_job_info_by_id")
@patch("app.api.pdf_generation.generate_pdf_task.AsyncResult")
def test_pdf_status_pending(
    mock_async_result, mock_get_job_info_by_id, client, auth_headers
):
    # Configure the mocks
    mock_get_job_info_by_id.return_value = {
        "job_id": "test-job-id-123",
        "client_job_id": "test123",
        "task_id": "test_task_id",
        "status": "PENDING",
    }

    mock_task = MagicMock()
    mock_task.state = "PENDING"
    mock_task.status = "PENDING"
    mock_async_result.return_value = mock_task

    # Make the request
    response = client.get(
        "/api/v1/generate-pdf/status?job_id=test-job-id-123",
        headers=auth_headers,
    )

    # Verify response
    assert response.status_code == 200
    assert response.json["status"] == "PENDING"
    assert response.json["job_id"] == "test-job-id-123"
    assert response.json["client_job_id"] == "test123"
    assert response.json["task_id"] == "test_task_id"


# Test PDF status endpoint - success status
@patch("celery.result.AsyncResult")
@patch("app.database.get_job_info_by_id")
def test_pdf_status_success(
    mock_get_job_info_by_id, mock_async_result, client, auth_headers
):
    # Configure the mocks
    mock_get_job_info_by_id.return_value = {
        "job_id": "test-job-id-456",
        "client_job_id": "test123",
        "task_id": "test_task_id",
        "status": "SUCCESS",
        "documents": [
            {
                "type": "generate",
                "status": "completed",
                "s3_key": "pdfs/test123.pdf",
                "download_url": "https://example.com/download/test123.pdf",
            }
        ],
    }

    mock_task = MagicMock()
    mock_task.state = "SUCCESS"
    mock_task.status = "SUCCESS"
    mock_task.info = {
        "client_job_id": "test123",
        "s3_key": "pdfs/test123.pdf",
        "download_url": "https://example.com/download/test123.pdf",
    }
    mock_async_result.return_value = mock_task

    # Make the request
    response = client.get(
        "/api/v1/generate-pdf/status?job_id=test-job-id-456",
        headers=auth_headers,
    )

    # Verify response
    assert response.status_code == 200
    assert response.json["status"] == "SUCCESS"
    assert response.json["job_id"] == "test-job-id-456"
    assert response.json["client_job_id"] == "test123"
    assert response.json["task_id"] == "test_task_id"
    assert (
        response.json["download_url"]
        == "https://example.com/download/test123.pdf"
    )


# Test PDF status endpoint - failure status
@patch("celery.result.AsyncResult")
@patch("app.database.get_job_info_by_id")
def test_pdf_status_failure(
    mock_get_job_info_by_id, mock_async_result, client, auth_headers
):
    # Configure the mocks
    mock_get_job_info_by_id.return_value = {
        "job_id": "test-job-id-789",
        "client_job_id": "test123",
        "task_id": "test_task_id",
        "status": "FAILURE",
        "documents": [],
    }

    mock_task = MagicMock()
    mock_task.state = "FAILURE"
    mock_task.status = "FAILURE"
    mock_task.info = {"error": "Something went wrong"}
    mock_async_result.return_value = mock_task

    # Make the request
    response = client.get(
        "/api/v1/generate-pdf/status?job_id=test-job-id-789",
        headers=auth_headers,
    )

    # Verify response
    assert response.status_code == 200
    assert response.json["status"] == "FAILURE"
    assert response.json["job_id"] == "test-job-id-789"
    assert response.json["client_job_id"] == "test123"
    assert response.json["task_id"] == "test_task_id"
    assert response.json["error"] == "Something went wrong"


# Test PDF status endpoint - missing job_id parameter
def test_pdf_status_missing_job_id(client, auth_headers):
    # Make the request without job_id parameter
    response = client.get("/api/v1/generate-pdf/status", headers=auth_headers)

    # Verify response
    assert response.status_code == 400
    assert response.json["error"] == "job_id query parameter is required"


# Test PDF status endpoint - job not found
@patch("app.database.get_job_info_by_id")
def test_pdf_status_job_not_found(
    mock_get_job_info_by_id, client, auth_headers
):
    # Configure the mock to return None (job not found)
    mock_get_job_info_by_id.return_value = None

    # Make the request
    response = client.get(
        "/api/v1/generate-pdf/status?job_id=nonexistent", headers=auth_headers
    )

    # Verify response
    assert response.status_code == 404
    assert response.json["error"] == "Job not found"


# Test PDF status endpoint - task_id not found for job
@patch("app.database.get_job_info_by_id")
def test_pdf_status_task_id_not_found(
    mock_get_job_info_by_id, client, auth_headers
):
    # Configure the mock to return a job without task_id
    mock_get_job_info_by_id.return_value = {
        "job_id": "test-job-id-no-task",
        "client_job_id": "test123",
        "task_id": None,
        "status": "PENDING",
    }

    # Make the request
    response = client.get(
        "/api/v1/generate-pdf/status?job_id=test-job-id-no-task",
        headers=auth_headers,
    )

    # Verify response
    assert response.status_code == 404
    assert response.json["error"] == "Task ID not found for this job"


# Dynamic PDF API Tests


# Test dynamic PDF generation missing parameters
def test_generate_pdf_dynamic_missing_params(client, auth_headers):
    response = client.post(
        "/api/v1/generate-pdf/dynamic", headers=auth_headers, json={}
    )
    assert response.status_code == 400
    assert response.json == {
        "error": "Missing required parameters: client_job_id and data are required"
    }


# Test dynamic PDF generation partial parameters
def test_generate_pdf_dynamic_partial_params(client, auth_headers):
    response = client.post(
        "/api/v1/generate-pdf/dynamic",
        headers=auth_headers,
        json={
            "client_job_id": "dynamic_test123",
            "template_url": "https://example.com/template.docx",
        },
    )
    assert response.status_code == 400
    assert response.json == {
        "error": "Missing required parameters: client_job_id and data are required"
    }


# Test dynamic PDF generation with valid parameters
@patch("app.api.pdf_generation.generate_pdf_dynamic_task")
@patch("app.api.pdf_generation.log_request")
def test_generate_pdf_dynamic_valid_params(
    mock_log_request, mock_generate_pdf_dynamic_task, client, auth_headers
):
    # Configure the mock to return a task with an ID
    mock_task = MagicMock()
    mock_task.id = "mock_dynamic_task_id"
    mock_generate_pdf_dynamic_task.delay.return_value = mock_task

    # Configure mock_log_request to return a job object with an id
    mock_job = MagicMock()
    mock_job.id = "test-job-uuid-dynamic-123"
    mock_log_request.return_value = mock_job

    # Test data with dynamic content
    job_data = {
        "client_job_id": "dynamic_test123",
        "template_url": "https://example.com/template.docx",
        "output_filename": "custom_report",
        "data": {
            "name": "Test User",
            "dd__note_body": [
                {
                    "type": "heading",
                    "style": "Heading 1",
                    "data": {"text": "Dynamic Content Test"},
                },
                {
                    "type": "paragraph",
                    "data": {
                        "runs": [
                            {"text": "This is a ", "bold": False},
                            {"text": "dynamic test", "bold": True},
                            {"text": " paragraph.", "bold": False},
                        ]
                    },
                },
            ],
        },
    }

    # Make the request
    response = client.post(
        "/api/v1/generate-pdf/dynamic", headers=auth_headers, json=job_data
    )

    # Verify response
    assert response.status_code == 202
    assert response.json["status"] == "queued"
    assert response.json["client_job_id"] == "dynamic_test123"
    assert response.json["job_id"] == "test-job-uuid-dynamic-123"
    assert response.json["output_filename"] == "custom_report"

    # Get the actual task_id from the response
    assert "task_id" in response.json
    task_id = response.json["task_id"]

    # Verify the task was called with keyword arguments
    call_kwargs = mock_generate_pdf_dynamic_task.delay.call_args[1]
    assert call_kwargs["job_id"] == "test-job-uuid-dynamic-123"
    assert call_kwargs["client_job_id"] == "dynamic_test123"
    assert call_kwargs["template_url"] == "https://example.com/template.docx"
    assert call_kwargs["json_data"] == job_data["data"]
    assert call_kwargs["output_filename"] == "custom_report"
    assert call_kwargs["use_empty_template"] == False
    assert "user_id" in call_kwargs  # user_id is added by the endpoint

    # Verify logging was called correctly
    # Extract the actual call to check the documents array structure
    call_args = mock_log_request.call_args
    assert call_args[1]["client_job_id"] == "dynamic_test123"
    assert call_args[1]["job_type"] == "generate"
    assert "documents" in call_args[1]
    assert len(call_args[1]["documents"]) == 1
    # Documents array should NOT contain template_url or data (stored in S3 instead)
    assert "template_url" not in call_args[1]["documents"][0]
    assert "data" not in call_args[1]["documents"][0]
    # But should contain processing metadata
    assert call_args[1]["documents"][0]["type"] == "generate"
    assert call_args[1]["documents"][0]["mode"] == "dynamic"
    assert call_args[1]["documents"][0]["status"] == "queued"
    # request_data is replaced with request_audit_s3_key (will be None initially, then updated)
    assert "request_audit_s3_key" in call_args[1]
    # task_id is None during initial log_request, then updated via update_job_task_id_by_id
    assert call_args[1]["task_id"] is None


# Test dynamic PDF generation with default output filename
@patch("app.api.pdf_generation.generate_pdf_dynamic_task")
@patch("app.api.pdf_generation.log_request")
def test_generate_pdf_dynamic_default_filename(
    mock_log_request, mock_generate_pdf_dynamic_task, client, auth_headers
):
    # Configure the mock
    mock_task = MagicMock()
    mock_task.id = "mock_dynamic_task_id_2"
    mock_generate_pdf_dynamic_task.delay.return_value = mock_task

    # Configure mock_log_request to return a job object with an id
    mock_job = MagicMock()
    mock_job.id = "test-job-uuid-dynamic-124"
    mock_log_request.return_value = mock_job

    # Test data without output_filename (should default to "output")
    job_data = {
        "client_job_id": "dynamic_test124",
        "template_url": "https://example.com/template.docx",
        "data": {
            "name": "Test User",
            "dd__note_body": [
                {
                    "type": "paragraph",
                    "data": {"runs": [{"text": "Simple test"}]},
                }
            ],
        },
    }

    # Make the request
    response = client.post(
        "/api/v1/generate-pdf/dynamic", headers=auth_headers, json=job_data
    )

    # Verify response
    assert response.status_code == 202
    assert response.json["status"] == "queued"
    assert response.json["client_job_id"] == "dynamic_test124"
    assert response.json["job_id"] == "test-job-uuid-dynamic-124"
    assert (
        response.json["output_filename"] == "output"
    )  # Should default to "output"

    # Verify the task was called with keyword arguments and default filename
    call_kwargs = mock_generate_pdf_dynamic_task.delay.call_args[1]
    assert call_kwargs["job_id"] == "test-job-uuid-dynamic-124"
    assert call_kwargs["client_job_id"] == "dynamic_test124"
    assert call_kwargs["template_url"] == "https://example.com/template.docx"
    assert call_kwargs["json_data"] == job_data["data"]
    assert call_kwargs["output_filename"] == "output"  # Default filename
    assert call_kwargs["use_empty_template"] == False
    assert "user_id" in call_kwargs  # user_id is added by the endpoint


# Test dynamic PDF with complex content structure
@patch("app.api.pdf_generation.generate_pdf_dynamic_task")
@patch("app.api.pdf_generation.log_request")
def test_generate_pdf_dynamic_complex_content(
    mock_log_request, mock_generate_pdf_dynamic_task, client, auth_headers
):
    # Configure the mock
    mock_task = MagicMock()
    mock_task.id = "mock_complex_task_id"
    mock_generate_pdf_dynamic_task.delay.return_value = mock_task

    # Configure mock_log_request to return a job object with an id
    mock_job = MagicMock()
    mock_job.id = "test-job-uuid-complex"
    mock_log_request.return_value = mock_job

    # Test data with complex dynamic content including lists, tables, etc.
    job_data = {
        "client_job_id": "complex_dynamic_test",
        "template_url": "https://example.com/complex_template.docx",
        "output_filename": "complex_report",
        "data": {
            "title": "Complex Report",
            "dd__note_body": [
                {
                    "type": "heading",
                    "style": "Heading 1",
                    "data": {"text": "Complex Dynamic Content"},
                },
                {
                    "type": "paragraph",
                    "data": {
                        "runs": [
                            {"text": "This report contains ", "bold": False},
                            {
                                "text": "various types",
                                "bold": True,
                                "color": "0066CC",
                            },
                            {"text": " of content.", "bold": False},
                        ]
                    },
                },
                {
                    "type": "list",
                    "data": {
                        "list_type": "bulleted",
                        "items": [
                            {
                                "runs": [
                                    {"text": "First bullet point", "bold": True}
                                ]
                            },
                            {
                                "runs": [
                                    {
                                        "text": "Second bullet with ",
                                        "bold": False,
                                    },
                                    {"text": "emphasis", "italic": True},
                                ]
                            },
                        ],
                    },
                },
                {
                    "type": "table",
                    "style": "Table Grid",
                    "data": {
                        "rows": [
                            [
                                {"runs": [{"text": "Column 1", "bold": True}]},
                                {"runs": [{"text": "Column 2", "bold": True}]},
                            ],
                            [
                                {"runs": [{"text": "Data 1"}]},
                                {"runs": [{"text": "Data 2"}]},
                            ],
                        ]
                    },
                },
                {
                    "type": "image",
                    "data": {
                        "src": "https://example.com/test-image.jpg",
                        "width": 4,
                        "height": 3,
                        "alt": "Test image",
                        "alignment": "center",
                    },
                },
                {"type": "divider", "data": {}},
            ],
        },
    }

    # Make the request
    response = client.post(
        "/api/v1/generate-pdf/dynamic", headers=auth_headers, json=job_data
    )

    # Verify response
    assert response.status_code == 202
    assert response.json["status"] == "queued"
    assert response.json["client_job_id"] == "complex_dynamic_test"
    assert response.json["job_id"] == "test-job-uuid-complex"
    assert response.json["output_filename"] == "complex_report"

    # Verify the task was called with keyword arguments and complex content
    call_kwargs = mock_generate_pdf_dynamic_task.delay.call_args[1]
    assert call_kwargs["job_id"] == "test-job-uuid-complex"
    assert call_kwargs["client_job_id"] == "complex_dynamic_test"
    assert (
        call_kwargs["template_url"]
        == "https://example.com/complex_template.docx"
    )
    assert call_kwargs["json_data"] == job_data["data"]
    assert call_kwargs["output_filename"] == "complex_report"
    assert call_kwargs["use_empty_template"] == False
    assert "user_id" in call_kwargs  # user_id is added by the endpoint


# Test logs endpoint functionality
@patch("app.api.logs.get_all_jobs")
def test_logs_endpoint(mock_get_all_jobs, client, auth_headers):
    # Mock return data
    mock_logs = [
        {
            "client_job_id": "test123",
            "template_url": "https://example.com/template.docx",
            "task_id": "task123",
            "status": "SUCCESS",
            "created_at": "2023-12-01T10:00:00Z",
            "updated_at": "2023-12-01T10:00:30Z",
        },
        {
            "client_job_id": "dynamic_test123",
            "template_url": "https://example.com/dynamic_template.docx",
            "task_id": "dynamic_task123",
            "status": "PROCESSING",
            "created_at": "2023-12-01T10:01:00Z",
            "updated_at": "2023-12-01T10:01:00Z",
        },
    ]
    mock_get_all_jobs.return_value = mock_logs

    # Make the request
    response = client.get("/api/v1/logs", headers=auth_headers)

    # Verify response
    assert response.status_code == 200
    assert response.json["total"] == 2
    assert response.json["offset"] == 0
    assert response.json["limit"] == 100
    assert len(response.json["logs"]) == 2

    # Verify first log entry
    first_log = response.json["logs"][0]
    assert first_log["client_job_id"] == "test123"
    assert first_log["status"] == "SUCCESS"

    # Verify second log entry
    second_log = response.json["logs"][1]
    assert second_log["client_job_id"] == "dynamic_test123"
    assert second_log["status"] == "PROCESSING"

    # Verify the function was called with default parameters
    mock_get_all_jobs.assert_called_once_with(
        limit=100,
        offset=0,
        status=None,
        client_job_id=None,
        job_type=None,
        user_id=None,
        job_id=None,
        date_from=None,
        date_to=None,
    )


# Test logs endpoint with query parameters
@patch("app.api.logs.get_all_jobs")
def test_logs_endpoint_with_params(mock_get_all_jobs, client, auth_headers):
    # Mock return data
    mock_logs = [{"client_job_id": "test123", "status": "SUCCESS"}]
    mock_get_all_jobs.return_value = mock_logs

    # Make the request with query parameters
    response = client.get(
        "/api/v1/logs?limit=50&offset=10&status=SUCCESS&client_job_id=test123",
        headers=auth_headers,
    )

    # Verify response
    assert response.status_code == 200
    assert response.json["limit"] == 50
    assert response.json["offset"] == 10

    # Verify the function was called with the specified parameters
    mock_get_all_jobs.assert_called_once_with(
        limit=50,
        offset=10,
        status="SUCCESS",
        client_job_id="test123",
        job_type=None,
        user_id=None,
        job_id=None,
        date_from=None,
        date_to=None,
    )


# Test authentication for all new endpoints
def test_generate_pdf_dynamic_no_auth(client):
    """Test that dynamic PDF generation requires JWT authentication"""
    response = client.post(
        "/api/v1/generate-pdf/dynamic",
        json={
            "client_job_id": "test",
            "template_url": "https://example.com/template.docx",
            "data": {"test": "data"},
        },
    )
    assert response.status_code == 401
    assert "Token is missing" in response.json["error"]


def test_logs_no_auth(client):
    """Test that logs endpoint requires JWT authentication"""
    response = client.get("/api/v1/logs")
    assert response.status_code == 401
    assert "Token is missing" in response.json["error"]


@patch("app.api.logs.get_all_jobs")
def test_logs_regular_user_sees_own_logs(mock_get_all_jobs, client, test_user_headers):
    """Test that regular users can access logs but only see their own"""
    # Mock return data
    mock_logs = [{"client_job_id": "user_test123", "status": "SUCCESS"}]
    mock_get_all_jobs.return_value = mock_logs

    response = client.get("/api/v1/logs", headers=test_user_headers)
    assert response.status_code == 200

    # Verify the function was called with user_id filter (not None like master user)
    call_kwargs = mock_get_all_jobs.call_args[1]
    assert call_kwargs["user_id"] is not None  # Regular user should have user_id filter
