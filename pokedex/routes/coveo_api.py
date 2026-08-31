"""Coveo API blueprint: token endpoint, SSRF-guarded proxy, and CRGA."""
import re

import requests as req_lib
from flask import Blueprint, jsonify, request

from pokedex.config import settings
from pokedex.coveo import CoveoClient

coveo_bp = Blueprint("coveo_api", __name__)

_COVEO_ORG   = settings.coveo_org
_COVEO_TOKEN = settings.coveo_token
_COVEO_BASE  = settings.coveo_base

# Only the search endpoints are proxyable. Anchored, no "..", no userinfo "@".
_ALLOWED_PATH = re.compile(r"^/rest/search/v2(/[A-Za-z0-9_-]+)*$")


@coveo_bp.route("/coveo-token", methods=["GET"])
def coveo_token():
    """
    Returns the Coveo API key so the browser can initialize Atomic.
    The key never appears in HTML/JS source — it is fetched at runtime.
    API keys act as their own search token; no /token exchange needed.
    """
    return jsonify({"token": _COVEO_TOKEN, "organizationId": _COVEO_ORG})


@coveo_bp.route("/coveo-proxy", methods=["POST"])
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

    url  = f"{_COVEO_BASE}{path}?organizationId={_COVEO_ORG}"
    hdrs = {
        "Authorization": f"Bearer {_COVEO_TOKEN}",
        "Content-Type":  "application/json",
    }

    resp = req_lib.request(method, url, json=body, headers=hdrs, timeout=15)
    return jsonify(resp.json()), resp.status_code


@coveo_bp.route("/rga-coveo", methods=["POST"])
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

    if result.stream_completed is False and result.error is None:
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
            "title":       c.get("title", ""),
            "uri":         c.get("uri") or c.get("clickUri", ""),
            "permanentid": c.get("permanentid", ""),
        }
        for c in result.citations
    ]

    return jsonify({"answer": result.answer, "citations": clean_citations})
