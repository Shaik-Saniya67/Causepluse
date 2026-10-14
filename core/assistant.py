"""CausePulse Assistant.

Answers are built from the uploaded cause-list data and the saved case list, using
deterministic logic first. An LLM (Groq, optional) is used only for open-ended questions
that the rules cannot route, and it only ever sees the structured records below.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Optional

from core.case_matcher import signal_summary
from core.models import NOT_FOUND_NOTE, STATUS_MATCHED, STATUS_NOT_FOUND, STATUS_REVIEW
from core.normalize import CASE_PATTERN, norm_court, parse_case_ref

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "llama-3.3-70b-versatile"

SUGGESTIONS = [
    "Find my cases listed in Court 3",
    "Show cases that need manual verification",
    "Which saved cases were not found in this PDF?",
    "Explain why entries were marked uncertain",
]

SYSTEM_PROMPT = (
    "You are CausePulse Assistant, helping an advocate read ONE uploaded court cause list. "
    "Answer ONLY from the JSON records provided. Never invent case numbers, courts, item numbers, "
    "hearing times, adjournments, case status or legal advice. Hearing time exists only if the "
    "'published_time' field is non-empty; item number is NOT a time. 'Not found' means not found in "
    "the uploaded PDF, not cancelled or removed. If the records do not contain the answer, say so "
    "plainly. Mention page numbers when you cite an entry. Be brief."
)


@dataclass
class Answer:
    text: str
    refs: list = field(default_factory=list)  # [(label, page)]
    used_llm: bool = False


def llm_available(api_key: Optional[str]) -> bool:
    return bool(api_key and api_key.strip())


def _line(r) -> str:
    s = r.saved
    name = f"**{s.label}**" + (f" ({s.nickname})" if s.nickname else "")
    e = r.entry
    if r.status == STATUS_MATCHED and e:
        bits = [e.court or "court not stated"]
        bits.append(f"item {e.item_number}" if e.item_number is not None else "no item number")
        bits.append(f"published time {e.published_time}" if e.published_time else "no time published")
        bits.append(f"page {e.page_number}")
        parties = f" — {e.party_names}" if e.party_names else ""
        return f"{name}{parties}: " + ", ".join(bits)
    if r.status == STATUS_REVIEW:
        where = "; ".join(f"{c.entry.court or '?'} p.{c.entry.page_number}" for c in r.candidates)
        return f"{name}: needs review" + (f" (candidates: {where})" if where else "") + f". {r.reason}"
    return f"{name}: not found in this PDF."


def _refs(results) -> list:
    out = []
    for r in results:
        for c in (r.candidates if r.status == STATUS_REVIEW else ([r] if r.entry else [])):
            e = c.entry if hasattr(c, "entry") and not hasattr(c, "saved") else r.entry
            if e:
                out.append((r.saved.label, e.page_number))
    return out


def _bulleted(results) -> str:
    return "\n".join(f"- {_line(r)}" for r in results)


def answer_rules(q: str, results: list, entries: list, doc) -> Optional[Answer]:
    ql = q.lower()
    review = [r for r in results if r.status == STATUS_REVIEW]
    notfound = [r for r in results if r.status == STATUS_NOT_FOUND]
    matched = [r for r in results if r.status == STATUS_MATCHED]

    ref = None
    m = CASE_PATTERN.search(q.upper())
    if m:
        ref = parse_case_ref(m.group(0))

    if re.search(r"\b(explain|why)\b", ql) and not ref:
        if not review:
            return Answer("Nothing is marked uncertain right now. Every saved case is either matched or not found.")
        parts = []
        for r in review:
            sig = signal_summary(r.candidates[0].signals) if r.candidates else ""
            parts.append(f"- **{r.saved.label}**: {r.reason}" + (f" ({sig})" if sig else ""))
        return Answer("These entries are uncertain because:\n" + "\n".join(parts) +
                      "\n\nOpen **Needs Review** to see the original page and decide.", _refs(review))

    cm = re.search(r"court\s*(?:room|no\.?|number|hall)?\s*#?\s*(\d+[a-z]?)", ql)
    if cm:
        target = norm_court(f"Court {cm.group(1)}")
        in_court = [r for r in matched if r.entry and norm_court(r.entry.court) == target]
        maybe = [r for r in review if any(norm_court(c.entry.court) == target for c in r.candidates)]
        total = sum(1 for e in entries if norm_court(e.court) == target)
        if not in_court and not maybe:
            return Answer(f"None of your saved cases were matched in Court {cm.group(1).upper()} in this PDF "
                          f"({total} entries are listed for that court).")
        text = f"Your cases in Court {cm.group(1).upper()} ({total} entries listed in total):\n" + _bulleted(in_court)
        if maybe:
            text += "\n\nPossible (needs review):\n" + _bulleted(maybe)
        return Answer(text, _refs(in_court + maybe))

    if ref:
        hits = []
        for r in results:
            try:
                sref = parse_case_ref(r.saved.case_number, r.saved.year)
            except ValueError:
                continue
            if sref and sref.number == ref.number and (not ref.year or sref.year == ref.year):
                hits.append(r)
        if hits:
            return Answer(_bulleted(hits), _refs(hits))
        found = [e for e in entries if e.number == ref.number and (not ref.year or e.year == ref.year)]
        if found:
            lines = "\n".join(f"- {e.case_number_raw} — {e.party_names or 'parties not extracted'}, "
                              f"{e.court or 'court not stated'}, page {e.page_number}" for e in found)
            return Answer("That number is not in your saved cases, but the cause list contains:\n" + lines,
                          [(e.case_number_raw, e.page_number) for e in found])
        return Answer(f"I couldn't find {m.group(0).strip()} in your saved cases or in this uploaded cause list. "
                      "That only describes this PDF, not the court's actual schedule.")

    if re.search(r"not found|missing|absent|not in|couldn.t find|didn.t find|not listed|unmatched", ql):
        if not notfound:
            return Answer("Every active saved case was either matched or flagged for review in this PDF.")
        return Answer("Not found in this uploaded PDF:\n" + _bulleted(notfound) + "\n\n" + NOT_FOUND_NOTE)

    if re.search(r"need|verif|uncertain|ambiguous|review|check|doubt", ql):
        if not review:
            return Answer("Nothing needs review right now.")
        return Answer("These need manual verification:\n" + _bulleted(review), _refs(review))

    if re.search(r"\btime|when|what hour|clock", ql):
        timed = [r for r in matched if r.entry and r.entry.published_time]
        if not timed:
            return Answer("No hearing times are published for your matched cases in this PDF. "
                          "Item numbers show listing order only; they are not times.")
        lines = "\n".join(f"- **{r.saved.label}**: {r.entry.published_time} ({r.entry.court}, page {r.entry.page_number})"
                          for r in timed)
        return Answer("Published hearing times in this PDF:\n" + lines +
                      "\n\nCases not listed here have no time printed in the document.", _refs(timed))

    if re.search(r"summary|overview|schedule|today|how many|hearing|list|status|all", ql):
        text = (f"{len(results)} tracked: **{len(matched)} matched**, **{len(review)} need review**, "
                f"**{len(notfound)} not found** in this PDF.")
        if matched:
            text += "\n\nYour matched hearings:\n" + _bulleted(matched)
        return Answer(text, _refs(matched))
    return None


def build_context(results: list, entries: list, doc) -> dict:
    recs = []
    for r in results:
        rec = {"saved_case": r.saved.label, "nickname": r.saved.nickname, "status": r.status, "reason": r.reason}
        if r.entry:
            e = r.entry
            rec["entry"] = dict(court=e.court, item_number=e.item_number, page=e.page_number,
                                published_time=e.published_time, parties=e.party_names, case_as_printed=e.case_number_raw)
        if r.status == STATUS_REVIEW:
            rec["candidates"] = [dict(court=c.entry.court, page=c.entry.page_number, item=c.entry.item_number,
                                      parties=c.entry.party_names) for c in r.candidates]
        recs.append(rec)
    ctx = {"document": getattr(doc, "filename", ""), "cause_list_date": getattr(doc, "list_date", None),
           "saved_case_results": recs}
    if len(entries) <= 250:
        ctx["all_entries"] = [dict(case=e.case_number_raw, court=e.court, item=e.item_number, page=e.page_number,
                                   time=e.published_time, parties=e.party_names) for e in entries]
    return ctx


def ask_llm(question: str, ctx: dict, api_key: str, model: Optional[str] = None, timeout: int = 25) -> Optional[str]:
    body = json.dumps({
        "model": model or os.getenv("GROQ_MODEL", DEFAULT_MODEL),
        "temperature": 0.1,
        "max_tokens": 500,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"RECORDS:\n{json.dumps(ctx, ensure_ascii=False)}\n\nQUESTION: {question}"},
        ],
    }).encode()
    req = urllib.request.Request(GROQ_URL, data=body, headers={
        "Content-Type": "application/json", "Authorization": f"Bearer {api_key}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
        return data["choices"][0]["message"]["content"].strip()
    except (urllib.error.URLError, TimeoutError, KeyError, ValueError, OSError):
        return None


HELP_TEXT = (
    "I can answer from your uploaded cause list and saved cases. Try:\n"
    "- *Find my cases listed in Court 3*\n- *Show cases that need manual verification*\n"
    "- *Which saved cases were not found in this PDF?*\n- *Which cases have a published time?*\n"
    "- *Where is CS/412/2023?*"
)


def answer_question(question: str, results: list, entries: list, doc,
                    api_key: Optional[str] = None, use_llm: bool = True) -> Answer:
    if doc is None:
        return Answer("No cause list is loaded yet. Upload a PDF (or load the demo data) and I can answer from it.")
    a = answer_rules(question, results, entries, doc)
    if a:
        return a
    if use_llm and llm_available(api_key):
        text = ask_llm(question, build_context(results, entries, doc), api_key)
        if text:
            return Answer(text + "\n\n*AI-assisted answer from your uploaded data. Verify against the source page.*",
                          used_llm=True)
        return Answer("The AI service didn't respond, so I can only answer the built-in questions.\n\n" + HELP_TEXT)
    return Answer("I'm not sure how to answer that from the uploaded data.\n\n" + HELP_TEXT)
