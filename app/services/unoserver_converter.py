"""
UnoServer Converter

This module provides PDF conversion using UnoServer client API.
"""
import os
import logging
from pathlib import Path
import socket

logger = logging.getLogger(__name__)


class UnoServerConverter:
    """PDF converter using UnoServer client API."""

    def __init__(self, host=None, port=None, timeout=None):
        """
        Initialize UnoServer converter.

        Args:
            host: UnoServer hostname (default: from UNOSERVER_HOST env var)
            port: UnoServer port (default: from UNOSERVER_PORT env var)
            timeout: Timeout in seconds (default: from UNO_SERVER_TIMEOUT env var)
        """
        self.host = host or os.environ.get("UNOSERVER_HOST", "unoserver")
        self.port = int(port or os.environ.get("UNOSERVER_PORT", "2003"))
        self.timeout = int(timeout or os.environ.get("UNO_SERVER_TIMEOUT", "60"))
        self.pdf_filter_options = self._build_pdf_filter_options()

        try:
            from unoserver.client import UnoClient

            self.client_class = UnoClient
            logger.info(f"UnoServer converter initialized: {self.host}:{self.port}")
        except ImportError:
            logger.error("unoserver package not installed")
            self.client_class = None

    @staticmethod
    def _build_pdf_filter_options():
        """
        Build LibreOffice PDF export filter options from environment variables.

        Returns a list of filter option strings controlling image compression
        and downsampling in the exported PDF.
        """
        use_lossless = os.environ.get(
            "PDF_USE_LOSSLESS_COMPRESSION", "false"
        ).lower() == "true"
        jpeg_quality = os.environ.get("PDF_JPEG_QUALITY", "80")
        reduce_resolution = os.environ.get(
            "PDF_REDUCE_IMAGE_RESOLUTION", "true"
        ).lower() == "true"
        max_resolution = os.environ.get("PDF_MAX_IMAGE_RESOLUTION", "150")

        options = [
            f"UseLosslessCompression={'true' if use_lossless else 'false'}",
            f"Quality={jpeg_quality}",
            f"ReduceImageResolution={'true' if reduce_resolution else 'false'}",
            f"MaxImageResolution={max_resolution}",
        ]

        return options

    def convert_to_pdf(self, input_path: str, output_dir: str) -> str:
        """
        Convert document to PDF using UnoServer API.

        Args:
            input_path: Path to the input document
            output_dir: Directory where the PDF should be saved

        Returns:
            Path to the generated PDF file

        Raises:
            Exception: If conversion fails or unoserver is unavailable
        """
        if not self.client_class:
            raise Exception("UnoServer client not available - unoserver package not installed")

        logger.info(f"Converting {input_path} using UnoServer ({self.host}:{self.port})")

        try:
            # Create client connection
            client = self.client_class(server=self.host, port=self.port)

            # Read input file as binary
            with open(input_path, "rb") as f:
                input_data = f.read()

            # Convert to PDF (returns binary PDF data)
            convert_kwargs = {"indata": input_data, "convert_to": "pdf"}
            if self.pdf_filter_options:
                convert_kwargs["filter_options"] = self.pdf_filter_options
            output_data = client.convert(**convert_kwargs)

            # Determine output path
            output_path = Path(output_dir) / f"{Path(input_path).stem}.pdf"

            # Write output file
            with open(output_path, "wb") as f:
                f.write(output_data)

            logger.info(f"Successfully converted to PDF: {output_path}")
            return str(output_path)

        except socket.timeout:
            raise Exception(f"UnoServer timed out after {self.timeout}s")
        except ConnectionRefusedError:
            raise Exception(
                f"Cannot connect to UnoServer at {self.host}:{self.port}. "
                "Ensure unoserver service is running."
            )
        except FileNotFoundError:
            raise Exception(f"Input file not found: {input_path}")
        except Exception as e:
            raise Exception(f"UnoServer conversion error: {type(e).__name__}: {e}")

    def is_available(self) -> bool:
        """
        Check if UnoServer is reachable.

        Returns:
            True if UnoServer is accessible, False otherwise
        """
        if not self.client_class:
            return False

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            result = sock.connect_ex((self.host, self.port))
            sock.close()
            return result == 0
        except Exception:
            return False
