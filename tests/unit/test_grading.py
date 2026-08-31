# tests/unit/test_grading.py
import json
from pathlib import Path
import pytest
from eval_harness.grading import check_type_claims
from eval_harness.typechart import TypeChart


@pytest.fixture(scope="module")
def chart():
    return TypeChart(Path("eval_data/type_cache.json"), offline=True)


@pytest.fixture(scope="module")
def universe():
    return json.loads(Path("eval_data/corpus.json").read_text()) + ["Porygon-Z", "Ho-Oh"]


# The bar this task exists to clear: correct answers must not be flagged.
MUST_NOT_FLAG = [
    "To beat Loudred, a Fighting-type attack works well.",
    "Lead with Onix, a Water-type move will still hurt it.",
    "Against Loudred, a Water-type move is your best bet.",
    "If you face Gengar, a Dark-type play is safest.",
    "For Onix, a Water-type or Grass-type will do.",
    "Switch to Blastoise, a Water-type Pokemon, to win.",   # true appositive, correct typing
    "Sableye, a Dark-type, is tricky.",                     # shorthand omission, not an error
    "Send Gyarados, a Water/Flying-type, and set up.",
    "Surf is a Water-type move.",
    "Your best option is a Fire-type attack.",
    "Gengar is a Ghost/Poison type.",
]

MUST_FLAG = [
    "Loudred, a Ground-type Pokemon, is weak to Water.",    # F-A: the appositive
    "Loudred, a Ground type, is weak to Water.",
    "Your Loudred is Ground-type so it fears Water.",       # the _NAME greediness bug
    "Loudred is a Ground-type Pokemon.",                    # existing pattern 1
    "Loudred, which is a Ground-type Pokemon, is weak.",    # existing pattern 2
    "Loudred (Ground), your lead, faints.",                 # existing pattern 3
    "Loudred's Ground-type moves hit hard.",                # existing pattern 4
    "The Porygon-Z, a Fighting-type, resists it.",          # hyphen-digit name
    "Ho-Oh is a Water-type legendary.",
]


@pytest.mark.parametrize("sentence", MUST_NOT_FLAG)
def test_correct_answers_are_not_flagged(chart, universe, sentence):
    errs = check_type_claims(sentence, chart, universe)
    assert not errs, f"False positive on a correct answer: {sentence!r} -> {errs}"


@pytest.mark.parametrize("sentence", MUST_FLAG)
def test_wrong_typings_are_flagged(chart, universe, sentence):
    assert check_type_claims(sentence, chart, universe), f"Missed: {sentence!r}"


def test_pokemon_field_keeps_universe_casing(chart):
    """grading.py:239 compares e['pokemon'] == wild by exact string."""
    errs = check_type_claims("Loudred, a Ground-type Pokemon, is weak.", chart, ["Loudred"])
    assert errs and errs[0]["pokemon"] == "Loudred"
