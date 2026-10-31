"""PDF and OCR Extraction Service for Offer Letter Analysis.

Conforms to Feature F7 & Section 3, 4, 11 of PROJECT_SPECIFICATION.md:
- Uses PyMuPDF (pymupdf) for text-based PDFs.
- Automatic scanned-page detection and Tesseract OCR integration.
- Strict upload security: magic byte verification, structural inspection, page/size/timeout limits.
- Safe temp-file lifecycle management (guaranteed deletion in finally blocks).
- Zero-leakage privacy: never logs raw OCR text, document bodies, or candidate PII.
"""

from dataclasses import dataclass, field
import hashlib
import io
import logging
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Dict, List, Optional, Tuple

from PIL import Image
import pymupdf
import pytesseract

from app.core.config import settings

logger = logging.getLogger("jobshield.services.pdf_extractor")


# Custom Exceptions for Upload Security and Extraction Failures
class PDFProcessingError(Exception):
    """Base exception for PDF and OCR processing failures."""


class OversizedFileError(PDFProcessingError):
    """Uploaded PDF exceeds configured file size limit."""


class ExcessivePagesError(PDFProcessingError):
    """Uploaded PDF exceeds configured page count limit."""


class InvalidPDFError(PDFProcessingError):
    """File content fails PDF magic bytes verification or structural parsing."""


class EncryptedPDFError(PDFProcessingError):
    """PDF is encrypted or password-protected."""


class OCRProcessingError(PDFProcessingError):
    """Tesseract OCR execution failed."""


class OCRTimeoutError(PDFProcessingError):
    """OCR subprocess exceeded configured execution timeout."""


@dataclass
class ExtractedDocument:
    """Structured extraction output containing per-page text and execution metadata."""

    file_name: str
    file_hash: str
    file_size_bytes: int
    page_count: int
    pages_text: Dict[int, str] = field(default_factory=dict)  # 1-indexed page number -> text
    is_scanned: bool = False
    ocr_applied: bool = False
    ocr_engine: Optional[str] = None
    ocr_available: bool = False
    limitations: List[str] = field(default_factory=list)

    @property
    def full_text(self) -> str:
        """Concatenated full text across all pages in sequential order."""
        return "\n\n".join(self.pages_text.get(page, "") for page in sorted(self.pages_text.keys()))


def resolve_tesseract_cmd() -> Optional[str]:
    """Resolves and validates the Tesseract OCR executable path.

    Checks:
    1. TESSERACT_CMD environment variable.
    2. settings.TESSERACT_CMD.
    3. System PATH via shutil.which('tesseract').
    4. Standard Windows 64-bit and 32-bit Program Files installation paths.

    Returns:
        Verified executable path string or None if unavailable.
    """
    candidates = [
        os.getenv("TESSERACT_CMD"),
        getattr(settings, "TESSERACT_CMD", None),
        shutil.which("tesseract"),
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]

    for cand in candidates:
        if cand and isinstance(cand, str):
            clean_path = cand.strip().strip('"')
            if clean_path and os.path.isfile(clean_path) and os.access(clean_path, os.X_OK):
                return clean_path

    return None


def is_ocr_available() -> bool:
    """Checks whether a valid Tesseract executable is installed and runnable."""
    cmd = resolve_tesseract_cmd()
    if not cmd:
        return False
    try:
        pytesseract.pytesseract.tesseract_cmd = cmd
        _ = pytesseract.get_tesseract_version()
        return True
    except Exception as exc:
        logger.debug("Tesseract verification probe failed: %s", exc)
        return False


def get_ocr_version() -> Optional[str]:
    """Returns the Tesseract version string if available, else None."""
    cmd = resolve_tesseract_cmd()
    if not cmd:
        return None
    try:
        pytesseract.pytesseract.tesseract_cmd = cmd
        ver = str(pytesseract.get_tesseract_version())
        return f"tesseract_v{ver}"
    except Exception:
        return None


def extract_text_and_ocr(
    file_bytes: bytes,
    file_name: str = "document.pdf",
    max_bytes: Optional[int] = None,
    max_pages: Optional[int] = None,
    ocr_timeout_seconds: Optional[int] = None,
) -> ExtractedDocument:
    """Safely inspects, validates, extracts text from, and optionally OCRs a PDF document.

    Enforces:
    - Maximum upload byte limits and %PDF- magic bytes header.
    - Structural parsing rejection of corrupted, truncated, or encrypted documents.
    - Maximum page count limits.
    - OCR subprocess execution limits and timeout controls.
    - Safe temporary file deletion in guaranteed finally blocks.
    - Never logs document contents or OCR text.
    """
    effective_max_bytes = max_bytes or settings.MAX_OFFER_LETTER_UPLOAD_BYTES
    effective_max_pages = max_pages or settings.MAX_OFFER_LETTER_PAGES
    timeout_sec = ocr_timeout_seconds or settings.OFFER_LETTER_TIMEOUT_SECONDS

    # 1. Byte size enforcement
    file_size = len(file_bytes)
    if file_size > effective_max_bytes:
        raise OversizedFileError(
            f"File size ({file_size} bytes) exceeds maximum permitted upload limit of {effective_max_bytes} bytes."
        )

    # 2. Magic bytes validation: PDF files must start with '%PDF-'
    if not file_bytes.startswith(b"%PDF-"):
        raise InvalidPDFError(
            "File rejected by security policy: Header does not match standard PDF magic bytes (%PDF-). "
            "Please upload a valid PDF document."
        )

    # Compute non-reversible SHA-256 digest for audit provenance
    file_hash = hashlib.sha256(file_bytes).hexdigest()

    # 3. Structural validation using PyMuPDF
    try:
        doc = pymupdf.open(stream=file_bytes, filetype="pdf")
    except Exception as exc:
        logger.warning("PyMuPDF failed to open PDF [hash_prefix=%s]: %s", file_hash[:12], type(exc).__name__)
        raise InvalidPDFError("Corrupt or invalid PDF document structure.") from exc

    try:
        # Check encryption
        if doc.is_encrypted:
            raise EncryptedPDFError(
                "Encrypted or password-protected PDFs are not supported for automated analysis. "
                "Please provide an unencrypted document."
            )

        page_count = len(doc)
        if page_count == 0:
            raise InvalidPDFError("PDF document contains 0 pages.")

        if page_count > effective_max_pages:
            raise ExcessivePagesError(
                f"Document exceeds maximum permitted page limit of {effective_max_pages} pages (received {page_count})."
            )

        # 4. Check OCR availability
        tesseract_cmd = resolve_tesseract_cmd()
        ocr_supported = False
        ocr_engine_name = None
        if tesseract_cmd:
            try:
                pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
                ocr_supported = True
                ocr_engine_name = get_ocr_version() or "tesseract"
            except Exception as e:
                logger.debug("Failed configuring pytesseract: %s", e)

        extracted = ExtractedDocument(
            file_name=Path(file_name).name,
            file_hash=file_hash,
            file_size_bytes=file_size,
            page_count=page_count,
            ocr_available=ocr_supported,
            ocr_engine=ocr_engine_name if ocr_supported else None,
        )

        # 5. Page-by-page extraction & selective OCR
        for page_idx in range(page_count):
            page_num = page_idx + 1
            page = doc[page_idx]

            # Native text extraction via PyMuPDF
            native_text = page.get_text() or ""
            stripped_text = native_text.strip()

            # Determine whether page has sufficient extractable text (at least 50 characters)
            if len(stripped_text) >= 50:
                extracted.pages_text[page_num] = native_text
            else:
                # Scanned or image-dominated page detected
                extracted.is_scanned = True

                if not ocr_supported:
                    extracted.limitations.append(
                        f"Page {page_num} appears to be a scanned image or contains little text, "
                        "but the Tesseract OCR engine is not configured on this host. OCR extraction skipped."
                    )
                    extracted.pages_text[page_num] = stripped_text  # Retain whatever minimal text was present
                    continue

                # Run OCR on the scanned page
                ocr_text = _run_ocr_on_page(page, page_num, timeout_seconds=timeout_sec)
                extracted.ocr_applied = True
                extracted.pages_text[page_num] = ocr_text

        return extracted

    finally:
        try:
            doc.close()
        except Exception:
            pass


def _run_ocr_on_page(page: pymupdf.Page, page_num: int, timeout_seconds: int = 30) -> str:
    """Renders a PDF page to a bounded pixmap and runs Tesseract OCR in a controlled temporary file.

    Guarantees temporary file cleanup on success, error, or timeout.
    """
    temp_img_path = None
    try:
        # Render pixmap with 150 DPI for balance of accuracy and memory
        pix = page.get_pixmap(dpi=settings.OCR_DPI)

        # Enforce image dimension bounds to protect against decompression bombs
        max_dim = settings.OCR_MAX_IMAGE_DIMENSION
        if pix.width > max_dim or pix.height > max_dim:
            logger.warning("Page %d pixmap exceeds maximum dimensions (%dx%d), downscaling", page_num, pix.width, pix.height)
            # Cap dimension via PIL
            img_raw = Image.open(io.BytesIO(pix.tobytes("png")))
            img_raw.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
        else:
            img_raw = Image.open(io.BytesIO(pix.tobytes("png")))

        # Use safe temporary file outside web-accessible directories
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_file:
            temp_img_path = tmp_file.name

        img_raw.save(temp_img_path, format="PNG")

        # Run pytesseract with timeout
        ocr_result = pytesseract.image_to_string(
            temp_img_path,
            timeout=timeout_seconds,
            config="--psm 1",  # Automatic page segmentation with OSD
        )
        return ocr_result or ""

    except (subprocess.TimeoutExpired, TimeoutError) as exc:
        logger.warning("Tesseract OCR timed out on page %d after %d seconds", page_num, timeout_seconds)
        raise OCRTimeoutError(f"OCR processing timed out on page {page_num} after {timeout_seconds} seconds.") from exc
    except RuntimeError as exc:
        if "timeout" in str(exc).lower():
            logger.warning("Tesseract OCR timed out on page %d after %d seconds", page_num, timeout_seconds)
            raise OCRTimeoutError(f"OCR processing timed out on page {page_num} after {timeout_seconds} seconds.") from exc
        logger.warning("OCR failed on page %d: %s", page_num, exc)
        return ""
    except Exception as exc:
        logger.warning("OCR failed on page %d: %s", page_num, type(exc).__name__)
        # Fallback to general image OCR attempt without OSD if PSM 1 fails
        try:
            if temp_img_path and os.path.exists(temp_img_path):
                return pytesseract.image_to_string(temp_img_path, timeout=timeout_seconds) or ""
        except Exception as retry_exc:
            logger.warning("OCR retry also failed on page %d: %s", page_num, retry_exc)
        return ""
    finally:
        # GUARANTEED CLEANUP of temporary file
        if temp_img_path and os.path.exists(temp_img_path):
            try:
                os.remove(temp_img_path)
            except OSError as err:
                logger.debug("Failed deleting temporary OCR file '%s': %s", temp_img_path, err)
