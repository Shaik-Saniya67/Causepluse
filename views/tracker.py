from __future__ import annotations

import pandas as pd
import streamlit as st

from components.nav import go, open_detail
from components.ui import dataframe, doc_label, empty_state, md, page_header, result_card_html
from core.case_matcher import match_all, sort_results
from core.exports import schedule_csv
from core.models import STATUS_LABELS
from core.normalize import norm_court
from core.service import load_app_data


def render(d):
    page_header("Hearing tracker", "Matched hearings",
                "Item numbers show listing order only. A hearing time appears only if it is printed in the PDF.")
    if len(d.documents) > 1:
        labels = {doc_label(x): x.id for x in d.documents}
        current = doc_label(d.doc)
        pick = st.selectbox("Hearing date / cause list", list(labels), index=list(labels).index(current), key="tracker_doc")
        if labels[pick] != d.doc.id:
            d.repo.set_setting("active_document_id", labels[pick])
            st.rerun()
    if not d.doc:
        empty_state("No cause list loaded", "Upload a PDF to see your hearings.")
        st.button("Upload Cause List", key="trk_up", type="primary", on_click=go, args=("upload",))
        return
    if not d.results:
        empty_state("No active saved cases", "Add case numbers in My Cases.")
        return

    courts = sorted({r.entry.court for r in d.results if r.entry and r.entry.court}, key=lambda c: (norm_court(c).zfill(4), c))
    f1, f2, f3 = st.columns([1.2, 1.2, 1])
    sel_courts = f1.multiselect("Court", courts, key="f_court", placeholder="All courts")
    sel_status = f2.multiselect("Status", [STATUS_LABELS[k] for k in STATUS_LABELS], key="f_status", placeholder="All statuses")
    q = f3.text_input("Search case number or party", key="f_q", placeholder="412 or Verma")
    view = st.radio("View", ["Cards", "Table"], horizontal=True, key="f_view",
                    index=0 if d.repo.get_setting("default_view", "Cards") == "Cards" else 1, label_visibility="collapsed")

    inv = {v: k for k, v in STATUS_LABELS.items()}
    rows = []
    for r in d.results:
        if sel_status and STATUS_LABELS[r.status] not in sel_status:
            continue
        if sel_courts:
            cs = {r.entry.court} if r.entry and r.status == "matched" else {c.entry.court for c in r.candidates}
            if not cs & set(sel_courts):
                continue
        if q.strip():
            hay = " ".join([r.saved.label, r.saved.nickname, r.saved.party_names,
                            r.entry.party_names if r.entry else "", r.entry.case_number_raw if r.entry else ""]).lower()
            if q.strip().lower() not in hay:
                continue
        rows.append(r)

    c1, c2 = st.columns([3, 1])
    c1.caption(f"Showing {len(rows)} of {len(d.results)} tracked cases")
    c2.download_button("Download schedule (CSV)", schedule_csv(rows, d.doc), "causepulse_schedule.csv", "text/csv",
                       key="dl_sched_tracker", disabled=not rows)
    if not rows:
        empty_state("Nothing matches these filters", "Clear a filter to see more.")
        return
    if view == "Table":
        df = pd.DataFrame([{
            "Case": r.saved.label, "Status": STATUS_LABELS[r.status],
            "Parties": (r.entry.party_names if r.entry else r.saved.party_names),
            "Court": r.entry.court if r.entry and r.status == "matched" else "",
            "Item": r.entry.item_number if r.entry and r.status == "matched" else None,
            "Published time": r.entry.published_time if r.entry and r.status == "matched" else "",
            "Source page": r.entry.page_number if r.entry and r.status == "matched" else None,
            "Note": r.reason if r.status != "matched" else ""} for r in rows])
        dataframe(df, hide_index=True)
        opts = {f"{r.saved.label} · {STATUS_LABELS[r.status]}": r.saved.id for r in rows}
        pick = st.selectbox("Open a case", list(opts), key="trk_pick")
        st.button("Open details", key="trk_open", on_click=open_detail, args=(opts[pick], None, "tracker"))
        return
    for r in rows:
        with st.container(key=f"row_trk_{r.saved.id}"):
            a, b = st.columns([8, 1.3])
            a.markdown(result_card_html(r), unsafe_allow_html=True)
            b.button("Open", key=f"open_trk_{r.saved.id}", on_click=open_detail, args=(r.saved.id, None, "tracker"))
