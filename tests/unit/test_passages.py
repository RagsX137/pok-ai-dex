"""Passage Retrieval API client + /api/passages route.

The corpus is scraped markdown from pokemondb.net, so raw passages carry nav
chrome and table markup. Half of these tests are about *rejecting* the junk —
rendering it verbatim in the dashboard's recommendation card looked broken.
"""
import json
from unittest.mock import patch

import pytest


# ── clean_passage_text ───────────────────────────────────────────────────────

def test_unwraps_markdown_links_to_their_label():
    from pokedex.coveo import clean_passage_text
    raw = "Pikachu is an [Electric](/type/electric) type that evolves into [Raichu](/pokedex/raichu) with a Thunder Stone item."
    out = clean_passage_text(raw)
    assert "Electric" in out and "Raichu" in out
    assert "/type/electric" not in out
    assert "](" not in out


def test_unescapes_html_entities():
    from pokedex.coveo import clean_passage_text
    raw = ("It is known for its stats &amp; moves, and it is the Pokemon that "
           "has been the mascot of the series since it was first introduced.")
    assert "&" in clean_passage_text(raw)
    assert "&amp;" not in clean_passage_text(raw)


def test_collapses_newlines_and_runs_of_whitespace():
    from pokedex.coveo import clean_passage_text
    raw = "Pikachu is an Electric type.\n\n   It evolves from Pichu when levelled up with high friendship."
    out = clean_passage_text(raw)
    assert "\n" not in out
    assert "  " not in out


def test_rejects_navigation_chrome():
    from pokedex.coveo import clean_passage_text
    raw = ("# Pikachu Pokédex: stats, moves, evolution &amp; locations | Pokémon Database  "
           "[Skip to main content](#main)  # Pikachu  - Contents - [Info](#dex-basics) "
           "- [Base stats](#dex-stats) - [Evolution chart](#dex-evolution)")
    assert clean_passage_text(raw) == ""


def test_rejects_table_separator_rows():
    from pokedex.coveo import clean_passage_text
    raw = "-" * 180
    assert clean_passage_text(raw) == ""


def test_rejects_passages_that_are_mostly_table_markup():
    from pokedex.coveo import clean_passage_text
    raw = ("| [Fly](/type/flying)   | [Psy](/type/psychic)   | [Bug](/type/bug)   | "
           "[Roc](/type/rock)   | [Gho](/type/ghost)   | [Dra](/type/dragon)   |")
    assert clean_passage_text(raw) == ""


@pytest.mark.parametrize("raw", [
    # Real passages from the live API. Flattening their markdown yields text
    # that is long and letter-rich but is a table, not an answer.
    "| [70](/item/tm70) | [Sleep Talk](/move/sleep-talk) | [Normal](/type/normal) | Status | - | - |"
    " | [72](/item/tm72) | [Electro Ball](/move/electro-ball) | [Electric](/type/electric) | Special | - | 100 |",
    "| EV yield | 3 Sp. Atk | | Catch rate | 45 (5.9% with PokeBall, full HP) |"
    " | Base Friendship | 50 (normal) | | Base Exp. | 285 | | Growth Rate | Medium Slow |",
    "| Egg Groups | Amorphous | | Gender | 50% male, 50% female | | Egg cycles | 20 (4,884-5,140 steps) |"
    " | Base stats | HP | 60 | 230 | 324 | Attack | 65 | 121 | 251 | Defense | 80 | 148 | 284 |",
])
def test_rejects_flattened_tables_that_survive_letter_count(raw):
    from pokedex.coveo import clean_passage_text
    assert clean_passage_text(raw) == ""


def test_keeps_only_the_prose_when_a_table_has_prose_glued_to_it():
    """Live passages are routinely a stat table followed by a flavour entry.
    Scoring the passage as a whole let the flavour text carry the table."""
    from pokedex.coveo import clean_passage_text
    raw = ("| Nor | Fir | Wat | Ele | Gra | Ice | 2 | Fly | Psy | Bug | Roc | 0 | "
           "| Base stats | HP | 60 | 230 | 324 | Attack | 65 | 121 | 251 | "
           "Shield It is said to emerge from darkness to steal the lives of those "
           "who become lost in mountains.")
    out = clean_passage_text(raw)
    assert out == ("Shield It is said to emerge from darkness to steal the lives "
                   "of those who become lost in mountains.")
    assert "230" not in out and "Attack" not in out


@pytest.mark.parametrize("raw", [
    # Pokedex flavour entries — the passages actually worth showing.
    "Shield It is said to emerge from darkness to steal the lives of those who become lost in mountains.",
    "It was created by a scientist after years of horrific gene splicing and DNA engineering experiments.",
    "This Pikachu wears its partner's cap, which is brimming with memories of traveling through the region.",
])
def test_keeps_real_pokedex_prose(raw):
    from pokedex.coveo import clean_passage_text
    assert clean_passage_text(raw) != ""


def test_strips_markdown_emphasis():
    from pokedex.coveo import clean_passage_text
    raw = "*Pikachu* is an Electric type Pokemon that was introduced in Generation 1 and it evolves into Raichu."
    out = clean_passage_text(raw)
    assert out.startswith("Pikachu is an Electric")
    assert "*" not in out


def test_drops_the_repeated_stat_range_boilerplate():
    """Prose by every shape test, but identical on every Pokemon's page."""
    from pokedex.coveo import clean_passage_text
    raw = ("The ranges shown on the right are for a level 100 Pokemon. "
           "Maximum values are based on a beneficial nature, 252 EVs, 31 IVs.")
    assert clean_passage_text(raw) == ""


def test_keeps_genuine_prose():
    from pokedex.coveo import clean_passage_text
    raw = ("Pikachu is an Electric type Pokemon introduced in Generation 1. "
           "It is known as the Mouse Pokemon and evolves into Raichu.")
    out = clean_passage_text(raw)
    assert out.startswith("Pikachu is an Electric type")
    assert len(out) > 40


# ── retrieve_passages ────────────────────────────────────────────────────────

class _Resp:
    def __init__(self, status, payload=None):
        self.status_code = status
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload


def _ok_payload():
    return {
        "responseId": "abc-123",
        "items": [
            {
                "text": "Pikachu is an Electric type Pokemon known as the Mouse Pokemon, and it evolves into Raichu.",
                "relevanceScore": 0.2,
                "document": {"title": "Pikachu Pokédex", "uri": "https://pokemondb.net/pokedex/pikachu"},
            },
            # Junk: must be filtered out before it reaches the UI.
            {
                "text": "-" * 120,
                "relevanceScore": 0.19,
                "document": {"title": "Raichu Pokédex", "uri": "https://pokemondb.net/pokedex/raichu"},
            },
        ],
    }


def test_returns_cleaned_passages_and_drops_junk():
    from pokedex.coveo import CoveoClient
    with patch("pokedex.coveo.requests.post", return_value=_Resp(200, _ok_payload())):
        passages = CoveoClient().retrieve_passages("Pikachu")
    assert len(passages) == 1
    assert passages[0].title == "Pikachu Pokédex"
    assert passages[0].uri.endswith("/pikachu")
    assert passages[0].score == pytest.approx(0.2)
    assert "Electric type" in passages[0].text


def test_sends_the_passage_search_hub_not_the_search_hub():
    """v3 rejects a searchHub that disagrees with the token's binding; v2 does
    not. The two hubs are therefore configured separately."""
    from pokedex.coveo import CoveoClient
    from pokedex.config import settings
    with patch("pokedex.coveo.requests.post", return_value=_Resp(200, _ok_payload())) as m:
        CoveoClient().retrieve_passages("Pikachu", max_passages=3)
    body = m.call_args.kwargs["json"]
    assert body["searchHub"] == settings.coveo_passage_hub
    assert body["maxPassages"] == 3
    assert body["localization"]["locale"]
    assert m.call_args.args[0].endswith("/rest/search/v3/passages/retrieve")


@pytest.mark.parametrize("status,payload", [
    (422, {"message": "This API requires a Passage Retrieval model associated to the pipeline."}),
    (429, {"message": "Request quota exceeded PerOrg[5 calls/PT1S] quota"}),
    (400, {"message": "Invalid parameter 'searchHub'"}),
])
def test_returns_empty_on_api_errors_rather_than_raising(status, payload):
    """The dashboard degrades to its pre-passage behaviour; it never 500s."""
    from pokedex.coveo import CoveoClient
    with patch("pokedex.coveo.requests.post", return_value=_Resp(status, payload)):
        assert CoveoClient().retrieve_passages("Pikachu") == []


def test_returns_empty_on_transport_error():
    from pokedex.coveo import CoveoClient
    import requests as req
    with patch("pokedex.coveo.requests.post", side_effect=req.Timeout("boom")):
        assert CoveoClient().retrieve_passages("Pikachu") == []


def test_returns_empty_for_blank_query_without_calling_coveo():
    from pokedex.coveo import CoveoClient
    with patch("pokedex.coveo.requests.post") as m:
        assert CoveoClient().retrieve_passages("   ") == []
    m.assert_not_called()


# ── /api/passages route ──────────────────────────────────────────────────────

@pytest.fixture
def client():
    from pokedex.app import create_app
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def test_passages_route_returns_passage_list(client):
    from pokedex.coveo import Passage
    stub = [Passage(text="Pikachu is an Electric type.", score=0.2,
                    title="Pikachu Pokédex", uri="https://pokemondb.net/pokedex/pikachu")]
    with patch("pokedex.routes.coveo_api.CoveoClient") as MockClient:
        MockClient.return_value.retrieve_passages.return_value = stub
        resp = client.post("/api/passages", json={"query": "Pikachu"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["passages"][0]["title"] == "Pikachu Pokédex"
    assert body["passages"][0]["score"] == pytest.approx(0.2)
    assert body["passages"][0]["text"].startswith("Pikachu is an Electric")


def test_passages_route_returns_empty_list_when_retrieval_fails(client):
    with patch("pokedex.routes.coveo_api.CoveoClient") as MockClient:
        MockClient.return_value.retrieve_passages.return_value = []
        resp = client.post("/api/passages", json={"query": "Pikachu"})
    assert resp.status_code == 200
    assert resp.get_json()["passages"] == []


def test_passages_route_rejects_missing_query(client):
    with patch("pokedex.routes.coveo_api.CoveoClient") as MockClient:
        resp = client.post("/api/passages", json={})
    assert resp.status_code == 400
    MockClient.return_value.retrieve_passages.assert_not_called()


def test_passages_route_clamps_max_passages(client):
    """Coveo accepts 1-20; anything outside that is a 400 from their side."""
    with patch("pokedex.routes.coveo_api.CoveoClient") as MockClient:
        MockClient.return_value.retrieve_passages.return_value = []
        client.post("/api/passages", json={"query": "Pikachu", "maxPassages": 999})
    assert MockClient.return_value.retrieve_passages.call_args.kwargs["max_passages"] == 20


# ── clean=False (the FactsStore path) ────────────────────────────────────────

def test_clean_false_returns_verbatim_markdown_and_keeps_every_item():
    """FactsStore slices on headings and short table cells.

    clean_passage_text removes both, and drops items that clean to "" — which
    is every chunk that is nothing but a moves table. Neither is acceptable for
    fact extraction, so clean=False must bypass the filter as well as the
    cleaner.
    """
    from pokedex.coveo import CoveoClient
    payload = {"items": [
        {"text": "## Training\n\n| EV yield | 1 Sp. Atk |",
         "relevanceScore": 0.5,
         "document": {"title": "Bulbasaur Pokédex", "uri": "u"}},
    ]}
    with patch("pokedex.coveo.requests.post", return_value=_Resp(200, payload)):
        passages = CoveoClient().retrieve_passages("Bulbasaur", clean=False)

    assert len(passages) == 1, "a table-only chunk must survive clean=False"
    assert passages[0].text.startswith("## Training")
    assert "| EV yield | 1 Sp. Atk |" in passages[0].text


def test_clean_true_still_drops_that_same_table_only_chunk():
    """The default is unchanged: the dashboard panel never renders raw markup."""
    from pokedex.coveo import CoveoClient
    payload = {"items": [
        {"text": "## Training\n\n| EV yield | 1 Sp. Atk |",
         "relevanceScore": 0.5,
         "document": {"title": "Bulbasaur Pokédex", "uri": "u"}},
    ]}
    with patch("pokedex.coveo.requests.post", return_value=_Resp(200, payload)):
        assert CoveoClient().retrieve_passages("Bulbasaur") == []
