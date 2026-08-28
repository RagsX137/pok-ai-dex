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


# ── Coveo Generative Answering RGA ────────────────────────────────────────────
@app.route("/api/rga-coveo", methods=["POST"])
def rga_coveo():
    """
    Uses Coveo's Relevance Generative Answering (CRGA / Professor-Oak).

    Flow (matching Coveo Headless GeneratedAnswerAPIClient):
      1. POST /rest/search/v2 with enableGenerativeQuestionAnswering=True
         → response.extendedResults.generativeQuestionAnsweringId (streamId)
      2. GET /rest/organizations/{org}/machinelearning/streaming/{streamId}
         Accept: */*  → SSE stream of genqa.* events
      3. Collect textDelta tokens + citations until genqa.endOfStreamType

    Body: { "query": str }
    Returns: { "answer": str, "citations": [...] }
    """
    import time as _time

    data  = request.get_json(force=True)
    query = data.get("query", "")

    hdrs_json = {
        "Authorization": f"Bearer {COVEO_TOKEN}",
        "Content-Type":  "application/json",
    }

    # ── Step 1: search to obtain the stream ID ────────────────────────────────
    search_url = f"{COVEO_BASE}/rest/search/v2?organizationId={COVEO_ORG}"
    search_body = {
        "q":                              query,
        "numberOfResults":                5,
        "searchHub":                      os.getenv("COVEO_SEARCH_HUB", "PokedexUI"),
        "pipeline":                       os.getenv("COVEO_RGA_PIPELINE",
                                                    os.getenv("COVEO_PIPELINE", "default")),
        "enableGenerativeQuestionAnswering": True,
    }

    stream_id = None
    search_results = []
    for _attempt in range(6):
        r_search = req_lib.post(search_url, json=search_body, headers=hdrs_json, timeout=15)
        if r_search.status_code != 200:
            return jsonify({
                "answer": f"(Coveo search error: {r_search.status_code})",
                "citations": [],
            }), 200
        search_data   = r_search.json()
        stream_id     = search_data.get("extendedResults", {}).get("generativeQuestionAnsweringId")
        search_results = search_data.get("results", [])
        if stream_id:
            break
        _time.sleep(1)

    if not stream_id:
        # No RGA model fired — return top search excerpts as a fallback answer
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

    # ── Step 2: consume the SSE stream ───────────────────────────────────────
    stream_url = (
        f"{COVEO_BASE}/rest/organizations/{COVEO_ORG}"
        f"/machinelearning/streaming/{stream_id}"
    )
    hdrs_sse = {
        "Authorization": f"Bearer {COVEO_TOKEN}",
        "Accept":        "*/*",
    }

    try:
        r_stream = req_lib.get(stream_url, headers=hdrs_sse, timeout=45, stream=True)
    except req_lib.RequestException as exc:
        return jsonify({"answer": f"(Stream request failed: {exc})", "citations": []}), 200

    if r_stream.status_code != 200:
        return jsonify({
            "answer": f"(CRGA stream error: {r_stream.status_code})",
            "citations": [],
        }), 200

    # ── Step 3: parse SSE events ──────────────────────────────────────────────
    answer_parts: list[str] = []
    citations:    list[dict] = []

    for raw_line in r_stream.iter_lines():
        if not raw_line:
            continue
        line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
        if not line.startswith("data:"):
            continue
        try:
            event = __import__("json").loads(line[len("data:"):].strip())
        except ValueError:
            continue

        payload_type = event.get("payloadType", "")
        payload_raw  = event.get("payload", "")
        finish       = event.get("finishReason")

        if event.get("finishReason") == "ERROR":
            return jsonify({
                "answer": f"(CRGA error: {event.get('errorMessage', 'unknown')})",
                "citations": [],
            }), 200

        if payload_raw:
            try:
                payload = __import__("json").loads(payload_raw)
            except ValueError:
                payload = {}
        else:
            payload = {}

        if payload_type == "genqa.messageType":
            delta = payload.get("textDelta", "")
            if delta and delta.strip():
                answer_parts.append(delta)
        elif payload_type == "genqa.citationsType":
            citations = payload.get("citations", [])
        elif payload_type == "genqa.endOfStreamType" or finish == "COMPLETED":
            break

    answer = "".join(answer_parts).strip() or "(no answer generated)"

    # Normalise citations to a consistent shape
    clean_citations = [
        {
            "title":     c.get("title", ""),
            "uri":       c.get("uri") or c.get("clickUri", ""),
            "permanentid": c.get("permanentid", ""),
        }
        for c in citations
    ]

    return jsonify({"answer": answer, "citations": clean_citations})


# ── Agentic ask ───────────────────────────────────────────────────────────────
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
    # macOS Monterey+ reserves port 5000 for AirPlay; use 5001 instead
    app.run(debug=True, port=5003)
