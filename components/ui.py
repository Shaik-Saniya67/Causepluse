"""Small HTML/Streamlit helpers shared by all views."""
from __future__ import annotations

import html
import re
from pathlib import Path

import streamlit as st

from core.exports import fmt_date
from core.models import STATUS_LABELS, STATUS_MATCHED, STATUS_NOT_FOUND, STATUS_REVIEW

ROOT = Path(__file__).resolve().parent
_CLS = {STATUS_MATCHED: "matched", STATUS_REVIEW: "review", STATUS_NOT_FOUND: "notfound"}


def esc(x) -> str:
    return html.escape("" if x is None else str(x), quote=True)


def H(s: str) -> str:
    """Collapse newlines/indent so Streamlit's markdown doesn't treat HTML as a code block."""
    return re.sub(r"\n\s*", "", s).strip()


def md(s: str):
    st.markdown(H(s), unsafe_allow_html=True)


def inject_css():
    css = (ROOT / "styles.css").read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def chip(status: str) -> str:
    return f'<span class="cp-chip cp-chip--{_CLS[status]}"><i></i>{STATUS_LABELS[status]}</span>'


def page_header(kicker: str, title: str, sub: str = ""):
    md(f'<div class="cp-kicker">{esc(kicker)}</div><div class="cp-title">{esc(title)}</div>'
       + (f'<div class="cp-sub">{esc(sub)}</div>' if sub else ""))


def metric_strip(counts: dict, have_doc: bool = True):
    def n(v):
        return f"{v:02d}" if have_doc else "—"
    cells = [
        ("Total tracked", f"{counts['tracked']:02d}", ""),
        ("Matched", n(counts["matched"]), "ok"),
        ("Needs review", n(counts["review"]), "warn"),
        ("Not found", n(counts["not_found"]), "bad"),
    ]
    md('<div class="cp-metrics">' + "".join(
        f'<div class="cp-metric cp-metric--{t}"><div class="cp-metric-num">{v}</div>'
        f'<div class="cp-metric-lab">{esc(l)}</div></div>' for l, v, t in cells) + "</div>")


def empty_state(title: str, text: str):
    md(f'<div class="cp-card cp-empty"><h3>{esc(title)}</h3><div>{esc(text)}</div></div>')


def result_card_html(r) -> str:
    s, e = r.saved, r.entry
    top_right, foot = "", ""
    if r.status == STATUS_MATCHED and e:
        bits = [e.court or "Court not stated"]
        if e.item_number is not None:
            bits.append(f"Item {e.item_number}")
        bits.append(f"p.{e.page_number}")
        top_right = " · ".join(bits)
        time = f"<span>Hearing time <b>{esc(e.published_time)}</b></span>" if e.published_time else \
            "<span>Time <b>not published</b></span>"
        foot = time + (f"<span>Stage <b>{esc(e.stage)}</b></span>" if e.stage else "")
        sub = e.party_names or s.party_names
    elif r.status == STATUS_REVIEW:
        top_right = " · ".join(f"{c.entry.court or '?'} p.{c.entry.page_number}" for c in r.candidates[:3]) or "Check saved details"
        foot = f"<span>{esc(r.reason)}</span>"
        sub = s.party_names or (r.entry.party_names if r.entry else "")
    else:
        top_right = "Not in uploaded document"
        foot = "<span>Not found in this PDF only. Not a statement about the court's actual schedule.</span>"
        sub = s.party_names
    nick = f" · {esc(s.nickname)}" if s.nickname else ""
    verified = ' <span class="cp-chip">verified by you</span>' if r.verified else ""
    return H(f'''<div class="cp-card cp-res cp-res--{_CLS[r.status]}">
      <div class="cp-res-top"><span>{chip(r.status)}{verified}</span><span class="cp-mono">{esc(top_right)}</span></div>
      <div class="cp-res-title">{esc(s.label)}<span style="font-size:.9rem;color:var(--muted)">{nick}</span></div>
      <div class="cp-res-sub">{esc(sub) if sub else "&nbsp;"}</div>
      <div class="cp-res-foot">{foot}</div></div>''')


def signals_html(signals: dict) -> str:
    cls = {"match": "m", "mismatch": "x", "unknown": ""}
    sym = {"match": "✓", "mismatch": "✗", "unknown": "?"}
    return '<div class="cp-sig">' + "".join(
        f'<span class="{cls[v]}">{sym[v]} {k}</span>' for k, v in signals.items()) + "</div>"


def field_rows(rows: list) -> str:
    return "".join(f'<div class="cp-field"><span>{esc(k)}</span><span>{v}</span></div>' for k, v in rows)


def doc_label(doc) -> str:
    d = fmt_date(doc.list_date) if doc.list_date else "date not found"
    return f"{d} · {doc.filename}"


@st.cache_data(show_spinner=False, max_entries=96)
def _render(_repo, doc_id, content_hash, page, bbox, crop):
    from core.source_evidence import render_source
    data = _repo.get_pdf_bytes(doc_id)
    return render_source(data, page, bbox, crop) if data else None


def source_image(repo, doc, entry, crop=True):
    try:
        return _render(repo, doc.id, doc.content_hash, entry.page_number, entry.bbox, crop)
    except Exception:
        return None


def dataframe(df, **kw):
    try:
        return st.dataframe(df, width="stretch", **kw)
    except Exception:
        return st.dataframe(df, use_container_width=True, **kw)
