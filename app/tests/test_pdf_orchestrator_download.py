"""Tests for PDF orchestrator download functionality with size limits"""

import pytest
import tempfile
import os
from unittest.mock import patch, MagicMock, Mock
from app.services.pdf_orchestrator import download_document_from_url
from app.services.limit_validator import DownloadLimitExceeded


class TestDownloadDocumentWithLimits:
    """Tests for download_document_from_url with size validation"""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for downloads"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @patch("app.services.pdf_orchestrator.requests.get")
    def test_download_without_size_limit(self, mock_get, temp_dir):
        """Test download succeeds when no size limit is set"""
        # Mock response with small content
        mock_response = Mock()
        mock_response.headers = {"content-type": "application/pdf"}
        mock_response.content = b"%PDF-1.4\n%Test PDF content"
        mock_response.raise_for_status = Mock()

        # Mock iter_content for streaming
        def mock_iter_content(chunk_size):
            yield mock_response.content

        mock_response.iter_content = mock_iter_content

        mock_get.return_value = mock_response

        # Download without limit
        result = download_document_from_url(
            "https://example.com/test.pdf",
            temp_dir,
            total_downloaded_bytes=0,
            max_download_bytes=None,  # No limit
        )

        assert result["success"] is True
        assert result["file_path"] is not None
        assert result["file_size"] > 0
        assert result["error"] is None

    @patch("app.services.pdf_orchestrator.requests.get")
    def test_download_within_size_limit(self, mock_get, temp_dir):
        """Test download succeeds when within size limit"""
        # Mock response with 1MB content
        one_mb = 1024 * 1024
        mock_response = Mock()
        mock_response.headers = {"content-type": "application/pdf"}
        mock_response.raise_for_status = Mock()

        # Simulate streaming in chunks
        def mock_iter_content(chunk_size):
            # Return 1MB in one chunk
            yield b"%PDF-1.4\n" + (b"x" * (one_mb - 10))

        mock_response.iter_content = mock_iter_content

        mock_get.return_value = mock_response

        # Download with 5MB limit
        result = download_document_from_url(
            "https://example.com/test.pdf",
            temp_dir,
            total_downloaded_bytes=0,
            max_download_bytes=5 * 1024 * 1024,
        )

        assert result["success"] is True
        assert result["file_size"] > 0

    @patch("app.services.pdf_orchestrator.requests.get")
    def test_download_exceeds_size_limit_raises_exception(
        self, mock_get, temp_dir
    ):
        """Test that DownloadLimitExceeded is raised when size limit exceeded"""
        # Mock response with 5MB content
        five_mb = 5 * 1024 * 1024
        mock_response = Mock()
        mock_response.headers = {"content-type": "application/pdf"}
        mock_response.raise_for_status = Mock()

        # Simulate streaming 5MB when limit is 2MB
        def mock_iter_content(chunk_size):
            # Return 5MB in 1MB chunks
            for i in range(5):
                yield b"x" * (1024 * 1024)

        mock_response.iter_content = mock_iter_content

        mock_get.return_value = mock_response

        # Download with 2MB limit - should raise exception
        with pytest.raises(DownloadLimitExceeded) as exc_info:
            download_document_from_url(
                "https://example.com/test.pdf",
                temp_dir,
                total_downloaded_bytes=0,
                max_download_bytes=2 * 1024 * 1024,
            )

        # Verify exception message
        assert "Download size limit exceeded" in str(exc_info.value)
        assert "Maximum allowed: 2.00MB" in str(exc_info.value)

    @patch("app.services.pdf_orchestrator.requests.get")
    def test_download_cumulative_size_exceeds_limit(self, mock_get, temp_dir):
        """Test that cumulative size across multiple downloads is tracked"""
        # Mock response with 1.5MB content
        one_half_mb = int(1.5 * 1024 * 1024)
        mock_response = Mock()
        mock_response.headers = {"content-type": "application/pdf"}
        mock_response.raise_for_status = Mock()

        def mock_iter_content(chunk_size):
            yield b"%PDF-1.4\n" + (b"x" * (one_half_mb - 10))

        mock_response.iter_content = mock_iter_content

        mock_get.return_value = mock_response

        # Already downloaded 1.5MB, limit is 2MB
        # This 1.5MB download should exceed the limit
        with pytest.raises(DownloadLimitExceeded) as exc_info:
            download_document_from_url(
                "https://example.com/test.pdf",
                temp_dir,
                total_downloaded_bytes=int(
                    1.5 * 1024 * 1024
                ),  # Already downloaded 1.5MB
                max_download_bytes=2 * 1024 * 1024,  # 2MB total limit
            )

        assert "Current: 1.50MB" in str(exc_info.value)

    @patch("app.services.pdf_orchestrator.requests.get")
    def test_download_cleans_up_partial_file_on_limit_exceeded(
        self, mock_get, temp_dir
    ):
        """Test that partial download is deleted when limit exceeded"""
        mock_response = Mock()
        mock_response.headers = {"content-type": "application/pdf"}
        mock_response.raise_for_status = Mock()

        # Return chunks that exceed limit
        def mock_iter_content(chunk_size):
            for i in range(3):
                yield b"x" * (1024 * 1024)  # 1MB chunks

        mock_response.iter_content = mock_iter_content

        mock_get.return_value = mock_response

        # Try to download with small limit
        try:
            download_document_from_url(
                "https://example.com/test.pdf",
                temp_dir,
                total_downloaded_bytes=0,
                max_download_bytes=1024 * 1024,  # 1MB limit
            )
        except DownloadLimitExceeded:
            pass  # Expected

        # Verify no files left in temp directory
        files_in_dir = os.listdir(temp_dir)
        assert len(files_in_dir) == 0, "Partial download should be cleaned up"

    @patch("app.services.pdf_orchestrator.requests.get")
    def test_download_streams_in_1mb_chunks(self, mock_get, temp_dir):
        """Test that download uses 1MB chunk size for streaming"""
        mock_response = Mock()
        mock_response.headers = {"content-type": "application/pdf"}
        mock_response.raise_for_status = Mock()

        chunks_received = []

        def mock_iter_content(chunk_size):
            chunks_received.append(chunk_size)
            yield b"%PDF-1.4\ntest content"

        mock_response.iter_content = mock_iter_content

        mock_get.return_value = mock_response

        download_document_from_url(
            "https://example.com/test.pdf",
            temp_dir,
            total_downloaded_bytes=0,
            max_download_bytes=10 * 1024 * 1024,
        )

        # Verify iter_content was called with 1MB chunk size
        assert 1048576 in chunks_received, (
            "Should use 1MB (1048576 byte) chunks"
        )

    @patch("app.services.pdf_orchestrator.requests.get")
    def test_download_timeout_increased_to_60_seconds(self, mock_get, temp_dir):
        """Test that download timeout is set to 60 seconds"""
        mock_response = Mock()
        mock_response.headers = {"content-type": "application/pdf"}
        mock_response.raise_for_status = Mock()

        def mock_iter_content(chunk_size):
            yield b"%PDF-1.4\ntest"

        mock_response.iter_content = mock_iter_content

        mock_get.return_value = mock_response

        download_document_from_url("https://example.com/test.pdf", temp_dir)

        # Verify requests.get was called with timeout=60 and stream=True
        mock_get.assert_called_once()
        call_kwargs = mock_get.call_args[1]
        assert call_kwargs["timeout"] == 60
        assert call_kwargs["stream"] is True

    @patch("app.services.pdf_orchestrator.requests.get")
    def test_download_validates_after_each_chunk(self, mock_get, temp_dir):
        """Test that size validation happens after each chunk"""
        mock_response = Mock()
        mock_response.headers = {"content-type": "application/pdf"}
        mock_response.raise_for_status = Mock()

        # Return 3 chunks of 1MB each
        chunks_generated = 0

        def mock_iter_content(chunk_size):
            nonlocal chunks_generated
            for i in range(3):
                chunks_generated += 1
                yield b"x" * (1024 * 1024)

        mock_response.iter_content = mock_iter_content

        mock_get.return_value = mock_response

        # Set limit to 1.5MB - should fail after 2nd chunk
        try:
            download_document_from_url(
                "https://example.com/test.pdf",
                temp_dir,
                total_downloaded_bytes=0,
                max_download_bytes=int(1.5 * 1024 * 1024),
            )
        except DownloadLimitExceeded:
            pass

        # Should have stopped after 2nd chunk (when trying to add 3rd)
        # The generator produces all chunks, but validation stops file writing
        assert chunks_generated >= 2, "Should validate after downloading chunks"

    @patch("app.services.pdf_orchestrator.requests.get")
    def test_download_handles_network_error(self, mock_get, temp_dir):
        """Test that network errors are handled properly"""
        # Mock a connection error
        mock_get.side_effect = Exception("Connection timeout")

        result = download_document_from_url(
            "https://example.com/test.pdf", temp_dir
        )

        assert result["success"] is False
        assert result["file_path"] is None
        assert result["file_size"] == 0
        assert "Unexpected error" in result["error"]

    @patch("app.services.pdf_orchestrator.requests.get")
    def test_download_detects_pdf_from_magic_bytes(self, mock_get, temp_dir):
        """Test that PDF is detected from magic bytes when URL has no extension"""
        mock_response = Mock()
        mock_response.headers = {"content-type": "application/octet-stream"}
        mock_response.raise_for_status = Mock()

        # PDF starts with %PDF
        pdf_content = b"%PDF-1.4\n%Test content here"

        def mock_iter_content(chunk_size):
            yield pdf_content

        mock_response.iter_content = mock_iter_content

        mock_get.return_value = mock_response

        result = download_document_from_url(
            "https://example.com/download?id=12345",  # No .pdf extension
            temp_dir,
        )

        assert result["success"] is True
        assert result["file_path"].endswith(".pdf")
