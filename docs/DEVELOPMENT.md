# Development Guide

Developer setup and contribution guide for HouseWorks PDF Toolkit.

---

## Table of Contents

- [Getting Started](#getting-started)
- [Development Environment](#development-environment)
- [Code Structure](#code-structure)
- [Development Workflow](#development-workflow)
- [Coding Standards](#coding-standards)
- [Adding New Features](#adding-new-features)
- [Debugging](#debugging)

---

## Getting Started

### Prerequisites

- Python 3.10+
- Docker & Docker Compose
- Git
- Visual Studio Code (recommended) or PyCharm
- Postman or cURL for API testing

### Initial Setup

```bash
# 1. Clone repository
git clone <repository-url>
cd pdf-toolkit

# 2. Create virtual environment
python3 -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Install dev dependencies
pip install pytest pytest-cov black flake8 mypy

# 5. Set up pre-commit hooks (optional)
pip install pre-commit
pre-commit install

# 6. Create .env file
cp .env.example .env
# Edit .env with your local configuration

# 7. Initialize database
python -c "from app.database import init_db; init_db()"

# 8. Run tests
pytest
```

---

## Development Environment

### Using Docker (Recommended)

```bash
# Start all services
docker-compose up

# Rebuild after code changes
docker-compose up --build

# Run specific service
docker-compose up api

# View logs
docker-compose logs -f worker

# Stop services
docker-compose down
```

### Local Development (Without Docker)

**Terminal 1 - Redis:**

```bash
redis-server
```

**Terminal 2 - Celery Worker:**

```bash
export PYTHONPATH=.
celery -A app.workers.celery_worker:celery worker --loglevel=info
```

**Terminal 3 - Flask API:**

```bash
export FLASK_APP=app/main.py
export FLASK_DEBUG=1
python app/main.py
```

### VS Code Configuration

**.vscode/settings.json:**

```json
{
  "python.linting.enabled": true,
  "python.linting.pylintEnabled": false,
  "python.linting.flake8Enabled": true,
  "python.formatting.provider": "black",
  "python.testing.pytestEnabled": true,
  "python.testing.unittestEnabled": false,
  "editor.formatOnSave": true
}
```

**.vscode/launch.json:**

```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "Flask API",
      "type": "python",
      "request": "launch",
      "module": "flask",
      "env": {
        "FLASK_APP": "app/main.py",
        "FLASK_DEBUG": "1"
      },
      "args": ["run", "--port=5001"],
      "jinja": true
    }
  ]
}
```

---

## Code Structure

```
app/
├── __init__.py              # Flask app initialization
├── main.py                  # Application entry point
├── database.py              # Database utilities & helpers
│
├── api/                     # API blueprints (routes)
│   ├── __init__.py
│   ├── auth.py              # Authentication endpoints
│   ├── pdf_generation.py   # PDF generation endpoints
│   ├── split_pdf.py         # PDF splitting endpoints
│   ├── webhook.py           # Webhook management
│   └── logs.py              # Logging endpoints
│
├── models/                  # Database models
│   ├── __init__.py
│   ├── user.py              # User model
│   └── pdf_job.py           # PdfJob & PdfSplitOutput models
│
├── services/                # Business logic layer
│   ├── pdf_generator.py    # PDF generation service
│   ├── pdf_splitter.py     # PDF splitting service
│   ├── upload_handler.py   # S3 upload service
│   └── webhook_notifier.py # Webhook notification service
│
├── workers/                 # Celery tasks
│   └── celery_worker.py    # Task definitions
│
├── middleware/              # Middleware layer
│   └── auth.py              # JWT authentication
│
└── tests/                   # Test suite
    ├── conftest.py          # Test fixtures
    ├── test_api.py
    ├── test_split_pdf_api.py
    ├── test_webhook.py
    └── ...
```

### Design Principles

1. **Separation of Concerns**: API routes → Services → Workers
2. **Blueprint Architecture**: Modular route organization
3. **Service Layer**: Business logic isolated from routes
4. **Database Abstraction**: Helper functions in database.py
5. **Testability**: Dependency injection where possible

---

## Development Workflow

### 1. Create Feature Branch

```bash
git checkout -b feature/pdf-watermark
```

### 2. Implement Feature

**Create Service:**

```python
# app/services/watermark_service.py
import fitz  # PyMuPDF

def add_watermark(pdf_path, text, output_path):
    """Add text watermark to PDF."""
    doc = fitz.open(pdf_path)

    for page in doc:
        # Add watermark logic
        pass

    doc.save(output_path)
    doc.close()
```

**Create API Route:**

```python
# app/api/watermark.py
from flask import Blueprint, request, jsonify
from app.middleware.auth import require_jwt_token

watermark_bp = Blueprint('watermark', __name__)

@watermark_bp.route("/api/v1/watermark", methods=["POST"])
@require_jwt_token
def add_watermark_route():
    # Implementation
    pass
```

**Register Blueprint:**

```python
# app/main.py
from app.api.watermark import watermark_bp
app.register_blueprint(watermark_bp)
```

### 3. Write Tests First (TDD)

```python
# app/tests/test_watermark.py
def test_add_watermark(client, test_user_headers):
    """Test adding watermark to PDF."""
    response = client.post('/api/v1/watermark',
                          headers=test_user_headers,
                          json={
                              "client_job_id": "test-watermark",
                              "document_url": "https://example.com/doc.pdf",
                              "watermark_text": "CONFIDENTIAL"
                          })

    assert response.status_code == 202
    assert 'task_id' in response.json
```

### 4. Run Tests

```bash
pytest app/tests/test_watermark.py -v
```

### 5. Code Quality Checks

```bash
# Format code
black app/

# Lint
flake8 app/

# Type check
mypy app/
```

### 6. Commit & Push

```bash
git add .
git commit -m "Add PDF watermark feature"
git push origin feature/pdf-watermark
```

### 7. Create Pull Request

```bash
gh pr create --title "Add PDF watermark feature" --body "Closes #123"
```

---

## Coding Standards

### Python Style Guide

**Follow PEP 8:**

- Line length: 88 characters (Black default)
- Indentation: 4 spaces
- Imports: Grouped (stdlib, third-party, local)

**Example:**

```python
import os
import time
from typing import List, Dict, Optional

import requests
from flask import Blueprint, request, jsonify

from app.middleware.auth import require_jwt_token
from app.services.pdf_generator import generate_pdf


def process_pdf(file_path: str, options: Dict[str, Any]) -> Optional[str]:
    """
    Process PDF with given options.

    Args:
        file_path: Path to PDF file
        options: Processing options

    Returns:
        Path to processed PDF or None if failed

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If options are invalid
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")

    # Implementation
    return processed_path
```

### Naming Conventions

- **Files**: `snake_case.py`
- **Classes**: `PascalCase`
- **Functions**: `snake_case()`
- **Constants**: `UPPER_CASE`
- **Private methods**: `_leading_underscore()`

### Documentation

**Docstrings (Google Style):**

```python
def split_pdf_by_pages(document_path: str, splits: List[Dict]) -> List[Dict]:
    """
    Split a PDF into multiple files.

    Args:
        document_path: Path to source PDF
        splits: List of split configurations

    Returns:
        List of dictionaries with split results

    Raises:
        FileNotFoundError: If source PDF doesn't exist
        InvalidSplitConfigError: If split config is invalid

    Example:
        >>> splits = [{"output_filename": "part1", "pages": [1, 2, 3]}]
        >>> results = split_pdf_by_pages("doc.pdf", splits)
    """
    pass
```

### Error Handling

```python
# Bad
try:
    result = risky_operation()
except:
    pass

# Good
try:
    result = risky_operation()
except FileNotFoundError as e:
    logger.error(f"File not found: {e}")
    raise
except Exception as e:
    logger.error(f"Unexpected error: {e}")
    return {"error": str(e)}
```

### Testing

- **Coverage**: Aim for > 80%
- **Test naming**: `test_<function>_<scenario>`
- **Fixtures**: Use `conftest.py`
- **Mocking**: Use `unittest.mock`

---

## Adding New Features

### Example: Add PDF Merging

**1. Create Service**

```python
# app/services/pdf_merger.py
import fitz

def merge_pdfs(pdf_paths: List[str], output_path: str) -> Dict[str, Any]:
    """Merge multiple PDFs into one."""
    merged = fitz.open()

    for pdf_path in pdf_paths:
        doc = fitz.open(pdf_path)
        merged.insert_pdf(doc)
        doc.close()

    merged.save(output_path)
    merged.close()

    return {
        "success": True,
        "output_path": output_path,
        "page_count": merged.page_count
    }
```

**2. Create Celery Task**

```python
# app/workers/celery_worker.py
@celery.task(name='merge_pdf_task', bind=True)
def merge_pdf_task(self, client_job_id, pdf_urls):
    """Celery task to merge PDFs."""
    # Download PDFs
    # Call merge_pdfs()
    # Upload result
    pass
```

**3. Create API Endpoint**

```python
# app/api/merge_pdf.py
from flask import Blueprint, request, jsonify
from app.middleware.auth import require_jwt_token
from app.workers.celery_worker import merge_pdf_task

merge_bp = Blueprint('merge', __name__)

@merge_bp.route("/api/v1/merge-pdf", methods=["POST"])
@require_jwt_token
def merge_pdf_route():
    data = request.json
    task = merge_pdf_task.delay(data['client_job_id'], data['pdf_urls'])
    return jsonify({"task_id": task.id}), 202
```

**4. Register Blueprint**

```python
# app/main.py
from app.api.merge_pdf import merge_bp
app.register_blueprint(merge_bp)
```

**5. Add Tests**

```python
# app/tests/test_merge_pdf.py
def test_merge_pdf(client, test_user_headers):
    with patch('app.api.merge_pdf.merge_pdf_task') as mock_task:
        mock_task.delay.return_value = MagicMock(id='task-123')
        response = client.post('/api/v1/merge-pdf',
                              headers=test_user_headers,
                              json={"client_job_id": "test", "pdf_urls": ["url1", "url2"]})
        assert response.status_code == 202
```

---

## Debugging

### Debugging Flask API

**Using pdb:**

```python
import pdb

@app.route('/debug-test')
def debug_test():
    x = 42
    pdb.set_trace()  # Breakpoint here
    return jsonify({"result": x * 2})
```

**Using VS Code Debugger:**

1. Set breakpoints in code
2. Press F5 to start debugging
3. Make API request to trigger breakpoint

### Debugging Celery Tasks

```python
# Run worker in foreground with debug logs
celery -A app.workers.celery_worker:celery worker --loglevel=debug

# Or add print statements
@celery.task
def my_task(arg):
    print(f"DEBUG: arg = {arg}")  # Will appear in worker logs
    return result
```

### Common Issues

**Import Errors:**

```bash
# Ensure PYTHONPATH is set
export PYTHONPATH=.
```

**Database Locked:**

```bash
# SQLite lock - ensure no other process is using DB
lsof pdf-toolkit.db
```

**Port Already in Use:**

```bash
# Find process using port 5001
lsof -i :5001
kill -9 <PID>
```

---

## Git Workflow

### Commit Messages

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types:**

- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation
- `style`: Formatting
- `refactor`: Code restructuring
- `test`: Adding tests
- `chore`: Maintenance

**Examples:**

```
feat(split-pdf): Add PDF splitting by labels

- Implement label resolution using PyMuPDF
- Add tests for label-based splitting
- Update API documentation

Closes #42
```

---

## Resources

- **Flask Docs**: https://flask.palletsprojects.com/
- **Celery Docs**: https://docs.celeryq.dev/
- **PyMuPDF Docs**: https://pymupdf.readthedocs.io/
- **pytest Docs**: https://docs.pytest.org/

---
