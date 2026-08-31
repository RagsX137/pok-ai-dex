"""Three-tier fact resolution: file, then LRU, then one live passage call."""
import json
from pathlib import Path

import pytest

from pokedex.coveo import Passage
from pokedex.facts_store import FactsStore

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "bulbasaur_passage.md"


class FakeClient:
    """Counts calls, so the cache can be asserted on rather than assumed."""

    def __init__(self, passages=None):
        self.calls: list[str] = []
        self._passages = passages if passages is not None else []

    def retrieve_passages(self, query, *, max_passages=5, clean=True, timeout=20):
        self.calls.append(query)
        assert clean is False, "the parser needs raw markdown, not cleaned prose"
        return self._passages


def _bulbasaur_passages():
    return [Passage(
        text=FIXTURE.read_text(encoding="utf-8"),
        score=0.2,
        title="Bulbasaur Pokédex: stats, moves, evolution & locations | Pokémon Database",
        uri="https://pokemondb.net/pokedex/bulbasaur",
    )]


@pytest.fixture
def missing_file(tmp_path):
    return tmp_path / "no_such_facts.json"


# ── live tier ────────────────────────────────────────────────────────────────

def test_fetches_and_parses_from_passages(missing_file):
    client = FakeClient(_bulbasaur_passages())
    facts = FactsStore(client=client, path=missing_file).get("bulbasaur")
    assert facts is not None
    assert facts.abilities == ["Overgrow"]
    assert facts.hidden_ability == "Chlorophyll"


def test_repeat_lookups_make_one_live_call(missing_file):
    client = FakeClient(_bulbasaur_passages())
    store = FactsStore(client=client, path=missing_file)
    store.get("bulbasaur")
    store.get("Bulbasaur")
    store.get("BULBASAUR")
    assert len(client.calls) == 1


def test_drops_passages_belonging_to_other_pokemon(missing_file):
    # A query for "Bulbasaur" also returns Ivysaur and Venusaur. Parsing those
    # into Bulbasaur's facts would report the wrong evolution line.
    others = [Passage(text="## Pokédex data\n\n| Abilities | 1. Overgrow |",
                      score=0.1,
                      title="Ivysaur Pokédex: stats | Pokémon Database",
                      uri="u")]
    store = FactsStore(client=FakeClient(others), path=missing_file)
    assert store.get("bulbasaur") is None


def test_accented_titles_still_match(missing_file):
    # Titles read "Pokédex". Matching without folding the accent drops every
    # passage and the store silently returns None for everything.
    client = FakeClient(_bulbasaur_passages())
    assert FactsStore(client=client, path=missing_file).get("bulbasaur") is not None


def test_no_passages_returns_none_not_an_error(missing_file):
    assert FactsStore(client=FakeClient([]), path=missing_file).get("bulbasaur") is None


def test_a_raising_client_returns_none(missing_file):
    class Boom:
        def retrieve_passages(self, *a, **k):
            raise RuntimeError("network gone")

    assert FactsStore(client=Boom(), path=missing_file).get("bulbasaur") is None


def test_blank_names_are_rejected(missing_file):
    store = FactsStore(client=FakeClient(_bulbasaur_passages()), path=missing_file)
    assert store.get("") is None
    assert store.get("   ") is None


# ── file tier ────────────────────────────────────────────────────────────────

def test_file_is_preferred_over_the_live_call(tmp_path):
    path = tmp_path / "facts.json"
    path.write_text(json.dumps({
        "gengar": {"name": "gengar", "abilities": ["Cursed Body"], "hidden_ability": None}
    }), encoding="utf-8")
    client = FakeClient(_bulbasaur_passages())
    facts = FactsStore(client=client, path=path).get("Gengar")
    assert facts.abilities == ["Cursed Body"]
    assert client.calls == [], "the file should have satisfied this lookup"


def test_falls_through_to_live_for_a_pokemon_missing_from_the_file(tmp_path):
    path = tmp_path / "facts.json"
    path.write_text(json.dumps({"gengar": {"name": "gengar"}}), encoding="utf-8")
    client = FakeClient(_bulbasaur_passages())
    facts = FactsStore(client=client, path=path).get("bulbasaur")
    assert facts.abilities == ["Overgrow"]
    assert client.calls == ["bulbasaur"]


def test_a_corrupt_facts_file_does_not_stop_construction(tmp_path):
    path = tmp_path / "facts.json"
    path.write_text("{ this is not json", encoding="utf-8")
    client = FakeClient(_bulbasaur_passages())
    # Must degrade to the live path rather than raising at import/boot time.
    assert FactsStore(client=client, path=path).get("bulbasaur") is not None


# ── eviction ─────────────────────────────────────────────────────────────────

def test_cache_is_bounded(missing_file):
    client = FakeClient(_bulbasaur_passages())
    store = FactsStore(client=client, path=missing_file, capacity=2)
    for name in ("a", "b", "c"):
        store._store(name, object())  # type: ignore[arg-type]
    assert len(store._cache) == 2
    assert "a" not in store._cache
