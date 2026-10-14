from __future__ import annotations

import re

import streamlit as st

from components.nav import go
from components.ui import chip, esc, field_rows, md, signals_html, source_image
from core.case_matcher import signal_summary
from core.models import NOT_FOUND_NOTE, STATUS_MATCHED, STATUS_NOT_FOUND, STATUS_REVIEW


def _save_cb(repo, entry_id):
    ss = st.session_state
    try:
        item = ss.get(f"ed_item_{entry_id}", "").strip()
        repo.update_entry(entry_id, case_number_raw=ss[f"ed_case_{entry_id}"], court=ss[f"ed_court_{entry_id}"],
                          item_number=int(item) if item.isdigit() else None,
                          party_names=ss[f"ed_par_{entry_id}"], stage=ss[f"ed_stage_{entry_id}"],
                          published_time=ss[f"ed_time_{entry_id}"])
        ss["flash"] = "Extraction corrected. Matching re-run, no re-upload needed."
    except ValueError as exc:
        ss["flash_err"] = str(exc)


def _decide(repo, saved_id, entry_id, decision):
    if decision is None:
        repo.clear_decision(saved_id, entry_id)
    else:
        repo.set_decision(saved_id, entry_id, decision)


def render(d):
    ss = st.session_state
    back = ss.get("back", "tracker")
    st.button("← Back", key="detail_back", on_click=go, args=(back,))
    sid, eid = ss.get("selected_saved_id"), ss.get("selected_entry_id")
    result = next((r for r in d.results if r.saved.id == sid), None) if sid else None
    entry = None
    if eid:
        entry = next((e for e in d.entries if e.id == eid), None)
    elif result and result.entry:
        entry = result.entry
    if not d.doc or (result is None and entry is None):
        md('<div class="cp-card cp-empty"><h3>Nothing selected</h3><div>Pick a case from the tracker.</div></div>')
        return

    status_html = chip(result.status) if result else '<span class="cp-chip">Extracted entry</span>'
    title = result.saved.label if result else (entry.case_number_raw if entry else "")
    md(f'<div class="cp-kicker">Case detail</div><div class="cp-title">{esc(title)}</div>{status_html}')

    left, right = st.columns([1, 1.15], gap="large")
    with left:
        if result:
            s = result.saved
            md('<div class="cp-kicker" style="margin-top:1rem">Saved case</div>' + '<div class="cp-card">' + field_rows([
                ("Case number", esc(s.label)), ("Nickname", esc(s.nickname) or "—"), ("Court", esc(s.court) or "—"),
                ("Parties", esc(s.party_names) or "—")]) + "</div>")
            md(f'<div class="cp-note" style="margin-top:.7rem"><b>Match reasoning:</b> {esc(result.reason)}</div>')
            if result.status == STATUS_NOT_FOUND:
                md(f'<div class="cp-note" style="margin-top:.5rem">{esc(NOT_FOUND_NOTE)}</div>')
            if result.signals:
                md(f'<div style="margin-top:.6rem">{signals_html(result.signals)}<div class="cp-mono" style="margin-top:.3rem">'
                   f'{esc(signal_summary(result.signals))}</div></div>')
            if result.verified and result.entry:
                st.button("Undo my confirmation", key="undo_conf", on_click=_decide,
                          args=(d.repo, s.id, result.entry.id, None))
            if result.status == STATUS_REVIEW and entry:
                b1, b2 = st.columns(2)
                b1.button("Confirm this entry", key="d_conf", type="primary", on_click=_decide,
                          args=(d.repo, s.id, entry.id, "confirmed"))
                b2.button("Reject this entry", key="d_rej", on_click=_decide, args=(d.repo, s.id, entry.id, "rejected"))
        if entry:
            md('<div class="cp-kicker" style="margin-top:1rem">Extracted from the cause list</div><div class="cp-card">' + field_rows([
                ("Case no. (printed)", esc(entry.case_number_raw)), ("Normalised", esc(entry.key)),
                ("Court", esc(entry.court) or "—"),
                ("Item number", str(entry.item_number) if entry.item_number is not None else "—"),
                ("Parties", esc(entry.party_names) or "—"), ("Stage", esc(entry.stage) or "—"),
                ("Published time", esc(entry.published_time) or "Not published in the source"),
                ("Source page", f"{entry.page_number} of {d.doc.page_count}"),
                ("Document", esc(d.doc.filename)),
                ("Corrected", "Yes, edited by you" if entry.corrected else "No")]) + "</div>")
            if entry.note:
                md(f'<div class="cp-note" style="margin-top:.5rem">{esc(entry.note)}</div>')
        elif result and result.status == STATUS_NOT_FOUND:
            q = re.sub(r"\D", " ", result.saved.case_number).split()
            num = q[0].lstrip("0") if q else ""
            st.caption("Search the document text in case it was extracted incorrectly:")
            term = st.text_input("Number or party name", value=num, key="nf_search")
            hits = [e for e in d.entries if term.strip() and term.strip().lower() in e.source_text.lower()][:8]
            for e in hits:
                st.button(f"p.{e.page_number} · {e.court or '?'} · {e.case_number_raw}", key=f"nf_hit_{e.id}",
                          on_click=go, args=("detail",), kwargs={"selected_entry_id": e.id})
            if term.strip() and not hits:
                st.caption("No row in the extracted text contains that.")
    with right:
        if entry:
            md('<div class="cp-kicker" style="margin-top:1rem">Source evidence</div>')
            img = source_image(d.repo, d.doc, entry)
            if img:
                st.image(img, caption=f"Page {entry.page_number}: matching row highlighted")
            with st.expander("Full page"):
                full = source_image(d.repo, d.doc, entry, crop=False)
                if full:
                    st.image(full)
            md(f'<div class="cp-kicker" style="margin:.6rem 0 .3rem">Extracted text</div><div class="cp-src">{esc(entry.source_text)}</div>')
    if entry:
        with st.expander("Correct this extraction and re-run matching"):
            k = entry.id
            st.text_input("Case number", entry.case_number_raw, key=f"ed_case_{k}")
            a, b = st.columns(2)
            a.text_input("Court", entry.court, key=f"ed_court_{k}")
            b.text_input("Item number", str(entry.item_number or ""), key=f"ed_item_{k}")
            st.text_input("Parties", entry.party_names, key=f"ed_par_{k}")
            c, e = st.columns(2)
            c.text_input("Stage", entry.stage, key=f"ed_stage_{k}")
            e.text_input("Published time (only if printed in the source)", entry.published_time, key=f"ed_time_{k}")
            st.button("Save correction", key=f"ed_save_{k}", type="primary", on_click=_save_cb, args=(d.repo, k))
