import pytest

from core.case_matcher import match_all, match_case, party_similarity, summarize
from core.models import Entry, SavedCase
from core.normalize import norm_court, parse_case_ref, within_one_edit
from core.service import load_app_data, load_demo
from database.repository import Repository

_id = iter(range(1, 10_000))


def entry(typ, num, year, court="Court 1", parties="", page=1, item=1):
    return Entry(next(_id), 1, page, item, f"{typ} {num}/{year}", typ, str(num), year, court, parties, "", "", "src")


def saved(case, year=None, court="", parties="", sid=None):
    return SavedCase(sid or next(_id), case, year, court, parties, "", True)


# ---------- normalisation ----------
@pytest.mark.parametrize("text", ["CS/412/2023", "cs 412/2023", "CS No. 412/2023", "CS-412-2023", "C.S. 412 / 2023", "CS  412/23"])
def test_format_variations_equal(text):
    assert parse_case_ref(text).key == "CS/412/2023"


def test_punctuated_types_collapse():
    assert parse_case_ref("CRL.M.C. 1180/2025").key == parse_case_ref("CRL M C 1180 / 2025").key == "CRLMC/1180/2025"
    assert parse_case_ref("W.P.(C)-2209-2024").key == parse_case_ref("WP(C) 2209/2024").key


def test_different_years_and_types_stay_different():
    assert parse_case_ref("CS/412/2023") != parse_case_ref("CS/412/2024")
    assert parse_case_ref("CS/412/2023") != parse_case_ref("CS(COMM)/412/2023")
    assert parse_case_ref("CS/412/2023") != parse_case_ref("CS/413/2023")


def test_leading_zeros_and_year_field():
    assert parse_case_ref("CS 00412", 2023).key == "CS/412/2023"
    with pytest.raises(ValueError):
        parse_case_ref("CS/412/2023", 2024)
    with pytest.raises(ValueError):
        parse_case_ref("CS/412", "abcd")
    assert parse_case_ref("not a case") is None and parse_case_ref("") is None


def test_helpers():
    assert within_one_edit("412", "413") and within_one_edit("412", "4125") and not within_one_edit("412", "412")
    assert not within_one_edit("412", "512x")
    assert norm_court("Court No. 3") == norm_court("COURT 3") == norm_court("3") == "3"
    assert party_similarity("Nair Textiles v. Bose Exports", "Gupta Brothers vs. Patel & Co.") == 0
    assert party_similarity("Nair Textiles v. Bose Exports", "Nair Textiles vs. Bose Exports Pvt. Ltd.") == 1
    assert party_similarity("", "x y") is None


# ---------- matching ----------
def test_exact_unique_match():
    r = match_case(saved("CS/412/2023"), [entry("CS", 412, 2023), entry("CS", 413, 2023)], {})
    assert r.status == "matched" and r.entry.number == "412"


def test_year_and_type_never_conflated():
    es = [entry("CS", 412, 2024), entry("CSCOMM", 412, 2023)]
    r = match_case(saved("CS/412/2023"), es, {})
    assert r.status == "review"           # only the different-type entry is a weak candidate
    assert "different case type" in r.reason
    assert match_case(saved("CS/412/2025"), es, {}).status == "not_found"


def test_exact_beats_weaker_candidates():
    es = [entry("CS", 412, 2023), entry("CSCOMM", 412, 2023)]
    assert match_case(saved("CS/412/2023"), es, {}).status == "matched"


def test_duplicate_numbers_need_review_never_silently_chosen():
    es = [entry("CS", 220, 2024, "Court 2", "Gupta vs. Patel"), entry("CS", 220, 2024, "Court 6", "Nair vs. Bose")]
    r = match_case(saved("CS/220/2024"), es, {})
    assert r.status == "review" and len(r.candidates) == 2 and r.entry is not None
    assert "share the case number" in r.reason


def test_duplicates_resolved_by_saved_court():
    es = [entry("CS", 220, 2024, "Court 2"), entry("CS", 220, 2024, "Court 6")]
    r = match_case(saved("CS/220/2024", court="Court No. 6"), es, {})
    assert r.status == "matched" and r.entry.court == "Court 6"


def test_duplicates_resolved_by_party_names():
    es = [entry("CS", 220, 2024, "Court 2", "Gupta Brothers vs. Patel & Co."),
          entry("CS", 220, 2024, "Court 6", "Nair Textiles vs. Bose Exports")]
    r = match_case(saved("CS/220/2024", parties="Nair Textiles v. Bose Exports"), es, {})
    assert r.status == "matched" and r.entry.court == "Court 6"


def test_same_number_but_different_parties_flagged():
    r = match_case(saved("CS/220/2024", parties="Nair Textiles v. Bose"),
                   [entry("CS", 220, 2024, parties="Gupta Brothers vs. Patel")], {})
    assert r.status == "review" and "party names" in r.reason


def test_saved_court_conflict_flagged():
    r = match_case(saved("CS/220/2024", court="Court 9"), [entry("CS", 220, 2024, "Court 2")], {})
    assert r.status == "review" and "court" in r.reason


def test_missing_type_or_year_always_review():
    es = [entry("CS", 412, 2023)]
    assert match_case(saved("412/2023"), es, {}).status == "review"
    assert match_case(saved("CS 412"), es, {}).status == "review"
    assert match_case(saved("CS 412", year=2023), es, {}).status == "matched"


def test_bounded_fuzzy_number():
    r = match_case(saved("CS/4123/2023"), [entry("CS", 4128, 2023)], {})
    assert r.status == "review" and "one character" in r.reason
    assert match_case(saved("CS/41/2023"), [entry("CS", 42, 2023)], {}).status == "not_found"  # too short to fuzz


def test_not_found_wording():
    r = match_case(saved("ARB.P. 140/2025"), [entry("ARBP", 140, 2024)], {})
    assert r.status == "not_found"
    assert "does not mean" in r.reason and "cancelled" in r.reason


def test_user_decisions():
    es = [entry("CS", 220, 2024, "Court 2"), entry("CS", 220, 2024, "Court 6")]
    sc = saved("CS/220/2024", sid=900)
    r = match_case(sc, es, {(900, es[1].id): "confirmed"})
    assert r.status == "matched" and r.verified and r.entry is es[1]
    r = match_case(sc, es, {(900, es[0].id): "rejected"})   # reject one -> the other is the only candidate
    assert r.status == "matched"
    r = match_case(sc, es, {(900, es[0].id): "rejected", (900, es[1].id): "rejected"})
    assert r.status == "not_found" and r.rejected_count == 2


def test_inactive_cases_skipped():
    sc = saved("CS/1/2024")
    sc.active = False
    assert match_all([sc], [entry("CS", 1, 2024)]) == []


def test_unreadable_saved_case_is_flagged_not_dropped():
    r = match_case(saved("???"), [entry("CS", 1, 2024)], {})
    assert r.status == "review" and "could not be read" in r.reason


# ---------- end to end on demo data ----------
def test_demo_pipeline_expected_counts():
    repo = Repository()
    load_demo(repo)
    d = load_app_data(repo)
    assert d.counts == {"tracked": 8, "matched": 6, "review": 1, "not_found": 1}
    by = {r.saved.label: r for r in d.results}
    assert by["CS 220/2024"].status == "review" and len(by["CS 220/2024"].candidates) == 2
    assert by["ARB.P. 140/2025"].status == "not_found"
    assert by["CRL.M.C. 1180/2025"].entry.year == 2025          # not the 2024 distractor
    assert by["CS/412/2023"].entry.case_number_raw == "CS No. 412/2023"
    assert by["CC 5521/2025"].entry.published_time == ""        # item number is never a time


def test_correction_reruns_matching_without_reupload():
    repo = Repository()
    load_demo(repo)
    d = load_app_data(repo)
    sc = next(r.saved for r in d.results if r.saved.label == "ARB.P. 140/2025")
    target = next(e for e in d.entries if e.case_number_raw == "ARB.P. 140/2024")
    repo.update_entry(target.id, case_number_raw="ARB.P. 140/2025")
    assert next(r for r in load_app_data(repo).results if r.saved.id == sc.id).status == "matched"
    with pytest.raises(ValueError):
        repo.update_entry(target.id, case_number_raw="garbage")


def test_duplicate_upload_is_reused():
    from core.sample_data import build_sample_pdf
    from core.service import process_pdf
    repo = Repository()
    a = process_pdf(repo, "a.pdf", build_sample_pdf())
    b = process_pdf(repo, "again.pdf", build_sample_pdf())
    assert b.reused and a.doc_id == b.doc_id and len(repo.list_documents()) == 1


def test_csv_export_content_and_formula_safety():
    from core.exports import safe_cell, schedule_csv
    repo = Repository()
    load_demo(repo)
    d = load_app_data(repo)
    text = schedule_csv(d.results, d.doc).decode("utf-8-sig")
    assert text.splitlines()[0].startswith("Hearing date (cause list),Case number")
    assert len(text.strip().splitlines()) == 9
    assert "Needs review" in text and "Not found" in text and "14 Oct 2026" in text
    assert safe_cell("=HYPERLINK(1)") == "'=HYPERLINK(1)" and safe_cell("CS 1") == "CS 1"


def test_source_evidence_renders_png():
    from core.sample_data import build_sample_pdf
    from core.source_evidence import render_source
    repo = Repository()
    load_demo(repo)
    d = load_app_data(repo)
    e = d.entries[0]
    png = render_source(repo.get_pdf_bytes(d.doc.id), e.page_number, e.bbox)
    assert png[:8] == b"\x89PNG\r\n\x1a\n" and len(png) > 2000
