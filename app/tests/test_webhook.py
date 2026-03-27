import pytest
import json
from unittest.mock import patch, MagicMock


def test_webhook_secret_generated_on_registration(client, auth_headers):
    """Test that webhook secret is auto-generated during user registration"""
    response = client.post(
        "/api/v1/auth/register",
        headers=auth_headers,
        json={"username": "webhookuser", "password": "testpass123"},
    )

    assert response.status_code == 201
    data = response.json
    assert "webhook_secret" in data
    assert (
        len(data["webhook_secret"]) > 30
    )  # token_urlsafe(32) produces ~43 chars
    assert "warning" in data


def test_webhook_secret_info_masked(test_user_headers, client):
    """Test that webhook secret info returns masked secret"""
    response = client.get(
        "/api/v1/webhook/secret-info", headers=test_user_headers
    )

    assert response.status_code == 200
    data = response.json
    assert data["has_secret"] is True
    assert "****..." in data["webhook_secret"]
    assert "created_at" in data


def test_webhook_secret_regeneration(test_user_headers, client):
    """Test webhook secret can be regenerated"""
    # Get initial secret info
    info_response = client.get(
        "/api/v1/webhook/secret-info", headers=test_user_headers
    )
    initial_secret = info_response.json["webhook_secret"]

    # Regenerate secret
    regen_response = client.post(
        "/api/v1/webhook/regenerate-secret", headers=test_user_headers
    )

    assert regen_response.status_code == 200
    data = regen_response.json
    assert "webhook_secret" in data
    assert "warning" in data
    assert "created_at" in data

    # Get new secret info
    new_info_response = client.get(
        "/api/v1/webhook/secret-info", headers=test_user_headers
    )
    new_secret = new_info_response.json["webhook_secret"]

    # Verify secret changed
    assert new_secret != initial_secret


def test_webhook_secret_regeneration_requires_auth(client):
    """Test webhook secret regeneration requires authentication"""
    response = client.post("/api/v1/webhook/regenerate-secret")

    assert response.status_code == 401


def test_webhook_test_endpoint(test_user_headers, client):
    """Test webhook test endpoint sends notification"""
    with patch(
        "app.services.webhook_notifier.send_webhook_notification"
    ) as mock_send:
        mock_send.return_value = {"success": True, "status_code": 200}

        response = client.post(
            "/api/v1/webhook/test",
            headers=test_user_headers,
            json={"webhook_url": "https://example.com/webhook"},
        )

        assert response.status_code == 200
        assert mock_send.called
        call_args = mock_send.call_args
        assert call_args[1]["webhook_url"] == "https://example.com/webhook"
        assert "webhook_secret" in call_args[1]


def test_webhook_test_missing_url(test_user_headers, client):
    """Test webhook test endpoint requires webhook_url"""
    response = client.post(
        "/api/v1/webhook/test", headers=test_user_headers, json={}
    )

    assert response.status_code == 400
    assert "webhook_url" in response.json["error"]


def test_webhook_test_no_secret_configured(client):
    """Test webhook test fails if user has no secret"""
    # Create user without webhook secret (manually)
    from app.models import User, db
    from app import app

    with app.app_context():
        user = User(username="nosecretuser")
        user.set_password("testpass123")
        user.webhook_secret = None  # Explicitly no secret
        db.session.add(user)
        db.session.commit()

    # Login to get token
    login_response = client.post(
        "/api/v1/auth/login",
        json={"username": "nosecretuser", "password": "testpass123"},
    )

    token = login_response.json["token"]
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    # Try to test webhook
    response = client.post(
        "/api/v1/webhook/test",
        headers=headers,
        json={"webhook_url": "https://example.com/webhook"},
    )

    assert response.status_code == 400
    assert "No webhook secret" in response.json["error"]


def test_update_user_metadata(test_user_headers, client):
    """Test user can update their metadata"""
    response = client.put(
        "/api/v1/auth/update-user-metadata",
        headers=test_user_headers,
        json={"meta_data": {"company": "Test Corp", "api_version": "v1"}},
    )

    assert response.status_code == 200
    assert response.json["message"] == "Metadata updated successfully"
    assert response.json["meta_data"]["company"] == "Test Corp"


def test_update_user_metadata_requires_auth(client):
    """Test metadata update requires authentication"""
    response = client.put(
        "/api/v1/auth/update-user-metadata", json={"meta_data": {}}
    )

    assert response.status_code == 401


def test_update_user_metadata_missing_field(test_user_headers, client):
    """Test metadata update requires meta_data field"""
    response = client.put(
        "/api/v1/auth/update-user-metadata", headers=test_user_headers, json={}
    )

    assert response.status_code == 400
    assert "meta_data" in response.json["error"]
