"""Application service layer: ties extraction, parsing, storage and matching together."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from core.case_matcher import match_all, sort_results, summarize
from core.case_parser import parse_extraction
from core.models import DocumentRecord
from core.pdf_extractor import PDFProcessingError, extract_document
from core.sample_data import DEMO_ADVOCATE, DEMO_CASES, DEMO_FILENAME, build_sample_pdf
from database.repository import Repository


@dataclass
class AppData:
    repo: Repository
    cases: list = field(default_factory=list)
    documents: list = field(default_factory=list)
    doc: Optional[DocumentRecord] = None
    entries: list = field(default_factory=list)
    decisions: dict = field(default_factory=dict)
    results: list = field(default_factory=list)
    counts: dict = field(default_factory=dict)
    advocate: str = "Advocate"
    demo: bool = False


def load_app_data(repo: Repository) -> AppData:
    docs = repo.list_documents()
    active_id = repo.get_setting("active_document_id")
    doc = next((d for d in docs if str(d.id) == active_id), None) or (docs[0] if docs else None)
    cases = repo.list_cases()
    entries = repo.entries_for(doc.id) if doc else []
    decisions = repo.decisions_for(doc.id) if doc else {}
    results = sort_results(match_all(cases, entries, decisions)) if doc else []
    counts = summarize(match_all(cases, entries, decisions)) if doc else {
        "tracked": sum(c.active for c in cases), "matched": 0, "review": 0, "not_found": 0}
    return AppData(repo, cases, docs, doc, entries, decisions, results, counts,
                   repo.get_setting("advocate_name", "Advocate"),
                   bool((doc and doc.is_demo) or any(c.is_demo for c in cases)))


@dataclass
class ProcessResult:
    doc_id: int
    reused: bool
    page_count: int
    entry_count: int
    seconds: float
    warnings: list


def process_pdf(repo: Repository, filename: str, data: bytes, is_demo: bool = False,
                progress: Optional[Callable[[int, float, str], None]] = None) -> ProcessResult:
    """progress(stage, fraction, message): stage 1=extract, 2=structure, 3=match."""
    t0 = time.perf_counter()
    cb = progress or (lambda *_: None)
    h = repo.hash_bytes(data)
    existing = repo.find_document_by_hash(h)
    if existing:
        repo.set_setting("active_document_id", existing.id)
        return ProcessResult(existing.id, True, existing.page_count, existing.entry_count,
                             time.perf_counter() - t0, existing.warnings)
    cb(1, 0.0, "Extracting document text")
    res = extract_document(data, lambda i, n: cb(1, i / n, f"Reading page {i} of {n}"))
    cb(2, 0.0, "Identifying case entries")
    parsed = parse_extraction(res)
    if not parsed.entries:
        raise PDFProcessingError(
            "no_entries",
            f"Text was read from {res.page_count} page(s), but no case-number rows were recognised. "
            "The layout may be unsupported (expected rows with an item number, case number such as "
            "CS/123/2024, and parties). Nothing was saved.")
    cb(2, 1.0, f"Found {len(parsed.entries)} entries")
    meta = dict(page_count=res.page_count, method=res.method, list_date=parsed.list_date,
                title=parsed.title, warnings=res.warnings + parsed.warnings)
    doc_id = repo.add_document(filename, data, meta, parsed.entries, is_demo)
    repo.set_setting("active_document_id", doc_id)
    cb(3, 1.0, "Matching against My Cases")
    return ProcessResult(doc_id, False, res.page_count, len(parsed.entries),
                         time.perf_counter() - t0, meta["warnings"])


def load_demo(repo: Repository) -> int:
    """Load the fictional demo advocate's cases and sample cause list."""
    if not any(c.is_demo for c in repo.list_cases()):
        for num, year, court, parties, nick in DEMO_CASES:
            repo.add_case(num, year, court, parties, nick, True, is_demo=True)
    if repo.get_setting("advocate_name") in (None, "", "Advocate"):
        repo.set_setting("advocate_name", DEMO_ADVOCATE)
    return process_pdf(repo, DEMO_FILENAME, build_sample_pdf(), is_demo=True).doc_id
