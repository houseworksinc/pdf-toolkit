import fitz  # PyMuPDF
import os
import requests
import tempfile
import logging
from typing import List, Dict, Union, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class PageNotFoundError(Exception):
    """Raised when a page reference cannot be found in the document."""

    pass


class InvalidSplitConfigError(Exception):
    """Raised when split configuration is invalid."""

    pass


def _resolve_physical_page(doc: fitz.Document, page_num: int) -> int:
    """
    Resolve physical page number (1-indexed) to page index (0-indexed).

    Args:
        doc: PyMuPDF document
        page_num: Physical page number (1-indexed)

    Returns:
        Page index (0-indexed)

    Raises:
        PageNotFoundError: If page number is out of range
    """
    if 1 <= page_num <= doc.page_count:
        return page_num - 1
    raise PageNotFoundError(
        f"Page {page_num} out of range (1-{doc.page_count})"
    )


def _resolve_page_label(doc: fitz.Document, label: Union[str, int]) -> int:
    """
    Resolve page label (e.g., 'i', 'ii', 'a') to page index (0-indexed).

    Args:
        doc: PyMuPDF document
        label: Page label (string or int)

    Returns:
        Page index (0-indexed)

    Raises:
        PageNotFoundError: If label is not found in document
    """
    search_label = str(label)

    for page_idx in range(doc.page_count):
        if doc[page_idx].get_label() == search_label:
            return page_idx

    raise PageNotFoundError(f"Label '{label}' not found in document")


def download_pdf_from_url(url: str, output_path: str) -> None:
    """
    Download PDF from URL to local path.

    Args:
        url: URL to download PDF from
        output_path: Local path to save PDF

    Raises:
        Exception: If download fails
    """
    try:
        logger.info(f"Downloading PDF from {url}")
        response = requests.get(url, timeout=60)
        response.raise_for_status()

        with open(output_path, "wb") as f:
            f.write(response.content)

        logger.info(f"Successfully downloaded PDF to {output_path}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to download PDF from {url}: {e}")
        raise Exception(f"Failed to download PDF: {e}")


def split_pdf_by_pages(
    document_path: str, splits: List[Dict], output_dir: str = "output"
) -> List[Dict]:
    """
    Split a PDF into multiple files based on physical page numbers or logical labels.

    Args:
        document_path: Path to the source PDF file
        splits: List of dictionaries containing:
            - file_name: Name for output file (without extension) [required]
            - pages: List of physical page numbers (1-indexed int) [optional]
            - labels: List of logical page labels (str/int like 'i', 'ii', 'a', '1') [optional]
            Note: Each split must have either 'pages' or 'labels', not both
        output_dir: Directory to save output files (default: "output")

    Returns:
        List of dictionaries with split results:
        [
            {
                'file_name': 'file-1',
                'file_path': '/path/to/file-1.pdf',
                'file_size': 12345,
                'page_count': 4,
                'success': True,
                'error': None
            },
            ...
        ]

    Raises:
        FileNotFoundError: If source PDF doesn't exist
        InvalidSplitConfigError: If split configuration is invalid
    """
    if not os.path.exists(document_path):
        raise FileNotFoundError(f"Source PDF not found: {document_path}")

    Path(output_dir).mkdir(parents=True, exist_ok=True)

    doc = fitz.open(document_path)
    results = []

    try:
        for split in splits:
            file_name = split.get("file_name")
            if not file_name:
                raise InvalidSplitConfigError(
                    "Missing 'file_name' in split configuration"
                )

            result = {
                "file_name": file_name,
                "file_path": None,
                "file_size": 0,
                "page_count": 0,
                "success": False,
                "error": None,
            }

            try:
                # Determine split type and get resolver function
                if "pages" in split and "labels" in split:
                    raise InvalidSplitConfigError(
                        f"Split '{file_name}' cannot have both 'pages' and 'labels'"
                    )
                elif "pages" in split:
                    references = split["pages"]
                    resolve_fn = _resolve_physical_page
                    use_labels = False
                elif "labels" in split:
                    references = split["labels"]
                    resolve_fn = _resolve_page_label
                    use_labels = True
                else:
                    raise InvalidSplitConfigError(
                        f"Split '{file_name}' must contain either 'pages' or 'labels'"
                    )

                # Create new PDF and add pages
                new_doc = fitz.open()
                page_labels = []

                try:
                    for ref in references:
                        physical_idx = resolve_fn(doc, ref)
                        new_doc.insert_pdf(
                            doc, from_page=physical_idx, to_page=physical_idx
                        )

                        if use_labels:
                            page_labels.append(doc[physical_idx].get_label())

                    # Set page labels if splitting by labels
                    if use_labels and page_labels:
                        label_rules = [
                            {"startpage": idx, "prefix": label}
                            for idx, label in enumerate(page_labels)
                        ]
                        new_doc.set_page_labels(label_rules)

                    # Save the PDF
                    output_path = os.path.join(output_dir, f"{file_name}.pdf")
                    new_doc.save(output_path)

                    # Get file info
                    file_size = os.path.getsize(output_path)

                    result["file_path"] = output_path
                    result["file_size"] = file_size
                    result["page_count"] = len(references)
                    result["success"] = True

                    logger.info(
                        f"Successfully created split PDF: {output_path} ({file_size} bytes, {len(references)} pages)"
                    )

                finally:
                    new_doc.close()

            except (PageNotFoundError, InvalidSplitConfigError) as e:
                error_msg = str(e)
                logger.error(
                    f"Error splitting PDF for '{file_name}': {error_msg}"
                )
                result["error"] = error_msg
            except Exception as e:
                error_msg = f"Unexpected error: {str(e)}"
                logger.error(
                    f"Error splitting PDF for '{file_name}': {error_msg}"
                )
                result["error"] = error_msg

            results.append(result)

    finally:
        doc.close()

    return results


def split_pdf_from_url(
    document_url: str, splits: List[Dict], output_dir: str = "output"
) -> List[Dict]:
    """
    Download PDF from URL and split it into multiple files.

    This is a convenience function that combines download and split operations.

    Args:
        document_url: URL to download PDF from
        splits: List of split configurations (same format as split_pdf_by_pages)
        output_dir: Directory to save output files

    Returns:
        List of split results (same format as split_pdf_by_pages)

    Raises:
        Exception: If download or split fails
    """
    # Create a temporary file for the downloaded PDF
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
        tmp_pdf_path = tmp_file.name

    try:
        # Download PDF
        download_pdf_from_url(document_url, tmp_pdf_path)

        # Split PDF
        results = split_pdf_by_pages(tmp_pdf_path, splits, output_dir)

        return results

    finally:
        # Clean up temporary file
        if os.path.exists(tmp_pdf_path):
            try:
                os.unlink(tmp_pdf_path)
                logger.debug(f"Cleaned up temporary PDF: {tmp_pdf_path}")
            except OSError as e:
                logger.warning(
                    f"Failed to delete temporary PDF {tmp_pdf_path}: {e}"
                )
