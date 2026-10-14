from __future__ import annotations

import streamlit as st

PAGES = [
    ("home", "Home", ":material/home:", "Today's overview and recent activity"),
    ("upload", "Upload Cause List", ":material/upload_file:", "Upload, extract and match PDF entries"),
    ("cases", "My Cases", ":material/folder_managed:", "Save, edit and manage tracked case numbers"),
    ("tracker", "Hearing Tracker", ":material/calendar_month:", "View matched hearings and filter by court"),
    ("review", "Needs Review", ":material/rule:", "Resolve ambiguous or missing matches"),
    ("settings", "Settings", ":material/settings:", "Profile, display and saved preferences"),
]
MOBILE_LABELS = {"home": "Home", "upload": "Upload", "cases": "Cases", "tracker": "Hearings", "review": "Review"}


def go(page: str, **state):
    """on_click callback: sets state before the rerun so navigation takes a single pass."""
    st.session_state["page"] = page
    for k, v in state.items():
        st.session_state[k] = v


def open_detail(saved_id=None, entry_id=None, back="tracker"):
    go("detail", selected_saved_id=saved_id, selected_entry_id=entry_id, back=back)
