"""CSV exports. Cells are sanitised against spreadsheet formula injection."""
from __future__ import annotations

import csv
import io
from typing import Optional

from core.models import STATUS_LABELS, STATUS_MATCHED, STATUS_REVIEW


def safe_cell(v) -> str:
    s = "" if v is None else str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@", "\t", "\r") else s


def fmt_date(iso: Optional[str]) -> str:
    if not iso:
        return ""
    from datetime import date
    try:
        return date.fromisoformat(iso).strftime("%d %b %Y")
    except ValueError:
        return iso


def schedule_rows(results: list, doc) -> list:
    rows = []
    for r in results:
        e = r.entry if r.status == STATUS_MATCHED else None
        cands = r.candidates if r.status == STATUS_REVIEW else []
        rows.append({
            "Hearing date (cause list)": fmt_date(doc.list_date) if doc else "",
            "Case number": r.saved.label,
            "Nickname": r.saved.nickname,
            "Party names": (e.party_names if e else r.saved.party_names),
            "Court": e.court if e else "",
            "Item number": e.item_number if e and e.item_number is not None else "",
            "Published hearing time": e.published_time if e else "",
            "Match status": STATUS_LABELS[r.status],
            "Match note": r.reason,
            "Source page": e.page_number if e else "",
            "Candidate pages": ", ".join(f"p.{c.entry.page_number}" for c in cands),
            "Source file": doc.filename if doc else "",
        })
    return rows


def _csv(rows: list, fieldnames: list) -> bytes:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fieldnames)
    w.writeheader()
    for r in rows:
        w.writerow({k: safe_cell(r.get(k, "")) for k in fieldnames})
    return buf.getvalue().encode("utf-8-sig")


SCHEDULE_FIELDS = ["Hearing date (cause list)", "Case number", "Nickname", "Party names", "Court",
                   "Item number", "Published hearing time", "Match status", "Match note",
                   "Source page", "Candidate pages", "Source file"]


def schedule_csv(results: list, doc) -> bytes:
    return _csv(schedule_rows(results, doc), SCHEDULE_FIELDS)


ENTRY_FIELDS = ["Page", "Court", "Item", "Case number (as printed)", "Normalised", "Party names",
                "Stage", "Published time", "Note", "Source text"]


def entries_csv(entries: list) -> bytes:
    rows = [{
        "Page": e.page_number, "Court": e.court, "Item": e.item_number or "",
        "Case number (as printed)": e.case_number_raw, "Normalised": e.key,
        "Party names": e.party_names, "Stage": e.stage, "Published time": e.published_time,
        "Note": e.note, "Source text": e.source_text,
    } for e in entries]
    return _csv(rows, ENTRY_FIELDS)
