"""CausePulse: Find · Track · Be Ready. Run with: streamlit run app.py"""
from __future__ import annotations

import os

import streamlit as st

st.set_page_config(page_title="CausePulse", page_icon="⚖️", layout="wide", initial_sidebar_state="expanded")

from components import assistant_panel
from components.nav import MOBILE_LABELS, PAGES, go
from components.ui import esc, inject_css, md
from core.service import load_app_data
from database.repository import Repository
from views import cases, detail, home, review, settings, tracker, upload


@st.cache_resource
def _file_repo() -> Repository:
    return Repository(os.getenv("CAUSEPULSE_DB", "causepulse.db"))


def get_repo() -> Repository:
    """CAUSEPULSE_STORAGE=session keeps each browser session's data private and in memory
    (recommended for public deployments). Default 'file' uses a local SQLite file."""
    if os.getenv("CAUSEPULSE_STORAGE", "file").lower() == "session":
        if "repo" not in st.session_state:
            st.session_state["repo"] = Repository(":memory:")
        return st.session_state["repo"]
    return _file_repo()


def get_api_key():
    key = os.getenv("GROQ_API_KEY")
    if key:
        return key
    try:
        return st.secrets.get("GROQ_API_KEY")
    except Exception:
        return None


def sidebar(d):
    cur = st.session_state["page"]
    active = "tracker" if cur == "detail" else cur
    with st.sidebar:
        md('<div class="cp-brand"><div class="cp-logo">⚖</div><div><b>CausePulse</b><span>Find · Track · Be Ready</span></div></div>')
        md('<div class="cp-side-label">Workspace</div>')
        for pid, label, icon, tip in PAGES:
            if pid == "review" and d.doc and d.counts.get("review"):
                label = f"{label}  ({d.counts['review']})"
            # No help= tooltip here: it wraps the button in a hover span (breaking the sidebar CSS)
            # and the bubble floats over the other nav buttons. Labels already say what each page is.
            st.button(label, key=f"nav_{pid}", icon=icon, on_click=go, args=(pid,),
                      type="primary" if pid == active else "secondary", use_container_width=True)
        foot = ('<span class="cp-demo-pill">DEMO DATA</span><br>' if d.demo else "")
        foot += (f"Active list: {esc(d.doc.filename)}" if d.doc else "No cause list loaded")
        foot += "<br>Matching runs on the uploaded PDF only. It is not a live court feed."
        md(f'<div class="cp-side-foot">{foot}</div>')


def mobile_nav(active):
    with st.container(key="mobile_nav"):
        cols = st.columns(5)
        for col, (pid, _, icon, tip) in zip(cols, PAGES[:5]):
            col.button(MOBILE_LABELS[pid], key=f"m_{pid}", icon=icon, on_click=go, args=(pid,),
                       type="primary" if pid == active else "secondary")


def main():
    st.session_state.setdefault("page", "home")
    inject_css()
    repo = get_repo()
    d = load_app_data(repo)
    api_key = get_api_key()
    sidebar(d)
    page = st.session_state["page"]
    mobile_nav("tracker" if page == "detail" else page)

    for k, fn in (("flash", st.toast), ("flash_err", st.error)):
        msg = st.session_state.pop(k, None)
        if msg:
            fn(msg)

    main_col, side_col = st.columns([2.8, 1.1], gap="medium")
    with main_col:
        with st.container(key=f"page-{page}"):
            if page == "home":
                home.render(d)
            elif page == "upload":
                upload.render(d)
            elif page == "cases":
                cases.render(d)
            elif page == "tracker":
                tracker.render(d)
            elif page == "review":
                review.render(d)
            elif page == "detail":
                detail.render(d)
            elif page == "settings":
                settings.render(d, api_key)
    with side_col:
        assistant_panel.render(d, api_key)


main()