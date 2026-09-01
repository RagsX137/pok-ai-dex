# tests/unit/test_matchup.py
import pytest
from pokedex.matchup import detect_matchup_intent, MatchupIntent

# --- helpers ----------------------------------------------------------------

def _hist(team, wild):
    """Fake a prior turn that established the team and wild Pokémon."""
    return [
        {
            "role": "user",
            "content": f"Tell me about {wild}",
            "pokemon_context": [wild],
        },
        {
            "role": "assistant",
            "content": f"{wild} is a Grass type.",
            "pokemon_context": [wild],
        },
    ]


# --- advantage probe --------------------------------------------------------

def test_detects_advantage_with_full_team():
    msg = (
        "My team is Venipede, Solosis, Iron Treads, Sawk, Carkol and Gothita. "
        "Which of them has a type advantage against Toucannon?"
    )
    result = detect_matchup_intent(msg, [])
    assert result is not None
    assert result.wild == "toucannon"
    assert len(result.team) == 6
    assert "venipede" in result.team
    assert result.probe == "advantage"


def test_detects_avoid_probe():
    msg = "Which of Pikachu, Bulbasaur, Charmander, Squirtle, Jigglypuff and Geodude would be a bad idea to send out against Gengar?"
    result = detect_matchup_intent(msg, [])
    assert result is not None
    assert result.wild == "gengar"
    assert result.probe == "avoid"


def test_returns_none_for_unrelated_question():
    result = detect_matchup_intent("What moves does Pikachu learn?", [])
    assert result is None


def test_returns_none_when_team_absent():
    result = detect_matchup_intent("Which of my team beats Toucannon?", [])
    assert result is None


def test_falls_back_to_history_for_wild():
    # The wild Pokémon was established in a prior turn; the current message
    # only references "it".
    history = _hist([], "lapras")  # wild established; team still needed in message
    msg = "My team is Pikachu, Bulbasaur, Charmander, Squirtle, Jigglypuff and Geodude. Which of them can beat it?"
    result = detect_matchup_intent(msg, history)
    assert result is not None
    assert result.wild == "lapras"


@pytest.mark.parametrize("team_phrase,expected", [
    ("Charizard and Blastoise", 2),
    ("Charizard, Blastoise and Venusaur", 3),
    ("Charizard, Blastoise, Venusaur and Pikachu", 4),
    ("Charizard, Blastoise, Venusaur, Pikachu and Snorlax", 5),
    ("Charizard, Blastoise, Venusaur, Pikachu, Snorlax and Geodude", 6),
])
def test_team_of_any_size_between_two_and_six(team_phrase, expected):
    """A real trainer rarely has exactly six. The old fixed-arity regex only
    matched a 6-name list, so every shorter team fell through to the LLM."""
    msg = f"My team is {team_phrase}. Which of them has an advantage against Onix?"
    result = detect_matchup_intent(msg, [])
    assert result is not None, f"{expected}-name team was not detected"
    assert len(result.team) == expected
    assert result.wild == "onix"


def test_which_of_accepts_short_list():
    msg = "Which of Pikachu, Bulbasaur and Geodude should I use against Gengar?"
    result = detect_matchup_intent(msg, [])
    assert result is not None
    assert result.team == ["pikachu", "bulbasaur", "geodude"]
    assert result.wild == "gengar"


def test_list_stops_at_the_end_of_the_sentence():
    """The name list ends at the first entry followed by other prose — a
    Pokémon named in a later sentence is not a team member."""
    msg = "My team is Pikachu and Charizard. Gengar, Onix are scary. Advantage against Onix?"
    result = detect_matchup_intent(msg, [])
    assert result is not None
    assert result.team == ["pikachu", "charizard"]


def test_ranking_probe():
    msg = (
        "Out of Pikachu, Bulbasaur, Charmander, Squirtle, Jigglypuff and Geodude, "
        "which single one is the safest switch-in against Raichu and why?"
    )
    result = detect_matchup_intent(msg, [])
    assert result is not None
    assert result.probe == "ranking"
    assert result.wild == "raichu"
    assert len(result.team) >= 5  # pin the fix — old {4} repetition dropped names 2-5
