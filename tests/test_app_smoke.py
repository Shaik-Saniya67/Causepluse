"""Drives the real Streamlit app headlessly: navigation, demo load, review decisions, assistant."""
import os

from streamlit.testing.v1 import AppTest

APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app.py")


def _app():
    return AppTest.from_file(APP, default_timeout=60).run()


def go(at, page):
    at.button(key=f"nav_{page}").click().run()
    assert not at.exception, at.exception
    return at


def test_full_workflow():
    at = _app()
    assert not at.exception
    at.button(key="home_demo").click().run()
    assert not at.exception
    for page in ("upload", "cases", "tracker", "review", "settings", "home"):
        go(at, page)
    go(at, "tracker")
    at.button(key=next(b.key for b in at.button if b.key.startswith("open_trk_"))).click().run()
    assert not at.exception
    at.button(key="detail_back").click().run()
    go(at, "review")
    next(b for b in at.button if b.key.startswith("conf_")).click().run()
    assert not at.exception
    go(at, "home")
    at.chat_input(key="assistant_input").set_value("Which saved cases were not found in this PDF?").run()
    assert not at.exception
    assert any("ARB.P. 140/2025" in m.value for m in at.markdown)


def test_add_edit_remove_case():
    at = _app()
    at.button(key="home_demo").click().run()
    go(at, "cases")
    form = next(t for t in at.text_input if t.label == "Case number")
    form.set_value("CS 999/2022")
    next(b for b in at.button if b.label == "Add case").click().run()
    assert not at.exception
    assert any("CS 999/2022" in e.label for e in at.expander)
