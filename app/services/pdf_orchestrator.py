"""
PDF Orchestrator Service

This module provides unified orchestration functions for PDF generation and document handling.
It serves as a wrapper layer that coordinates between different PDF services.
"""

import os
import requests
import tempfile
import logging
import mimetypes
from pathlib import Path
from typing import Dict, Any, Optional

from app.services.pdf_generator import generate_pdf, generate_pdf_dynamic
from app.services.limit_validator import (
    validate_cumulative_size,
    DownloadLimitExceeded,
)

logger = logging.getLogger(__name__)


# Supported file format categories and extensions
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

# Flatten all supported extensions for easy lookup
ALL_SUPPORTED_EXTENSIONS = [
    ext for formats in SUPPORTED_FORMATS.values() for ext in formats
]

# Standard page sizes in points (72 dpi)
PAGE_SIZES = {
    "A4": (595.0, 842.0),
    "LETTER": (612.0, 792.0),
}


def optimize_pdf(pdf_path: str) -> str:
    """
    Re-save a PDF with garbage collection, deflation, and stream cleaning
    to reduce file size. Non-blocking: logs a warning on failure and returns
    the original path unchanged.

    Args:
        pdf_path: Path to the PDF file to optimize

    Returns:
        The same pdf_path (optimized in-place)
    """
    import fitz

    try:
        doc = fitz.open(pdf_path)
        doc.save(pdf_path, garbage=4, deflate=True, clean=True)
        doc.close()
        logger.info(f"Optimized PDF: {os.path.basename(pdf_path)}")
    except Exception as e:
        logger.warning(f"PDF optimization failed (non-blocking): {e}")
    return pdf_path


def create_empty_template(output_dir: str) -> str:
    """
    Create an empty Word document template.

    Args:
        output_dir: Directory to save the empty template

    Returns:
        Path to the created empty template file
    """
    from docx import Document

    try:
        logger.info("Creating empty Word template")

        # Create a blank document
        doc = Document()

        # Save to output directory
        template_path = os.path.join(
            output_dir, f"empty_template_{os.urandom(8).hex()}.docx"
        )
        doc.save(template_path)

        logger.info(f"Empty template created at {template_path}")
        return template_path

    except Exception as e:
        logger.error(f"Failed to create empty template: {str(e)}")
        raise Exception(f"Empty template creation failed: {str(e)}")


def convert_image_to_pdf_page(image_path: str, page_size: str = "A4") -> str:
    """
    Convert an image file to a single-page PDF with the specified page dimensions.

    The image is scaled to fit within the page while maintaining its aspect ratio,
    and centered on the page.

    Args:
        image_path: Path to the source image file
        page_size: Page size key ("A4" or "LETTER"). Defaults to "A4".

    Returns:
        Path to the converted PDF file
    """
    import fitz  # PyMuPDF

    page_width, page_height = PAGE_SIZES.get(page_size, PAGE_SIZES["A4"])

    # Open image to get its dimensions
    img_doc = fitz.open(image_path)
    try:
        # Get image as a pixmap for dimensions
        page = img_doc[0]
        img_width = page.rect.width
        img_height = page.rect.height
    finally:
        img_doc.close()

    # Calculate scale to fit within page while maintaining aspect ratio
    # Leave a small margin (36 points = 0.5 inch on each side)
    margin = 36
    available_width = page_width - 2 * margin
    available_height = page_height - 2 * margin

    scale_x = available_width / img_width
    scale_y = available_height / img_height
    scale = min(scale_x, scale_y, 1.0)  # Don't upscale

    scaled_width = img_width * scale
    scaled_height = img_height * scale

    # Center image on page
    x_offset = (page_width - scaled_width) / 2
    y_offset = (page_height - scaled_height) / 2

    # Create new PDF with the specified page size
    pdf_doc = fitz.open()
    try:
        pdf_page = pdf_doc.new_page(width=page_width, height=page_height)
        img_rect = fitz.Rect(
            x_offset, y_offset,
            x_offset + scaled_width, y_offset + scaled_height,
        )
        pdf_page.insert_image(img_rect, filename=image_path)

        # Save to a temporary file next to the source image
        output_dir = os.path.dirname(image_path)
        output_path = os.path.join(
            output_dir, f"img2pdf_{os.urandom(8).hex()}.pdf"
        )
        pdf_doc.save(output_path, garbage=4, deflate=True, clean=True)

        logger.info(
            f"Converted image to {page_size} PDF: {os.path.basename(image_path)} -> {os.path.basename(output_path)}"
        )
        return output_path
    finally:
        pdf_doc.close()


def resize_pdf_to_page_size(pdf_path: str, page_size: str = "A4") -> str:
    """
    Resize all pages of a PDF to the specified page dimensions.

    Each source page is scaled to fit within the target page size while
    maintaining its aspect ratio, and centered on the new page.

    Args:
        pdf_path: Path to the PDF file to resize
        page_size: Page size key ("A4" or "LETTER"). Defaults to "A4".

    Returns:
        Path to the resized PDF (overwrites the original)
    """
    import fitz  # PyMuPDF

    target_width, target_height = PAGE_SIZES.get(page_size, PAGE_SIZES["A4"])

    src_doc = fitz.open(pdf_path)
    try:
        new_doc = fitz.open()
        try:
            for page_num in range(len(src_doc)):
                new_page = new_doc.new_page(width=target_width, height=target_height)
                new_page.show_pdf_page(new_page.rect, src_doc, page_num)

            new_doc.save(pdf_path, garbage=4, deflate=True, clean=True)
            logger.info(
                f"Resized PDF to {page_size}: {os.path.basename(pdf_path)} ({len(src_doc)} pages)"
            )
            return pdf_path
        finally:
            new_doc.close()
    finally:
        src_doc.close()



def generate_single_pdf(
    template_path: str,
    data: Dict[str, Any],
    mode: str = "static",
    output_dir: Optional[str] = None,
    output_filename: Optional[str] = None,
    page_size: str = "A4",
) -> Dict[str, Any]:
    """
    Generate a single PDF using either static or dynamic mode.

    This is a unified wrapper around generate_pdf() and generate_pdf_dynamic().

    Args:
        template_path: Path to the downloaded Word template file
        data: JSON data to inject into the template
        mode: Generation mode - 'static' or 'dynamic' (default: 'static')
        output_dir: Directory to save the output PDF (default: temp directory)
        output_filename: Base filename for output (without extension)

    Returns:
        Dictionary with:
            - success: bool
            - pdf_path: str (path to generated PDF)
            - docx_path: str (path to generated DOCX, only for dynamic)
            - error: str (if success=False)
            - processing_time: float (seconds)
    """
    try:
        # Create output directory if not specified
        if output_dir is None:
            output_dir = tempfile.mkdtemp()
        else:
            Path(output_dir).mkdir(parents=True, exist_ok=True)

        # Generate output filename if not provided
        if output_filename is None:
            output_filename = f"output_{os.urandom(8).hex()}"

        if mode == "dynamic":
            # Use dynamic PDF generation
            result = generate_pdf_dynamic(
                template_path=template_path,
                json_data=data,
                output_dir=output_dir,
                output_filename=output_filename,
            )

            # Resize generated PDF pages to target page size
            if result.get("success") and result.get("pdf_path"):
                resize_pdf_to_page_size(result["pdf_path"], page_size)

            return result

        else:
            # Use static PDF generation (default)
            pdf_path = generate_pdf(
                template_path=template_path,
                json_data=data,
                output_dir=output_dir,
            )

            # Resize generated PDF pages to target page size
            resize_pdf_to_page_size(pdf_path, page_size)

            return {
                "success": True,
                "pdf_path": pdf_path,
                "error": None,
                "processing_time": 0.0,  # generate_pdf doesn't track time
            }

    except Exception as e:
        logger.error(f"PDF generation failed (mode={mode}): {str(e)}")
        return {
            "success": False,
            "pdf_path": None,
            "error": str(e),
            "processing_time": 0.0,
        }


def download_template(
    template_url: Optional[str],
    output_dir: str,
    use_empty_template: bool = False,
    template_hash: Optional[str] = None,
    enable_cache: bool = True,
) -> str:
    """
    Download a Word template file from a URL, or create an empty template if requested.

    Supports caching when template_hash is provided. Cached templates are stored
    on the filesystem with metadata in Redis. TTL is refreshed on each access.

    Args:
        template_url: URL to download the template from (optional if use_empty_template is True)
        output_dir: Directory to save the downloaded template
        use_empty_template: If True, create an empty template instead of downloading
        template_hash: Client-provided hash for cache lookup (optional, caching only if provided)
        enable_cache: Whether to use caching when template_hash is provided (default: True)

    Returns:
        Path to the downloaded or created template file

    Raises:
        Exception: If download fails or if template_url is missing when use_empty_template is False
    """
    # If use_empty_template flag is set, create an empty template
    if use_empty_template:
        logger.info("use_empty_template flag is True, creating empty template")
        return create_empty_template(output_dir)

    # Otherwise, template_url is required
    if not template_url:
        raise Exception(
            "template_url is required when use_empty_template is False"
        )

    # Check cache if template_hash is provided and caching is enabled
    if template_hash and enable_cache:
        try:
            from app.services.template_cache import get_cached_template, store_template

            # Try to get from cache
            cached_path = get_cached_template(template_hash, output_dir)
            if cached_path:
                logger.info(
                    f"Using cached template for hash={template_hash}"
                )
                return cached_path

            logger.info(
                f"Template cache MISS for hash={template_hash}, downloading from URL"
            )
        except Exception as e:
            logger.warning(
                f"Cache lookup failed, falling back to download: {e}"
            )

    try:
        logger.info(f"Downloading template from {template_url}")

        response = requests.get(template_url, timeout=30)
        response.raise_for_status()

        # Determine filename from URL or use default
        filename = os.path.basename(template_url.split("?")[0])
        if not filename or not filename.endswith(".docx"):
            filename = f"template_{os.urandom(8).hex()}.docx"

        template_path = os.path.join(output_dir, filename)

        with open(template_path, "wb") as f:
            f.write(response.content)

        logger.info(f"Template downloaded successfully to {template_path}")

        # Store in cache if template_hash is provided and caching is enabled
        if template_hash and enable_cache:
            try:
                from app.services.template_cache import store_template

                store_template(template_hash, template_path)
            except Exception as e:
                logger.warning(
                    f"Failed to cache template (non-blocking): {e}"
                )

        return template_path

    except requests.exceptions.RequestException as e:
        logger.error(
            f"Failed to download template from {template_url}: {str(e)}"
        )
        raise Exception(f"Template download failed: {str(e)}")


def download_document_from_url(
    url: str,
    output_dir: str,
    total_downloaded_bytes: int = 0,
    max_download_bytes: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Download a document from a URL with chunk-based streaming and size validation.

    Supports: PDF, images, documents (DOCX, DOC, ODT, etc.),
    spreadsheets (XLSX, CSV, etc.), presentations, and more.

    Args:
        url: URL to download the document from
        output_dir: Directory to save the downloaded file
        total_downloaded_bytes: Total bytes already downloaded in this job
        max_download_bytes: Maximum allowed cumulative download size in bytes (None = no limit)

    Returns:
        Dictionary with:
            - success: bool
            - file_path: str (path to downloaded file)
            - file_size: int (bytes)
            - original_filename: str (original filename from URL, for ZIP naming)
            - error: str (if success=False)
    """
    file_path = None
    original_filename = None

    try:
        logger.info(f"Downloading document from {url}")

        # Start streaming download
        response = requests.get(url, timeout=60, stream=True)
        response.raise_for_status()

        # Try to get filename from URL
        base_filename = os.path.basename(url.split("?")[0])

        # Check if filename has a valid extension
        has_valid_extension = any(
            base_filename.lower().endswith(e) for e in ALL_SUPPORTED_EXTENSIONS
        )

        # Store original filename for ZIP naming (only if it has valid extension)
        if has_valid_extension and base_filename not in ["view", "download", "file"]:
            original_filename = base_filename

        # Get content-type for extension detection
        content_type = (
            response.headers.get("content-type", "").split(";")[0].strip()
        )

        # Determine the extension for the downloaded file
        if (
            not base_filename
            or not has_valid_extension
            or base_filename in ["view", "download", "file"]
        ):
            # Try to get extension from content-type using mimetypes
            ext = (
                mimetypes.guess_extension(content_type)
                if content_type
                else None
            )

            # Fix common mimetypes issues
            if ext == ".htm":
                ext = ".html"
            elif ext == ".jpe":
                ext = ".jpg"

            # If mimetypes didn't help, we'll need to detect from first chunk
            if not ext:
                ext = None  # Will be determined from magic bytes

            # Generate unique filename (no original filename available)
            unique_suffix = os.urandom(4).hex()
            filename = f"document_{unique_suffix}{ext if ext else ''}"
        else:
            # Generate unique filename from original to prevent overwrites
            name, ext = os.path.splitext(base_filename)
            unique_suffix = os.urandom(4).hex()
            filename = f"{name}_{unique_suffix}{ext}"

        file_path = os.path.join(output_dir, filename)

        # Download file in chunks with size validation
        chunk_size = 1048576  # 1 MB chunks
        current_file_bytes = 0
        first_chunk = None

        with open(file_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:  # Filter out keep-alive new chunks
                    # Store first chunk for magic bytes detection if needed
                    if first_chunk is None:
                        first_chunk = chunk

                    # Validate cumulative size if limit is set
                    if max_download_bytes is not None:
                        is_valid, error_message = validate_cumulative_size(
                            total_downloaded_bytes,
                            current_file_bytes + len(chunk),
                            max_download_bytes,
                        )
                        if not is_valid:
                            # Close file and delete partial download
                            f.close()
                            if os.path.exists(file_path):
                                os.remove(file_path)
                            raise DownloadLimitExceeded(error_message)

                    # Write chunk to file
                    f.write(chunk)
                    current_file_bytes += len(chunk)

        # If extension wasn't determined earlier, detect from magic bytes
        if not has_valid_extension and first_chunk:
            content_start = first_chunk[:20]
            ext_detected = None

            if content_start.startswith(b"%PDF"):
                ext_detected = ".pdf"
            elif content_start.startswith(b"\x89PNG"):
                ext_detected = ".png"
            elif content_start.startswith(b"\xff\xd8\xff"):
                ext_detected = ".jpg"
            elif content_start.startswith(
                b"GIF87a"
            ) or content_start.startswith(b"GIF89a"):
                ext_detected = ".gif"
            elif content_start.startswith(b"PK\x03\x04"):
                # ZIP-based formats (DOCX, XLSX, PPTX, ODT, ODS, ODP)
                if "word" in content_type or "document" in content_type:
                    ext_detected = ".docx"
                elif "sheet" in content_type or "excel" in content_type:
                    ext_detected = ".xlsx"
                elif (
                    "presentation" in content_type
                    or "powerpoint" in content_type
                ):
                    ext_detected = ".pptx"
                else:
                    ext_detected = ".bin"
            else:
                ext_detected = ".bin"

            # Rename file if we detected a better extension
            if ext_detected and not filename.endswith(ext_detected):
                new_filename = f"document_{os.urandom(8).hex()}{ext_detected}"
                new_file_path = os.path.join(output_dir, new_filename)
                os.rename(file_path, new_file_path)
                file_path = new_file_path

        file_size = os.path.getsize(file_path)

        logger.info(
            f"Document downloaded successfully to {file_path} ({file_size} bytes)"
        )

        return {
            "success": True,
            "file_path": file_path,
            "file_size": file_size,
            "original_filename": original_filename,
            "error": None,
        }

    except DownloadLimitExceeded as e:
        # Don't catch this - let it propagate to the caller for special handling
        logger.error(f"Download limit exceeded for {url}: {str(e)}")
        raise
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to download document from {url}: {str(e)}")
        # Clean up partial download if it exists
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
        return {
            "success": False,
            "file_path": None,
            "file_size": 0,
            "original_filename": None,
            "error": f"Download failed: {str(e)}",
        }
    except Exception as e:
        logger.error(
            f"Unexpected error downloading document from {url}: {str(e)}"
        )
        # Clean up partial download if it exists
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
        return {
            "success": False,
            "file_path": None,
            "file_size": 0,
            "original_filename": None,
            "error": f"Unexpected error: {str(e)}",
        }


def merge_local_pdfs(
    pdf_paths: list, output_filename: str, output_dir: str, page_size: str = "A4"
) -> Dict[str, Any]:
    """
    Merge multiple local files into a single PDF.

    Supports all file formats:
    - PDFs: .pdf (Tier 1 - Direct merge)
    - Images: .png, .jpg, .jpeg, .gif, .bmp, .tiff, .tif, .svg (Tier 3 - PyMuPDF conversion)
    - Documents: .doc, .docx, .odt, .rtf, .txt, .epub, .fb2, .html, .htm, .wpd (Tier 2 - UnoServer)
    - Spreadsheets: .xls, .xlsx, .xlsm, .ods, .csv, .tsv (Tier 2 - UnoServer)
    - Presentations: .ppt, .pptx, .odp (Tier 2 - UnoServer)
    - Drawings: .odg, .vsd, .vsdx (Tier 2 - UnoServer)

    Args:
        pdf_paths: List of local file paths to documents to merge
        output_filename: Base name for the output file (without .pdf extension)
        output_dir: Directory to save the merged PDF

    Returns:
        Dictionary with:
            - success: bool
            - pdf_path: str (path to merged PDF)
            - file_size: int (bytes)
            - num_documents: int (number of documents merged)
            - error: str (if success=False)
    """
    try:
        import fitz  # PyMuPDF
        import subprocess
        import shutil

        if not pdf_paths:
            raise ValueError("No file paths provided for merging")

        logger.info(f"Merging {len(pdf_paths)} documents")

        # Ensure output filename has .pdf extension
        if not output_filename.endswith(".pdf"):
            output_filename = f"{output_filename}.pdf"

        output_path = os.path.join(output_dir, output_filename)

        def get_file_category(file_path: str) -> str:
            """Determine the category of a file based on its extension."""
            ext = Path(file_path).suffix.lower()
            if not ext:
                return "unknown"
            for category, extensions in SUPPORTED_FORMATS.items():
                if ext in extensions:
                    return category
            return "unknown"

        def convert_with_unoserver(file_path: str, temp_dir: str) -> str:
            """Convert document/spreadsheet/presentation files to PDF using UnoServer."""
            from app.services.unoserver_converter import UnoServerConverter

            try:
                logger.info(
                    f"Converting {os.path.basename(file_path)} to PDF using UnoServer"
                )
                converter = UnoServerConverter()

                # Check if UnoServer is available
                if not converter.is_available():
                    raise Exception(
                        "UnoServer is not available. "
                        "Ensure the unoserver container is running."
                    )

                # Convert using UnoServer
                converted_pdf_path = converter.convert_to_pdf(file_path, temp_dir)

                logger.info(
                    f"UnoServer conversion successful for {os.path.basename(file_path)}"
                )

                if not os.path.exists(converted_pdf_path):
                    raise Exception(
                        f"UnoServer conversion did not produce expected output: {converted_pdf_path}"
                    )

                return converted_pdf_path

            except Exception as e:
                logger.error(f"UnoServer conversion failed: {e}")
                raise Exception(f"UnoServer conversion failed: {e}")

        # Create temporary directory for conversions
        temp_conversion_dir = tempfile.mkdtemp()
        target_width, target_height = PAGE_SIZES.get(page_size, PAGE_SIZES["A4"])

        try:
            # Create new PDF document for merging
            merged_doc = fitz.open()

            def insert_pdf_with_page_size(source_doc):
                """Insert all pages from source_doc into merged_doc, resizing to target page size."""
                for page_num in range(len(source_doc)):
                    src_page = source_doc[page_num]
                    # Check if page already matches target size (within 1pt tolerance)
                    # AND is not rotated (rotation % 180 == 0)
                    # If rotated 90/270, width/height are swapped visually, so we must resize/render
                    is_correct_size = (
                        abs(src_page.rect.width - target_width) < 1
                        and abs(src_page.rect.height - target_height) < 1
                    )
                    is_upright = src_page.rotation % 180 == 0
                    
                    if is_correct_size and is_upright:
                        # Already correct size — insert directly (preserves text selectability)
                        merged_doc.insert_pdf(source_doc, from_page=page_num, to_page=page_num)
                    else:
                        # Resize: render source page onto a new page at target dimensions
                        new_page = merged_doc.new_page(width=target_width, height=target_height)
                        new_page.show_pdf_page(new_page.rect, source_doc, page_num)

            # Merge each document
            for idx, doc_path in enumerate(pdf_paths):
                logger.info(
                    f"Processing document {idx + 1}/{len(pdf_paths)}: {os.path.basename(doc_path)}"
                )

                # Check if file exists
                if not os.path.exists(doc_path):
                    raise FileNotFoundError(f"File not found: {doc_path}")

                category = get_file_category(doc_path)
                ext = Path(doc_path).suffix.lower()

                try:
                    if category == "pdf":
                        # Tier 1: PDF merge with page sizing
                        source_doc = fitz.open(doc_path)
                        try:
                            insert_pdf_with_page_size(source_doc)
                        finally:
                            source_doc.close()

                    elif category == "image":
                        # Tier 3: Image to PDF with page sizing
                        logger.info(
                            f"Converting image to {page_size} PDF: {os.path.basename(doc_path)}"
                        )
                        converted_pdf_path = convert_image_to_pdf_page(
                            doc_path, page_size=page_size
                        )
                        try:
                            source_doc = fitz.open(converted_pdf_path)
                            try:
                                insert_pdf_with_page_size(source_doc)
                            finally:
                                source_doc.close()
                        finally:
                            if os.path.exists(converted_pdf_path):
                                os.remove(converted_pdf_path)

                    elif category in [
                        "document",
                        "spreadsheet",
                        "presentation",
                        "drawing",
                    ]:
                        # Tier 2: UnoServer conversion + page sizing
                        logger.info(
                            f"Converting {category} to PDF using UnoServer: {os.path.basename(doc_path)}"
                        )
                        converted_pdf_path = convert_with_unoserver(
                            doc_path, temp_conversion_dir
                        )
                        source_doc = fitz.open(converted_pdf_path)
                        try:
                            insert_pdf_with_page_size(source_doc)
                        finally:
                            source_doc.close()
                            # Clean up temporary converted PDF
                            if os.path.exists(converted_pdf_path):
                                os.remove(converted_pdf_path)

                    elif ext == ".bin" or not ext:
                        # Unknown extension - try to detect from content
                        logger.info(
                            f"Unknown file type, attempting to detect: {os.path.basename(doc_path)}"
                        )
                        with open(doc_path, "rb") as f:
                            magic_bytes = f.read(20)

                        if magic_bytes.startswith(b"%PDF"):
                            # It's a PDF
                            source_doc = fitz.open(doc_path)
                            try:
                                insert_pdf_with_page_size(source_doc)
                            finally:
                                source_doc.close()
                        elif (
                            magic_bytes.startswith(b"\x89PNG")
                            or magic_bytes.startswith(b"\xff\xd8\xff")
                            or magic_bytes.startswith(b"GIF87a")
                            or magic_bytes.startswith(b"GIF89a")
                        ):
                            # It's an image - convert with page sizing
                            logger.info(
                                f"Detected as image, converting to {page_size} PDF: {os.path.basename(doc_path)}"
                            )
                            converted_pdf_path = convert_image_to_pdf_page(
                                doc_path, page_size=page_size
                            )
                            try:
                                source_doc = fitz.open(converted_pdf_path)
                                try:
                                    insert_pdf_with_page_size(source_doc)
                                finally:
                                    source_doc.close()
                            finally:
                                if os.path.exists(converted_pdf_path):
                                    os.remove(converted_pdf_path)
                        else:
                            raise Exception(f"Unsupported file format: {ext}")

                    else:
                        raise Exception(f"Unsupported file format: {ext}")

                except Exception as e:
                    logger.error(
                        f"Failed to merge document {doc_path}: {str(e)}"
                    )
                    raise Exception(
                        f"Failed to merge '{os.path.basename(doc_path)}': {str(e)}"
                    )

            # Save merged PDF
            merged_doc.save(output_path, garbage=4, deflate=True, clean=True)
            merged_doc.close()

            file_size = os.path.getsize(output_path)

            logger.info(
                f"Successfully merged {len(pdf_paths)} documents into {output_path} ({file_size} bytes)"
            )

            return {
                "success": True,
                "pdf_path": output_path,
                "file_size": file_size,
                "num_documents": len(pdf_paths),
                "error": None,
            }

        finally:
            # Clean up temporary conversion directory
            try:
                if os.path.exists(temp_conversion_dir):
                    shutil.rmtree(temp_conversion_dir)
            except Exception as e:
                logger.warning(
                    f"Failed to clean up temporary conversion directory: {str(e)}"
                )

    except Exception as e:
        logger.error(f"Merge operation failed: {str(e)}")
        return {
            "success": False,
            "pdf_path": None,
            "file_size": 0,
            "num_documents": 0,
            "error": str(e),
        }
