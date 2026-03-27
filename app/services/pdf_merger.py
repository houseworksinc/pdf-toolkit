import fitz  # PyMuPDF
import os
import requests
import tempfile
import subprocess
import shutil
import uuid
from typing import List, Dict
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class DocumentNotFoundError(Exception):
    """Raised when a document file cannot be found."""

    pass


class MergeError(Exception):
    """Raised when document merge operation fails."""

    pass


class UnsupportedFormatError(Exception):
    """Raised when file format is not supported."""

    pass


# Supported file format categories
SUPPORTED_FORMATS = {
    "pdf": [".pdf"],
    "image": [".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".tif", ".svg"],
    "document": [
        ".doc",
        ".docx",
        ".odt",
        ".rtf",
        ".txt",
        ".epub",
        ".fb2",
        ".html",
        ".htm",
        ".wpd",
    ],
    "spreadsheet": [".xls", ".xlsx", ".xlsm", ".ods", ".csv", ".tsv"],
    "presentation": [".ppt", ".pptx", ".odp"],
    "drawing": [".odg", ".vsd", ".vsdx"],
}

# Flatten all supported extensions
ALL_SUPPORTED_EXTENSIONS = [
    ext for formats in SUPPORTED_FORMATS.values() for ext in formats
]


def _get_file_extension(file_path: str) -> str:
    """Extract and normalize file extension."""
    return Path(file_path).suffix.lower()


def _get_file_category(file_path: str) -> str:
    """
    Determine the category of a file based on its extension.

    Returns:
        Category name: 'pdf', 'image', 'document', 'spreadsheet', 'presentation', 'drawing'

    Raises:
        UnsupportedFormatError: If file extension is not supported
    """
    ext = _get_file_extension(file_path)

    if not ext:
        raise UnsupportedFormatError(f"File has no extension: {file_path}")

    for category, extensions in SUPPORTED_FORMATS.items():
        if ext in extensions:
            return category

    raise UnsupportedFormatError(
        f"Unsupported file format: {ext}\n"
        f"Supported formats: {', '.join(ALL_SUPPORTED_EXTENSIONS)}"
    )


def _convert_with_unoserver(
    file_path: str, output_dir: str, download_url: str = None
) -> str:
    """
    Convert document/spreadsheet/presentation files to PDF using UnoServer.

    Converts files like:
    - Documents: DOCX, ODT, EPUB, RTF, TXT, HTML
    - Spreadsheets: XLSX, ODS, CSV, TSV
    - Presentations: PPTX, ODP
    - Drawings: ODG, VSDX

    Args:
        file_path: Path to the source file
        output_dir: Directory to save the converted PDF
        download_url: Optional URL to download file from (if file_path doesn't exist)

    Returns:
        Path to the converted PDF file

    Raises:
        Exception: If UnoServer conversion fails
    """
    from app.services.unoserver_converter import UnoServerConverter

    file_extension = _get_file_extension(file_path)
    temp_dir = tempfile.TemporaryDirectory()
    temp_file_name = str(uuid.uuid4()) + file_extension
    temp_file_path = os.path.join(temp_dir.name, temp_file_name)

    if download_url:
        # Download file from URL
        response = requests.get(download_url)
        response.raise_for_status()
        with open(temp_file_path, "wb") as f:
            f.write(response.content)
    else:
        # Copy local file to temp directory
        shutil.copy(file_path, temp_file_path)

    try:
        logger.info(f"Converting {temp_file_path} to PDF using UnoServer")
        converter = UnoServerConverter()

        # Check if UnoServer is available
        if not converter.is_available():
            raise Exception(
                "UnoServer is not available. "
                "Ensure the unoserver container is running."
            )

        # Convert using UnoServer
        converted_pdf_path = converter.convert_to_pdf(temp_file_path, output_dir)

        logger.info(f"UnoServer conversion successful for {temp_file_path}")
        return converted_pdf_path

    except Exception as e:
        logger.error(f"Error converting {temp_file_path}: {e}")
        raise
    finally:
        temp_dir.cleanup()


def _download_file(url: str, output_dir: str) -> str:
    """
    Download a file from URL to the specified directory.

    Args:
        url: URL to download from
        output_dir: Directory to save the downloaded file

    Returns:
        Path to the downloaded file

    Raises:
        DocumentNotFoundError: If the file cannot be downloaded
    """
    try:
        logger.info(f"Downloading file from {url}")
        response = requests.get(url, timeout=30)
        response.raise_for_status()

        # Get filename from URL or use a generated name
        filename = os.path.basename(url.split("?")[0]) or f"file_{hash(url)}"

        # If no extension, try to get from content-type
        if not Path(filename).suffix:
            content_type = response.headers.get("content-type", "")
            if "pdf" in content_type:
                filename += ".pdf"
            elif "png" in content_type:
                filename += ".png"
            elif "jpeg" in content_type or "jpg" in content_type:
                filename += ".jpg"

        file_path = os.path.join(output_dir, filename)

        with open(file_path, "wb") as f:
            f.write(response.content)

        logger.info(f"Successfully downloaded file to {file_path}")
        return file_path

    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to download file from {url}: {str(e)}")
        raise DocumentNotFoundError(
            f"Failed to download file from {url}: {str(e)}"
        )


# NOTE: The merge_documents_from_urls function has been deprecated.
# Use download_document_from_url() + merge_local_pdfs() from pdf_orchestrator.py instead.
# This approach allows for better individual document status tracking.
