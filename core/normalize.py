"""Case-number normalisation.

A case reference is reduced to (type, number, year):
  "CS No. 412/2023", "cs-412-2023", "CS/412/2023"  ->  CS / 412 / 2023
  "CRL.M.C. 1180 / 2025"                            ->  CRLMC / 1180 / 2025
  "W.P.(C)-2209-2024"                               ->  WPC / 2209 / 2024
Different years or different case types are *never* collapsed together.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

# Type tokens are upper-case (CS, CRL.M.C., W.P.(C), BAIL APPLN.). Searching is
# case-sensitive on purpose so that party-name words are not swallowed.
CASE_PATTERN = re.compile(
    r"(?<![A-Za-z0-9/])"
    r"(?P<type>(?:[A-Z][A-Z.&()]*[\s/\-]?){0,4}?)"
    r"(?:(?:NO|No)\.?\s*)?"
    r"(?P<num>\d{1,6})"
    r"\s*[/\-\\]\s*"
    r"(?P<year>\d{4}|\d{2})"
    r"(?![\d/])"
)
_NUMBER_ONLY = re.compile(
    r"(?P<type>(?:[A-Z][A-Z.&()]*[\s/\-]?){0,4}?)\s*(?:(?:NO|No)\.?\s*)?(?P<num>\d{1,6})"
)


@dataclass(frozen=True)
class CaseRef:
    type: str
    number: str
    year: Optional[int]

    @property
    def key(self) -> str:
        return "/".join(p for p in (self.type, self.number, str(self.year or "")) if p)


def normalize_type(raw: str) -> str:
    t = (raw or "").upper()
    t = re.sub(r"\bCASE\b", " ", t)
    t = re.sub(r"\bNO\b\.?", " ", t)
    return re.sub(r"[^A-Z0-9]", "", t)


def normalize_number(raw: str) -> str:
    n = re.sub(r"\D", "", raw or "").lstrip("0")
    return n or "0"


def normalize_year(raw) -> Optional[int]:
    if raw in (None, ""):
        return None
    s = re.sub(r"\D", "", str(raw))
    if not s:
        return None
    if len(s) == 2:
        y = int(s)
        return 2000 + y if y <= 60 else 1900 + y
    if len(s) == 4:
        y = int(s)
        return y if 1900 <= y <= 2100 else None
    return None


def ref_from_match(m: re.Match) -> CaseRef:
    return CaseRef(
        type=normalize_type(m.group("type")),
        number=normalize_number(m.group("num")),
        year=normalize_year(m.group("year")),
    )


def parse_case_ref(text, year=None) -> Optional[CaseRef]:
    """Parse user-typed case text. Raises ValueError on a year conflict."""
    if text is None:
        return None
    s = re.sub(r"\s+", " ", str(text).strip().upper())
    if not s:
        return None
    hint = normalize_year(year) if year not in (None, "") else None
    if year not in (None, "") and hint is None:
        raise ValueError(f"'{year}' is not a valid year.")
    m = CASE_PATTERN.search(s)
    if m:
        ref = ref_from_match(m)
        if hint and ref.year and hint != ref.year:
            raise ValueError(
                f"Year in the case number ({ref.year}) doesn't match the Year field ({hint})."
            )
        return CaseRef(ref.type, ref.number, ref.year or hint)
    m2 = _NUMBER_ONLY.fullmatch(s)
    if m2:
        return CaseRef(normalize_type(m2.group("type")), normalize_number(m2.group("num")), hint)
    return None


def within_one_edit(a: str, b: str) -> bool:
    """True if strings differ by exactly one insert/delete/substitute."""
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1
    short, long_ = (a, b) if len(a) < len(b) else (b, a)
    for i in range(len(long_)):
        if long_[:i] + long_[i + 1:] == short:
            return True
    return False


def norm_court(court: str) -> str:
    """'Court No. 3' / 'Court 3' / '3' -> '3'; other labels -> lowercase alnum."""
    c = (court or "").strip().lower()
    if not c:
        return ""
    m = re.search(r"(?:court\s*(?:room|hall)?|hall)\s*(?:no\.?|number|#)?\s*[:.\-]?\s*(\d+[a-z]?)", c)
    if m:
        return m.group(1)
    if re.fullmatch(r"\d+[a-z]?", c):
        return c
    return re.sub(r"[^a-z0-9]", "", c)
