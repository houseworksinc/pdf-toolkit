# Testing Guide

Comprehensive testing guide for HouseWorks PDF Toolkit.

---

## Table of Contents

- [Test Structure](#test-structure)
- [Running Tests](#running-tests)
- [Writing Tests](#writing-tests)
- [Test Coverage](#test-coverage)
- [Integration Testing](#integration-testing)
- [Performance Testing](#performance-testing)

---

## Test Structure

```
app/tests/
├── conftest.py                    # Shared fixtures
├── test_api.py                    # API endpoint tests
├── test_merge_pdf_api.py          # Merge PDF API tests
├── test_zip_files_api.py          # ZIP creation API tests
├── test_split_pdf_api.py          # Split PDF API tests
├── test_webhook.py                # Webhook tests
├── test_database.py               # Database tests
├── test_jwt_auth.py               # Authentication tests
├── test_generate_pdf.py           # PDF generation tests
├── test_unoserver_converter.py    # UnoServer converter tests
└── test_app.py                    # General app tests
```

---

## Running Tests

### All Tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific test file
pytest app/tests/test_split_pdf_api.py -v
pytest app/tests/test_merge_pdf_api.py -v
pytest app/tests/test_zip_files_api.py -v
pytest app/tests/test_unoserver_converter.py -v

# Run specific test
pytest app/tests/test_api.py::test_generate_pdf -v
pytest app/tests/test_merge_pdf_api.py::test_create_merge_success -v
pytest app/tests/test_unoserver_converter.py::test_successful_conversion -v

# Run tests matching pattern
pytest -k "split" -v
pytest -k "merge" -v
pytest -k "zip" -v
pytest -k "unoserver" -v
```

### Using Test Runner Script

```bash
# Run all tests
python run_tests.py

# Run with coverage report
python run_tests.py --coverage
```

### Watch Mode (Continuous Testing)

```bash
# Install pytest-watch
pip install pytest-watch

# Run in watch mode
ptw -- -v
```

---

## Writing Tests

### Basic Test Structure

```python
import pytest
from unittest.mock import patch, MagicMock

def test_example():
    """Test description."""
    # Arrange
    input_data = {"key": "value"}

    # Act
    result = function_to_test(input_data)

    # Assert
    assert result == expected_output
```

### Using Fixtures

**conftest.py:**

```python
import pytest
from app import app as flask_app
from app.database import init_db
from app.models import User, db

@pytest.fixture
def app():
    """Create Flask app for testing."""
    flask_app.config['TESTING'] = True
    flask_app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'

    with flask_app.app_context():
        init_db()
        yield flask_app

        db.session.remove()
        db.drop_all()

@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()

@pytest.fixture
def test_user(app):
    """Create test user."""
    with app.app_context():
        user = User(username='testuser')
        user.set_password('testpass')
        db.session.add(user)
        db.session.commit()
        return user

@pytest.fixture
def test_user_headers(client):
    """Get JWT auth headers for test user."""
    # Register user
    client.post('/api/v1/auth/register',
                json={'username': 'testuser', 'password': 'testpass'})

    # Login
    response = client.post('/api/v1/auth/login',
                          json={'username': 'testuser', 'password': 'testpass'})
    token = response.json['token']

    return {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
```

### Testing API Endpoints

```python
def test_register_user(client):
    """Test user registration."""
    response = client.post('/api/v1/auth/register',
                          json={
                              'username': 'newuser',
                              'password': 'password123'
                          })

    assert response.status_code == 201
    data = response.json
    assert data['username'] == 'newuser'
    assert 'webhook_secret' in data

def test_generate_pdf(client, test_user_headers):
    """Test PDF generation endpoint."""
    with patch('app.api.pdf_generation.generate_pdf_task') as mock_task:
        mock_task.delay.return_value = MagicMock(id='task-123')

        response = client.post('/api/v1/generate-pdf',
                              headers=test_user_headers,
                              json={
                                  'client_job_id': 'test-job',
                                  'template_url': 'https://example.com/template.docx',
                                  'data': {'name': 'Test'}
                              })

        assert response.status_code == 202
        assert response.json['task_id'] == 'task-123'
        assert mock_task.delay.called

def test_merge_pdfs(client, test_user_headers):
    """Test PDF merging endpoint."""
    with patch('app.api.merge_pdf.merge_pdfs_task') as mock_task:
        mock_task.delay.return_value = MagicMock(id='merge-task-456')

        response = client.post('/api/v1/merge-pdfs',
                              headers=test_user_headers,
                              json={
                                  'client_job_id': 'merge-job-001',
                                  'document_urls': [
                                      'https://example.com/doc1.pdf',
                                      'https://example.com/doc2.pdf'
                                  ]
                              })

        assert response.status_code == 200
        assert response.json['task_id'] == 'merge-task-456'
        assert mock_task.delay.called

def test_create_zip(client, test_user_headers):
    """Test ZIP creation endpoint."""
    with patch('app.api.zip_files.create_zip_task') as mock_task:
        mock_task.delay.return_value = MagicMock(id='zip-task-789')

        response = client.post('/api/v1/create-zip',
                              headers=test_user_headers,
                              json={
                                  'client_job_id': 'zip-job-001',
                                  'document_urls': [
                                      'https://example.com/file1.pdf',
                                      'https://example.com/image.png',
                                      'https://example.com/data.xlsx'
                                  ]
                              })

        assert response.status_code == 200
        assert response.json['task_id'] == 'zip-task-789'
        assert mock_task.delay.called
```

### Testing with Mocks

```python
from unittest.mock import patch, MagicMock, call

def test_split_pdf_task():
    """Test split PDF Celery task."""
    with patch('app.workers.celery_worker.split_pdf_from_url') as mock_split:
        with patch('app.workers.celery_worker.upload_split_file') as mock_upload:
            # Configure mocks
            mock_split.return_value = [{
                'output_filename': 'part1',
                'success': True,
                'file_path': '/tmp/part1.pdf',
                'file_size': 1024
            }]

            mock_upload.return_value = {
                'success': True,
                's3_key': 'splits/job123/part1.pdf',
                'download_url': 'https://s3.amazonaws.com/...'
            }

            # Call task
            from app.workers.celery_worker import split_pdf_task
            result = split_pdf_task(
                client_job_id='test-job',
                document_url='https://example.com/doc.pdf',
                splits=[{'output_filename': 'part1', 'pages': [1, 2]}]
            )

            # Verify
            assert mock_split.called
            assert mock_upload.called
            assert result['status'] == 'SUCCESS'
```

### Testing Database Operations

```python
def test_log_request(app):
    """Test logging PDF job to database."""
    from app.database import log_request

    with app.app_context():
        job = log_request(
            client_job_id='test-123',
            job_type='generate_static',
            template_url='https://example.com/template.docx',
            meta_data={'client': 'test'}
        )

        assert job.client_job_id == 'test-123'
        assert job.status == 'PENDING'

def test_update_job_status(app):
    """Test updating job status."""
    from app.database import log_request, update_job_status

    with app.app_context():
        # Create job
        log_request(client_job_id='test-456', job_type='generate_static')

        # Update status
        update_job_status(
            client_job_id='test-456',
            status='SUCCESS',
            s3_key='pdfs/test-456.pdf',
            download_url='https://s3.amazonaws.com/...'
        )

        # Verify
        from app.database import get_job_info
        job = get_job_info('test-456')
        assert job['status'] == 'SUCCESS'
        assert job['s3_key'] == 'pdfs/test-456.pdf'
```

### Testing Webhooks

```python
def test_webhook_signature_generation():
    """Test HMAC signature generation."""
    from app.services.webhook_notifier import generate_webhook_signature

    payload = {"client_job_id": "test", "status": "completed"}
    secret = "test_secret"

    signature = generate_webhook_signature(payload, secret)

    assert signature.startswith('sha256=')
    assert len(signature) == 71  # 'sha256=' + 64 hex chars

def test_send_webhook_notification():
    """Test sending webhook with retry."""
    from app.services.webhook_notifier import send_webhook_notification

    with patch('requests.post') as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.text = 'OK'

        result = send_webhook_notification(
            webhook_url='https://example.com/webhook',
            payload={'client_job_id': 'test'},
            webhook_secret='secret123'
        )

        assert result['success'] is True
        assert mock_post.called
```

### Parametrized Tests

```python
@pytest.mark.parametrize("status_code,expected", [
    (200, True),
    (201, True),
    (400, False),
    (500, False),
])
def test_webhook_response_codes(status_code, expected):
    """Test webhook considers 2xx as success."""
    from app.services.webhook_notifier import send_webhook_notification

    with patch('requests.post') as mock_post:
        mock_post.return_value.status_code = status_code

        result = send_webhook_notification(
            webhook_url='https://example.com/webhook',
            payload={'client_job_id': 'test'},
            webhook_secret='secret'
        )

        assert result['success'] is expected
```

---

## Test Coverage

### Generate Coverage Report

```bash
# Run tests with coverage
pytest --cov=app --cov-report=html --cov-report=term

# Open HTML report
open htmlcov/index.html
```

### Coverage Configuration

**.coveragerc:**

```ini
[run]
source = app
omit =
    */tests/*
    */venv/*
    */__pycache__/*

[report]
exclude_lines =
    pragma: no cover
    def __repr__
    raise AssertionError
    raise NotImplementedError
    if __name__ == .__main__.:
```

### Current Coverage

```
Name                               Stmts   Miss  Cover
------------------------------------------------------
app/__init__.py                       15      0   100%
app/api/auth.py                       45      2    96%
app/api/pdf_generation.py             38      1    97%
app/api/merge_pdf.py                  68      3    96%
app/api/zip_files.py                  64      3    95%
app/api/split_pdf.py                  82      4    95%
app/api/webhook.py                    56      3    95%
app/database.py                      120      8    93%
app/middleware/auth.py                45      2    96%
app/models/user.py                    25      0   100%
app/models/pdf_job.py                 48      0   100%
app/services/pdf_generator.py        145     12    92%
app/services/pdf_merger.py            95      6    94%
app/services/zip_creator.py           72      4    94%
app/services/pdf_splitter.py         112      8    93%
app/services/upload_handler.py        98      6    94%
app/services/webhook_notifier.py      78      4    95%
app/workers/celery_worker.py         345     35    90%
------------------------------------------------------
TOTAL                               1551    101    93%
```

---

## Integration Testing

### Full Workflow Test

```python
def test_full_pdf_generation_workflow(client, test_user_headers):
    """Test complete PDF generation flow."""
    # 1. Submit job
    response = client.post('/api/v1/generate-pdf',
                          headers=test_user_headers,
                          json={
                              'client_job_id': 'integration-test-001',
                              'template_url': 'https://example.com/template.docx',
                              'data': {'name': 'Test User'}
                          })

    assert response.status_code == 202
    task_id = response.json['task_id']

    # 2. Check status (would be async in real scenario)
    with patch('app.workers.celery_worker.generate_pdf_task'):
        status_response = client.get(f'/api/v1/generate-pdf/status?client_job_id=integration-test-001',
                                     headers=test_user_headers)
        assert status_response.status_code == 200

    # 3. Verify logs
    logs_response = client.get('/api/v1/logs?client_job_id=integration-test-001',
                               headers=test_user_headers)
    assert logs_response.status_code == 200
    assert len(logs_response.json['logs']) > 0
```

### Testing with Docker

```bash
# Run tests in Docker environment
docker-compose run --rm api pytest -v

# Run specific test
docker-compose run --rm api pytest app/tests/test_api.py::test_generate_pdf -v
```

---

## Performance Testing

### Load Testing with Locust

**locustfile.py:**

```python
from locust import HttpUser, task, between

class PDFGeneratorUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        """Login and get token."""
        response = self.client.post("/api/v1/auth/login", json={
            "username": "testuser",
            "password": "testpass"
        })
        self.token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

    @task(3)
    def generate_pdf(self):
        """Generate PDF task."""
        self.client.post("/api/v1/generate-pdf",
                        headers=self.headers,
                        json={
                            "client_job_id": f"load-test-{self.environment.runner.user_count}",
                            "template_url": "https://example.com/template.docx",
                            "data": {"name": "Load Test"}
                        })

    @task(1)
    def check_status(self):
        """Check job status."""
        self.client.get("/api/v1/generate-pdf/status?client_job_id=load-test-001", headers=self.headers)
```

**Run Load Test:**

```bash
pip install locust
locust -f locustfile.py --host=http://localhost:5001
```

### Benchmarking

```python
import time
import pytest

@pytest.mark.benchmark
def test_pdf_generation_performance():
    """Benchmark PDF generation."""
    from app.services.pdf_generator import generate_pdf

    start = time.time()

    for i in range(100):
        generate_pdf(
            template_path="/path/to/template.docx",
            data={"name": f"User {i}"}
        )

    duration = time.time() - start
    avg_time = duration / 100

    assert avg_time < 2.0  # Should be under 2 seconds per PDF
    print(f"Average time per PDF: {avg_time:.2f}s")
```

---

## Continuous Integration

### GitHub Actions

**.github/workflows/test.yml:**

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v2

      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: "3.10"

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-cov

      - name: Run tests
        run: |
          pytest --cov=app --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@v2
        with:
          file: ./coverage.xml
```

---

## Test Best Practices

✅ **Write tests before code (TDD)**
✅ **One assertion per test (when possible)**
✅ **Use descriptive test names**
✅ **Keep tests independent**
✅ **Use fixtures for setup**
✅ **Mock external dependencies**
✅ **Test edge cases and errors**
✅ **Maintain > 80% coverage**

---

## Troubleshooting Tests

### Test Fails Intermittently

```python
# Add retries for flaky tests
@pytest.mark.flaky(reruns=3)
def test_flaky_operation():
    pass
```

### Database Lock Issues

```python
# Use separate test database
@pytest.fixture
def app():
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///test_{os.getpid()}.db'
    yield app
    os.remove(f'test_{os.getpid()}.db')
```

### Slow Tests

```bash
# Profile slow tests
pytest --durations=10

# Run only fast tests
pytest -m "not slow"
```

---

## Resources

- pytest docs: https://docs.pytest.org/
- Coverage.py: https://coverage.readthedocs.io/
- Locust: https://locust.io/

---
