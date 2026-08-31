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
