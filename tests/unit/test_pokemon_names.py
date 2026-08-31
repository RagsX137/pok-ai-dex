# tests/unit/test_pokemon_names.py
from pathlib import Path
import pytest
from pokedex import pokemon_names as pn

pn.init(Path("."))

# One fixture, exercised by every call site. These are the names that broke
# each of the four ad-hoc regexes.
HARD_NAMES = ["Porygon-Z", "Porygon2", "Ho-Oh", "Jangmo-o", "Kommo-o",
              "Mr. Mime", "Mime Jr.", "Farfetch'd", "Type: Null", "Chien-Pao"]

@pytest.mark.parametrize("name", HARD_NAMES)
def test_hard_names_resolve_exactly(name):
    assert pn.resolve(name) == name.lower()

@pytest.mark.parametrize("text,expected", [
    ("should i use charizard", "charizard"),
    ("is snorlax", "snorlax"),
    ("would you pick jangmo-o", "jangmo-o"),
    ("the tank", None),
    ("do i lead with the sweeper", None),
])
def test_resolve_suffix(text, expected):
    assert pn.resolve_suffix(text) == expected

@pytest.mark.parametrize("text,expected", [
    ("blastoise against this", "blastoise"),
    ("blissey the better wall", "blissey"),
    ("kommo-o for this", "kommo-o"),
    ("bad in this matchup", None),
])
def test_resolve_prefix(text, expected):
    assert pn.resolve_prefix(text) == expected

@pytest.mark.parametrize("word", ["speed", "bulk", "tank", "heal", "lead",
                                  "toxic", "mega", "null", "atk", "sand"])
def test_english_words_never_resolve(word):
    """Exact resolution must not coerce. These all had an edit-distance-2
    neighbour in the corpus (speed→seel, tank→sawk, null→numel)."""
    assert pn.resolve(word) is None
    assert pn.resolve_suffix(word) is None

def test_closest_is_still_fuzzy_for_spellcheck():
    """The user-facing spell-check endpoint keeps its tolerance."""
    assert pn.closest("charizrd") == "charizard"
