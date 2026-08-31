# tests/unit/test_coach_routes.py
import pytest
from unittest.mock import patch, MagicMock


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


def test_coach_challenge_returns_prompt(client):
    r = client.post("/api/coach-challenge", json={})
    assert r.status_code == 200
    d = r.get_json()
    assert "prompt" in d
    assert "session_id" in d
    assert "scenario" in d
    assert len(d["prompt"]) > 10
