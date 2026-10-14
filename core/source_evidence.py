"""Render the original PDF page (optionally cropped) with the matching row highlighted."""
from __future__ import annotations

from typing import Optional

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    import fitz

GOLD = (0.78, 0.65, 0.42)


def render_source(pdf_bytes: bytes, page_number: int, bbox: Optional[tuple] = None,
                  crop: bool = True, zoom: float = 2.0) -> bytes:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        page = doc[page_number - 1]
        clip = None
        if bbox:
            rect = fitz.Rect(*bbox)
            page.draw_rect(rect, color=GOLD, fill=GOLD, fill_opacity=0.30, width=1.0)
            if crop:
                clip = fitz.Rect(page.rect.x0, max(page.rect.y0, rect.y0 - 75),
                                 page.rect.x1, min(page.rect.y1, rect.y1 + 75))
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip, alpha=False)
        return pix.tobytes("png")
    finally:
        doc.close()
