from __future__ import annotations

import pandas as pd
import streamlit as st

from components.nav import go, open_detail
from components.ui import dataframe, doc_label, esc, md, page_header
from core.exports import entries_csv, fmt_date
from core.pdf_extractor import MAX_BYTES, PDFProcessingError
from core.sample_data import DEMO_FILENAME, build_sample_pdf
from core.service import load_demo, process_pdf

STAGES = ["Extract document text", "Identify and structure case entries", "Match against My Cases"]


def _stages_html(active: int, msg: str = "") -> str:
    rows = []
    for i, name in enumerate(STAGES, 1):
        cls = "done" if i < active else "active" if i == active else ""
        dot = "✓" if i < active else ""
        extra = f' <span class="cp-mono">{esc(msg)}</span>' if i == active and msg else ""
        rows.append(f'<div class="cp-stage {cls}"><span class="dot">{dot}</span><span>{name}{extra}</span></div>')
    return '<div class="cp-card"><div class="cp-stages">' + "".join(rows) + '</div><div class="cp-scan"></div></div>'


def _run(repo, filename, data, is_demo=False):
    ph = st.empty()
    ph.markdown(_stages_html(1), unsafe_allow_html=True)

    def cb(stage, frac, msg):
        ph.markdown(_stages_html(stage, msg), unsafe_allow_html=True)

    try:
        res = process_pdf(repo, filename, data, is_demo, cb)
        st.session_state["last_upload"] = {"ok": True, "name": filename, "reused": res.reused,
                                           "seconds": res.seconds, "warnings": res.warnings,
                                           "pages": res.page_count, "entries": res.entry_count}
    except PDFProcessingError as exc:
        st.session_state["last_upload"] = {"ok": False, "name": filename, "code": exc.code, "message": str(exc)}
    except Exception as exc:  # never show a raw traceback for a bad file
        st.session_state["last_upload"] = {"ok": False, "name": filename, "code": "unexpected",
                                           "message": f"Unexpected problem while reading this file: {exc}"}
    ph.empty()
    st.rerun()


def render(d):
    page_header("Step 1", "Upload today's cause list",
                f"PDF documents up to {MAX_BYTES // (1024 * 1024)} MB · text-based PDFs only · demo mode supports a prepared sample file")
    up = st.file_uploader("Drop a cause-list PDF here, or choose a file from your device", type=["pdf"],
                          key="uploader")
    c1, c2, c3 = st.columns(3)
    go_btn = c1.button("Process cause list", type="primary", key="process_btn", disabled=up is None)
    demo_btn = c2.button("Use demo sample", key="use_sample")
    c3.download_button("Download sample PDF", build_sample_pdf(), DEMO_FILENAME, "application/pdf", key="dl_sample")

    if go_btn and up is not None:
        _run(d.repo, up.name, up.getvalue())
    if demo_btn:
        load_demo(d.repo)
        st.session_state["last_upload"] = {"ok": True, "name": DEMO_FILENAME, "reused": False, "seconds": 0.0,
                                           "warnings": [], "demo": True}
        st.rerun()

    last = st.session_state.get("last_upload")
    if last:
        if last["ok"]:
            note = "already uploaded earlier; reused the saved extraction" if last.get("reused") else \
                (f"processed in {last['seconds']:.2f}s" if last.get("seconds") else "loaded")
            md(f'<div class="cp-ok"><b>{esc(last["name"])}</b> {note}.</div>')
            for w in last.get("warnings", []):
                st.warning(w)
        else:
            md(f'<div class="cp-err"><b>Couldn\'t use {esc(last["name"])}.</b><br>{esc(last["message"])}</div>')

    if not d.doc:
        return
    md('<div class="cp-kicker" style="margin:1.1rem 0 .4rem">Current document</div>')
    md(f'''<div class="cp-card"><div class="cp-res-title" style="margin-top:0">{esc(d.doc.filename)}</div>
      <div class="cp-res-foot"><span><b>{d.doc.page_count}</b> pages</span><span>Extraction <b>{esc(d.doc.extraction_method)}</b></span>
      <span><b>{d.doc.entry_count}</b> entries</span><span>List date <b>{esc(fmt_date(d.doc.list_date) or "not found")}</b></span>
      <span>Matched <b>{d.counts["matched"]}</b></span><span>Needs review <b>{d.counts["review"]}</b></span>
      <span>Not found <b>{d.counts["not_found"]}</b></span></div></div>''')
    for w in d.doc.warnings:
        st.warning(w)
    b1, b2 = st.columns(2)
    b1.button("Open Hearing Tracker", key="up_to_tracker", on_click=go, args=("tracker",))
    b2.button("Open Needs Review", key="up_to_review", on_click=go, args=("review",))

    with st.expander(f"Extracted entries ({len(d.entries)})"):
        df = pd.DataFrame([{"Page": e.page_number, "Court": e.court, "Item": e.item_number,
                            "Case no. (as printed)": e.case_number_raw, "Normalised": e.key,
                            "Parties": e.party_names, "Stage": e.stage, "Published time": e.published_time}
                           for e in d.entries])
        dataframe(df, hide_index=True)
        st.download_button("Export extracted entries (CSV)", entries_csv(d.entries), "causepulse_entries.csv",
                           "text/csv", key="dl_entries_up")
        opts = {f"p.{e.page_number} · {e.court or '?'} · {e.case_number_raw}": e.id for e in d.entries}
        if opts:
            pick = st.selectbox("Inspect or correct an entry", list(opts), key="inspect_pick")
            st.button("Open entry", key="inspect_open", on_click=open_detail, args=(None, opts[pick], "upload"))
