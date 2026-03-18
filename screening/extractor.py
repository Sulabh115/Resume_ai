"""
screening/extractor.py

Handles PDF → raw text extraction.
Uses PyMuPDF for text-based PDFs and falls back to
Tesseract OCR for image-based (scanned) PDFs.
"""

import io
import fitz          # PyMuPDF
import pytesseract
from PIL import Image


def extract_text_from_pdf(pdf_path: str) -> str:
    """
    Extract raw text from a PDF file.

    Strategy:
        1. Try native text extraction per page (fast, accurate).
        2. If a page has no extractable text, fall back to OCR.

    Args:
        pdf_path: Absolute file-system path to the PDF.

    Returns:
        Raw text string. Empty string if extraction fails entirely.
    """
    doc = fitz.open(pdf_path)
    pages_text = []

    for page_num in range(len(doc)):
        page = doc[page_num]

        # ── Step 1: native text extraction ───────────────────────────
        text = page.get_text().strip()

        if text:
            pages_text.append(text)
            continue

        # ── Step 2: OCR fallback for image-only pages ─────────────────
        pix       = page.get_pixmap()
        img_bytes = pix.tobytes("png")
        img       = Image.open(io.BytesIO(img_bytes))
        ocr_text  = pytesseract.image_to_string(img)
        pages_text.append(ocr_text)

    doc.close()
    return "\n".join(pages_text).strip()


def extract_text_from_resume(resume) -> str:
    """
    Convenience wrapper that accepts a Django FileField / InMemoryUploadedFile
    object (i.e. application.resume.file) and returns extracted text.

    Usage inside views / utils:
        text = extract_text_from_resume(application.resume.file)
    """
    # Django FileField exposes .path for files stored on disk
    return extract_text_from_pdf(resume.path)