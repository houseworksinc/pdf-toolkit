"""Tests for download limit validation functionality"""

import pytest
from app.services.limit_validator import (
    validate_download_count,
    validate_cumulative_size,
    bytes_to_mb,
    bytes_to_human_readable,
    DownloadLimitExceeded,
)


class TestValidateDownloadCount:
    """Tests for validate_download_count function"""

    def test_validate_count_within_limit(self):
        """Test validation passes when count is within limit"""
        is_valid, error_msg = validate_download_count(5, 10)
        assert is_valid is True
        assert error_msg == ""

    def test_validate_count_at_limit(self):
        """Test validation passes when count equals limit"""
        is_valid, error_msg = validate_download_count(10, 10)
        assert is_valid is True
        assert error_msg == ""

    def test_validate_count_exceeds_limit(self):
        """Test validation fails when count exceeds limit"""
        is_valid, error_msg = validate_download_count(15, 10)
        assert is_valid is False
        assert "Too many documents" in error_msg
        assert "Maximum 10 downloads allowed" in error_msg
        assert "15 requested" in error_msg

    def test_validate_count_single_document(self):
        """Test validation with limit of 1 document"""
        is_valid, error_msg = validate_download_count(1, 1)
        assert is_valid is True
        assert error_msg == ""

    def test_validate_count_exceeds_single_limit(self):
        """Test validation fails with 2 documents when limit is 1"""
        is_valid, error_msg = validate_download_count(2, 1)
        assert is_valid is False
        assert "Maximum 1 downloads allowed" in error_msg
        assert "2 requested" in error_msg

    def test_validate_count_zero_documents(self):
        """Test validation with zero documents (edge case)"""
        is_valid, error_msg = validate_download_count(0, 10)
        assert is_valid is True
        assert error_msg == ""


class TestValidateCumulativeSize:
    """Tests for validate_cumulative_size function"""

    def test_validate_size_within_limit(self):
        """Test validation passes when cumulative size is within limit"""
        current_bytes = 1024 * 1024  # 1 MB
        new_bytes = 2 * 1024 * 1024  # 2 MB
        max_bytes = 10 * 1024 * 1024  # 10 MB

        is_valid, error_msg = validate_cumulative_size(
            current_bytes, new_bytes, max_bytes
        )
        assert is_valid is True
        assert error_msg == ""

    def test_validate_size_at_limit(self):
        """Test validation passes when cumulative size equals limit"""
        current_bytes = 5 * 1024 * 1024  # 5 MB
        new_bytes = 5 * 1024 * 1024  # 5 MB
        max_bytes = 10 * 1024 * 1024  # 10 MB

        is_valid, error_msg = validate_cumulative_size(
            current_bytes, new_bytes, max_bytes
        )
        assert is_valid is True
        assert error_msg == ""

    def test_validate_size_exceeds_limit(self):
        """Test validation fails when cumulative size exceeds limit"""
        current_bytes = 5 * 1024 * 1024  # 5 MB
        new_bytes = 8 * 1024 * 1024  # 8 MB
        max_bytes = 10 * 1024 * 1024  # 10 MB

        is_valid, error_msg = validate_cumulative_size(
            current_bytes, new_bytes, max_bytes
        )
        assert is_valid is False
        assert "Download size limit exceeded" in error_msg
        assert "Current: 5.00MB" in error_msg
        assert "Attempted total: 13.00MB" in error_msg
        assert "Maximum allowed: 10.00MB" in error_msg

    def test_validate_size_first_chunk_exceeds(self):
        """Test validation fails when first download exceeds limit"""
        current_bytes = 0  # No previous downloads
        new_bytes = 15 * 1024 * 1024  # 15 MB
        max_bytes = 10 * 1024 * 1024  # 10 MB

        is_valid, error_msg = validate_cumulative_size(
            current_bytes, new_bytes, max_bytes
        )
        assert is_valid is False
        assert "Current: 0.00MB" in error_msg
        assert "Attempted total: 15.00MB" in error_msg

    def test_validate_size_small_amounts(self):
        """Test validation with small byte amounts"""
        current_bytes = 100  # 100 bytes
        new_bytes = 200  # 200 bytes
        max_bytes = 1024  # 1 KB

        is_valid, error_msg = validate_cumulative_size(
            current_bytes, new_bytes, max_bytes
        )
        assert is_valid is True
        assert error_msg == ""


class TestBytesToMb:
    """Tests for bytes_to_mb conversion function"""

    def test_bytes_to_mb_1mb(self):
        """Test converting exactly 1 MB"""
        result = bytes_to_mb(1024 * 1024)
        assert result == 1.0

    def test_bytes_to_mb_fractional(self):
        """Test converting fractional MB"""
        result = bytes_to_mb(1536 * 1024)  # 1.5 MB
        assert abs(result - 1.5) < 0.01

    def test_bytes_to_mb_zero(self):
        """Test converting zero bytes"""
        result = bytes_to_mb(0)
        assert result == 0.0

    def test_bytes_to_mb_large_value(self):
        """Test converting large byte value"""
        result = bytes_to_mb(1024 * 1024 * 1024)  # 1 GB = 1024 MB
        assert result == 1024.0


class TestBytesToHumanReadable:
    """Tests for bytes_to_human_readable conversion function"""

    def test_bytes_format(self):
        """Test formatting bytes (< 1 KB)"""
        assert bytes_to_human_readable(500) == "500 B"
        assert bytes_to_human_readable(1023) == "1023 B"

    def test_kilobytes_format(self):
        """Test formatting kilobytes"""
        assert bytes_to_human_readable(1024) == "1.0 KB"
        assert bytes_to_human_readable(2048) == "2.0 KB"
        assert bytes_to_human_readable(1536) == "1.5 KB"

    def test_megabytes_format(self):
        """Test formatting megabytes"""
        assert bytes_to_human_readable(1024 * 1024) == "1.0 MB"
        assert bytes_to_human_readable(5 * 1024 * 1024) == "5.0 MB"
        assert bytes_to_human_readable(int(1.5 * 1024 * 1024)) == "1.5 MB"

    def test_gigabytes_format(self):
        """Test formatting gigabytes"""
        assert bytes_to_human_readable(1024 * 1024 * 1024) == "1.00 GB"
        assert bytes_to_human_readable(2 * 1024 * 1024 * 1024) == "2.00 GB"

    def test_zero_bytes(self):
        """Test formatting zero bytes"""
        assert bytes_to_human_readable(0) == "0 B"


class TestDownloadLimitExceededException:
    """Tests for DownloadLimitExceeded exception"""

    def test_exception_can_be_raised(self):
        """Test that DownloadLimitExceeded can be raised"""
        with pytest.raises(DownloadLimitExceeded):
            raise DownloadLimitExceeded("Test error message")

    def test_exception_message(self):
        """Test that exception message is preserved"""
        error_msg = "Download size limit exceeded"
        with pytest.raises(DownloadLimitExceeded) as exc_info:
            raise DownloadLimitExceeded(error_msg)

        assert str(exc_info.value) == error_msg

    def test_exception_is_exception_subclass(self):
        """Test that DownloadLimitExceeded is an Exception subclass"""
        assert issubclass(DownloadLimitExceeded, Exception)
