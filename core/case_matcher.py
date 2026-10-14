"""Deterministic matching of saved cases against cause-list entries.

Tiers (the strongest non-empty tier wins):
  1  exact on type + number + year
  2  number (+year/type where known) but the saved case lacks type or year
  3  same number and year, different case type
  4  same type/year, number differs by one character (possible typo/extraction error)
Only tier 1 can produce an automatic "Matched". Everything else is "Needs review".
Nothing is ever silently chosen between two plausible entries.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Optional

from core.models import (
    NOT_FOUND_NOTE, STATUS_MATCHED, STATUS_NOT_FOUND, STATUS_REVIEW,
    Candidate, Entry, MatchResult, SavedCase,
)
from core.normalize import CaseRef, norm_court, parse_case_ref, within_one_edit

PARTY_OK = 0.5
PARTY_BAD = 0.25
_STOP = {"vs", "v", "versus", "and", "the", "pvt", "ltd", "limited", "private", "co",
         "company", "state", "of", "anr", "ors", "another", "others", "m", "s"}


def _tokens(s: str) -> set:
    return {t for t in re.findall(r"[a-z0-9]+", (s or "").lower()) if t not in _STOP and len(t) > 1}


def party_similarity(a: str, b: str) -> Optional[float]:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return None
    small, big = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    hits = sum(1 for t in small if t in big or any(SequenceMatcher(None, t, u).ratio() >= 0.85 for u in big))
    return hits / len(small)


def courts_equal(a: str, b: str) -> Optional[bool]:
    na, nb = norm_court(a), norm_court(b)
    if not na or not nb:
        return None
    return na == nb


def compute_signals(sc: SavedCase, ref: CaseRef, e: Entry) -> dict:
    def tri(x, y):
        if x in (None, "") or y in (None, ""):
            return "unknown"
        return "match" if x == y else "mismatch"

    sim = party_similarity(sc.party_names, e.party_names)
    court = courts_equal(sc.court, e.court)
    return {
        "number": tri(ref.number, e.number),
        "year": tri(ref.year, e.year),
        "type": tri(ref.type, e.case_type),
        "court": "unknown" if court is None else ("match" if court else "mismatch"),
        "parties": "unknown" if sim is None else ("match" if sim >= PARTY_OK else ("mismatch" if sim < PARTY_BAD else "unknown")),
    }


def signal_summary(signals: dict) -> str:
    m = sum(v == "match" for v in signals.values())
    x = sum(v == "mismatch" for v in signals.values())
    u = sum(v == "unknown" for v in signals.values())
    parts = [f"{m} of {len(signals)} signals agree"]
    if x:
        parts.append(f"{x} conflict")
    if u:
        parts.append(f"{u} unknown")
    return " · ".join(parts)


def _order(e: Entry):
    m = re.search(r"\d+", e.court or "")
    return (int(m.group()) if m else 999, e.court, e.page_number, e.item_number or 0)


def _tier(ref: CaseRef, entries: list):
    t1 = [e for e in entries if ref.type and ref.year and e.number == ref.number
          and e.year == ref.year and e.case_type == ref.type]
    if t1:
        return 1, t1
    t2 = [e for e in entries if e.number == ref.number
          and (ref.year is None or e.year == ref.year)
          and (not ref.type or e.case_type == ref.type)]
    if t2 and (not ref.type or ref.year is None):
        return 2, t2
    if ref.year:
        t3 = [e for e in entries if e.number == ref.number and e.year == ref.year
              and ref.type and e.case_type and e.case_type != ref.type]
        if t3:
            return 3, t3
    t4 = [e for e in entries if len(ref.number) >= 3 and len(e.number) >= 3
          and within_one_edit(ref.number, e.number)
          and (ref.year is None or e.year == ref.year)
          and (not ref.type or e.case_type == ref.type)]
    if t4:
        return 4, t4
    return 0, []


def _joined(items):
    items = list(items)
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def match_case(sc: SavedCase, entries: list, decisions: dict) -> MatchResult:
    try:
        ref = parse_case_ref(sc.case_number, sc.year)
    except ValueError as exc:
        ref = None
        err = str(exc)
    else:
        err = "The saved case number could not be read."
    if ref is None:
        return MatchResult(sc, STATUS_REVIEW, reason=f"{err} Edit it in My Cases.")

    confirmed = [e for e in entries if decisions.get((sc.id, e.id)) == "confirmed"]
    if confirmed:
        e = confirmed[0]
        sig = compute_signals(sc, ref, e)
        return MatchResult(sc, STATUS_MATCHED, e, [Candidate(e, "Confirmed by you", sig)],
                           "You confirmed this entry as your case.", True, sig)
    rejected = [e for e in entries if decisions.get((sc.id, e.id)) == "rejected"]
    live = [e for e in entries if decisions.get((sc.id, e.id)) != "rejected"]
    tier, cands = _tier(ref, live)
    if not cands:
        reason = NOT_FOUND_NOTE
        if rejected:
            reason += f" You rejected {len(rejected)} possible entr{'y' if len(rejected) == 1 else 'ies'}."
        return MatchResult(sc, STATUS_NOT_FOUND, reason=reason, rejected_count=len(rejected))
    cands = sorted(cands, key=_order)

    def cand(e, why):
        return Candidate(e, why, compute_signals(sc, ref, e), tier)

    if tier == 1:
        pool, notes, court_conflict = cands, [], False
        if sc.court:
            in_court = [e for e in pool if courts_equal(sc.court, e.court) is True]
            if in_court and len(in_court) < len(pool):
                pool = in_court
                notes.append("narrowed using the court you saved")
            elif not in_court and any(courts_equal(sc.court, e.court) is False for e in pool):
                court_conflict = True
        if len(pool) > 1 and sc.party_names:
            good = [e for e in pool
                    if (party_similarity(sc.party_names, e.party_names) or 0) >= PARTY_OK]
            if len(good) == 1:
                pool = good
                notes.append("narrowed using the party names you saved")
        if len(pool) == 1:
            e = pool[0]
            problems = []
            if court_conflict:
                problems.append(f"your saved court ({sc.court}) differs from the listed court ({e.court})")
            ps = party_similarity(sc.party_names, e.party_names)
            if ps is not None and ps < PARTY_BAD:
                problems.append("the party names look different")
            c = cand(e, "Exact match on case type, number and year.")
            if problems:
                c.reason = "Case number matches, but " + " and ".join(problems) + "."
                return MatchResult(sc, STATUS_REVIEW, e, [c], c.reason, False, c.signals)
            extra = ""
            if len(cands) > 1:
                extra = f" {len(cands)} entries share this number; {notes[0]}." if notes else ""
            c.reason = "Exact match on case type, number and year." + extra
            return MatchResult(sc, STATUS_MATCHED, e, [c], c.reason, False, c.signals)
        cs = [cand(e, f"Entry in {e.court or 'unknown court'}, page {e.page_number}.") for e in pool]
        reason = (f"{len(pool)} entries in this cause list share the case number {ref.key}. "
                  "Pick the one that is yours (or reject them all).")
        return MatchResult(sc, STATUS_REVIEW, pool[0], cs, reason, False, cs[0].signals)

    if tier == 2:
        missing = _joined([m for m, absent in (("case type", not ref.type), ("year", ref.year is None)) if absent])
        reason = (f"Your saved case has no {missing}, so {len(cands)} listed "
                  f"entr{'y' if len(cands) == 1 else 'ies'} with number {ref.number} could be yours. "
                  "Confirm which one, if any.")
    elif tier == 3:
        types = _joined(sorted({e.case_type for e in cands}))
        reason = (f"Same number and year, but a different case type (saved {ref.type}, listed {types}). "
                  "These may be different cases.")
    else:
        nums = _joined(sorted({e.number for e in cands}))
        reason = (f"No exact match. Listed number {nums} differs from your saved {ref.number} by one "
                  "character: possibly a typo or an extraction error.")
    cs = [cand(e, reason) for e in cands]
    return MatchResult(sc, STATUS_REVIEW, cands[0], cs, reason, False, cs[0].signals)


def match_all(saved: list, entries: list, decisions: Optional[dict] = None) -> list:
    decisions = decisions or {}
    return [match_case(sc, entries, decisions) for sc in saved if sc.active]


def summarize(results: list) -> dict:
    return {
        "tracked": len(results),
        "matched": sum(r.status == STATUS_MATCHED for r in results),
        "review": sum(r.status == STATUS_REVIEW for r in results),
        "not_found": sum(r.status == STATUS_NOT_FOUND for r in results),
    }


def sort_results(results: list) -> list:
    order = {STATUS_MATCHED: 0, STATUS_REVIEW: 1, STATUS_NOT_FOUND: 2}

    def key(r):
        e = r.entry
        return (order[r.status],) + (_order(e) if e else (999, "", 0, 0)) + (r.saved.label,)

    return sorted(results, key=key)
