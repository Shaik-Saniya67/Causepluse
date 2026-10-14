"""Plain data classes shared across CausePulse. No Streamlit imports here."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

STATUS_MATCHED = "matched"
STATUS_REVIEW = "review"
STATUS_NOT_FOUND = "not_found"
STATUS_LABELS = {
    STATUS_MATCHED: "Matched",
    STATUS_REVIEW: "Needs review",
    STATUS_NOT_FOUND: "Not found",
}
NOT_FOUND_NOTE = (
    "Not found in the uploaded cause list. This does not mean the case was "
    "cancelled, adjourned or removed from the court's schedule."
)


@dataclass
class SavedCase:
    id: int
    case_number: str
    year: Optional[int] = None
    court: str = ""
    party_names: str = ""
    nickname: str = ""
    active: bool = True
    is_demo: bool = False

    @property
    def label(self) -> str:
        """Human-readable case reference exactly as the advocate saved it."""
        import re

        text = self.case_number.strip()
        if self.year and not re.search(r"\d\s*[/\-\\]\s*\d{2,4}\s*$", text):
            return f"{text}/{self.year}"
        return text


@dataclass
class Entry:
    id: int
    document_id: int
    page_number: int
    item_number: Optional[int]
    case_number_raw: str
    case_type: str
    number: str
    year: Optional[int]
    court: str = ""
    party_names: str = ""
    stage: str = ""
    published_time: str = ""
    source_text: str = ""
    bbox: Optional[tuple] = None
    corrected: bool = False
    note: str = ""

    @property
    def key(self) -> str:
        return "/".join(p for p in (self.case_type, self.number, str(self.year or "")) if p)


@dataclass
class DocumentRecord:
    id: int
    filename: str
    upload_time: str
    page_count: int
    processing_status: str
    content_hash: str
    extraction_method: str
    list_date: Optional[str]
    title: Optional[str]
    warnings: list = field(default_factory=list)
    entry_count: int = 0
    is_demo: bool = False


@dataclass
class Candidate:
    entry: Entry
    reason: str
    signals: dict
    tier: int = 1


@dataclass
class MatchResult:
    saved: SavedCase
    status: str
    entry: Optional[Entry] = None
    candidates: list = field(default_factory=list)
    reason: str = ""
    verified: bool = False
    signals: dict = field(default_factory=dict)
    rejected_count: int = 0
