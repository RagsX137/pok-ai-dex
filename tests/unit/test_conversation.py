# tests/unit/test_conversation.py
import pytest


def test_new_session_is_empty():
    from pokedex.conversation import get_or_create, clear
    clear("s1")
    turns = get_or_create("s1")
    assert turns == []


def test_append_and_retrieve():
    from pokedex.conversation import append_turn, get_history, clear
    clear("s2")
    append_turn("s2", "user", "hello")
    append_turn("s2", "assistant", "hi", pokemon_context=["Pikachu"])
    history = get_history("s2")
    assert len(history) == 2
    assert history[0] == {"role": "user", "content": "hello", "pokemon_context": None}
    assert history[1]["pokemon_context"] == ["Pikachu"]


def test_max_turns_evicts_oldest():
    from pokedex.conversation import append_turn, get_history, clear, MAX_TURNS
    clear("s3")
    for i in range(MAX_TURNS + 5):
        append_turn("s3", "user", f"msg{i}")
    history = get_history("s3")
    assert len(history) == MAX_TURNS
    assert history[0]["content"] == f"msg{5}"


def test_get_history_returns_copy():
    from pokedex.conversation import append_turn, get_history, clear
    clear("s4")
    append_turn("s4", "user", "x")
    h = get_history("s4")
    h.clear()
    assert len(get_history("s4")) == 1


def test_clear_removes_session():
    from pokedex.conversation import append_turn, get_history, clear
    append_turn("s5", "user", "y")
    clear("s5")
    assert get_history("s5") == []


def test_unknown_session_returns_empty():
    from pokedex.conversation import get_history
    assert get_history("no-such-session-xyz") == []
