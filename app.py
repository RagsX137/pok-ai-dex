import os
from pathlib import Path

import requests as req_lib
from flask import Flask, jsonify, request, send_from_directory
from flask import render_template_string
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

IMAGES_DIR   = Path(__file__).parent / "pokemon_images"
FRONTEND_DIR = Path(__file__).parent / "frontend"
COVEO_ORG    = os.getenv("COVEO_ORGANIZATION_ID", "")
COVEO_TOKEN  = os.getenv("COVEO_ACCESS_TOKEN", "")
COVEO_BASE   = f"https://{COVEO_ORG}.org.coveo.com" if COVEO_ORG else "https://platform.cloud.coveo.com"

# ── Active model (mutable at runtime via /api/set-model) ─────────────────────
_active_model = os.getenv("OLLAMA_MODEL", "llama3")


# ── Static frontend ───────────────────────────────────────────────────────────
@app.route("/")
def index():
    html = (FRONTEND_DIR / "index.html").read_text()
    return render_template_string(html, COVEO_ORGANIZATION_ID=COVEO_ORG)


@app.route("/frontend/<path:filename>")
def frontend_static(filename):
    return send_from_directory(FRONTEND_DIR, filename)


@app.route("/images/<filename>")
def serve_image(filename):
    return send_from_directory(IMAGES_DIR, filename)


# ── Coveo token endpoint ──────────────────────────────────────────────────────
@app.route("/api/coveo-token", methods=["GET"])
def coveo_token():
    """
    Returns the Coveo API key so the browser can initialize Atomic.
    The key never appears in HTML/JS source — it is fetched at runtime.
    API keys act as their own search token; no /token exchange needed.
    """
    return jsonify({"token": COVEO_TOKEN, "organizationId": COVEO_ORG})


# ── Coveo proxy ───────────────────────────────────────────────────────────────
@app.route("/api/coveo-proxy", methods=["POST"])
def coveo_proxy():
    """
    Body: { "method": "POST", "path": "/rest/search/v2", "body": {...} }
    Proxies the request to Coveo REST API and returns the raw JSON response.
    Injects COVEO_ACCESS_TOKEN server-side so the browser never sees the token.
    """
    data   = request.get_json(force=True)
    method = data.get("method", "POST").upper()
    path   = data.get("path", "/rest/search/v2")
    body   = data.get("body", {})

    url  = f"{COVEO_BASE}{path}?organizationId={COVEO_ORG}"
    hdrs = {
        "Authorization": f"Bearer {COVEO_TOKEN}",
        "Content-Type":  "application/json",
    }

    resp = req_lib.request(method, url, json=body, headers=hdrs, timeout=15)
    return jsonify(resp.json()), resp.status_code


# ── Ollama RGA ────────────────────────────────────────────────────────────────
@app.route("/api/rga", methods=["POST"])
def rga():
    """
    Body: { "query": str, "context": [{"title": str, "excerpt": str}] }
    Returns: { "answer": str }
    """
    from agent import generate_rga_answer
    data    = request.get_json(force=True)
    query   = data.get("query", "")
    context = data.get("context", [])
    answer  = generate_rga_answer(query, context)
    return jsonify({"answer": answer})


# ── Pokémon detail lookup (name → CSV stats) ─────────────────────────────────
@app.route("/api/pokemon-detail", methods=["GET"])
def pokemon_detail():
    """
    Query param: ?name=Garchomp
    Returns structured stats from the local CSV so the UI stats panel
    can be populated even though the Coveo source is raw HTML.
    """
    from pokedex_tools import get_pokemon_detail
    name   = request.args.get("name", "").strip()
    result = get_pokemon_detail(name)
    if result is None:
        return jsonify({"error": "not found"}), 404
    return jsonify(result)


# ── Original agentic ask ──────────────────────────────────────────────────────
@app.route("/api/ask", methods=["POST"])
def ask():
    """
    Body: { "query": str }
    Returns: { "message": str, "pokemon_list": [...] }
    """
    from agent import run_agent
    data   = request.get_json(force=True)
    query  = data.get("query", "")
    result = run_agent(query)
    return jsonify(result)


# ── Model selector ────────────────────────────────────────────────────────────
@app.route("/api/set-model", methods=["POST"])
def set_model():
    """Body: { "model": str } — updates the active Ollama model at runtime."""
    global _active_model
    data = request.get_json(force=True)
    _active_model = data.get("model", _active_model)
    os.environ["OLLAMA_MODEL"] = _active_model
    return jsonify({"model": _active_model})


@app.route("/api/models")
def list_models():
    """Return the names of all locally pulled Ollama models."""
    import ollama as ol
    client = ol.Client(host=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
    try:
        models = client.list()
        names  = [m["name"] for m in models.get("models", [])]
    except Exception:
        names = []
    return jsonify({"models": names})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
