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


def test_corpus_loads_without_importing_coveo_api():
    """The corpus must not depend on import order.

    It was populated by a module-scope init() in coveo_api.py, so importing a
    consumer on its own (pokedex.matchup, the eval harness) left it empty —
    and an empty corpus resolves nothing, so callers silently disabled
    themselves rather than failing. Run in a subprocess: this module's own
    import already loaded the corpus for the rest of the suite.
    """
    import subprocess
    import sys

    src = (
        "import sys\n"
        "from pokedex import matchup\n"
        "assert 'pokedex.routes.coveo_api' not in sys.modules\n"
        "r = matchup.detect_matchup_intent("
        "    'My team is Charizard and Blastoise. Advantage against Onix?', [])\n"
        "assert r is not None and r.wild == 'onix', r\n"
    )
    proc = subprocess.run([sys.executable, "-c", src],
                          capture_output=True, text=True, cwd=".")
    assert proc.returncode == 0, proc.stderr


@pytest.mark.parametrize("text,expected", [
    ("blaziken. which of them wins", "blaziken"),
    ("charizard, blastoise", "charizard"),
    ("mime jr. is small", "mime jr."),   # the period is canonical here
])
def test_resolve_prefix_tolerates_sentence_punctuation(text, expected):
    assert pn.resolve_prefix(text) == expected


@pytest.mark.parametrize("text,expected", [
    ("should i use charizard.", "charizard"),
    ("what about farfetch'd,", "farfetch'd"),
    ("i picked mime jr.", "mime jr."),
])
def test_resolve_suffix_tolerates_sentence_punctuation(text, expected):
    assert pn.resolve_suffix(text) == expected
