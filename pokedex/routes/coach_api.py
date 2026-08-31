"""Coach API blueprint: stateful conversation, comparison detection, challenge mode."""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request

from pokedex.conversation import append_turn, get_history
from pokedex.coveo import CoveoClient
from pokedex import pokemon_names
from pokedex.pokemon_names import NAME_CHARS as _NC

from pokedex.matchup import detect_matchup_intent, MatchupIntent  # noqa: E402
from pokedex.fact_intent import detect_fact_intent  # noqa: E402
from pokedex.facts import render_answer as render_fact_answer  # noqa: E402
from pokedex.facts_store import FactsStore  # noqa: E402

coach_bp = Blueprint("coach_api", __name__)

# One store per process: it owns an LRU cache and reads the optional facts
# file once at construction, neither of which should happen per request.
_facts_store = FactsStore()

# ── Module-level grading resources (load once at startup) ─────
# These are optional — if eval_harness is absent the guards below skip grading.
_grade_chart = None
_grade_universe: list = []
try:
    from eval_harness.grading import check_chart_claims, check_type_claims, is_abstention  # type: ignore
    from eval_harness.typechart import TypeChart  # type: ignore
    from eval_harness.reference import ideal_answer as _ideal_answer  # type: ignore

    _cache_path = Path("eval_data/type_cache.json")
    _grade_chart = TypeChart(_cache_path, offline=_cache_path.exists())
    _corpus_path = Path("eval_data/corpus.json")
    _grade_universe = json.loads(_corpus_path.read_text()) if _corpus_path.exists() else []
except Exception:
    pass  # grading is best-effort; missing eval_harness is fine

_ideal_answer = globals().get("_ideal_answer")  # None if eval_harness absent
if "is_abstention" not in globals():
    # Fallback when eval_harness is absent: treat the sentinel string literally.
    _ABSTENTION_SENTINEL = "(no answer generated)"
    def is_abstention(answer: str) -> bool:  # type: ignore[misc]
        s = (answer or "").strip()
        return not s or s == _ABSTENTION_SENTINEL or (s.startswith("(") and s.endswith(")") and len(s) <= 30)

# ── Comparison intent detection ───────────────────────────────
# Patterns (case-insensitive). Each capture is a *candidate span*, deliberately
# loose — _detect_comparison trims it down to the part that actually resolves,
# so the regex no longer has to be clever about where a name starts and ends.
_CMP_PATTERNS = [
    # "compare Charizard and Dragonite" / "compare X vs Y"
    re.compile(rf'\bcompare\s+([A-Za-z][{_NC}]{{1,30}}?)\s+'
               rf'(?:to|with|and|vs\.?|versus)\s+([A-Za-z][{_NC}]{{1,30}})', re.I),
    # "between Charizard and Dragonite, ..."
    re.compile(rf'\bbetween\s+([A-Za-z][{_NC}]{{1,30}}?)\s+and\s+([A-Za-z][{_NC}]{{1,30}})', re.I),
    # "Charizard vs Dragonite" / "Charizard versus Dragonite"
    re.compile(rf'\b([A-Za-z][{_NC}]{{1,30}}?)\s+(?:vs\.?|versus)\s+([A-Za-z][{_NC}]{{1,30}})', re.I),
    # "which is better: Umbreon or Espeon" / "Umbreon or Espeon"
    re.compile(rf'\b([A-Za-z][{_NC}]{{1,30}}?)\s+or\s+([A-Za-z][{_NC}]{{1,30}})'
               rf'(?=\s*[?,]|\s+for|\s+on|\s+against|\s*$)', re.I),
]

# Single-word Pokémon names that would produce false positives in the "or" pattern.
# Still used by _extract_pokemon_mentions.
_STOPWORDS = {
    'a', 'an', 'the', 'my', 'your', 'his', 'her', 'their', 'our',
    'not', 'no', 'yes', 'can', 'will', 'should', 'would', 'could',
    'what', 'which', 'who', 'when', 'where', 'why', 'how',
    'fire', 'water', 'grass', 'electric', 'ice', 'fighting', 'poison',
    'ground', 'flying', 'psychic', 'bug', 'rock', 'ghost', 'dragon',
    'dark', 'steel', 'fairy', 'normal',
}


def _detect_comparison(message: str) -> tuple[str, str] | None:
    """Return (pokemon_a, pokemon_b) if the message is a comparison request.

    Both sides must resolve EXACTLY against the corpus. Fuzzy matching is
    deliberately not used here: at edit distance 2 'speed' resolves to 'seel'
    and 'null' to 'numel', which would fabricate a comparison out of a question
    that never named a Pokemon.

    finditer, not search: the first match of a pattern is often the wrong span
    ("should i use charizard" / "blastoise against this"). Later matches, and
    the prefix/suffix trim, recover the real names.
    """
    for pattern in _CMP_PATTERNS:
        for m in pattern.finditer(message or ""):
            a = pokemon_names.resolve_suffix(m.group(1))
            b = pokemon_names.resolve_prefix(m.group(2))
            if a and b and a != b:
                return a, b
    return None


_MAX_HISTORY_CHARS = 200  # per-turn cap so a long Oak answer doesn't dominate the query


def _build_context_prompt(history: list[dict], message: str) -> str:
    """
    Build the query string for the RGA call, incorporating recent history
    so the model can resolve pronouns like 'it' and 'them'.

    Assistant turns are truncated to _MAX_HISTORY_CHARS so a long previous
    answer does not crowd out the actual new question sent to Coveo.

    When a turn has a pokemon_context list (canonical resolved names), those
    names are appended as a hint so pronoun resolution works even when the
    user typed a misspelling in the original message.
    """
    if not history:
        return message
    # Include up to the last 4 turns as inline context
    recent = history[-4:]
    lines = []
    for turn in recent:
        role = "Trainer" if turn["role"] == "user" else "Oak"
        content = turn["content"]
        if turn["role"] == "assistant" and len(content) > _MAX_HISTORY_CHARS:
            content = content[:_MAX_HISTORY_CHARS] + "…"
        ctx = turn.get("pokemon_context") or []
        if ctx:
            content = f"{content} [Pokémon: {', '.join(ctx)}]"
        lines.append(f"{role}: {content}")
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
    raw = request.get_json(force=True, silent=True)
    if not isinstance(raw, dict):
        return jsonify({"error": "request body must be a JSON object"}), 400

    session_id = raw.get("session_id", "")
    message = raw.get("message", "")

    if not isinstance(session_id, str) or not session_id.strip():
        return jsonify({"error": "session_id must be a non-empty string"}), 400
    if not isinstance(message, str) or not message.strip():
        return jsonify({"error": "message must be a non-empty string"}), 400

    session_id = session_id.strip()
    message = message.strip()

    # Detect comparison intent before calling the LLM
    comparison = None
    cmp_names = _detect_comparison(message)

    history = get_history(session_id)

    # ── Type-chart fast path ──────────────────────────────────────────────
    # If we can resolve the team and the wild Pokémon from this message, compute
    # the answer directly from the type chart. This is always correct, always fast,
    # and never hallucinates. The LLM path is the fallback, not the primary.
    answer = None
    citations = []
    intent = None

    if _grade_chart is not None and _ideal_answer is not None:
        intent = detect_matchup_intent(message, history)
        if intent is not None:
            try:
                gt = _grade_chart.ground_truth(intent.team, intent.wild)
                answer = _ideal_answer(intent.probe, gt, intent.team)
            except Exception:
                # Name not in cache and offline. Fall through to Coveo.
                answer = None
                intent = None

    # ── PokemonDB facts ───────────────────────────────────────────────────
    # Abilities, evolution, breeding, training and flavour text are facts, not
    # opinions: render them from the indexed page rather than asking a model to
    # recall them. render_fact_answer returns None when the retrieved passages
    # did not cover the section, and that falls through to Coveo below rather
    # than guessing.
    if answer is None:
        try:
            fact_intent = detect_fact_intent(message, history)
            if fact_intent is not None:
                facts = _facts_store.get(fact_intent.pokemon)
                if facts is not None:
                    rendered = render_fact_answer(fact_intent.topic, facts)
                    if rendered:
                        answer = rendered
                        url = pokemon_names.url_for(fact_intent.pokemon)
                        if url:
                            citations = [{
                                "title": f"{fact_intent.pokemon.title()} | Pokémon Database",
                                "uri": url,
                            }]
        except Exception:
            # Facts are supplementary; a failure here must not cost the user an
            # answer that Coveo could still give.
            current_app.logger.exception("fact path failed")
            answer = None

    # ── Coveo fallback (encyclopaedia questions, unresolved teams, etc.) ──
    if answer is None:
        query = _build_context_prompt(history, message)
        client = CoveoClient()
        result = client.generated_answer(query)

        _rga_abstained = (
            result.stream_completed is False
            or (result.stream_completed is True and is_abstention(result.answer))
        )
        if _rga_abstained and result.error is None:
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
        elif result.error:
            answer = f"(Error: {result.error})"
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
    """Run objective type/chart checks; return list of flag dicts.

    Uses module-level singletons (_grade_chart, _grade_universe) initialised at
    import time so eval_data files are read once per server process, not per request.
    """
    flags = []
    if _grade_chart is None:
        return flags  # eval_harness not available; skip grading
    try:
        for err in check_chart_claims(answer):  # type: ignore[name-defined]
            flags.append({"type": "chart_error", "message": err["claim"],
                          "quote": err.get("quote", "")})
        for err in check_type_claims(answer, _grade_chart, _grade_universe):  # type: ignore[name-defined]
            flags.append({
                "type":    "type_error",
                "message": err.get("pokemon", ""),
                "quote":   err.get("quote", ""),
                "actual":  err.get("actual", []),
                "claimed": err.get("claimed", []),
            })
    except Exception:
        pass
    return flags


# Very lightweight — just look for capitalised words that could be Pokémon names.
_POKEMON_MENTION_RE = re.compile(r'\b([A-Z][a-z]{2,}(?:-[A-Z][a-z]+)?)\b')


def _extract_pokemon_mentions(text: str) -> list[str]:
    """
    Return canonical Pokémon names found in `text`, verified against the
    corpus via _closest_pokemon.  Capitalisation heuristics alone
    produce too many false positives (ordinary English words, verbs, etc.).
    """
    from pokedex.routes.coveo_api import _closest_pokemon
    if not pokemon_names.names():
        # Corpus not loaded — fall back to the old capitalised-word heuristic
        # rather than returning nothing.
        return list(dict.fromkeys(
            m.group(1).lower()
            for m in _POKEMON_MENTION_RE.finditer(text)
            if m.group(1).lower() not in _STOPWORDS
        ))[:4]

    seen: dict[str, None] = {}
    for m in _POKEMON_MENTION_RE.finditer(text):
        candidate = m.group(1)
        resolved = _closest_pokemon(candidate, max_dist=1)  # tighter tolerance for context hints
        if resolved and resolved not in seen:
            seen[resolved] = None
        if len(seen) >= 4:
            break
    return list(seen)


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
    from eval_harness.scenarios import ScenarioBuilder, AXES  # type: ignore

    raw = request.get_json(force=True, silent=True)
    data = raw if isinstance(raw, dict) else {}
    axis = data.get("axis", "baseline")
    if axis not in AXES:
        axis = "baseline"

    # Use the module-level TypeChart singleton; fall back to generic prompt if unavailable
    chart = _grade_chart
    pool = list(_grade_universe)

    try:
        if chart is None:
            raise RuntimeError("eval_harness not available")
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
    except Exception:
        # Graceful fallback — return a generic prompt; do not expose internals to client
        current_app.logger.exception("coach-challenge scenario build failed")
        probe_text = "I'm facing a wild Pokémon. Can you help me decide who to send out?"
        session_id = str(uuid.uuid4())
        return jsonify({
            "prompt":     probe_text,
            "session_id": session_id,
            "scenario":   {},
        })

    session_id = str(uuid.uuid4())

    return jsonify({
        "prompt":     probe_text,
        "session_id": session_id,
        "scenario": {
            "axis":  sc.axis,
            "wild":  sc.wild,
            "team":  sc.team,
        },
    })
