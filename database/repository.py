"""SQLite persistence. Thread-safe wrapper; use ':memory:' for per-session storage."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Optional

from core.models import DocumentRecord, Entry, SavedCase
from core.normalize import norm_court, normalize_number, normalize_type, normalize_year, parse_case_ref

SCHEMA = """
CREATE TABLE IF NOT EXISTS saved_cases(
  id INTEGER PRIMARY KEY AUTOINCREMENT, case_number TEXT NOT NULL, year INTEGER,
  court TEXT DEFAULT '', party_names TEXT DEFAULT '', nickname TEXT DEFAULT '',
  active INTEGER DEFAULT 1, is_demo INTEGER DEFAULT 0, created_at TEXT);
CREATE TABLE IF NOT EXISTS documents(
  id INTEGER PRIMARY KEY AUTOINCREMENT, filename TEXT, upload_time TEXT, page_count INTEGER,
  processing_status TEXT, content_hash TEXT, extraction_method TEXT, list_date TEXT, title TEXT,
  warnings TEXT DEFAULT '[]', entry_count INTEGER DEFAULT 0, is_demo INTEGER DEFAULT 0, pdf_bytes BLOB);
CREATE TABLE IF NOT EXISTS entries(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  page_number INTEGER, item_number INTEGER, case_number_raw TEXT, case_type TEXT, number TEXT,
  year INTEGER, court TEXT DEFAULT '', party_names TEXT DEFAULT '', stage TEXT DEFAULT '',
  published_time TEXT DEFAULT '', source_text TEXT DEFAULT '', bbox TEXT, corrected INTEGER DEFAULT 0,
  note TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS decisions(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  saved_case_id INTEGER NOT NULL REFERENCES saved_cases(id) ON DELETE CASCADE,
  entry_id INTEGER NOT NULL REFERENCES entries(id) ON DELETE CASCADE,
  decision TEXT NOT NULL CHECK(decision IN ('confirmed','rejected')),
  UNIQUE(saved_case_id, entry_id));
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
"""

_ENTRY_COLS = ("page_number,item_number,case_number_raw,case_type,number,year,court,party_names,"
               "stage,published_time,source_text,bbox,corrected,note")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Repository:
    def __init__(self, path: str = ":memory:"):
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        with self._lock:
            self.conn.executescript(SCHEMA)
            self.conn.commit()

    def _run(self, sql, params=(), commit=True):
        with self._lock:
            cur = self.conn.execute(sql, params)
            if commit:
                self.conn.commit()
            return cur

    # ---- saved cases -------------------------------------------------
    @staticmethod
    def _case(r) -> SavedCase:
        return SavedCase(r["id"], r["case_number"], r["year"], r["court"] or "", r["party_names"] or "",
                         r["nickname"] or "", bool(r["active"]), bool(r["is_demo"]))

    def add_case(self, case_number, year=None, court="", party_names="", nickname="",
                 active=True, is_demo=False) -> int:
        cur = self._run(
            "INSERT INTO saved_cases(case_number,year,court,party_names,nickname,active,is_demo,created_at)"
            " VALUES(?,?,?,?,?,?,?,?)",
            (case_number.strip(), year, court.strip(), party_names.strip(), nickname.strip(),
             int(active), int(is_demo), _now()))
        return cur.lastrowid

    def update_case(self, case_id, **fields):
        allowed = {"case_number", "year", "court", "party_names", "nickname", "active"}
        sets = {k: v for k, v in fields.items() if k in allowed}
        if not sets:
            return
        if "active" in sets:
            sets["active"] = int(sets["active"])
        cols = ", ".join(f"{k}=?" for k in sets)
        self._run(f"UPDATE saved_cases SET {cols} WHERE id=?", (*sets.values(), case_id))

    def delete_case(self, case_id):
        self._run("DELETE FROM saved_cases WHERE id=?", (case_id,))

    def list_cases(self) -> list:
        return [self._case(r) for r in self._run("SELECT * FROM saved_cases ORDER BY id", commit=False)]

    # ---- documents ---------------------------------------------------
    @staticmethod
    def _doc(r) -> DocumentRecord:
        return DocumentRecord(r["id"], r["filename"], r["upload_time"], r["page_count"],
                              r["processing_status"], r["content_hash"], r["extraction_method"],
                              r["list_date"], r["title"], json.loads(r["warnings"] or "[]"),
                              r["entry_count"], bool(r["is_demo"]))

    @staticmethod
    def hash_bytes(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def add_document(self, filename, data: bytes, meta: dict, entries: list, is_demo=False) -> int:
        with self._lock:
            cur = self.conn.execute(
                "INSERT INTO documents(filename,upload_time,page_count,processing_status,content_hash,"
                "extraction_method,list_date,title,warnings,entry_count,is_demo,pdf_bytes)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (filename, _now(), meta.get("page_count", 0), "processed", self.hash_bytes(data),
                 meta.get("method", ""), meta.get("list_date"), meta.get("title"),
                 json.dumps(meta.get("warnings", [])), len(entries), int(is_demo), data))
            doc_id = cur.lastrowid
            for e in entries:
                self.conn.execute(
                    f"INSERT INTO entries(document_id,{_ENTRY_COLS}) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (doc_id, e["page_number"], e["item_number"], e["case_number_raw"], e["case_type"],
                     e["number"], e["year"], e.get("court", ""), e.get("party_names", ""),
                     e.get("stage", ""), e.get("published_time", ""), e.get("source_text", ""),
                     json.dumps(e["bbox"]) if e.get("bbox") else None, 0, e.get("note", "")))
            self.conn.commit()
        return doc_id

    def find_document_by_hash(self, content_hash: str) -> Optional[DocumentRecord]:
        r = self._run("SELECT * FROM documents WHERE content_hash=? LIMIT 1", (content_hash,), False).fetchone()
        return self._doc(r) if r else None

    def list_documents(self) -> list:
        cols = ("id,filename,upload_time,page_count,processing_status,content_hash,extraction_method,"
                "list_date,title,warnings,entry_count,is_demo")
        return [self._doc(r) for r in self._run(f"SELECT {cols} FROM documents ORDER BY id DESC", commit=False)]

    def get_document(self, doc_id) -> Optional[DocumentRecord]:
        for d in self.list_documents():
            if d.id == doc_id:
                return d
        return None

    def get_pdf_bytes(self, doc_id) -> Optional[bytes]:
        r = self._run("SELECT pdf_bytes FROM documents WHERE id=?", (doc_id,), False).fetchone()
        return bytes(r["pdf_bytes"]) if r and r["pdf_bytes"] is not None else None

    def delete_document(self, doc_id):
        self._run("DELETE FROM documents WHERE id=?", (doc_id,))
        if self.get_setting("active_document_id") == str(doc_id):
            self._run("DELETE FROM settings WHERE key='active_document_id'")

    # ---- entries -----------------------------------------------------
    @staticmethod
    def _entry(r) -> Entry:
        return Entry(r["id"], r["document_id"], r["page_number"], r["item_number"], r["case_number_raw"],
                     r["case_type"] or "", r["number"] or "", r["year"], r["court"] or "",
                     r["party_names"] or "", r["stage"] or "", r["published_time"] or "",
                     r["source_text"] or "", tuple(json.loads(r["bbox"])) if r["bbox"] else None,
                     bool(r["corrected"]), r["note"] or "")

    def entries_for(self, doc_id) -> list:
        rows = self._run("SELECT * FROM entries WHERE document_id=? ORDER BY id", (doc_id,), False)
        return [self._entry(r) for r in rows]

    def get_entry(self, entry_id) -> Optional[Entry]:
        r = self._run("SELECT * FROM entries WHERE id=?", (entry_id,), False).fetchone()
        return self._entry(r) if r else None

    def update_entry(self, entry_id, case_number_raw=None, court=None, item_number=None,
                     party_names=None, stage=None, published_time=None):
        """Correct an extracted entry. Raises ValueError on an unreadable case number."""
        sets = {}
        if case_number_raw is not None:
            ref = parse_case_ref(case_number_raw)
            if ref is None or ref.year is None:
                raise ValueError("Enter a case number with number and year, e.g. CS/412/2023.")
            sets.update(case_number_raw=case_number_raw.strip(), case_type=ref.type,
                        number=normalize_number(ref.number), year=ref.year)
        if court is not None:
            sets["court"] = court.strip()
        if item_number is not None:
            sets["item_number"] = item_number
        if party_names is not None:
            sets["party_names"] = party_names.strip()
        if stage is not None:
            sets["stage"] = stage.strip()
        if published_time is not None:
            sets["published_time"] = published_time.strip()
        if sets:
            sets["corrected"] = 1
            cols = ", ".join(f"{k}=?" for k in sets)
            self._run(f"UPDATE entries SET {cols} WHERE id=?", (*sets.values(), entry_id))

    # ---- review decisions --------------------------------------------
    def set_decision(self, saved_case_id, entry_id, decision):
        self._run("INSERT INTO decisions(saved_case_id,entry_id,decision) VALUES(?,?,?) "
                  "ON CONFLICT(saved_case_id,entry_id) DO UPDATE SET decision=excluded.decision",
                  (saved_case_id, entry_id, decision))

    def clear_decision(self, saved_case_id, entry_id):
        self._run("DELETE FROM decisions WHERE saved_case_id=? AND entry_id=?", (saved_case_id, entry_id))

    def clear_decisions_for_case(self, saved_case_id):
        self._run("DELETE FROM decisions WHERE saved_case_id=?", (saved_case_id,))

    def decisions_for(self, doc_id) -> dict:
        rows = self._run("SELECT d.saved_case_id, d.entry_id, d.decision FROM decisions d "
                         "JOIN entries e ON e.id=d.entry_id WHERE e.document_id=?", (doc_id,), False)
        return {(r["saved_case_id"], r["entry_id"]): r["decision"] for r in rows}

    # ---- settings & housekeeping -------------------------------------
    def get_setting(self, key, default=None):
        r = self._run("SELECT value FROM settings WHERE key=?", (key,), False).fetchone()
        return r["value"] if r else default

    def set_setting(self, key, value):
        self._run("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                  (key, str(value)))

    def delete_demo_data(self):
        self._run("DELETE FROM documents WHERE is_demo=1")
        self._run("DELETE FROM saved_cases WHERE is_demo=1")

    def clear_documents(self):
        self._run("DELETE FROM documents")
        self._run("DELETE FROM settings WHERE key='active_document_id'")

    def clear_all(self):
        for t in ("decisions", "entries", "documents", "saved_cases", "settings"):
            self._run(f"DELETE FROM {t}")
