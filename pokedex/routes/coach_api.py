"""Coach API blueprint: stateful conversation, comparison detection, challenge mode."""
from __future__ import annotations

import re
import uuid

from flask import Blueprint, jsonify, request

from pokedex.conversation import append_turn, get_history
from pokedex.coveo import CoveoClient

coach_bp = Blueprint("coach_api", __name__)

# ── Comparison intent detection ───────────────────────────────
# Patterns (case-insensitive). Each returns (name_a, name_b) or None.
_CMP_PATTERNS = [
    # "compare Charizard and Dragonite" / "compare X vs Y"
    re.compile(
        r'\bcompare\s+([A-Za-z][A-Za-z\'\-\.♀♂ ]{1,30}?)\s+'
        r'(?:and|vs\.?|versus)\s+([A-Za-z][A-Za-z\'\-\.♀♂ ]{1,30})',
        re.I
    ),
    # "Charizard vs Dragonite" / "Charizard versus Dragonite"
    re.compile(
        r'\b([A-Za-z][A-Za-z\'\-\.♀♂ ]{1,30}?)\s+'
        r'(?:vs\.?|versus)\s+([A-Za-z][A-Za-z\'\-\.♀♂ ]{1,30})',
        re.I
    ),
    # "which is better: Umbreon or Espeon" / "Umbreon or Espeon"
    re.compile(
        r'\b([A-Za-z][A-Za-z\'\-\.♀♂ ]{1,30}?)\s+or\s+([A-Za-z][A-Za-z\'\-\.♀♂ ]{1,30})'
        r'(?=\s*[?,]|\s+for|\s+on|\s+against|\s*$)',
        re.I
    ),
]

# Single-word Pokémon names that would produce false positives in the "or" pattern.
_STOPWORDS = {
    'a', 'an', 'the', 'my', 'your', 'his', 'her', 'their', 'our',
    'not', 'no', 'yes', 'can', 'will', 'should', 'would', 'could',
    'what', 'which', 'who', 'when', 'where', 'why', 'how',
    'fire', 'water', 'grass', 'electric', 'ice', 'fighting', 'poison',
    'ground', 'flying', 'psychic', 'bug', 'rock', 'ghost', 'dragon',
    'dark', 'steel', 'fairy', 'normal',
}


def _detect_comparison(message: str) -> tuple[str, str] | None:
    """Return (pokemon_a, pokemon_b) if the message is a comparison request."""
    for pattern in _CMP_PATTERNS:
        m = pattern.search(message)
        if m:
            a = m.group(1).strip().lower()
            b = m.group(2).strip().lower()
            # Reject stopwords and strings over 25 chars (not Pokémon names)
            if a in _STOPWORDS or b in _STOPWORDS:
                continue
            if len(a) > 25 or len(b) > 25:
                continue
            return a, b
    return None


def _build_context_prompt(history: list[dict], message: str) -> str:
    """
    Build the query string for the RGA call, incorporating recent history
    so the model can resolve pronouns like 'it' and 'them'.
    """
    if not history:
        return message
    # Include up to the last 4 turns as inline context
    recent = history[-4:]
    lines = []
    for turn in recent:
        role = "Trainer" if turn["role"] == "user" else "Oak"
        lines.append(f"{role}: {turn['content']}")
    lines.append(f"Trainer: {message}")
    return "\n".join(lines)


# ── /api/coach ────────────────────────────────────────────────
@coach_bp.route("/coach", methods=["POST"])
def coach():
    """
    Body: { "session_id": str, "message": str }
    Returns: {
        "answer": str,
        "citations": list,
        "session_id": str,
        "comparison": { "pokemon_a": str, "pokemon_b": str,
                        "verdict": str, "winner": str | null } | null,
        "grading_flags": list   # list of {type, message} dicts
    }
    """
    data = request.get_json(force=True)
    session_id = data.get("session_id", "").strip()
    message = data.get("message", "").strip()

    if not session_id:
        return jsonify({"error": "session_id is required"}), 400
    if not message:
        return jsonify({"error": "message is required"}), 400

    # Detect comparison intent before calling the LLM
    comparison = None
    cmp_names = _detect_comparison(message)

    history = get_history(session_id)
    query = _build_context_prompt(history, message)

    client = CoveoClient()
    result = client.generated_answer(query)

    # Fallback to search excerpts if RGA did not fire
    if result.stream_completed is False and result.error is None:
        search_results = client.search(query, num=5).get("results", [])
        snippets = "; ".join(
            r.get("excerpt", r.get("title", ""))[:200]
            for r in search_results[:3]
            if r.get("excerpt") or r.get("title")
        )
        answer = (
            f"(RGA model did not trigger. Top result: {snippets})"
            if snippets else "(RGA model did not trigger for this query.)"
        )
        citations = []
    elif result.error:
        answer = f"(Error: {result.error})"
        citations = []
    else:
        answer = result.answer
        citations = [
            {
                "title": c.get("title", ""),
                "uri":   c.get("uri") or c.get("clickUri", ""),
            }
            for c in result.citations
        ]

    # Grading flags (type/chart errors in the answer)
    grading_flags = _grade_answer(answer, cmp_names)

    # Build comparison block
    if cmp_names:
        comparison = {
            "pokemon_a": cmp_names[0],
            "pokemon_b": cmp_names[1],
            "verdict":   answer,   # full answer is the verdict for the client to display
            "winner":    None,     # client computes BST winner from fetched stats
        }

    # Persist turns
    pokemon_ctx = list(cmp_names) if cmp_names else _extract_pokemon_mentions(message)
    append_turn(session_id, "user", message, pokemon_context=pokemon_ctx)
    append_turn(session_id, "assistant", answer, pokemon_context=pokemon_ctx)

    return jsonify({
        "answer":        answer,
        "citations":     citations,
        "session_id":    session_id,
        "comparison":    comparison,
        "grading_flags": grading_flags,
    })


def _grade_answer(answer: str, cmp_names: tuple[str, str] | None) -> list[dict]:
    """Run objective type/chart checks; return list of flag dicts."""
    flags = []
    try:
        from eval_harness.grading import check_chart_claims
        for err in check_chart_claims(answer):
            flags.append({"type": "chart_error", "message": err["claim"],
                          "quote": err.get("quote", "")})
    except Exception:
        pass
    return flags


# Very lightweight — just look for capitalised words that could be Pokémon names.
_POKEMON_MENTION_RE = re.compile(r'\b([A-Z][a-z]{2,}(?:-[A-Z][a-z]+)?)\b')


def _extract_pokemon_mentions(text: str) -> list[str]:
    return list(dict.fromkeys(
        m.group(1).lower()
        for m in _POKEMON_MENTION_RE.finditer(text)
        if m.group(1).lower() not in _STOPWORDS
    ))[:4]


# ── /api/coach-challenge ──────────────────────────────────────
@coach_bp.route("/coach-challenge", methods=["POST"])
def coach_challenge():
    """
    Body: { "axis"?: str }   — optional axis name from eval_harness.scenarios.AXES
    Returns: { "prompt": str, "session_id": str, "scenario": dict }

    Draws a random battle scenario and returns the first probe question
    as a ready-to-send coach message. The scenario dict gives the client
    enough information to render the team and wild Pokémon.
    """
    import random
    from eval_harness.scenarios import ScenarioBuilder, AXES, DEFAULT_PROBES
    from eval_harness.typechart import TypeChart
    from pathlib import Path

    data = request.get_json(force=True) or {}
    axis = data.get("axis", "baseline")
    if axis not in AXES:
        axis = "baseline"

    try:
        cache_path = Path("eval_data/type_cache.json")
        chart = TypeChart(cache_path, offline=cache_path.exists())
        # Load Pokémon names from corpus or fall back to a small hardcoded set
        try:
            import json
            corpus_path = Path("eval_data/corpus.json")
            pool = json.loads(corpus_path.read_text()) if corpus_path.exists() else []
        except Exception:
            pool = []
        if len(pool) < 7:
            pool = [
                "charizard", "blastoise", "venusaur", "pikachu", "gengar",
                "alakazam", "machamp", "gyarados", "lapras", "eevee",
                "vaporeon", "jolteon", "flareon", "mewtwo", "dragonite",
            ]
        rng = random.Random()
        builder = ScenarioBuilder(pool, chart, rng)
        sc = builder.draw(axis=axis)
        if sc is None:
            return jsonify({"error": f"could not build a scenario for axis {axis!r}"}), 500
        builder.attach_probes(sc, ["advantage"])
        probe_text = sc.probes[0][1] if sc.probes else (
            f"My team is {', '.join(sc.team)}. "
            f"Which of them has a type advantage against {sc.wild}?"
        )
    except Exception as exc:
        # Graceful fallback — return a generic prompt
        probe_text = "I'm facing a wild Pokémon. Can you help me decide who to send out?"
        session_id = str(uuid.uuid4())
        return jsonify({
            "prompt":     probe_text,
            "session_id": session_id,
            "scenario":   {},
            "error":      str(exc),
        })

    session_id = str(uuid.uuid4())
    append_turn(session_id, "user", probe_text, pokemon_context=sc.team + [sc.wild])

    return jsonify({
        "prompt":     probe_text,
        "session_id": session_id,
        "scenario": {
            "axis":  sc.axis,
            "wild":  sc.wild,
            "team":  sc.team,
        },
    })
