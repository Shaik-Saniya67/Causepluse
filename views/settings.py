from __future__ import annotations

import streamlit as st

from components.ui import esc, doc_label, md, page_header
from core.assistant import DEFAULT_MODEL, llm_available
from core.exports import entries_csv, schedule_csv


def render(d, api_key):
    repo = d.repo
    page_header("Preferences", "Settings & reports")
    with st.form("profile"):
        name = st.text_input("Advocate display name", d.advocate)
        view = st.radio("Default Hearing Tracker view", ["Cards", "Table"], horizontal=True,
                        index=0 if repo.get_setting("default_view", "Cards") == "Cards" else 1)
        use_llm = st.checkbox("Use the AI model for open-ended assistant questions", repo.get_setting("use_llm", "1") == "1",
                              help="Built-in questions never need it. Only structured records are sent, never the PDF itself.")
        if st.form_submit_button("Save preferences", type="primary"):
            repo.set_setting("advocate_name", name.strip() or "Advocate")
            repo.set_setting("default_view", view)
            repo.set_setting("use_llm", "1" if use_llm else "0")
            st.session_state["flash"] = "Preferences saved."
            st.rerun()
    status = f"configured (model {DEFAULT_MODEL})" if llm_available(api_key) else "not configured (assistant uses built-in answers only)"
    st.caption(f"AI model: {status}. Keys are read from environment variables or Streamlit secrets, never from code.")

    md('<div class="cp-kicker" style="margin:1.2rem 0 .4rem">Reports</div>')
    c1, c2 = st.columns(2)
    c1.download_button("Personalised schedule (CSV)", schedule_csv(d.results, d.doc) if d.doc else b"",
                       "causepulse_schedule.csv", "text/csv", key="set_dl_sched", disabled=not d.doc)
    c2.download_button("Extracted entries (CSV)", entries_csv(d.entries) if d.doc else b"",
                       "causepulse_entries.csv", "text/csv", key="set_dl_entries", disabled=not d.doc)

    md('<div class="cp-kicker" style="margin:1.2rem 0 .4rem">Uploaded documents</div>')
    if not d.documents:
        st.caption("No documents stored.")
    for doc in d.documents:
        a, b = st.columns([4, 1])
        active = " (active)" if d.doc and doc.id == d.doc.id else ""
        a.markdown(f"**{doc.filename}**{active}  \n{doc_label(doc)} · {doc.page_count} pages · {doc.entry_count} entries")
        b.button("Delete", key=f"del_doc_{doc.id}", on_click=lambda i=doc.id: repo.delete_document(i))

    md('<div class="cp-kicker" style="margin:1.2rem 0 .4rem">Data controls</div>')
    st.button("Clear all uploaded document data", key="clear_docs", on_click=repo.clear_documents)
    st.button("Remove demo data", key="clear_demo", on_click=repo.delete_demo_data)
    with st.expander("Reset everything"):
        ok = st.checkbox("I understand this deletes saved cases, documents and settings", key="reset_ok")
        st.button("Reset all data", key="reset_all", disabled=not ok, on_click=repo.clear_all)
