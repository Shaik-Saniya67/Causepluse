"""PDF text extraction with PyMuPDF. Keeps page numbers and row positions."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

try:  # PyMuPDF >= 1.24.3
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    import fitz

MAX_BYTES = 20 * 1024 * 1024
MAX_PAGES = 400
MIN_TEXT_CHARS = 25
METHOD = "PyMuPDF text layer (no OCR)"


class PDFProcessingError(Exception):
    """User-facing extraction problem. `code` is machine-readable."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass
class Row:
    text: str
    cells: list
    bbox: tuple
    page: int


@dataclass
class ExtractionResult:
    page_count: int
    pages: list  # list[list[Row]] (index 0 == page 1)
    chars: int = 0
    method: str = METHOD
    warnings: list = field(default_factory=list)


def validate_pdf_bytes(data: bytes, max_bytes: int = MAX_BYTES) -> None:
    if not data:
        raise PDFProcessingError("not_pdf", "The file is empty.")
    if len(data) > max_bytes:
        raise PDFProcessingError(
            "too_large", f"The file is larger than the {max_bytes // (1024 * 1024)} MB limit."
        )
    if b"%PDF" not in data[:1024]:
        raise PDFProcessingError(
            "not_pdf", "This doesn't look like a PDF file. Please upload a .pdf cause list."
        )


def build_rows(words: list, page_no: int, y_tol: float = 3.0) -> list:
    """Group PyMuPDF word tuples into visual rows, then split rows into cells."""
    ws = [w for w in words if str(w[4]).strip()]
    ws.sort(key=lambda w: ((w[1] + w[3]) / 2, w[0]))
    groups: list = []
    for w in ws:
        yc = (w[1] + w[3]) / 2
        if groups and abs(yc - groups[-1][0]) <= y_tol:
            groups[-1][1].append(w)
        else:
            groups.append([yc, [w]])
    rows = []
    for _, g in groups:
        g.sort(key=lambda w: w[0])
        cells, cur, prev = [], [], None
        for w in g:
            if prev is not None:
                gap = w[0] - prev[2]
                h = max(prev[3] - prev[1], 1.0)
                if gap > max(9.0, 1.1 * h):
                    cells.append(" ".join(cur))
                    cur = []
            cur.append(str(w[4]))
            prev = w
        cells.append(" ".join(cur))
        bbox = (
            min(w[0] for w in g) - 2,
            min(w[1] for w in g) - 1.5,
            max(w[2] for w in g) + 2,
            max(w[3] for w in g) + 1.5,
        )
        rows.append(Row(" ".join(str(w[4]) for w in g), [c for c in cells if c], bbox, page_no))
    return rows


def extract_document(
    data: bytes, progress: Optional[Callable[[int, int], None]] = None
) -> ExtractionResult:
    validate_pdf_bytes(data)
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception:
        raise PDFProcessingError(
            "unreadable", "This PDF could not be opened. It may be corrupted or malformed."
        )
    try:
        if doc.needs_pass:
            raise PDFProcessingError(
                "encrypted", "This PDF is password-protected. Remove the password and upload again."
            )
        n = doc.page_count
        if n == 0:
            raise PDFProcessingError("unreadable", "This PDF has no pages.")
        if n > MAX_PAGES:
            raise PDFProcessingError("too_many_pages", f"This PDF has {n} pages (limit {MAX_PAGES}).")
        pages, chars, no_text, warnings = [], 0, [], []
        for i in range(n):
            try:
                words = doc[i].get_text("words")
            except Exception:
                words = []
                warnings.append(f"Page {i + 1} could not be read and was skipped.")
            c = sum(len(str(w[4])) for w in words)
            chars += c
            if c < MIN_TEXT_CHARS:
                no_text.append(i + 1)
            pages.append(build_rows(words, i + 1))
            if progress:
                progress(i + 1, n)
        if len(no_text) == n:
            raise PDFProcessingError(
                "scanned",
                "No selectable text was found. This looks like a scanned (image-only) PDF. "
                "OCR is not enabled in this MVP, so no schedule was produced. Please upload a "
                "text-based cause-list PDF.",
            )
        if no_text:
            shown = ", ".join(map(str, no_text[:10])) + ("…" if len(no_text) > 10 else "")
            warnings.append(
                f"No text found on page(s) {shown}: they may be scanned images and were not searched."
            )
        return ExtractionResult(n, pages, chars, METHOD, warnings)
    finally:
        doc.close()
