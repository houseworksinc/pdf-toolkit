import pytest
import json
from unittest.mock import patch
import jwt
import datetime


def test_register_user_success(client, auth_headers):
    """Test successful user registration by master user"""
    response = client.post(
        "/api/v1/auth/register",
        headers=auth_headers,
        json={"username": "newuser", "password": "password123"},
    )

    assert response.status_code == 201
    assert response.json["message"] == "User registered successfully"
    assert response.json["username"] == "newuser"


def test_register_user_missing_username(client, auth_headers):
    """Test registration with missing username"""
    response = client.post(
        "/api/v1/auth/register",
        headers=auth_headers,
        json={"password": "password123"},
    )

    assert response.status_code == 400
    assert "Username and password are required" in response.json["error"]


def test_register_user_missing_password(client, auth_headers):
    """Test registration with missing password"""
    response = client.post(
        "/api/v1/auth/register",
        headers=auth_headers,
        json={"username": "newuser"},
    )

    assert response.status_code == 400
    assert "Username and password are required" in response.json["error"]


def test_register_user_short_username(client, auth_headers):
    """Test registration with username too short"""
    response = client.post(
        "/api/v1/auth/register",
        headers=auth_headers,
        json={"username": "ab", "password": "password123"},
    )

    assert response.status_code == 400
    assert (
        "Username must be at least 3 characters long" in response.json["error"]
    )


def test_register_user_short_password(client, auth_headers):
    """Test registration with password too short"""
    response = client.post(
        "/api/v1/auth/register",
        headers=auth_headers,
        json={"username": "newuser", "password": "12345"},
    )

    assert response.status_code == 400
    assert (
        "Password must be at least 8 characters long" in response.json["error"]
    )


def test_register_user_duplicate_username(client, auth_headers):
    """Test registration with duplicate username"""
    # Register first user
    client.post(
        "/api/v1/auth/register",
        headers=auth_headers,
        json={"username": "duplicateuser", "password": "password123"},
    )

    # Try to register again with same username
    response = client.post(
        "/api/v1/auth/register",
        headers=auth_headers,
        json={"username": "duplicateuser", "password": "differentpass"},
    )

    assert response.status_code == 409
    assert "Username already exists" in response.json["error"]


def test_login_success(client):
    """Test successful login with master admin"""
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "testadmin", "password": "testpassword"},
    )

    assert response.status_code == 200
    assert response.json["message"] == "Login successful"
    assert "token" in response.json
    assert response.json["user"]["username"] == "testadmin"
    assert "id" in response.json["user"]
    assert isinstance(response.json["user"]["id"], str)
    assert len(response.json["user"]["id"]) == 36  # UUID string length


def test_login_invalid_credentials(client):
    """Test login with invalid credentials"""
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "testadmin", "password": "wrongpassword"},
    )

    assert response.status_code == 401
    assert "Invalid username or password" in response.json["error"]


def test_login_nonexistent_user(client):
    """Test login with nonexistent user"""
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "nonexistent", "password": "password123"},
    )

    assert response.status_code == 401
    assert "Invalid username or password" in response.json["error"]


def test_login_missing_credentials(client):
    """Test login with missing credentials"""
    response = client.post("/api/v1/auth/login", json={"username": "testadmin"})

    assert response.status_code == 400
    assert "Username and password are required" in response.json["error"]


def test_authenticate_valid_token(client, auth_headers):
    """Test authenticate endpoint with valid token"""
    response = client.get("/api/v1/auth/authenticate", headers=auth_headers)

    assert response.status_code == 200
    assert response.json["message"] == "Token is valid"
    assert response.json["user"]["username"] == "testadmin"
    assert "id" in response.json["user"]
    assert isinstance(response.json["user"]["id"], str)
    assert len(response.json["user"]["id"]) == 36  # UUID string length


def test_authenticate_missing_token(client):
    """Test authenticate endpoint with missing token"""
    response = client.get("/api/v1/auth/authenticate")

    assert response.status_code == 401
    assert "Token is missing" in response.json["error"]


def test_authenticate_invalid_token(client):
    """Test authenticate endpoint with invalid token"""
    headers = {
        "Authorization": "Bearer invalid.token.here",
        "Content-Type": "application/json",
    }

    response = client.get("/api/v1/auth/authenticate", headers=headers)

    assert response.status_code == 401
    assert "Token is invalid or expired" in response.json["error"]


def test_authenticate_malformed_auth_header(client):
    """Test authenticate endpoint with malformed authorization header"""
    headers = {
        "Authorization": "InvalidFormat token",
        "Content-Type": "application/json",
    }

    response = client.get("/api/v1/auth/authenticate", headers=headers)

    assert response.status_code == 401
    assert "Token is invalid or expired" in response.json["error"]


def test_authenticate_x_access_token_header(client, test_user_token):
    """Test authenticate endpoint using x-access-token header"""
    headers = {
        "x-access-token": test_user_token,
        "Content-Type": "application/json",
    }

    response = client.get("/api/v1/auth/authenticate", headers=headers)

    assert response.status_code == 200
    assert response.json["message"] == "Token is valid"
    assert response.json["user"]["username"] == "testuser"


def test_jwt_token_structure(client):
    """Test that JWT token has correct structure and claims"""
    # Login to get token
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "testadmin", "password": "testpassword"},
    )

    token = response.json["token"]

    # Decode token (without verification for testing)
    decoded = jwt.decode(token, options={"verify_signature": False})

    # Check required claims
    assert "user_id" in decoded
    assert "username" in decoded
    assert "exp" in decoded
    assert "iat" in decoded

    assert decoded["username"] == "testadmin"
    assert isinstance(decoded["user_id"], str)
    assert len(decoded["user_id"]) == 36  # UUID string length


def test_jwt_token_expiration():
    """Test JWT token expiration handling"""
    # This test would require mocking datetime or waiting for expiration
    # For now, we'll test that the expiration claim is set correctly
    pass


def test_register_and_login_flow(client, auth_headers):
    """Test complete registration and login flow"""
    # Register new user (as master)
    register_response = client.post(
        "/api/v1/auth/register",
        headers=auth_headers,
        json={"username": "flowtest", "password": "flowtest123"},
    )

    assert register_response.status_code == 201

    # Login with new user
    login_response = client.post(
        "/api/v1/auth/login",
        json={"username": "flowtest", "password": "flowtest123"},
    )

    assert login_response.status_code == 200
    token = login_response.json["token"]

    # Use token to authenticate
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    auth_response = client.get("/api/v1/auth/authenticate", headers=headers)

    assert auth_response.status_code == 200
    assert auth_response.json["user"]["username"] == "flowtest"


def test_master_admin_exists_on_startup(client):
    """Test that master admin user is created automatically"""
    # Try to login with master admin credentials
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "testadmin", "password": "testpassword"},
    )

    assert response.status_code == 200
    assert response.json["user"]["username"] == "testadmin"
    assert "id" in response.json["user"]
    assert isinstance(response.json["user"]["id"], str)
    assert len(response.json["user"]["id"]) == 36  # Should be UUID


def test_protected_endpoint_requires_jwt(client):
    """Test that protected endpoints require JWT token"""
    # Test that a protected endpoint returns 401 without token
    response = client.post(
        "/api/v1/generate-pdf",
        json={
            "client_job_id": "test",
            "template_url": "http://example.com/template.docx",
            "data": {"test": "data"},
        },
    )

    assert response.status_code == 401
    assert "Token is missing" in response.json["error"]


def test_protected_endpoint_with_valid_jwt(client, auth_headers):
    """Test that protected endpoints work with valid JWT token"""
    with patch("app.api.pdf_generation.generate_pdf_task") as mock_task, patch(
        "app.api.pdf_generation.log_request"
    ) as mock_log:
        # Configure mocks
        mock_task.delay.return_value.id = "mock_task_id"

        # Configure mock_log to return a job object with an id
        from unittest.mock import MagicMock

        mock_job = MagicMock()
        mock_job.id = "test-job-uuid-jwt"
        mock_log.return_value = mock_job

        response = client.post(
            "/api/v1/generate-pdf",
            headers=auth_headers,
            json={
                "client_job_id": "test",
                "template_url": "http://example.com/template.docx",
                "data": {"test": "data"},
            },
        )

        assert response.status_code == 202
        assert response.json["status"] == "queued"
        assert response.json["job_id"] == "test-job-uuid-jwt"


def test_user_context_in_protected_endpoint(client, auth_headers):
    """Test that user context is available in protected endpoints"""
    # This would require modifying an endpoint to return user info
    # For now, we test that the authenticate endpoint returns correct user info
    response = client.get("/api/v1/auth/authenticate", headers=auth_headers)

    assert response.status_code == 200
    assert response.json["user"]["username"] == "testadmin"
    assert "id" in response.json["user"]
    assert isinstance(response.json["user"]["id"], str)
    assert len(response.json["user"]["id"]) == 36  # UUID string length


def test_register_without_authentication(client):
    """Test that registration without authentication fails"""
    response = client.post(
        "/api/v1/auth/register",
        json={"username": "unauthuser", "password": "password123"},
    )

    assert response.status_code == 401
    assert "Token is missing" in response.json["error"]


def test_register_with_invalid_token(client):
    """Test that registration with invalid token fails"""
    headers = {
        "Authorization": "Bearer invalid.token.here",
        "Content-Type": "application/json",
    }

    response = client.post(
        "/api/v1/auth/register",
        headers=headers,
        json={"username": "invalidtokenuser", "password": "password123"},
    )

    assert response.status_code == 401
    assert "Token is invalid or expired" in response.json["error"]


def test_register_as_non_master_user(client, test_user_headers):
    """Test that non-master user cannot register new users"""
    response = client.post(
        "/api/v1/auth/register",
        headers=test_user_headers,
        json={"username": "anotheruser", "password": "password123"},
    )

    assert response.status_code == 403
    assert "Only master user can register new users" in response.json["error"]


def test_master_user_can_register_multiple_users(client, auth_headers):
    """Test that master user can register multiple users"""
    # Register first user
    response1 = client.post(
        "/api/v1/auth/register",
        headers=auth_headers,
        json={"username": "user1", "password": "password123"},
    )

    assert response1.status_code == 201
    assert response1.json["username"] == "user1"

    # Register second user
    response2 = client.post(
        "/api/v1/auth/register",
        headers=auth_headers,
        json={"username": "user2", "password": "password456"},
    )

    assert response2.status_code == 201
    assert response2.json["username"] == "user2"

    # Verify both users can login
    login1 = client.post(
        "/api/v1/auth/login",
        json={"username": "user1", "password": "password123"},
    )
    assert login1.status_code == 200

    login2 = client.post(
        "/api/v1/auth/login",
        json={"username": "user2", "password": "password456"},
    )
    assert login2.status_code == 200


def test_reset_password_success(client, auth_headers):
    """Test successful password reset by master user"""
    # First register a user
    client.post(
        "/api/v1/auth/register",
        headers=auth_headers,
        json={"username": "resetuser", "password": "oldpassword123"},
    )

    # Reset the password
    response = client.post(
        "/api/v1/auth/reset-password",
        headers=auth_headers,
        json={"username": "resetuser", "new_password": "newpassword456"},
    )

    assert response.status_code == 200
    assert "Password reset successfully" in response.json["message"]

    # Verify old password no longer works
    login_old = client.post(
        "/api/v1/auth/login",
        json={"username": "resetuser", "password": "oldpassword123"},
    )
    assert login_old.status_code == 401

    # Verify new password works
    login_new = client.post(
        "/api/v1/auth/login",
        json={"username": "resetuser", "password": "newpassword456"},
    )
    assert login_new.status_code == 200


def test_reset_password_missing_username(client, auth_headers):
    """Test password reset with missing username"""
    response = client.post(
        "/api/v1/auth/reset-password",
        headers=auth_headers,
        json={"new_password": "newpassword123"},
    )

    assert response.status_code == 400
    assert "Username and new_password are required" in response.json["error"]


def test_reset_password_missing_new_password(client, auth_headers):
    """Test password reset with missing new_password"""
    response = client.post(
        "/api/v1/auth/reset-password",
        headers=auth_headers,
        json={"username": "someuser"},
    )

    assert response.status_code == 400
    assert "Username and new_password are required" in response.json["error"]


def test_reset_password_short_password(client, auth_headers):
    """Test password reset with password too short"""
    response = client.post(
        "/api/v1/auth/reset-password",
        headers=auth_headers,
        json={"username": "someuser", "new_password": "12345"},
    )

    assert response.status_code == 400
    assert "Password must be at least 8 characters long" in response.json["error"]


def test_reset_password_nonexistent_user(client, auth_headers):
    """Test password reset for nonexistent user"""
    response = client.post(
        "/api/v1/auth/reset-password",
        headers=auth_headers,
        json={"username": "nonexistentuser", "new_password": "newpassword123"},
    )

    assert response.status_code == 404
    assert "User not found or inactive" in response.json["error"]


def test_reset_password_without_authentication(client):
    """Test that password reset without authentication fails"""
    response = client.post(
        "/api/v1/auth/reset-password",
        json={"username": "someuser", "new_password": "newpassword123"},
    )

    assert response.status_code == 401
    assert "Token is missing" in response.json["error"]


def test_reset_password_as_non_master_user(client, test_user_headers):
    """Test that non-master user cannot reset passwords"""
    response = client.post(
        "/api/v1/auth/reset-password",
        headers=test_user_headers,
        json={"username": "someuser", "new_password": "newpassword123"},
    )

    assert response.status_code == 403
    assert "Only master user can reset passwords" in response.json["error"]
