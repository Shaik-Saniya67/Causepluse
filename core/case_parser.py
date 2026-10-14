"""Turn extracted PDF rows into structured cause-list entries.

Only fields literally present in the source are captured. Nothing is invented:
a hearing time is recorded only if a time string appears in the row.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from core.normalize import CASE_PATTERN, normalize_number, normalize_type, normalize_year
from core.pdf_extractor import ExtractionResult

COURT_RE = re.compile(
    r"^\s*(?:COURT\s*ROOM|COURTROOM|COURT\s*HALL|COURT)\s*(?:NO\.?|NUMBER|#)?\s*[:.\-]?\s*(?P<c>\d{1,3}[A-Z]?)\b",
    re.I,
)
HEADER_RE = re.compile(r"\b(item|s\.?\s*no)\b.*\b(case|party|parties)\b", re.I)
PAGE_RE = re.compile(r"^\s*page\s+\d+(\s+of\s+\d+)?\s*$", re.I)
ITEM_CELL = re.compile(r"^\d{1,3}[.)]?$")
ITEM_PREFIX = re.compile(r"^(\d{1,3})[.)]?\s+(?=\S)")
VS_RE = re.compile(r"\b(?:vs?\.?|versus)\b", re.I)
TIME_RE = re.compile(
    r"(?<![\d:./])(?:(?:[01]?\d|2[0-3]):[0-5]\d(?:\s*(?:AM|PM)\b)?|(?:1[0-2]|0?[1-9])(?:[.:][0-5]\d)?\s*(?:AM|PM)\b)(?![\d:/])",
    re.I,
)
_CONNECTOR = re.compile(r"\s*(?:&|AND|WITH|,|;|/)?\s*")
_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
DATE_NUM = re.compile(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{4})\b")
DATE_TXT = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?[\s,.-]+([A-Za-z]{3,9})\.?[\s,.-]+(\d{4})\b")


@dataclass
class ParseOutput:
    entries: list = field(default_factory=list)  # list[dict]
    list_date: Optional[str] = None
    title: Optional[str] = None
    warnings: list = field(default_factory=list)


def detect_list_date(texts: list) -> Optional[str]:
    for t in texts:
        for m in DATE_TXT.finditer(t):
            mon = _MONTHS.get(m.group(2)[:3].lower())
            if mon:
                try:
                    return date(int(m.group(3)), mon, int(m.group(1))).isoformat()
                except ValueError:
                    pass
        for m in DATE_NUM.finditer(t):
            try:
                return date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
            except ValueError:
                pass
    return None


def _leading_case_matches(cell: str) -> list:
    """Case numbers at the very start of a cell, e.g. 'CS 1/2024 & CS 2/2024'."""
    out, pos = [], 0
    while True:
        c = _CONNECTOR.match(cell, pos)
        pos = c.end() if c else pos
        m = CASE_PATTERN.match(cell, pos)
        if not m:
            break
        out.append(m)
        pos = m.end()
    return out


def _union(a, b):
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


def _split_time(cells: list):
    """Pull the last published time out of the trailing cells. Returns (time, cells)."""
    cells = list(cells)
    for i in range(len(cells) - 1, -1, -1):
        found = list(TIME_RE.finditer(cells[i]))
        if found:
            m = found[-1]
            t = re.sub(r"\s+", " ", m.group(0)).strip()
            cells[i] = (cells[i][: m.start()] + cells[i][m.end():]).strip(" -|,")
            return t, [c for c in cells if c]
    return "", [c for c in cells if c]


def _parse_entry_row(row, court: str, page_no: int):
    cells = row.cells
    item = None
    rest = cells
    if len(cells) > 1 and ITEM_CELL.match(cells[0]):
        item = int(re.sub(r"\D", "", cells[0]))
        rest = cells[1:]
    else:
        m = ITEM_PREFIX.match(row.text)
        if m:
            item = int(m.group(1))
            rest = [row.text[m.end():]]
    case_idx, matches = None, []
    for i, c in enumerate(rest[:2]):
        ms = _leading_case_matches(c)
        if ms:
            case_idx, matches = i, ms
            break
    if not matches:
        return None, item is not None
    tail_cells = [rest[case_idx][matches[-1].end():].strip(" -|,")] + rest[case_idx + 1:]
    tail_cells = [c for c in tail_cells if c]
    published_time, tail_cells = _split_time(tail_cells)
    parties, stage_cells = "", []
    vs_idx = next((i for i, c in enumerate(tail_cells) if VS_RE.search(c)), None)
    if vs_idx is not None:
        parties = tail_cells[vs_idx]
        stage_cells = tail_cells[:vs_idx] + tail_cells[vs_idx + 1:]
    elif tail_cells:
        parties = tail_cells[0]
        stage_cells = tail_cells[1:]
    entries = []
    primary_raw = matches[0].group(0).strip(" /-&,;")
    for k, m in enumerate(matches):
        raw = m.group(0).strip(" /-&,;")
        entries.append(
            dict(
                page_number=page_no,
                item_number=item,
                case_number_raw=raw,
                case_type=normalize_type(m.group("type")),
                number=normalize_number(m.group("num")),
                year=normalize_year(m.group("year")),
                court=court,
                party_names=parties,
                stage=" | ".join(stage_cells),
                published_time=published_time,
                source_text=row.text,
                bbox=tuple(row.bbox),
                note="" if k == 0 else f"Listed together with {primary_raw}",
            )
        )
    return entries, False


def parse_extraction(res: ExtractionResult) -> ParseOutput:
    out = ParseOutput()
    court = ""
    unparsed = []
    first_rows = [r.text for r in (res.pages[0] if res.pages else [])][:20]
    out.list_date = detect_list_date(first_rows)
    out.title = next((t for t in first_rows[:10] if re.search(r"cause\s*list", t, re.I)), None)
    for page_no, rows in enumerate(res.pages, 1):
        prev = None  # entries of the previous row on this page
        for row in rows:
            text = row.text.strip()
            if not text:
                continue
            if PAGE_RE.match(text):
                prev = None
                continue
            has_case = bool(CASE_PATTERN.search(text))
            mc = COURT_RE.match(text)
            if mc and not has_case:
                court = f"Court {mc.group('c').upper()}"
                prev = None
                continue
            if HEADER_RE.search(text) and not has_case:
                prev = None
                continue
            entries, item_without_case = _parse_entry_row(row, court, page_no)
            if entries:
                out.entries.extend(entries)
                prev = entries
                continue
            if prev and (row.bbox[1] - prev[0]["bbox"][3]) <= 5.0 and not item_without_case:
                for e in prev:
                    e["source_text"] += " " + text
                    e["bbox"] = _union(e["bbox"], row.bbox)
                    if len(row.cells) == 1 and not TIME_RE.fullmatch(text):
                        e["party_names"] = (e["party_names"] + " " + text).strip()
                continue
            if item_without_case:
                unparsed.append((page_no, text[:60]))
            prev = None
    if unparsed:
        pages = sorted({p for p, _ in unparsed})
        out.warnings.append(
            f"{len(unparsed)} row(s) started with an item number but no recognisable case number "
            f"(page(s) {', '.join(map(str, pages[:8]))}). They were not added."
        )
    if out.entries and not any(e["court"] for e in out.entries):
        out.warnings.append("No court headings (e.g. 'COURT NO. 3') were recognised; courts are blank.")
    return out
