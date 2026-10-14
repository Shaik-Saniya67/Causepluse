from __future__ import annotations

import csv
import io

import streamlit as st

from components.ui import chip, esc, md, page_header
from core.models import STATUS_NOT_FOUND
from core.normalize import parse_case_ref


def _validate(case_number: str, year_txt: str, repo, exclude_id=None):
    """Returns (year, error)."""
    if not case_number.strip():
        return None, "Enter a case number."
    try:
        ref = parse_case_ref(case_number, year_txt.strip() or None)
    except ValueError as exc:
        return None, str(exc)
    if ref is None:
        return None, "Couldn't read that case number. Try a format like CS/412/2023 or CRL.M.C. 1180/2025."
    for c in repo.list_cases():
        if c.id == exclude_id:
            continue
        try:
            other = parse_case_ref(c.case_number, c.year)
        except ValueError:
            continue
        if other and other.key == ref.key:
            return None, f"{c.label} is already tracked."
    return ref.year, None


def _import_lines(repo, text: str):
    ok, errs = 0, []
    for n, row in enumerate(csv.reader(io.StringIO(text)), 1):
        row = [c.strip() for c in row]
        if not row or not row[0]:
            continue
        year, err = _validate(row[0], "", repo)
        if err:
            errs.append(f"Line {n}: {err}")
            continue
        repo.add_case(row[0], year, row[1] if len(row) > 1 else "", row[2] if len(row) > 2 else "",
                      row[3] if len(row) > 3 else "")
        ok += 1
    return ok, errs


def render(d):
    repo = d.repo
    page_header("Tracked cases", "My Cases",
                "Case numbers are matched after normalising spaces, slashes and punctuation. Different years or case types are never merged.")
    status_by_id = {r.saved.id: r for r in d.results}

    with st.expander("Add a case", expanded=not d.cases):
        with st.form("add_case", clear_on_submit=True):
            a, b = st.columns([2, 1])
            num = a.text_input("Case number", placeholder="e.g. CS/412/2023 or CRL.M.C. 1180/2025")
            yr = b.text_input("Year (optional if in the number)", placeholder="2023")
            c, e = st.columns(2)
            court = c.text_input("Court (optional)", placeholder="Court 3")
            nick = e.text_input("Nickname (optional)")
            parties = st.text_input("Party names (optional, improves disambiguation)")
            if st.form_submit_button("Add case", type="primary"):
                year, err = _validate(num, yr, repo)
                if err:
                    st.error(err)
                else:
                    repo.add_case(num, year, court, parties, nick)
                    st.session_state["flash"] = f"Added {num.strip()}."
                    st.rerun()

    with st.expander("Import a small list"):
        st.caption("One case per line: case number, court, party names, nickname (comma-separated; everything after the case number is optional).")
        text = st.text_area("Cases to import", height=110, key="import_text",
                            placeholder="CS/412/2023, Court 3, Verma Traders v. Sharma, Verma suit\nBAIL APPLN. 3341/2026")
        if st.button("Import", key="import_btn"):
            ok, errs = _import_lines(repo, text)
            if ok:
                st.session_state["flash"] = f"Imported {ok} case(s)."
            for e in errs:
                st.error(e)
            if ok and not errs:
                st.rerun()

    if not d.cases:
        md('<div class="cp-card cp-empty"><h3>No saved cases yet</h3><div>Add your first case number above.</div></div>')
        return
    md(f'<div class="cp-kicker" style="margin:1rem 0 .4rem">{len(d.cases)} saved · {sum(c.active for c in d.cases)} active</div>')
    for c in d.cases:
        r = status_by_id.get(c.id)
        badge = {"matched": "✓ matched", "review": "◐ review", "not_found": "○ not found"}.get(r.status, "") if r else ""
        title = f"{c.label}" + (f" · {c.nickname}" if c.nickname else "") + ("" if c.active else " · inactive") + \
            (f"   [{badge}]" if badge else "")
        with st.expander(title):
            with st.form(f"edit_{c.id}"):
                a, b = st.columns([2, 1])
                num = a.text_input("Case number", c.case_number, key=f"n_{c.id}")
                yr = b.text_input("Year", str(c.year or ""), key=f"y_{c.id}")
                x, y = st.columns(2)
                court = x.text_input("Court", c.court, key=f"c_{c.id}")
                nick = y.text_input("Nickname", c.nickname, key=f"k_{c.id}")
                parties = st.text_input("Party names", c.party_names, key=f"p_{c.id}")
                active = st.checkbox("Active (included in matching)", c.active, key=f"a_{c.id}")
                s1, s2 = st.columns(2)
                save = s1.form_submit_button("Save changes", type="primary")
                delete = s2.form_submit_button("Remove case")
            if save:
                year, err = _validate(num, yr, repo, exclude_id=c.id)
                if err:
                    st.error(err)
                else:
                    repo.update_case(c.id, case_number=num.strip(), year=year, court=court.strip(),
                                     party_names=parties.strip(), nickname=nick.strip(), active=active)
                    st.session_state["flash"] = "Saved. Matching re-run."
                    st.rerun()
            if delete:
                repo.delete_case(c.id)
                st.session_state["flash"] = f"Removed {c.label}."
                st.rerun()
