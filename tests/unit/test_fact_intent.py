"""Routing questions to a PokemonDB fact topic.

The negative cases carry as much weight as the positive ones. This detector
sits between the type-chart fast path and Coveo, so a false positive steals a
question that one of the other two answers better.
"""
from pathlib import Path

import pytest

from pokedex import pokemon_names
from pokedex.fact_intent import detect_fact_intent, find_pokemon

pokemon_names.init(Path(__file__).resolve().parents[2])


@pytest.mark.parametrize("message,topic", [
    ("What are Gengar's abilities?", "abilities"),
    ("Does Bulbasaur have a hidden ability?", "abilities"),
    ("How does Bulbasaur evolve?", "evolution"),
    ("What does Charmander evolve into?", "evolution"),
    ("What egg group is Pikachu in?", "breeding"),
    ("How long does a Dratini egg take to hatch?", "breeding"),
    ("What is Snorlax's catch rate?", "training"),
    ("What EV yield does Machamp give?", "training"),
    ("What moves does Pikachu learn?", "moves"),
    ("Tell me about Mimikyu", "entries"),
])
def test_classifies_topics(message, topic):
    intent = detect_fact_intent(message)
    assert intent is not None, f"no intent for {message!r}"
    assert intent.topic == topic


@pytest.mark.parametrize("message", [
    # Belongs to the type-chart fast path.
    "My team is Charizard, Blastoise, Venusaur, Pikachu, Gengar and Alakazam. "
    "Which has a type advantage against Onix?",
    # Belongs to Coveo: a type question with no fact keyword.
    "What is Bulbasaur weak to?",
    "What type is Gengar?",
    # No Pokemon named and no pronoun to resolve.
    "What are the best abilities in the game?",
    # Names a Pokemon but asks nothing this module can answer.
    "Is Charizard any good?",
])
def test_declines_what_it_should_not_answer(message):
    assert detect_fact_intent(message) is None


def test_resolves_a_pronoun_from_history():
    history = [
        {"role": "user", "content": "Tell me about Gengar",
         "pokemon_context": ["gengar"]},
        {"role": "assistant", "content": "Gengar, the Shadow Pokémon…",
         "pokemon_context": ["gengar"]},
    ]
    intent = detect_fact_intent("What about its abilities?", history)
    assert intent is not None
    assert intent.pokemon == "gengar"
    assert intent.topic == "abilities"


def test_a_pronoun_with_no_history_is_not_an_intent():
    assert detect_fact_intent("What about its abilities?", []) is None


def test_possessives_and_punctuation_resolve():
    assert find_pokemon("What are Gengar's abilities?") == "gengar"
    assert find_pokemon("what about pikachu, then?") == "pikachu"


def test_hyphenated_and_apostrophe_names_resolve():
    assert find_pokemon("How does Ho-Oh evolve?") == "ho-oh"
    assert find_pokemon("What moves does Farfetch'd learn?") == "farfetch'd"


def test_multiword_names_beat_their_fragments():
    # "Mr. Mime" must win over a bare "mime" fragment.
    assert find_pokemon("What are Mr. Mime's abilities?") == "mr. mime"


def test_never_invents_a_name_from_a_near_miss():
    # pokemon_names.closest maps 'speed'->'seel' at edit distance 2. Routing
    # must use exact resolution only, or this question answers about Seel.
    assert find_pokemon("what about speed and abilities") is None
