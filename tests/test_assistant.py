from core.assistant import answer_question, answer_rules, SUGGESTIONS
from core.service import load_app_data, load_demo
from database.repository import Repository


def _d():
    repo = Repository()
    load_demo(repo)
    return load_app_data(repo)


def ask(d, q, **kw):
    return answer_question(q, d.results, d.entries, d.doc, **kw)


def test_court_question_uses_data_only():
    d = _d()
    a = ask(d, "Find my cases listed in Court 3")
    assert "CS/412/2023" in a.text and "CC 5521/2025" in a.text and "MACP" not in a.text
    assert "11:30 AM" in a.text and "page 1" in a.text


def test_review_and_not_found_answers():
    d = _d()
    assert "CS 220/2024" in ask(d, "Show cases that need manual verification").text
    nf = ask(d, "Which saved cases were not found in this PDF?")
    assert "ARB.P. 140/2025" in nf.text and "does not mean" in nf.text


def test_item_number_never_presented_as_time():
    d = _d()
    a = ask(d, "what time is CC 5521/2025?")
    assert "no time published" in a.text


def test_unknown_case_not_invented():
    d = _d()
    a = ask(d, "Where is CS/999/2020?")
    assert "couldn't find" in a.text


def test_no_document_and_no_llm_fallback():
    d = _d()
    assert "No cause list" in answer_question("hi", [], [], None).text
    a = ask(d, "tell me a joke", api_key=None)
    assert "not sure" in a.text and not a.used_llm


def test_llm_failure_degrades_gracefully(monkeypatch):
    import core.assistant as m
    monkeypatch.setattr(m, "ask_llm", lambda *a, **k: None)
    d = _d()
    a = ask(d, "tell me a joke", api_key="x")
    assert "didn't respond" in a.text and not a.used_llm


def test_suggestions_all_answerable_by_rules():
    d = _d()
    for q in SUGGESTIONS:
        assert answer_rules(q, d.results, d.entries, d.doc) is not None
