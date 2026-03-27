import zipfile
import os
import tempfile
from typing import List, Dict, Optional
from pathlib import Path
import logging
from app.services.pdf_orchestrator import download_document_from_url
from app.services.limit_validator import DownloadLimitExceeded

logger = logging.getLogger(__name__)


def _get_unique_filename(filename: str, used_names: set) -> str:
    """
    Generate a unique filename by adding a numeric suffix if needed.

    Args:
        filename: Original filename (e.g., "document.pdf")
        used_names: Set of filenames already used in the archive

    Returns:
        Unique filename (e.g., "document_1.pdf" if "document.pdf" exists)
    """
    if filename not in used_names:
        used_names.add(filename)
        return filename

    name, ext = os.path.splitext(filename)
    counter = 1

    while True:
        new_filename = f"{name}_{counter}{ext}"
        if new_filename not in used_names:
            used_names.add(new_filename)
            return new_filename
        counter += 1


class ZipCreationError(Exception):
    """Raised when ZIP archive creation fails."""

    pass


class DocumentNotFoundError(Exception):
    """Raised when a document file cannot be found."""

    pass


def create_zip_from_urls(
    document_urls: List[str],
    output_filename: str = "archive",
    output_dir: str = None,
    max_download_bytes: Optional[int] = None,
) -> Dict:
    """
    Create a ZIP archive from multiple files downloaded from URLs.

    Accepts files of any type and compresses them into a single ZIP file.
    All files are stored at the root level of the ZIP (no directory structure).

    Args:
        document_urls: List of URLs to files to include in the archive
        output_filename: Name for output ZIP file (without .zip extension)
        output_dir: Directory to save output file (default: temp directory)
        max_download_bytes: Maximum allowed cumulative download size in bytes (None = no limit)

    Returns:
        Dict with keys:
            - success: bool
            - zip_path: str (path to created ZIP)
            - file_size: int (size in bytes)
            - num_files: int (number of files in ZIP)
            - error: str (if success=False)

    Raises:
        DocumentNotFoundError: If any source file cannot be downloaded
        DownloadLimitExceeded: If cumulative download size exceeds limit
        ZipCreationError: If ZIP creation fails
    """
    if not document_urls:
        raise ZipCreationError("No files provided for archiving")

    # Create output directory if not specified
    if output_dir is None:
        output_dir = tempfile.mkdtemp()
    else:
        Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Ensure output filename has .zip extension
    if not output_filename.endswith(".zip"):
        output_filename = f"{output_filename}.zip"

    output_path = os.path.join(output_dir, output_filename)

    # Create temporary directory for downloads
    download_dir = tempfile.mkdtemp()

    # Initialize cumulative download tracking
    total_downloaded_bytes = 0

    try:
        # Download all files with size validation
        logger.info(f"Downloading {len(document_urls)} files for ZIP archive")
        downloaded_files = []
        for idx, url in enumerate(document_urls):
            try:
                # Download file with streaming and size validation
                result = download_document_from_url(
                    url=url,
                    output_dir=download_dir,
                    total_downloaded_bytes=total_downloaded_bytes,
                    max_download_bytes=max_download_bytes,
                )

                if result["success"]:
                    file_path = result["file_path"]
                    file_size = result["file_size"]
                    downloaded_files.append(file_path)
                    total_downloaded_bytes += file_size
                    logger.info(
                        f"Downloaded {idx + 1}/{len(document_urls)}: {os.path.basename(file_path)} ({file_size} bytes)"
                    )
                else:
                    error_msg = result.get("error", "Unknown error")
                    logger.error(f"Failed to download {url}: {error_msg}")
                    raise DocumentNotFoundError(
                        f"Failed to download file from {url}: {error_msg}"
                    )

            except DownloadLimitExceeded as e:
                # Re-raise limit exceeded errors for worker to handle
                logger.error(
                    f"Download limit exceeded while downloading {url}: {str(e)}"
                )
                raise
            except DocumentNotFoundError:
                # Re-raise document not found errors
                raise

        # Create ZIP archive
        logger.info(f"Creating ZIP archive with {len(downloaded_files)} files")
        used_names = set()
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for file_path in downloaded_files:
                # Use only the filename (no directory structure)
                # Handle duplicate filenames by adding numeric suffix
                original_name = os.path.basename(file_path)
                arcname = _get_unique_filename(original_name, used_names)
                zipf.write(file_path, arcname=arcname)
                if arcname != original_name:
                    logger.info(
                        f"Added to ZIP: {arcname} (renamed from {original_name})"
                    )
                else:
                    logger.info(f"Added to ZIP: {arcname}")

        # Get file size
        file_size = os.path.getsize(output_path)

        logger.info(
            f"Successfully created ZIP archive at {output_path} ({file_size} bytes)"
        )

        return {
            "success": True,
            "zip_path": output_path,
            "file_size": file_size,
            "num_files": len(downloaded_files),
        }

    except DownloadLimitExceeded:
        # Re-raise download limit errors for worker to handle
        raise

    except DocumentNotFoundError:
        # Re-raise document not found errors
        raise

    except Exception as e:
        logger.error(f"ZIP creation failed: {str(e)}")
        raise ZipCreationError(f"Failed to create ZIP archive: {str(e)}")

    finally:
        # Clean up downloaded files
        try:
            import shutil

            if os.path.exists(download_dir):
                shutil.rmtree(download_dir)
                logger.info(f"Cleaned up download directory: {download_dir}")
        except Exception as e:
            logger.warning(f"Failed to clean up download directory: {str(e)}")


def create_zip_from_local_files(
    file_paths: List[str],
    output_filename: str,
    output_dir: str,
    original_filenames: Optional[List[str]] = None,
) -> Dict:
    """
    Create a ZIP archive from multiple local files.

    This function is used by process-and-zip to create a ZIP from already processed/downloaded files.
    All files are stored at the root level of the ZIP (no directory structure).

    Args:
        file_paths: List of local file paths to include in the archive
        output_filename: Name for output ZIP file (without .zip extension)
        output_dir: Directory to save output file
        original_filenames: Optional list of original filenames to use in the ZIP archive.
                          Must be same length as file_paths if provided. None entries
                          will use the basename from file_path.

    Returns:
        Dict with keys:
            - success: bool
            - zip_path: str (path to created ZIP)
            - file_size: int (size in bytes)
            - num_files: int (number of files in ZIP)
            - error: str (if success=False)

    Raises:
        ZipCreationError: If ZIP creation fails or files don't exist
    """
    if not file_paths:
        raise ZipCreationError("No files provided for archiving")

    # Validate all files exist
    for file_path in file_paths:
        if not os.path.exists(file_path):
            raise ZipCreationError(f"File not found: {file_path}")

    # Create output directory if it doesn't exist
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Ensure output filename has .zip extension
    if not output_filename.endswith(".zip"):
        output_filename = f"{output_filename}.zip"

    output_path = os.path.join(output_dir, output_filename)

    try:
        # Create ZIP archive
        logger.info(f"Creating ZIP archive with {len(file_paths)} local files")
        used_names = set()
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for idx, file_path in enumerate(file_paths):
                # Determine the name to use in the archive
                # Priority: original_filenames > basename of file_path
                if original_filenames and idx < len(original_filenames) and original_filenames[idx]:
                    desired_name = original_filenames[idx]
                else:
                    desired_name = os.path.basename(file_path)

                # Handle duplicate filenames by adding numeric suffix
                arcname = _get_unique_filename(desired_name, used_names)
                zipf.write(file_path, arcname=arcname)
                if arcname != desired_name:
                    logger.info(
                        f"Added to ZIP: {arcname} (renamed from {desired_name})"
                    )
                else:
                    logger.info(f"Added to ZIP: {arcname}")

        # Get file size
        file_size = os.path.getsize(output_path)

        logger.info(
            f"Successfully created ZIP archive at {output_path} ({file_size} bytes)"
        )

        return {
            "success": True,
            "zip_path": output_path,
            "file_size": file_size,
            "num_files": len(file_paths),
            "error": None,
        }

    except Exception as e:
        logger.error(f"ZIP creation from local files failed: {str(e)}")
        return {
            "success": False,
            "zip_path": None,
            "file_size": 0,
            "num_files": 0,
            "error": f"Failed to create ZIP archive: {str(e)}",
        }
