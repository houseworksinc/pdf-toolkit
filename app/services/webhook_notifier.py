import hmac
import hashlib
import json
import time
import requests
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


def generate_webhook_signature(payload: Dict[str, Any], secret: str) -> str:
    """
    Generate HMAC-SHA256 signature for webhook payload.

    Args:
        payload: Dictionary payload to sign
        secret: Webhook secret key

    Returns:
        Hexadecimal signature string
    """
    # Convert payload to JSON string with sorted keys for consistency
    payload_string = json.dumps(payload, sort_keys=True, separators=(",", ":"))

    # Generate HMAC-SHA256 signature
    signature = hmac.new(
        key=secret.encode("utf-8"),
        msg=payload_string.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()

    return signature


def send_webhook_notification(
    webhook_url: str,
    payload: Dict[str, Any],
    webhook_secret: str,
    max_retries: int = 3,
    timeout: int = 10,
) -> Dict[str, Any]:
    """
    Send webhook notification with HMAC signature and retry logic.

    Args:
        webhook_url: Target webhook URL
        payload: Data to send
        webhook_secret: Secret for signing
        max_retries: Maximum number of retry attempts (default: 3)
        timeout: Request timeout in seconds (default: 10)

    Returns:
        Dictionary with status and response info
    """
    if not webhook_url:
        return {
            "success": False,
            "error": "No webhook URL provided",
            "status_code": None,
        }

    if not webhook_secret:
        return {
            "success": False,
            "error": "No webhook secret configured",
            "status_code": None,
        }

    # Generate signature
    signature = generate_webhook_signature(payload, webhook_secret)
    timestamp = str(int(time.time()))

    # Prepare headers
    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Signature": f"sha256={signature}",
        "X-Webhook-Timestamp": timestamp,
        "X-Job-ID": payload.get("client_job_id", ""),
        "User-Agent": "PDF-Toolkit-Webhook/1.0",
    }

    # Retry with exponential backoff
    for attempt in range(max_retries):
        try:
            logger.info(
                f"Sending webhook to {webhook_url} (attempt {attempt + 1}/{max_retries})"
            )

            response = requests.post(
                webhook_url, json=payload, headers=headers, timeout=timeout
            )

            # Consider 2xx status codes as success
            if 200 <= response.status_code < 300:
                logger.info(f"Webhook delivered successfully to {webhook_url}")
                return {
                    "success": True,
                    "status_code": response.status_code,
                    "response_text": response.text[:500],  # Limit response text
                    "attempt": attempt + 1,
                }
            else:
                logger.warning(
                    f"Webhook returned non-success status {response.status_code}: {response.text[:200]}"
                )

                # If it's a client error (4xx), don't retry
                if 400 <= response.status_code < 500:
                    return {
                        "success": False,
                        "error": f"Client error: {response.status_code}",
                        "status_code": response.status_code,
                        "response_text": response.text[:500],
                        "attempt": attempt + 1,
                    }

        except requests.exceptions.Timeout:
            logger.error(f"Webhook timeout on attempt {attempt + 1}")
            if attempt == max_retries - 1:
                return {
                    "success": False,
                    "error": "Request timeout",
                    "status_code": None,
                    "attempt": attempt + 1,
                }

        except requests.exceptions.ConnectionError as e:
            logger.error(
                f"Webhook connection error on attempt {attempt + 1}: {str(e)}"
            )
            if attempt == max_retries - 1:
                return {
                    "success": False,
                    "error": f"Connection error: {str(e)[:200]}",
                    "status_code": None,
                    "attempt": attempt + 1,
                }

        except Exception as e:
            logger.error(
                f"Webhook unexpected error on attempt {attempt + 1}: {str(e)}"
            )
            if attempt == max_retries - 1:
                return {
                    "success": False,
                    "error": f"Unexpected error: {str(e)[:200]}",
                    "status_code": None,
                    "attempt": attempt + 1,
                }

        # Exponential backoff: wait 2^attempt seconds (1s, 2s, 4s, etc.)
        if attempt < max_retries - 1:
            wait_time = 2**attempt
            logger.info(f"Retrying webhook in {wait_time} seconds...")
            time.sleep(wait_time)

    # All retries exhausted
    return {
        "success": False,
        "error": "All retry attempts exhausted",
        "status_code": None,
        "attempt": max_retries,
    }


def verify_webhook_signature(
    payload: Dict[str, Any], received_signature: str, secret: str
) -> bool:
    """
    Verify webhook signature (for testing/validation purposes).

    Args:
        payload: Webhook payload
        received_signature: Signature from X-Webhook-Signature header
        secret: Webhook secret

    Returns:
        True if signature is valid, False otherwise
    """
    # Remove 'sha256=' prefix if present
    if received_signature.startswith("sha256="):
        received_signature = received_signature[7:]

    expected_signature = generate_webhook_signature(payload, secret)

    # Constant-time comparison to prevent timing attacks
    return hmac.compare_digest(expected_signature, received_signature)


def build_webhook_payload(
    client_job_id: str,
    task_id: str,
    status: str,
    job_id: Optional[str] = None,
    started_at: Optional[str] = None,
    ended_at: Optional[str] = None,
    processing_time: Optional[float] = None,
    progress: Optional[int] = None,
    meta_data: Optional[Dict[str, Any]] = None,
    splits: Optional[list] = None,
    documents: Optional[list] = None,
    download_url: Optional[str] = None,
    error: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build standardized webhook payload.

    Args:
        client_job_id: Client job identifier
        task_id: Celery task identifier
        status: Job status (queued, running, completed, failed)
        job_id: Job UUID (optional, but recommended for consistency with status endpoints)
        started_at: ISO timestamp when job started
        ended_at: ISO timestamp when job ended
        processing_time: Processing time in seconds
        progress: Progress percentage (0-100), only included if provided
        meta_data: Custom metadata
        splits: List of split information (for split jobs only)
        documents: List of document information (for all job types)
        download_url: Download URL for final output
        error: Error message if failed

    Returns:
        Formatted webhook payload dictionary
    """
    payload = {
        "job_id": job_id,
        "client_job_id": client_job_id,
        "task_id": task_id,
        "status": status,
        "started_at": started_at,
        "ended_at": ended_at,
        "processing_time": f"{processing_time:.2f}"
        if processing_time is not None
        else None,
        "progress": progress,
        "meta_data": meta_data or {},
        "splits": splits if splits is not None else [],
        "documents": documents or [],
        "download_url": download_url,
        "error": error,
    }

    # Remove None values and empty lists for optional fields
    filtered_payload = {}
    for k, v in payload.items():
        if v is None:
            continue
        # Remove empty splits array if no splits provided
        if k == "splits" and splits is None:
            continue
        # Remove empty progress if not provided
        if k == "progress" and progress is None:
            continue
        filtered_payload[k] = v

    return filtered_payload
