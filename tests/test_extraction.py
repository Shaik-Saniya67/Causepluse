import pytest

try:
    import pymupdf as fitz
except ImportError:
    import fitz

from core.case_parser import TIME_RE, detect_list_date, parse_extraction
from core.pdf_extractor import PDFProcessingError, extract_document
from core.sample_data import build_sample_pdf


def _pdf(lines):
    doc = fitz.open()
    page = doc.new_page()
    y = 60
    for x_cells in lines:
        for x, t in x_cells:
            page.insert_text((x, y), t, fontsize=9)
        y += 22
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture(scope="module")
def sample():
    res = extract_document(build_sample_pdf())
    return res, parse_extraction(res)


def test_sample_extraction_counts(sample):
    res, parsed = sample
    assert res.page_count == 2
    assert len(parsed.entries) == 33
    assert parsed.list_date == "2026-10-14"
    assert "FICTIONAL" in parsed.title
    assert not parsed.warnings


def test_source_page_and_text_kept(sample):
    _, parsed = sample
    for e in parsed.entries:
        assert e["page_number"] in (1, 2)
        assert e["source_text"].strip()
        assert e["bbox"] and len(e["bbox"]) == 4
        assert e["court"].startswith("Court ")


def test_format_variations_normalised(sample):
    _, parsed = sample
    keys = {e["case_number_raw"]: (e["case_type"], e["number"], e["year"]) for e in parsed.entries}
    assert keys["CS No. 412/2023"] == ("CS", "412", 2023)
    assert keys["CRL.M.C. 1180 / 2025"] == ("CRLMC", "1180", 2025)
    assert keys["W.P.(C)-2209-2024"] == ("WPC", "2209", 2024)
    assert keys["CS(COMM) 412/2023"] == ("CSCOMM", "412", 2023)


def test_item_number_is_not_a_time(sample):
    _, parsed = sample
    by = {(e["court"], e["item_number"]): e for e in parsed.entries}
    assert by[("Court 3", 7)]["published_time"] == ""         # no time printed: stays empty
    assert by[("Court 3", 6)]["published_time"] == "11:30 AM"  # printed: captured literally
    assert by[("Court 5", 1)]["published_time"] == "10:30 AM"
    assert sum(bool(e["published_time"]) for e in parsed.entries) == 9


def test_wrapped_party_lines_joined(sample):
    _, parsed = sample
    e = next(x for x in parsed.entries if x["case_number_raw"] == "CS No. 412/2023")
    assert e["party_names"] == "Verma Traders vs. Sharma Logistics Pvt. Ltd."
    assert "Pvt. Ltd." in e["source_text"]


def test_duplicate_case_numbers_kept_separate(sample):
    _, parsed = sample
    dups = [e for e in parsed.entries if e["case_number_raw"] == "CS 220/2024"]
    assert {e["court"] for e in dups} == {"Court 2", "Court 6"}
    assert {e["page_number"] for e in dups} == {1, 2}


def test_time_regex_rejects_non_times():
    assert TIME_RE.search("Rs 12.50 paid") is None
    assert TIME_RE.search("15/10/2026") is None
    assert TIME_RE.search("10.30 AM").group(0) == "10.30 AM"
    assert TIME_RE.search("14:05").group(0) == "14:05"


def test_date_detection():
    assert detect_list_date(["CAUSE LIST FOR 14 OCTOBER 2026"]) == "2026-10-14"
    assert detect_list_date(["Date: 05.11.2026"]) == "2026-11-05"
    assert detect_list_date(["no date here"]) is None
    assert detect_list_date(["31/02/2026"]) is None


def test_row_without_case_number_warns():
    data = _pdf([[(40, "COURT NO. 1")], [(40, "1"), (72, "CS/10/2024"), (212, "A vs. B")],
                 [(40, "2"), (72, "NOT A CASE"), (212, "C vs. D")]])
    parsed = parse_extraction(extract_document(data))
    assert len(parsed.entries) == 1
    assert any("item number" in w for w in parsed.warnings)


def test_connected_matters_become_separate_entries():
    data = _pdf([[(40, "COURT NO. 2")], [(40, "1"), (72, "CS 5/2024 & CS 6/2024"), (260, "A vs. B")]])
    parsed = parse_extraction(extract_document(data))
    assert [e["number"] for e in parsed.entries] == ["5", "6"]
    assert "together with" in parsed.entries[1]["note"]


def test_scanned_pdf_gives_clear_error():
    doc = fitz.open()
    page = doc.new_page()
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 60, 60), False)
    pix.clear_with(200)
    page.insert_image(fitz.Rect(50, 50, 300, 300), stream=pix.tobytes("png"))
    data = doc.tobytes()
    with pytest.raises(PDFProcessingError) as exc:
        extract_document(data)
    assert exc.value.code == "scanned"
    assert "scanned" in str(exc.value).lower()


def test_garbage_and_empty_files_rejected():
    for blob, code in ((b"hello world, not a pdf", "not_pdf"), (b"", "not_pdf"), (b"%PDF-1.4 garbage", "unreadable")):
        with pytest.raises(PDFProcessingError) as exc:
            extract_document(blob)
        assert exc.value.code == code


def test_encrypted_pdf_rejected():
    doc = fitz.open()
    doc.new_page().insert_text((50, 50), "secret cause list text " * 5)
    data = doc.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, user_pw="pw", owner_pw="pw")
    with pytest.raises(PDFProcessingError) as exc:
        extract_document(data)
    assert exc.value.code == "encrypted"


def test_oversize_rejected():
    from core.pdf_extractor import validate_pdf_bytes
    with pytest.raises(PDFProcessingError) as exc:
        validate_pdf_bytes(b"%PDF" + b"0" * 2048, max_bytes=1024)
    assert exc.value.code == "too_large"


def test_text_pdf_with_unsupported_layout_saves_nothing():
    from core.service import process_pdf
    from database.repository import Repository
    repo = Repository()
    data = _pdf([[(40, "Annual report: nothing resembling a cause list lives here at all, sorry.")]])
    with pytest.raises(PDFProcessingError) as exc:
        process_pdf(repo, "report.pdf", data)
    assert exc.value.code == "no_entries"
    assert repo.list_documents() == []
