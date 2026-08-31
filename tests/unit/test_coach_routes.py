# tests/unit/test_coach_routes.py
import pytest
from unittest.mock import patch, MagicMock

from pokedex.routes.coach_api import _build_context_prompt


@pytest.fixture
def client():
    from pokedex.app import create_app
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def test_coach_route_registered(client):
    rules = {r.rule for r in client.application.url_map.iter_rules()}
    assert "/api/coach" in rules
    assert "/api/coach-challenge" in rules


def test_coach_requires_message(client):
    r = client.post("/api/coach", json={"session_id": "abc"})
    assert r.status_code == 400
    assert b"message" in r.data


def test_coach_requires_session_id(client):
    r = client.post("/api/coach", json={"message": "hello"})
    assert r.status_code == 400
    assert b"session_id" in r.data


def test_coach_returns_answer_shape(client):
    mock_result = MagicMock()
    mock_result.answer = "Charizard is Fire/Flying."
    mock_result.citations = []
    mock_result.stream_completed = True
    mock_result.error = None
    with patch("pokedex.routes.coach_api.CoveoClient") as MockClient:
        MockClient.return_value.generated_answer.return_value = mock_result
        r = client.post("/api/coach", json={"session_id": "test-1", "message": "tell me about Charizard"})
    assert r.status_code == 200
    d = r.get_json()
    assert "answer" in d
    assert "citations" in d
    assert "session_id" in d
    assert "comparison" in d
    assert "grading_flags" in d


def test_coach_detect_comparison_intent(client):
    mock_result = MagicMock()
    mock_result.answer = "Charizard vs Dragonite comparison."
    mock_result.citations = []
    mock_result.stream_completed = True
    mock_result.error = None
    with patch("pokedex.routes.coach_api.CoveoClient") as MockClient:
        MockClient.return_value.generated_answer.return_value = mock_result
        r = client.post("/api/coach", json={
            "session_id": "test-2",
            "message": "compare Charizard and Dragonite"
        })
    assert r.status_code == 200
    d = r.get_json()
    assert d["comparison"] is not None
    assert d["comparison"]["pokemon_a"] == "charizard"
    assert d["comparison"]["pokemon_b"] == "dragonite"


def test_build_context_prompt_injects_pokemon_context():
    """pokemon_context canonical names must appear in the context string so that
    follow-up pronouns like 'them' can be resolved even after a misspelled query."""
    history = [
        {
            "role": "user",
            "content": "diff between pikachu and electrabusz",
            "pokemon_context": ["pikachu", "electabuzz"],
        },
        {
            "role": "assistant",
            "content": "Pikachu and Electabuzz are both Electric-type Pokémon...",
            "pokemon_context": ["pikachu", "electabuzz"],
        },
    ]
    result = _build_context_prompt(history, "Can geodude beat either of them?")
    # Both canonical names must be present so Coveo can resolve 'them'
    assert "pikachu" in result
    assert "electabuzz" in result
    # The misspelling alone is not enough — the canonical hint must be explicit
    assert "[Pokémon: pikachu, electabuzz]" in result


def test_build_context_prompt_no_context_unchanged():
    """Turns without pokemon_context should not be affected."""
    history = [
        {"role": "user", "content": "what type is Charmander?", "pokemon_context": []},
        {"role": "assistant", "content": "Charmander is a Fire type.", "pokemon_context": None},
    ]
    result = _build_context_prompt(history, "And Bulbasaur?")
    assert "[Pokémon:" not in result
    assert "And Bulbasaur?" in result


def test_coach_challenge_returns_prompt(client):
    r = client.post("/api/coach-challenge", json={})
    assert r.status_code == 200
    d = r.get_json()
    assert "prompt" in d
    assert "session_id" in d
    assert "scenario" in d
    assert len(d["prompt"]) > 10


def test_coach_matchup_answered_from_typechart(client):
    """When a 6-name team + wild are present, the answer must name at least one
    teammate (or say 'none'). It must NOT be an encyclopedia entry."""
    # No mock needed — _grade_chart is module-level and real.
    # We mock CoveoClient to confirm it is NOT called on this path.
    with patch("pokedex.routes.coach_api.CoveoClient") as MockCoveo:
        r = client.post("/api/coach", json={
            "session_id": "typechart-test",
            "message": (
                "My team is Venipede, Solosis, Iron Treads, Sawk, Carkol and Gothita. "
                "Which of them has a type advantage against Toucannon?"
            ),
        })
    assert r.status_code == 200
    d = r.get_json()
    answer = d["answer"].lower()
    # The answer must mention at least one teammate by name, OR say "none".
    team_lower = ["venipede", "solosis", "iron treads", "sawk", "carkol", "gothita"]
    named = any(t in answer for t in team_lower) or "none" in answer
    assert named, f"Answer did not name any teammate: {d['answer']}"
    # Coveo must not have been called.
    MockCoveo.assert_not_called()


def test_coach_no_advantage_says_none(client):
    """When no teammate has an advantage, the answer must say 'none' (not fabricate one)."""
    # Build a team of 6 pure-Normal types all present in the type cache vs. pure Steel.
    # Normal hits Steel for 0.5x — none of them have an advantage.
    # (Uses cache-resident names to avoid LookupError before Task 10 backfills the cache.)
    with patch("pokedex.routes.coach_api.CoveoClient") as MockCoveo:
        r = client.post("/api/coach", json={
            "session_id": "none-test",
            "message": (
                "My team is Aipom, Blissey, Bouffalant, Buneary, Chansey and Rattata. "
                "Which of them has a type advantage against Registeel?"
            ),
        })
    assert r.status_code == 200
    d = r.get_json()
    assert "none" in d["answer"].lower() or "no teammate" in d["answer"].lower()
    MockCoveo.assert_not_called()


def test_extract_pokemon_mentions_no_english_words():
    from pokedex.routes.coach_api import _extract_pokemon_mentions
    # English words that happen to be capitalised must not appear.
    result = _extract_pokemon_mentions("I Am Shouting Every Word Here")
    assert result == [], f"Expected [], got {result}"

def test_extract_pokemon_mentions_finds_real_names():
    from pokedex.routes.coach_api import _extract_pokemon_mentions
    result = _extract_pokemon_mentions("Tell me about Lapras and Venusaur")
    assert "lapras" in result
    assert "venusaur" in result
    # "Tell" and "About" must not be in the result.
    assert "tell" not in result
    assert "about" not in result


def test_abstention_fallback_fires_for_sentinel(client):
    """When Coveo returns the literal sentinel, the excerpt fallback must run — not show the sentinel raw."""
    mock_result = MagicMock()
    mock_result.answer = "(no answer generated)"
    mock_result.citations = []
    mock_result.stream_completed = True
    mock_result.error = None

    mock_search = {"results": [
        {"title": "Pikachu Pokédex", "excerpt": "Pikachu is an Electric-type Pokémon."}
    ]}

    with patch("pokedex.routes.coach_api.CoveoClient") as MockClient:
        MockClient.return_value.generated_answer.return_value = mock_result
        MockClient.return_value.search.return_value = mock_search
        r = client.post("/api/coach", json={
            "session_id": "abstain-test",
            "message": "tell me about Pikachu"
        })

    assert r.status_code == 200
    d = r.get_json()
    # The raw sentinel must not reach the client.
    assert d["answer"] != "(no answer generated)"
    # The search fallback text must be present.
    assert "RGA model did not trigger" in d["answer"] or "Pikachu" in d["answer"]


@pytest.mark.parametrize("body,expected_status", [
    (b"[1,2,3]",                                  400),
    (b'"just a string"',                           400),
    (b'{"session_id":1,"message":"hi"}',           400),
    (b'{"session_id":"x","message":999}',          400),
    (b'{"session_id":"x","message":["a","b"]}',    400),
    (b'{"session_id":"x","message":{"a":1}}',      400),
])
def test_coach_rejects_malformed_body(client, body, expected_status):
    r = client.post("/api/coach", data=body,
                    content_type="application/json")
    assert r.status_code == expected_status, f"body={body!r} got {r.status_code}"


def test_challenge_does_not_pre_store_turn(client):
    """coach-challenge must not store a user turn; that is /api/coach's job."""
    from pokedex.conversation import get_history
    r = client.post("/api/coach-challenge", json={})
    assert r.status_code == 200
    d = r.get_json()
    # The session returned by challenge must be empty — no pre-stored turn.
    history = get_history(d["session_id"])
    assert history == [], f"Expected empty history, got {history}"

import pytest
from pokedex.routes.coach_api import _detect_comparison

COMPARISONS = [
    # (message, expected)
    ("Compare Charizard to Dragonite",                    ("charizard", "dragonite")),
    ("between Charizard and Dragonite, who wins",         ("charizard", "dragonite")),
    ("Charizard vs Dragonite",                            ("charizard", "dragonite")),
    ("Charizard vs Dragonite, who wins?",                 ("charizard", "dragonite")),
    ("Which is better: Umbreon or Espeon?",               ("umbreon", "espeon")),
    # hyphen + digit names — the class the old character class could not see
    ("Porygon-Z or Porygon2, which is better?",           ("porygon-z", "porygon2")),
    ("Ho-Oh or Lugia?",                                   ("ho-oh", "lugia")),
    ("Mr. Mime or Mime Jr.?",                             ("mr. mime", "mime jr.")),
    ("compare Farfetch'd with Sirfetch'd",                ("farfetch'd", "sirfetch'd")),
    # lead-in words before the first name — regressed by search()+continue
    ("Should I use Charizard or Blastoise against this?", ("charizard", "blastoise")),
    ("Do I send Gengar or Alakazam?",                     ("gengar", "alakazam")),
    ("Is Snorlax or Blissey the better wall?",            ("snorlax", "blissey")),
    ("Would you pick Jangmo-o or Kommo-o for this?",      ("jangmo-o", "kommo-o")),
]

@pytest.mark.parametrize("message,expected", COMPARISONS)
def test_detect_comparison_positives(message, expected):
    assert _detect_comparison(message) == expected

BENIGN = [
    "Do I lead with the tank or the sweeper?",
    "Should I heal it or switch out?",
    "Is Charizard good or bad in this matchup?",
    "Rate my team out of ten or give me a grade",
    "Can you explain STAB versus base power for me?",
    "Should I switch or stay in?",
    "Do I use an item or attack?",
    # single words with an edit-distance-2 neighbour in the corpus: these are
    # exactly what fuzzy "validation" would have coerced into a comparison
    "Speed or bulk?",
    "Toxic or seed?",
    "Tank or wall?",
    "Lead or switch?",
]

@pytest.mark.parametrize("message", BENIGN)
def test_detect_comparison_no_false_positives(message):
    assert _detect_comparison(message) is None
