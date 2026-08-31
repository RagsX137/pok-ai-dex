import pytest

pytestmark = pytest.mark.e2e


def test_nonsense_query_does_not_crash(search):
    page = search("zzzznotapokemon")
    assert page.locator("#results-list").count() == 1
    assert page.locator("#rp-name").inner_text() != ""


def test_clicking_a_result_row_updates_the_right_panel(search):
    page = search("fire", expect=None)
    page.wait_for_selector("#results-list .ritem", timeout=15000)
    rows = page.locator("#results-list .ritem")
    if rows.count() < 2:
        pytest.skip("need at least two results to test row selection")
    before = page.locator("#rp-name").inner_text()
    rows.nth(1).click()
    page.wait_for_function(
        "(prev) => document.querySelector('#rp-name')?.textContent.trim() !== prev",
        arg=before, timeout=15000,
    )
    assert page.locator("#results-list .ritem.sel").count() == 1


def test_similar_grid_excludes_the_current_pokemon(search):
    page = search("Pikachu", expect="Pikachu")
    page.wait_for_selector("#similar-grid .sim-card", timeout=20000)
    names = page.locator("#similar-grid .sim-card").all_inner_texts()
    assert names
    assert not any("Pikachu" in n for n in names)
