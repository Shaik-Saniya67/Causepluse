from __future__ import annotations

import streamlit as st

from components.nav import go, open_detail
from components.ui import empty_state, esc, md, page_header, signals_html, source_image
from core.case_matcher import signal_summary
from core.models import STATUS_REVIEW


def _decide(repo, saved_id, entry_id, decision):
    if decision is None:
        repo.clear_decision(saved_id, entry_id)
    else:
        repo.set_decision(saved_id, entry_id, decision)
    st.session_state["flash"] = {"confirmed": "Confirmed. Case moved to Matched (verified by you).",
                                 "rejected": "Rejected. That entry won't be suggested again for this case.",
                                 None: "Decision cleared."}[decision]


def _saved_card(r):
    nick = f' <span style="font-size:.9rem;color:var(--muted)">· {esc(r.saved.nickname)}</span>' if r.saved.nickname else ""
    md(f'<div class="cp-card"><div class="cp-kicker">Your saved case</div>'
       f'<div class="cp-res-title" style="margin-top:.2rem">{esc(r.saved.label)}{nick}</div>'
       f'<div class="cp-note" style="margin-top:.5rem"><b>Why uncertain:</b> {esc(r.reason)}</div></div>')


def _fact(label, value):
    return f'<div class="cp-fact"><span>{esc(label)}</span><b>{value}</b></div>'


def _candidate_header(e, idx, total):
    item = e.item_number if e.item_number is not None else "—"
    time = esc(e.published_time) if e.published_time else "Not published"
    facts = "".join([
        _fact("Court", esc(e.court or "Not stated")),
        _fact("Item", esc(item)),
        _fact("Page", esc(e.page_number)),
        _fact("Hearing time", time),
    ])
    md(f'<div class="cp-cand-kicker">Possible match {idx} of {total}</div>'
       f'<div class="cp-cand-title">{esc(e.case_number_raw)}</div>'
       f'<div class="cp-cand-parties">{esc(e.party_names) or "Parties not extracted"}</div>'
       f'<div class="cp-facts">{facts}</div>')


def _candidate(d, r, c, idx, total):
    e = c.entry
    # NOTE: container keys must not start with "row_" (styles.css uses that prefix for
    # card + Open-button rows and would squeeze these columns).
    with st.container(key=f"cand_{r.saved.id}_{e.id}"):
        _candidate_header(e, idx, total)
        info, evidence = st.columns([1, 1], gap="medium")
        with info:
            md(f'<div class="cp-cand-label">Matching signals</div>'
               f'<div>{signals_html(c.signals)}</div>'
               f'<div class="cp-mono" style="margin-top:.4rem">{esc(signal_summary(c.signals))}</div>'
               f'<div class="cp-cand-label">Text as extracted from the PDF</div>'
               f'<div class="cp-src">{esc(e.source_text)}</div>')
        with evidence:
            md('<div class="cp-cand-label" style="margin-top:0">Original page</div>')
            img = source_image(d.repo, d.doc, e)
            if img:
                st.image(img, caption=f"Original page {e.page_number}, row highlighted")
            else:
                st.caption("Source page preview unavailable.")
        with st.container(key=f"revact_{r.saved.id}_{e.id}"):
            b1, b2, b3 = st.columns([1, 1, 1.5])
            b1.button("Confirm", key=f"conf_{r.saved.id}_{e.id}", type="primary", use_container_width=True,
                      on_click=_decide, args=(d.repo, r.saved.id, e.id, "confirmed"))
            b2.button("Reject", key=f"rej_{r.saved.id}_{e.id}", use_container_width=True,
                      on_click=_decide, args=(d.repo, r.saved.id, e.id, "rejected"))
            b3.button("Details", key=f"det_{r.saved.id}_{e.id}", use_container_width=True,
                      on_click=open_detail, args=(r.saved.id, e.id, "review"))


def render(d):
    page_header("Needs review", "Resolve uncertain matches",
                "CausePulse never picks between two plausible cases for you. Check the original page, then confirm or reject.")
    if not d.doc:
        empty_state("No cause list loaded", "Upload a PDF first.")
        st.button("Upload Cause List", key="rev_up", type="primary", on_click=go, args=("upload",))
        return
    review = [r for r in d.results if r.status == STATUS_REVIEW]
    if not review:
        empty_state("Nothing needs review", "Every active case is matched or not found in this document.")
    for r in review:
        _saved_card(r)
        total = len(r.candidates)
        for idx, c in enumerate(r.candidates, 1):
            _candidate(d, r, c, idx, total)
        st.caption("Leave a case unresolved to decide later; it stays in this list and is counted as 'Needs review'.")
        st.divider()