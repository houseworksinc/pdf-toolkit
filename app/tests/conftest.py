import os
import sys
import pytest
import tempfile
from unittest.mock import patch

# Create a temporary database file for all tests
_temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
_temp_db_path = _temp_db.name
_temp_db.close()

# Set environment variables BEFORE importing the app
# This is critical because app/__init__.py reads these during module import
os.environ["JWT_SECRET_KEY"] = "test-secret-key"
os.environ["JWT_ACCESS_TOKEN_EXPIRES"] = "3600"
os.environ["POSTGRES_USER"] = "test"
os.environ["POSTGRES_PASSWORD"] = "test"
os.environ["POSTGRES_DB"] = "test"
os.environ["POSTGRES_HOST"] = "localhost"  # Set to localhost for tests
os.environ["DATABASE_URL"] = (
    f"sqlite:///{_temp_db_path}"  # Override to use SQLite
)
os.environ["MASTER_USERNAME"] = "testadmin"
os.environ["MASTER_PASSWORD"] = "testpassword"
os.environ["AWS_S3_BUCKET_NAME"] = "test-bucket"
os.environ["AWS_REGION"] = "us-east-1"
os.environ["ENV"] = "test"
os.environ["CELERY_BROKER_URL"] = "redis://localhost:6379/0"
os.environ["CELERY_RESULT_BACKEND"] = "redis://localhost:6379/0"

# Now import the app
from app.main import app
from app.database import init_db


@pytest.fixture(scope="function")
def client():
    # Configure app for testing
    app.config["TESTING"] = True
    app.config["JWT_SECRET_KEY"] = "test-secret-key"
    app.config["JWT_ACCESS_TOKEN_EXPIRES"] = 3600

    # Set default download limits for tests
    app.config["MAX_DOWNLOADS_PER_JOB"] = 50
    app.config["MAX_DOWNLOAD_SIZE_MB"] = 5120

    # Get db instance from models
    from app.models import db

    # Push application context
    with app.app_context():
        # Drop all tables and recreate
        db.drop_all()
        db.create_all()

        # Initialize the test database (creates master admin)
        init_db()

    # Create test client
    with app.test_client() as test_client:
        yield test_client


@pytest.fixture
def auth_headers(client):
    """Fixture that provides JWT authentication headers for tests"""
    # Login with the master admin user to get a token
    login_response = client.post(
        "/api/v1/auth/login",
        json={"username": "testadmin", "password": "testpassword"},
    )

    assert login_response.status_code == 200
    token = login_response.json["token"]

    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


@pytest.fixture
def test_user_token(client):
    """Create a test user and return their JWT token"""
    # First, login as master admin to get authorization
    master_login_response = client.post(
        "/api/v1/auth/login",
        json={"username": "testadmin", "password": "testpassword"},
    )

    assert master_login_response.status_code == 200
    master_token = master_login_response.json["token"]

    # Register a test user using master authentication
    register_response = client.post(
        "/api/v1/auth/register",
        headers={
            "Authorization": f"Bearer {master_token}",
            "Content-Type": "application/json",
        },
        json={"username": "testuser", "password": "testpass123"},
    )

    assert register_response.status_code == 201

    # Login to get token
    login_response = client.post(
        "/api/v1/auth/login",
        json={"username": "testuser", "password": "testpass123"},
    )

    assert login_response.status_code == 200
    return login_response.json["token"]


@pytest.fixture
def test_user_headers(test_user_token):
    """Fixture that provides JWT headers for a regular test user"""
    return {
        "Authorization": f"Bearer {test_user_token}",
        "Content-Type": "application/json",
    }


@pytest.fixture(autouse=True)
def mock_audit_storage():
    """Auto-mock audit storage to prevent S3 access in tests"""
    with patch(
        "app.services.request_audit.store_audit_data",
        return_value="request_audit/test-job-id.json",
    ):
        yield
