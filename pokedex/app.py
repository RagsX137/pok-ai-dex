import os
import re

import requests as req_lib
from flask import Flask, jsonify, request, send_from_directory
from flask import render_template_string
from flask_cors import CORS
from dotenv import load_dotenv

from pokedex.config import settings
from pokedex.coveo import CoveoClient

load_dotenv()

app = Flask(__name__)
# Scope CORS to this app's own origins. Reflecting any Origin let *any* website
# read /api/coveo-token — i.e. the live Coveo API key — from a visitor's browser.
CORS(app, origins=[
    "http://127.0.0.1:5003", "http://localhost:5003",
])

IMAGES_DIR   = settings.images_dir
FRONTEND_DIR = settings.frontend_dir
COVEO_ORG    = settings.coveo_org
COVEO_TOKEN  = settings.coveo_token
COVEO_BASE   = settings.coveo_base

# ── Active model (mutable at runtime via /api/set-model) ─────────────────────
_active_model = os.getenv("OLLAMA_MODEL", "llama3")


# ── Static frontend ───────────────────────────────────────────────────────────
@app.route("/")
def index():
    html = (FRONTEND_DIR / "classic" / "index.html").read_text()
    return render_template_string(html, COVEO_ORGANIZATION_ID=COVEO_ORG)


@app.route("/dashboard")
def dashboard():
    html = (FRONTEND_DIR / "dashboard.html").read_text()
    return render_template_string(html, COVEO_ORGANIZATION_ID=COVEO_ORG)


@app.route("/readme")
def readme():
    return send_from_directory(FRONTEND_DIR, "readme.html")


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


# Only the search endpoints are proxyable. Anchored, no "..", no userinfo "@".
_ALLOWED_PATH = re.compile(r"^/rest/search/v2(/[A-Za-z0-9_-]+)*$")


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

    # The Authorization header is attached unconditionally below, so `path`
    # must not be able to steer the request at another host. A leading "@"
    # turned the intended host into URL userinfo and relocated the request
    # (https://org.org.coveo.com@evil.example/…), leaking the bearer token.
    if not isinstance(path, str) or not _ALLOWED_PATH.match(path):
        return jsonify({"error": "path not allowed"}), 400
    if method not in ("GET", "POST"):
        return jsonify({"error": "method not allowed"}), 405

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
    from pokedex.agent import generate_rga_answer
    data    = request.get_json(force=True)
    query   = data.get("query", "")
    context = data.get("context", [])
    answer  = generate_rga_answer(query, context)
    return jsonify({"answer": answer})


# ── Coveo Generative Answering RGA ────────────────────────────────────────────
@app.route("/api/rga-coveo", methods=["POST"])
def rga_coveo():
    """
    Uses Coveo's Relevance Generative Answering (CRGA / Professor-Oak) via
    `CoveoClient.generated_answer`. This route only shapes that result into
    the JSON response: the "RGA model did not trigger" fallback (needs the
    top search excerpts) and the citation normalisation are HTTP-response
    concerns, so they stay here rather than in the client.

    Body: { "query": str }
    Returns: { "answer": str, "citations": [...] }
    """
    data  = request.get_json(force=True)
    query = data.get("query", "")

    client = CoveoClient()
    result = client.generated_answer(query)

    if result.answer_generated is False and result.error is None:
        # No RGA model fired — return top search excerpts as a fallback answer
        search_results = client.search(query, num=5).get("results", [])
        snippets = "; ".join(
            r.get("excerpt", r.get("title", ""))[:200]
            for r in search_results[:3]
            if r.get("excerpt") or r.get("title")
        )
        return jsonify({
            "answer": f"(RGA model did not trigger. Top result: {snippets})" if snippets
                      else "(RGA model did not trigger for this query.)",
            "citations": [],
        }), 200

    # Normalise citations to a consistent shape
    clean_citations = [
        {
            "title":     c.get("title", ""),
            "uri":       c.get("uri") or c.get("clickUri", ""),
            "permanentid": c.get("permanentid", ""),
        }
        for c in result.citations
    ]

    return jsonify({"answer": result.answer, "citations": clean_citations})


# ── Agentic ask ───────────────────────────────────────────────────────────────
@app.route("/api/ask", methods=["POST"])
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


# ── Model selector ────────────────────────────────────────────────────────────
@app.route("/api/set-model", methods=["POST"])
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


@app.route("/api/models")
def list_models():
    """Return the names of all locally pulled Ollama models."""
    import ollama as ol
    client = ol.Client(host=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
    try:
        resp = client.list()
        # ollama >= 0.4 returns a pydantic ListResponse whose entries expose
        # `.model`; older versions returned {"models": [{"name": ...}]}. The
        # old dict access raised KeyError('name') and was silently swallowed,
        # so the UI fell back to five hardcoded models, none of them installed.
        raw = getattr(resp, "models", None)
        if raw is None and isinstance(resp, dict):
            raw = resp.get("models", [])
        names = [
            getattr(m, "model", None) or (m.get("model") or m.get("name"))
            for m in (raw or [])
        ]
        names = [n for n in names if n]
    except Exception as exc:
        app.logger.warning("ollama list failed: %s", exc)
        names = []
    return jsonify({"models": names})
