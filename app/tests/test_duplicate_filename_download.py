"""Tests for duplicate filename handling in downloads and ZIP creation"""

import pytest
import tempfile
import os
import zipfile
from unittest.mock import patch, Mock
from app.services.pdf_orchestrator import download_document_from_url
from app.services.zip_creator import create_zip_from_local_files


class TestDownloadUniqueFilenames:
    """Tests for download_document_from_url unique filename generation"""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for downloads"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @patch("app.services.pdf_orchestrator.requests.get")
    def test_download_same_filename_urls_creates_unique_files(
        self, mock_get, temp_dir
    ):
        """Test that downloading files with same name creates unique local files"""
        # Mock response with PDF content
        mock_response = Mock()
        mock_response.headers = {"content-type": "application/pdf"}
        mock_response.raise_for_status = Mock()

        def mock_iter_content(chunk_size):
            yield b"%PDF-1.4\nTest PDF content"

        mock_response.iter_content = mock_iter_content
        mock_get.return_value = mock_response

        # Download two files with the same name
        result1 = download_document_from_url(
            "https://example.com/document.pdf", temp_dir
        )
        result2 = download_document_from_url(
            "https://other.com/document.pdf", temp_dir
        )

        assert result1["success"] is True
        assert result2["success"] is True

        # File paths should be different (unique)
        assert result1["file_path"] != result2["file_path"]

        # Both files should exist
        assert os.path.exists(result1["file_path"])
        assert os.path.exists(result2["file_path"])

        # Both files should be in temp_dir
        files_in_dir = os.listdir(temp_dir)
        assert len(files_in_dir) == 2

    @patch("app.services.pdf_orchestrator.requests.get")
    def test_download_returns_original_filename(self, mock_get, temp_dir):
        """Test that original filename is returned in download result"""
        mock_response = Mock()
        mock_response.headers = {"content-type": "application/pdf"}
        mock_response.raise_for_status = Mock()

        def mock_iter_content(chunk_size):
            yield b"%PDF-1.4\nTest PDF content"

        mock_response.iter_content = mock_iter_content
        mock_get.return_value = mock_response

        result = download_document_from_url(
            "https://example.com/my-important-document.pdf", temp_dir
        )

        assert result["success"] is True
        assert result["original_filename"] == "my-important-document.pdf"

        # The actual file path should be different (with unique suffix)
        assert "my-important-document.pdf" != os.path.basename(result["file_path"])
        assert result["file_path"].endswith(".pdf")

    @patch("app.services.pdf_orchestrator.requests.get")
    def test_download_returns_none_original_filename_for_unknown_extension(
        self, mock_get, temp_dir
    ):
        """Test that original_filename is None when URL has no valid extension"""
        mock_response = Mock()
        mock_response.headers = {"content-type": "application/pdf"}
        mock_response.raise_for_status = Mock()

        pdf_content = b"%PDF-1.4\nTest content"

        def mock_iter_content(chunk_size):
            yield pdf_content

        mock_response.iter_content = mock_iter_content
        mock_get.return_value = mock_response

        result = download_document_from_url(
            "https://example.com/download?id=12345",  # No extension
            temp_dir,
        )

        assert result["success"] is True
        assert result["original_filename"] is None

    @patch("app.services.pdf_orchestrator.requests.get")
    def test_download_returns_none_original_filename_for_generic_filename(
        self, mock_get, temp_dir
    ):
        """Test that original_filename is None for generic filenames like 'view' or 'download'"""
        mock_response = Mock()
        mock_response.headers = {"content-type": "application/pdf"}
        mock_response.raise_for_status = Mock()

        pdf_content = b"%PDF-1.4\nTest content"

        def mock_iter_content(chunk_size):
            yield pdf_content

        mock_response.iter_content = mock_iter_content
        mock_get.return_value = mock_response

        for url in [
            "https://example.com/view",
            "https://example.com/download",
            "https://example.com/file",
        ]:
            result = download_document_from_url(url, temp_dir)
            assert result["success"] is True
            assert result["original_filename"] is None

    @patch("app.services.pdf_orchestrator.requests.get")
    def test_download_error_includes_original_filename_as_none(
        self, mock_get, temp_dir
    ):
        """Test that failed downloads include original_filename as None"""
        mock_get.side_effect = Exception("Connection error")

        result = download_document_from_url(
            "https://example.com/test.pdf", temp_dir
        )

        assert result["success"] is False
        assert result["original_filename"] is None


class TestZipCreatorOriginalFilenames:
    """Tests for create_zip_from_local_files with original filenames"""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory"""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    def test_create_zip_with_original_filenames(self, temp_dir):
        """Test that ZIP uses original filenames when provided"""
        # Create test files with unique names (simulating download behavior)
        file1 = os.path.join(temp_dir, "report_abc123.pdf")
        file2 = os.path.join(temp_dir, "report_def456.pdf")

        with open(file1, "wb") as f:
            f.write(b"%PDF-1.4 content 1")
        with open(file2, "wb") as f:
            f.write(b"%PDF-1.4 content 2")

        output_dir = os.path.join(temp_dir, "output")
        os.makedirs(output_dir)

        # Create ZIP with original filenames
        result = create_zip_from_local_files(
            file_paths=[file1, file2],
            output_filename="archive",
            output_dir=output_dir,
            original_filenames=["report.pdf", "report.pdf"],  # Same name
        )

        assert result["success"] is True
        assert result["num_files"] == 2

        # Extract and check filenames in ZIP
        with zipfile.ZipFile(result["zip_path"], "r") as zipf:
            names = zipf.namelist()
            assert len(names) == 2
            # First file should be report.pdf
            assert "report.pdf" in names
            # Second should be deduplicated (report_1.pdf)
            assert "report_1.pdf" in names

    def test_create_zip_with_duplicate_original_filenames(self, temp_dir):
        """Test that duplicate original filenames are deduplicated in ZIP"""
        # Create 3 test files
        files = []
        for i in range(3):
            path = os.path.join(temp_dir, f"file_{i}.pdf")
            with open(path, "wb") as f:
                f.write(f"%PDF-1.4 content {i}".encode())
            files.append(path)

        output_dir = os.path.join(temp_dir, "output")
        os.makedirs(output_dir)

        # All original filenames are the same
        result = create_zip_from_local_files(
            file_paths=files,
            output_filename="archive",
            output_dir=output_dir,
            original_filenames=["document.pdf", "document.pdf", "document.pdf"],
        )

        assert result["success"] is True
        assert result["num_files"] == 3

        # Check ZIP contents
        with zipfile.ZipFile(result["zip_path"], "r") as zipf:
            names = sorted(zipf.namelist())
            assert len(names) == 3
            assert "document.pdf" in names
            assert "document_1.pdf" in names
            assert "document_2.pdf" in names

    def test_create_zip_with_none_original_filenames(self, temp_dir):
        """Test that None original filenames fall back to file path basename"""
        file1 = os.path.join(temp_dir, "unique_file1.pdf")
        file2 = os.path.join(temp_dir, "unique_file2.pdf")

        with open(file1, "wb") as f:
            f.write(b"%PDF-1.4 content 1")
        with open(file2, "wb") as f:
            f.write(b"%PDF-1.4 content 2")

        output_dir = os.path.join(temp_dir, "output")
        os.makedirs(output_dir)

        # Mix of None and actual filenames
        result = create_zip_from_local_files(
            file_paths=[file1, file2],
            output_filename="archive",
            output_dir=output_dir,
            original_filenames=[None, "custom_name.pdf"],
        )

        assert result["success"] is True

        # Check ZIP contents
        with zipfile.ZipFile(result["zip_path"], "r") as zipf:
            names = zipf.namelist()
            assert len(names) == 2
            # First file should use basename since original is None
            assert "unique_file1.pdf" in names
            # Second file should use the custom name
            assert "custom_name.pdf" in names

    def test_create_zip_without_original_filenames(self, temp_dir):
        """Test that ZIP works correctly without original_filenames parameter"""
        file1 = os.path.join(temp_dir, "file1.pdf")
        file2 = os.path.join(temp_dir, "file2.pdf")

        with open(file1, "wb") as f:
            f.write(b"%PDF-1.4 content 1")
        with open(file2, "wb") as f:
            f.write(b"%PDF-1.4 content 2")

        output_dir = os.path.join(temp_dir, "output")
        os.makedirs(output_dir)

        # No original_filenames - should use basenames
        result = create_zip_from_local_files(
            file_paths=[file1, file2],
            output_filename="archive",
            output_dir=output_dir,
        )

        assert result["success"] is True

        with zipfile.ZipFile(result["zip_path"], "r") as zipf:
            names = zipf.namelist()
            assert "file1.pdf" in names
            assert "file2.pdf" in names

    def test_create_zip_with_shorter_original_filenames_list(self, temp_dir):
        """Test that ZIP handles original_filenames list shorter than file_paths"""
        files = []
        for i in range(3):
            path = os.path.join(temp_dir, f"file_{i}.pdf")
            with open(path, "wb") as f:
                f.write(f"%PDF-1.4 content {i}".encode())
            files.append(path)

        output_dir = os.path.join(temp_dir, "output")
        os.makedirs(output_dir)

        # original_filenames is shorter than file_paths
        result = create_zip_from_local_files(
            file_paths=files,
            output_filename="archive",
            output_dir=output_dir,
            original_filenames=["custom1.pdf"],  # Only 1 name for 3 files
        )

        assert result["success"] is True

        with zipfile.ZipFile(result["zip_path"], "r") as zipf:
            names = zipf.namelist()
            assert len(names) == 3
            # First file uses custom name
            assert "custom1.pdf" in names
            # Other files use basenames
            assert "file_1.pdf" in names
            assert "file_2.pdf" in names
