"""Parsing and rendering PokemonDB page markdown.

Every test runs against tests/fixtures/bulbasaur_passage.md, a passage captured
verbatim from the live Passage Retrieval API. A hand-written fixture would
drift from what Coveo actually returns, and the shape of that text is the whole
problem this module solves.
"""
from pathlib import Path

import pytest

from pokedex.facts import (
    PokemonFacts,
    build_facts,
    fold,
    kv_table,
    parse_abilities,
    parse_evolution,
    render_answer,
    split_sections,
    strip_markup,
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "bulbasaur_passage.md"


@pytest.fixture(scope="module")
def passage() -> str:
    return FIXTURE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def facts(passage) -> PokemonFacts:
    return build_facts("bulbasaur", [passage])


# ── text helpers ─────────────────────────────────────────────────────────────

def test_fold_strips_the_accent_that_broke_section_matching():
    # "Pokédex" vs "pokedex" — matching without folding finds nothing at all.
    assert fold("Pokédex data") == "pokedex data"


def test_strip_markup_unwraps_links_and_entities():
    out = strip_markup("[Grass](/type/grass) &amp; *Poison*")
    assert out == "Grass & Poison"


# ── sectioning ───────────────────────────────────────────────────────────────

def test_split_sections_keys_on_normalised_headings(passage):
    keys = split_sections(passage, "bulbasaur")
    for expected in ("pokedex data", "training", "breeding",
                     "evolution chart", "pokedex entries"):
        assert expected in keys, f"missing {expected!r}; got {sorted(keys)}"


def test_section_key_drops_the_pokemon_name(passage):
    # "## Moves learned by Bulbasaur" must key the same on every page.
    keys = split_sections(passage, "bulbasaur")
    assert "moves learned" in keys
    assert not any("bulbasaur" in k for k in keys)


def test_kv_table_reads_a_two_column_table(passage):
    dex = kv_table(split_sections(passage, "bulbasaur")["pokedex data"])
    assert dex["species"] == "Seed Pokémon"
    assert dex["height"].startswith("0.7 m")


# ── abilities ────────────────────────────────────────────────────────────────

def test_parses_abilities_and_hidden_ability(facts):
    assert facts.abilities == ["Overgrow"]
    assert facts.hidden_ability == "Chlorophyll"


def test_hidden_ability_is_not_counted_as_a_normal_ability():
    # The real cell has no "2." before the hidden ability, so splitting on the
    # numbering alone would silently include it as a normal ability.
    normal, hidden = parse_abilities(
        "1. [Overgrow](/ability/overgrow)  [Chlorophyll](/ability/chlorophyll) (hidden ability)"
    )
    assert normal == ["Overgrow"]
    assert hidden == "Chlorophyll"


def test_parses_two_normal_abilities():
    normal, hidden = parse_abilities("1. [Static](/ability/static)  2. [Lightning Rod](/a)")
    assert normal == ["Static", "Lightning Rod"]
    assert hidden is None


# ── other sections ───────────────────────────────────────────────────────────

def test_parses_the_evolution_line_with_levels(facts):
    assert facts.evolution == [
        ("Bulbasaur", "Level 16"),
        ("Ivysaur", "Level 32"),
        ("Venusaur", None),
    ]


def test_parses_training_and_breeding(facts):
    assert facts.ev_yield == "1 Sp. Atk"
    assert facts.catch_rate.startswith("45")
    assert facts.base_exp == "64"
    assert facts.growth_rate == "Medium Slow"
    assert facts.egg_groups == ["Grass", "Monster"]
    assert facts.egg_cycles.startswith("20")


def test_parses_flavour_entries_and_level_up_moves(facts):
    assert len(facts.entries) > 10
    assert all(game and text for game, text in facts.entries)
    assert facts.level_up_moves
    assert ("1", "Growl") in facts.level_up_moves
    # The header row must not survive as a move.
    assert not any(fold(lv).startswith("lv") for lv, _ in facts.level_up_moves)


def test_types_come_from_the_dex_table(facts):
    assert facts.types == ["Grass", "Poison"]


# ── rendering ────────────────────────────────────────────────────────────────

def test_renders_abilities(facts):
    out = render_answer("abilities", facts)
    assert "Bulbasaur's ability is Overgrow." in out
    assert "hidden ability is Chlorophyll" in out


def test_renders_evolution(facts):
    out = render_answer("evolution", facts)
    assert out == ("Bulbasaur evolves into Ivysaur at Level 16, "
                   "then into Venusaur at Level 32.")


def test_renders_breeding_and_training(facts):
    assert "Grass and Monster egg groups" in render_answer("breeding", facts)
    assert "1 Sp. Atk" in render_answer("training", facts)


def test_renders_moves_capped_with_a_remainder(facts):
    out = render_answer("moves", facts)
    assert out.count("(Lv.") <= 8
    assert "more by level up" in out


def test_render_returns_none_when_the_section_is_missing():
    # The contract coach_api depends on: no facts means fall through to CRGA,
    # never a half-built sentence.
    empty = PokemonFacts(name="mew")
    for topic in ("abilities", "evolution", "training", "breeding", "entries", "moves"):
        assert render_answer(topic, empty) is None


def test_render_returns_none_for_an_unknown_topic(facts):
    assert render_answer("locations", facts) is None


def test_single_stage_pokemon_says_it_does_not_evolve():
    solo = PokemonFacts(name="tauros", evolution=[("Tauros", None)])
    assert render_answer("evolution", solo) == "Tauros does not evolve."


# ── round trip ───────────────────────────────────────────────────────────────

def test_survives_a_json_round_trip(facts):
    import json
    revived = PokemonFacts.from_dict(json.loads(json.dumps(facts.to_dict())))
    assert revived.abilities == facts.abilities
    assert revived.evolution == facts.evolution
    assert render_answer("evolution", revived) == render_answer("evolution", facts)
