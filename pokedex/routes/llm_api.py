"""LLM API blueprint: Ollama RGA, agentic ask, model selector."""
import os

from flask import Blueprint, jsonify, request

from pokedex.config import settings
from pokedex.ollama_client import chat, list_local_models

llm_bp = Blueprint("llm_api", __name__)

# Active model — process-local module state; does not survive a restart.
# This is existing behaviour: /api/set-model writes it, every /api/rga request
# reads it. Two concurrent browser sessions share the same value.
_active_model = os.getenv("OLLAMA_MODEL", settings.ollama_model)


@llm_bp.route("/rga", methods=["POST"])
def rga():
    """
    Body: { "query": str, "context": [{"title": str, "excerpt": str}] }
    Returns: { "answer": str }
    """
    from pokedex.agent import generate_rga_answer
    data    = request.get_json(force=True)
    query   = data.get("query", "")
    context = data.get("context", [])
    answer  = generate_rga_answer(query, context)
    return jsonify({"answer": answer})


@llm_bp.route("/ask", methods=["POST"])
def ask():
    """
    Body: { "query": str }
    Returns: { "message": str, "pokemon_list": [...] }
    """
    from pokedex.agent import run_agent
    data   = request.get_json(force=True)
    query  = data.get("query", "")
    result = run_agent(query)
    return jsonify(result)


@llm_bp.route("/set-model", methods=["POST"])
def set_model():
    """Body: { "model": str } — updates the active Ollama model at runtime."""
    global _active_model
    data  = request.get_json(force=True)
    model = data.get("model", _active_model)

    # Validate against the models actually pulled locally. This endpoint writes
    # process-wide state that every request then uses, so it must not accept
    # arbitrary strings from any caller.
    if not isinstance(model, str) or not model.strip():
        return jsonify({"error": "model must be a non-empty string"}), 400
    allowed = set(list_models().get_json().get("models", []))
    if allowed and model not in allowed:
        return jsonify({
            "error": f"unknown model {model!r}",
            "available": sorted(allowed),
        }), 400

    _active_model = model
    os.environ["OLLAMA_MODEL"] = _active_model
    return jsonify({"model": _active_model})


@llm_bp.route("/models")
def list_models():
    """Return the names of all locally pulled Ollama models."""
    return jsonify({"models": list_local_models()})
