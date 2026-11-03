"""
parser.py
---------
Handles extraction of clean plain text from uploaded resume and job
description files.

Supported inputs:
  - Resume:  PDF (PyMuPDF / fitz), DOCX (python-docx), PPTX (python-pptx)
  - Job Description: PDF (PyMuPDF / fitz), DOCX (python-docx), PPTX (python-pptx), or raw text

All extraction functions raise a `ParsingError` with a user-friendly
message on failure so the API layer can surface a clean error response
instead of a stack trace.
"""

from __future__ import annotations

import io
import os

import pymupdf as fitz  # PyMuPDF
from docx import Document
from pptx import Presentation

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB

ALLOWED_RESUME_EXTENSIONS = {".pdf", ".docx", ".pptx"}
ALLOWED_JD_FILE_EXTENSIONS = {".pdf", ".docx", ".pptx"}


class ParsingError(Exception):
    """Raised when a file cannot be parsed into usable text."""


def _get_extension(filename: str) -> str:
    return os.path.splitext(filename or "")[1].lower()


def validate_file_size(file_bytes: bytes, filename: str) -> None:
    if file_bytes is None or len(file_bytes) == 0:
        raise ParsingError(f"'{filename}' is empty. Please upload a valid file.")
    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        size_mb = len(file_bytes) / (1024 * 1024)
        raise ParsingError(
            f"'{filename}' is {size_mb:.1f}MB, which exceeds the 10MB file size limit."
        )


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract all readable text from a PDF, including text inside simple tables."""
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
    except Exception as exc:
        raise ParsingError(
            "Could not open the PDF file. It may be corrupted or password protected."
        ) from exc

    try:
        pages_text = []
        for page in doc:
            text = page.get_text("text")
            if text:
                pages_text.append(text)
        doc.close()
    except Exception as exc:
        raise ParsingError("Failed while extracting text from the PDF.") from exc

    full_text = "\n".join(pages_text).strip()
    if not full_text:
        raise ParsingError(
            "No readable text could be found in the PDF. It may be a scanned image "
            "without a text layer."
        )
    return full_text


def extract_text_from_docx(file_bytes: bytes) -> str:
    """Extract all text from a DOCX file, including paragraphs and table cells."""
    try:
        document = Document(io.BytesIO(file_bytes))
    except Exception as exc:
        raise ParsingError(
            "Could not open the DOCX file. It may be corrupted or in an unsupported format."
        ) from exc

    try:
        chunks = []

        for para in document.paragraphs:
            if para.text and para.text.strip():
                chunks.append(para.text.strip())

        for table in document.tables:
            for row in table.rows:
                row_cells = [cell.text.strip() for cell in row.cells if cell.text and cell.text.strip()]
                if row_cells:
                    chunks.append(" | ".join(row_cells))

        # Headers / footers can sometimes contain contact info or skill summaries
        for section in document.sections:
            try:
                header = section.header
                for para in header.paragraphs:
                    if para.text and para.text.strip():
                        chunks.append(para.text.strip())
            except Exception:
                pass
    except Exception as exc:
        raise ParsingError("Failed while extracting text from the DOCX file.") from exc

    full_text = "\n".join(chunks).strip()
    if not full_text:
        raise ParsingError("No readable text could be found in the DOCX file.")
    return full_text


def extract_text_from_pptx(file_bytes: bytes) -> str:
    """Extract text from every slide (including tables and notes) of a PPTX."""
    try:
        presentation = Presentation(io.BytesIO(file_bytes))
    except Exception as exc:
        raise ParsingError(
            "Could not open the PPTX file. It may be corrupted or in an unsupported format."
        ) from exc

    try:
        chunks = []
        for slide_index, slide in enumerate(presentation.slides, start=1):
            slide_chunks = []
            for shape in slide.shapes:
                if shape.has_text_frame:
                    for paragraph in shape.text_frame.paragraphs:
                        text = "".join(run.text for run in paragraph.runs).strip()
                        if text:
                            slide_chunks.append(text)
                if shape.has_table:
                    for row in shape.table.rows:
                        row_cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                        if row_cells:
                            slide_chunks.append(" | ".join(row_cells))
            if slide_chunks:
                chunks.append(f"[Slide {slide_index}]\n" + "\n".join(slide_chunks))
    except Exception as exc:
        raise ParsingError("Failed while extracting text from the PPTX file.") from exc

    full_text = "\n".join(chunks).strip()
    if not full_text:
        raise ParsingError("No readable text could be found in the PPTX file.")
    return full_text


def parse_resume(filename: str, file_bytes: bytes) -> str:
    """Dispatch resume parsing based on file extension. Returns extracted text."""
    validate_file_size(file_bytes, filename)
    ext = _get_extension(filename)

    if ext not in ALLOWED_RESUME_EXTENSIONS:
        raise ParsingError(
            f"Unsupported resume file type '{ext or 'unknown'}'. Please upload a PDF, DOCX, or PPTX file."
        )

    if ext == ".pdf":
        return extract_text_from_pdf(file_bytes)
    if ext == ".docx":
        return extract_text_from_docx(file_bytes)
    if ext == ".pptx":
        return extract_text_from_pptx(file_bytes)

    # Should be unreachable given the check above
    raise ParsingError("Unsupported resume file type.")


def parse_jd_file(filename: str, file_bytes: bytes) -> str:
    """Dispatch job description file parsing based on file extension."""
    validate_file_size(file_bytes, filename)
    ext = _get_extension(filename)

    if ext not in ALLOWED_JD_FILE_EXTENSIONS:
        raise ParsingError(
            f"Unsupported job description file type '{ext or 'unknown'}'. "
            "Please upload a PDF, DOCX, or PPTX file, or paste the text instead."
        )

    if ext == ".pdf":
        return extract_text_from_pdf(file_bytes)
    if ext == ".docx":
        return extract_text_from_docx(file_bytes)
    if ext == ".pptx":
        return extract_text_from_pptx(file_bytes)

    # Should be unreachable given the check above
    raise ParsingError("Unsupported job description file type.")
