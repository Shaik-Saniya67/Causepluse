from __future__ import annotations

import streamlit as st

from components.ui import esc, md
from core.assistant import SUGGESTIONS, answer_question, llm_available


def _ask(q: str):
    st.session_state["pending_q"] = q


def _clear():
    st.session_state["chat"] = []


def render(d, api_key):
    ss = st.session_state
    ss.setdefault("chat", [])
    use_llm = d.repo.get_setting("use_llm", "1") == "1" and llm_available(api_key)
    with st.container(key="assistant_panel"):
        src = d.doc.filename if d.doc else "no document yet"
        md(f'''<div class="cp-asst-head"><span class="cp-mono">Assistant</span><br><b>CausePulse Assistant</b>
          <small>Answers only from your uploaded cause list and saved cases · {esc(src)}</small></div>''')
        hist = st.container(height=340, border=False)
        typed = st.chat_input("Ask about your cause list…", key="assistant_input")
        for i, qtxt in enumerate(SUGGESTIONS):
            st.button(qtxt, key=f"sugg_{i}", on_click=_ask, args=(qtxt,))
        q = ss.pop("pending_q", None) or typed
        if q:
            ans = answer_question(q, d.results, d.entries, d.doc, api_key, use_llm)
            text = ans.text
            if ans.refs:
                pages = sorted({p for _, p in ans.refs})
                text += "\n\n*Source page(s): " + ", ".join(f"p.{p}" for p in pages) + "*"
            ss["chat"] += [("you", q), ("assistant", text)]
        with hist:
            if not ss["chat"]:
                st.caption("Ask a question or tap a suggestion below. I won't invent case status, hearing dates or adjournments.")
            for role, text in ss["chat"]:
                md(f'<div class="cp-msg-label">{"You" if role == "you" else "Assistant"}</div>')
                st.markdown(esc(text) if role == "you" else text)
        if ss["chat"]:
            st.button("Clear conversation", key="chat_clear", on_click=_clear)
