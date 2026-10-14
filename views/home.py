from __future__ import annotations

from datetime import datetime
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from components.nav import go, open_detail
from components.ui import chip, doc_label, esc, md, metric_strip, result_card_html, empty_state, ROOT
from core.exports import fmt_date, schedule_csv
from core.service import load_demo

_SCALES = (ROOT / "justice_3d.html").read_text(encoding="utf-8")


def _scales():
    """Static, trusted HTML shipped with the app. st.iframe on new Streamlit, components.html on older."""
    if hasattr(st, "iframe"):
        st.iframe(_SCALES, height=230)
    else:  # Streamlit < 1.5x
        components.html(_SCALES, height=230)


def _greeting() -> str:
    try:
        from zoneinfo import ZoneInfo
        h = datetime.now(ZoneInfo("Asia/Kolkata")).hour
    except Exception:
        h = datetime.now().hour
    return "Good morning" if h < 12 else "Good afternoon" if h < 17 else "Good evening"


def _load_demo_cb(repo):
    try:
        load_demo(repo)
        st.session_state["flash"] = "Demo data loaded: fictional advocate, cases and a sample cause list."
    except Exception as exc:  # surface any failure instead of a blank screen
        st.session_state["flash_err"] = f"Could not load demo data: {exc}"


def render(d):
    date_txt = fmt_date(d.doc.list_date) if d.doc and d.doc.list_date else "No cause list loaded"
    with st.container(key="hero"):
        left, right = st.columns([1.5, 1], vertical_alignment="center")
        with left:
            demo = '<span class="cp-chip cp-chip--demo">DEMO DATA</span>' if d.demo else ""
            md(f'''<div class="cp-hero"><span class="cp-mono">Hearing date · {esc(date_txt)}</span> {demo}
              <h2>{_greeting()}, {esc(d.advocate)}.</h2>
              <p>Find your cases. Verify the source. Prepare for your court day.</p>
              <p style="font-size:.82rem;opacity:.8">{esc(doc_label(d.doc)) if d.doc else "Upload a cause-list PDF or load the demo to begin."}</p></div>''')
        with right:
            _scales()

    if not d.doc and not d.cases:
        empty_state("Start in under a minute",
                    "Load the fictional demo advocate and sample cause list, or add your own cases and upload a PDF.")
        c1, c2 = st.columns(2)
        c1.button("Load demo data", type="primary", key="home_demo", on_click=_load_demo_cb, args=(d.repo,))
        c2.button("Upload a cause list", key="home_up", on_click=go, args=("upload",))
        return

    metric_strip(d.counts, have_doc=bool(d.doc))
    if d.demo:
        md('<div class="cp-note">Demo data is fictional and clearly labelled. Counts above come from matching the demo advocate\'s cases against the generated sample PDF.</div>')

    a, b, c = st.columns(3)
    a.button("Upload Cause List", key="qa_up", type="primary", on_click=go, args=("upload",))
    b.button(f"View Needs Review ({d.counts['review']})", key="qa_rev", on_click=go, args=("review",))
    c.download_button("Download Schedule", schedule_csv(d.results, d.doc) if d.doc else b"", "causepulse_schedule.csv",
                      "text/csv", key="qa_dl", disabled=not d.doc)

    if d.doc:
        status = ('<span class="cp-chip cp-chip--matched"><i></i>Processed</span>')
        md(f'''<div class="cp-card" style="margin:.9rem 0"><div class="cp-res-top">{status}
          <span class="cp-mono">{esc(d.doc.extraction_method)}</span></div>
          <div class="cp-res-title" style="font-size:1.1rem">{esc(d.doc.filename)}</div>
          <div class="cp-res-foot"><span><b>{d.doc.page_count}</b> pages</span><span><b>{d.doc.entry_count}</b> entries extracted</span>
          <span>List date <b>{esc(fmt_date(d.doc.list_date) or "not found")}</b></span></div></div>''')

    md('<div class="cp-kicker" style="margin:.8rem 0 .4rem">Personalised schedule</div>')
    if not d.doc:
        empty_state("No cause list yet", "Upload a PDF to see your personalised schedule.")
        return
    if not d.results:
        empty_state("No active saved cases", "Add case numbers in My Cases to build a schedule.")
        return
    for r in d.results[:6]:
        with st.container(key=f"row_home_{r.saved.id}"):
            c1, c2 = st.columns([8, 1.3])
            c1.markdown(result_card_html(r), unsafe_allow_html=True)
            c2.button("Open", key=f"open_home_{r.saved.id}", on_click=open_detail, args=(r.saved.id, None, "home"))
    if len(d.results) > 6:
        st.button(f"View all {len(d.results)} in Hearing Tracker", key="home_all", on_click=go, args=("tracker",))
