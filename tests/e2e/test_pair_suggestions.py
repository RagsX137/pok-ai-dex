"""The "Pair with:" row on the Professor Oak card.

Derived from the type chart, not from Passage Retrieval: the corpus is
per-Pokemon Pokedex pages and holds no team-composition content, so there is
nothing to retrieve for this. Being computed, it is also deterministic enough
to assert on exactly.
"""
import pytest

pytestmark = pytest.mark.e2e


def _pair_chips(page):
    return [t.strip() for t in page.locator("#ai-pair-row .echip").all_inner_texts()]


def test_gengar_pairs_with_dark(search):
    """Gengar is weak to Ground, Psychic, Ghost and Dark. Dark answers three of
    the four, and nothing else answers two, so it should stand alone."""
    page = search("Gengar", expect="Gengar")
    assert _pair_chips(page) == ["Dark"]


def test_dragonite_pairs_with_steel_first(search):
    """Steel resists all four of Dragonite's weaknesses (Ice, Rock, Dragon,
    Fairy), so it must rank first."""
    page = search("Dragonite", expect="Dragonite")
    chips = _pair_chips(page)
    assert chips and chips[0] == "Steel"


def test_single_weakness_pokemon_still_get_suggestions(search):
    """Pikachu's only weakness is Ground. Requiring two covered weaknesses
    would hide the row for every mono-weakness Pokemon; covering the one
    weakness is the whole answer here."""
    page = search("Pikachu", expect="Pikachu")
    chips = _pair_chips(page)
    assert chips, "expected suggestions for a single-weakness Pokemon"
    # Flying is immune to Ground; Grass and Bug resist it.
    assert set(chips) <= {"Grass", "Flying", "Bug"}


def test_bulbasaur_pairs_with_steel_first(search):
    """Bulbasaur is weak to Fire, Ice, Flying and Psychic. Steel resists three
    of the four and must lead; Fire and Water each answer two."""
    page = search("Bulbasaur", expect="Bulbasaur")
    chips = _pair_chips(page)
    assert chips and chips[0] == "Steel"
    assert set(chips) == {"Steel", "Fire", "Water"}
