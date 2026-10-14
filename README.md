# CausePulse — Find · Track · Be Ready

A mobile-first legal-tech app for solo advocates. Upload a court **cause-list PDF**, match it against your saved case
numbers, get a personalised hearing schedule, and verify every result against the **original PDF page**.
Built for WarriorHacks 2.0 (24-hour build). Python + Streamlit + PyMuPDF + SQLite.

> All bundled sample data is **fictional demo data** (fictional court, parties and judges), clearly labelled in the UI and PDF.
> CausePulse works only from the PDF you upload. It is not a live court feed and gives no legal advice.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Open http://localhost:8501 and click **Load demo data** on Home (8 fictional cases + a generated sample cause list
-> **6 matched · 1 needs review · 1 not found**). You can also download the sample PDF from the Upload page.

## Features

| Screen | What it does |
|---|---|
| Home | Greeting, hearing date, 4 metric cards, latest document status, quick actions, personalised schedule, 3D scales hero |
| Upload Cause List | PDF upload (max 20 MB), live 3-stage progress, page count / extraction method / entries, clear errors, entry inspector |
| My Cases | Add / edit / remove / deactivate cases, bulk import, duplicate detection |
| Hearing Tracker | Filters (court, status, search, cause-list date), card/table views, CSV export |
| Needs Review | Candidate entries with reasons, signal checks, highlighted source page, Confirm / Reject |
| Case Detail | Extracted fields, match reasoning, source evidence (highlighted row + full page), **correct an extraction and re-run matching without re-uploading** |
| Assistant | Answers from the uploaded data only, with source pages; optional LLM for open-ended questions |
| Settings | Name, default view, reports (CSV), delete documents, clear demo data, reset |

## Reliability rules (enforced in code and tests)

- Deterministic Python does normalisation, matching and sorting. The LLM never parses or invents data.
- Types, numbers and **years are never merged**: `CS/412/2023`, `CS/412/2024` and `CS(COMM)/412/2023` are different cases.
- Only an **exact** type + number + year match is auto-"Matched". Duplicate numbers, missing type/year, different case type,
  one-character near-misses, court or party conflicts -> **Needs review**. Nothing is silently chosen.
- Hearing time is shown **only if printed** in the row. Item numbers are listing order, never times.
- "Not found" always means *not found in the uploaded document*, never cancelled or removed.
- Every entry keeps its page number, source text and row position (used to highlight the row).
- Scanned/image, encrypted, corrupt, non-PDF, oversized and unrecognised-layout files produce a clear message; nothing is saved.
- CSV cells are sanitised against spreadsheet formula injection. API keys are read only from env vars / secrets.
- Confidence is shown as **signal agreement** (number/year/type/court/parties), not an invented percentage.

## Matching tiers

1. Exact type + number + year -> Matched (narrowed by your saved court / party names if the number appears more than once).
2. Number matches but your saved case has no type or year -> Needs review.
3. Same number + year, different case type -> Needs review.
4. Same type/year, number differs by one character (typo/extraction error, 3+ digits) -> Needs review.
5. Otherwise -> Not found (in this PDF).

## Project layout

```
app.py                  shell: sidebar, mobile nav, page router, assistant column
views/                  home, upload, cases, tracker, review, detail, settings
components/             styles.css, justice_3d.html (Three.js), ui.py, nav.py, assistant_panel.py
core/                   normalize, pdf_extractor, case_parser, case_matcher, assistant, exports,
                        source_evidence, sample_data, service, models
database/repository.py  SQLite (saved cases, documents, entries, review decisions, settings)
tests/                  extraction, matching, assistant, headless app workflow (53 tests)
```
(`views/` is used instead of `pages/` so Streamlit doesn't auto-generate its own default navigation.)

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

## Optional AI assistant

Built-in questions work with no key. For open-ended questions set `GROQ_API_KEY` (env var or Streamlit secret).
Only structured records (not the PDF) are sent, with instructions to answer strictly from them.
Never commit keys: `.env` and `.streamlit/secrets.toml` are git-ignored.

## Deployment (Streamlit Community Cloud)

1. Push this folder to a GitHub repo (no secrets in it).
2. share.streamlit.io -> *New app* -> pick the repo, branch, and `app.py`.
3. *Advanced settings -> Secrets*:
   ```toml
   CAUSEPULSE_STORAGE = "session"
   GROQ_API_KEY = ""        # optional
   ```
   Secrets are exposed as environment variables, so `session` mode is picked up automatically.
4. **Why `session`:** in the default `file` mode every visitor shares one SQLite file, and the cloud filesystem is
   ephemeral. `session` keeps each visitor's cases and documents private and in memory (the demo reloads in one click).
   For persistent personal use, run locally or on a VM/Docker host with `CAUSEPULSE_STORAGE=file` and a mounted volume.
5. Docker/VM: `pip install -r requirements.txt && streamlit run app.py --server.port 8501 --server.address 0.0.0.0`.

Verify after deploying: Load demo data -> counts 6/1/1 -> Needs Review -> Confirm -> download the CSV.

## Known limits / next steps

- No OCR: scanned PDFs are rejected with a clear message (Tesseract could be added as a fallback).
- The parser targets row-per-case tables (`item · case no. · parties · stage · time`) under `COURT NO. n` headings and
  upper-case case types (`CS`, `CRL.M.C.`, `W.P.(C)`). Other layouts need a parser tweak.
- The 3D scales are built procedurally in Three.js (loaded from cdnjs) with an animated SVG fallback if WebGL or the
  CDN is unavailable. To use a GLB model instead, load it with `GLTFLoader` in `components/justice_3d.html`.
- Post-hackathon: scheduled court scraping, WhatsApp/SMS alerts, accounts, calendar sync.
