"""
Service for validating download limits to prevent resource exhaustion.
"""

import logging
from typing import Tuple

logger = logging.getLogger(__name__)


class DownloadLimitExceeded(Exception):
    """Exception raised when download limits are exceeded."""

    pass


def validate_download_count(count: int, max_count: int) -> Tuple[bool, str]:
    """
    Validate that the number of documents to download is within the allowed limit.

    Args:
        count: Number of documents requested for download
        max_count: Maximum allowed documents per job

    Returns:
        Tuple of (is_valid, error_message)
        - is_valid: True if count is within limit, False otherwise
        - error_message: Empty string if valid, descriptive error if invalid
    """
    if count > max_count:
        error_msg = f"Too many documents. Maximum {max_count} downloads allowed per job, but {count} requested."
        logger.warning(f"Download count validation failed: {error_msg}")
        return False, error_msg

    return True, ""


def validate_cumulative_size(
    current_bytes: int, new_bytes: int, max_bytes: int
) -> Tuple[bool, str]:
    """
    Validate that the cumulative download size is within the allowed limit.

    Args:
        current_bytes: Total bytes downloaded so far
        new_bytes: Bytes just downloaded or about to be added
        max_bytes: Maximum allowed cumulative download size in bytes

    Returns:
        Tuple of (is_valid, error_message)
        - is_valid: True if cumulative size is within limit, False otherwise
        - error_message: Empty string if valid, descriptive error if invalid
    """
    total_bytes = current_bytes + new_bytes

    if total_bytes > max_bytes:
        current_mb = bytes_to_mb(current_bytes)
        total_mb = bytes_to_mb(total_bytes)
        max_mb = bytes_to_mb(max_bytes)

        error_msg = (
            f"Download size limit exceeded. "
            f"Current: {current_mb:.2f}MB, "
            f"Attempted total: {total_mb:.2f}MB, "
            f"Maximum allowed: {max_mb:.2f}MB"
        )
        logger.warning(f"Download size validation failed: {error_msg}")
        return False, error_msg

    return True, ""


def bytes_to_mb(bytes_value: int) -> float:
    """Convert bytes to megabytes."""
    return bytes_value / (1024 * 1024)


def bytes_to_human_readable(bytes_value: int) -> str:
    """
    Convert bytes to human-readable format (KB, MB, GB).

    Args:
        bytes_value: Size in bytes

    Returns:
        Human-readable string (e.g., "1.5 GB", "500.2 MB", "10.0 KB")
    """
    if bytes_value < 1024:
        return f"{bytes_value} B"
    elif bytes_value < 1024 * 1024:
        return f"{bytes_value / 1024:.1f} KB"
    elif bytes_value < 1024 * 1024 * 1024:
        return f"{bytes_value / (1024 * 1024):.1f} MB"
    else:
        return f"{bytes_value / (1024 * 1024 * 1024):.2f} GB"
