import pytest

pytestmark = pytest.mark.e2e


def _weak(page):
    return page.locator("#weak-chips").inner_html()


def test_charizard_has_quadruple_rock_weakness(search):
    page = search("Charizard", expect="Charizard")
    html = _weak(page)
    assert "Rock" in html and "×4" in html


def test_dragonite_has_quadruple_ice_weakness(search):
    page = search("Dragonite", expect="Dragonite")
    html = _weak(page)
    assert "Ice" in html and "×4" in html


def test_gyarados_has_quadruple_electric_weakness(search):
    page = search("Gyarados", expect="Gyarados")
    html = _weak(page)
    assert "Electric" in html and "×4" in html


def test_gengar_is_immune_to_normal_and_fighting(search):
    page = search("Gengar", expect="Gengar")
    html = _weak(page)
    assert "Ghost" in html and "Dark" in html and "Ground" in html
    assert "Fighting" not in html
    assert "Normal" not in html


def test_steelix_is_immune_to_poison(search):
    page = search("Steelix", expect="Steelix")
    assert "Poison" not in _weak(page)


def test_snorlax_only_weakness_is_fighting(search):
    page = search("Snorlax", expect="Snorlax")
    html = _weak(page)
    assert "Fighting" in html
    assert "Water" not in html and "Fire" not in html
