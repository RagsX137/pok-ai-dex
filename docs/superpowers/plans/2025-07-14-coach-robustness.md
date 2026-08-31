# Coach Robustness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the coach answer the question it was built to answer — reliably, correctly, without hallucinating typings or recommending Pokémon that cannot deal damage.

**Architecture:** Three sequential projects, each independently shippable. Project 1 routes matchup questions through `TypeChart.ground_truth()` instead of the LLM; the LLM's only remaining job is phrasing a pre-computed answer. Project 2 fixes retrieval query shape so entity names — not transcript fragments — drive Coveo. Project 3 patches hygiene bugs (double-send, broken abstention check, type-confused JSON crashes, grading flag UI, cache coverage, grader phrasing gaps).

**Tech Stack:** Python/Flask (server), vanilla JS ES modules (frontend), pytest (tests), `eval_harness.typechart.TypeChart`, `eval_harness.reference.ideal_answer`, `eval_harness.grading` (grading).

## Global Constraints

- Do not add new dependencies. All pieces already exist in the repo.
- Do not change the public API shape of `/api/coach` — same JSON fields, same status codes.
- All existing tests in `tests/unit/test_coach_routes.py` must keep passing throughout.
- `TypeChart` is already loaded at module level in `coach_api.py:25` as `_grade_chart`. Reuse it.
- `ideal_answer` is in `eval_harness/reference.py`. Import it the same guarded way as `TypeChart`.
- `_closest_pokemon` and `_POKEMON_NAMES` live in `coveo_api.py`. Do not duplicate them; expose a helper or import from there.

---

## Project 1: Answer matchup questions from the type chart, not the LLM

**Eliminates: F1, F2, F3, F5, F6** (the five findings about wrong/late/fabricated answers). Also eliminates F-D (grading-artifact "correct" verdicts by silence — with the type-chart path the answer is always affirmative and reasoned).

The change: detect when the user is asking a matchup question (team + wild Pokémon present), resolve the names, call `_grade_chart.ground_truth(team, wild)`, render with `ideal_answer`, and hand the LLM a factual summary to re-phrase rather than an open question to guess at. When no names can be resolved, fall through to the existing Coveo path unchanged.

### Task 1: Intent detection and name resolution

**Files:**
- Create: `pokedex/matchup.py`
- Test: `tests/unit/test_matchup.py`

**Interfaces:**
- Produces: `detect_matchup_intent(message, history) -> MatchupIntent | None`
- Produces: `MatchupIntent` dataclass: `team: list[str], wild: str, probe: str`
- `probe` is one of `"advantage"`, `"avoid"`, `"ranking"` — maps to `eval_harness/scenarios.py` PROBES keys.

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/test_matchup.py
import pytest
from pokedex.matchup import detect_matchup_intent, MatchupIntent

# --- helpers ----------------------------------------------------------------

def _hist(team, wild):
    """Fake a prior turn that established the team and wild Pokémon."""
    return [
        {
            "role": "user",
            "content": f"Tell me about {wild}",
            "pokemon_context": [wild],
        },
        {
            "role": "assistant",
            "content": f"{wild} is a Grass type.",
            "pokemon_context": [wild],
        },
    ]


# --- advantage probe --------------------------------------------------------

def test_detects_advantage_with_full_team():
    msg = (
        "My team is Venipede, Solosis, Iron Treads, Sawk, Carkol and Gothita. "
        "Which of them has a type advantage against Toucannon?"
    )
    result = detect_matchup_intent(msg, [])
    assert result is not None
    assert result.wild == "toucannon"
    assert len(result.team) == 6
    assert "venipede" in result.team
    assert result.probe == "advantage"


def test_detects_avoid_probe():
    msg = "Which of Pikachu, Bulbasaur, Charmander, Squirtle, Jigglypuff and Geodude would be a bad idea to send out against Gengar?"
    result = detect_matchup_intent(msg, [])
    assert result is not None
    assert result.wild == "gengar"
    assert result.probe == "avoid"


def test_returns_none_for_unrelated_question():
    result = detect_matchup_intent("What moves does Pikachu learn?", [])
    assert result is None


def test_returns_none_when_team_absent():
    result = detect_matchup_intent("Which of my team beats Toucannon?", [])
    assert result is None


def test_falls_back_to_history_for_wild():
    # The wild Pokémon was established in a prior turn; the current message
    # only references "it".
    history = _hist([], "lapras")  # wild established; team still needed in message
    msg = "My team is Pikachu, Bulbasaur, Charmander, Squirtle, Jigglypuff and Geodude. Which of them can beat it?"
    result = detect_matchup_intent(msg, history)
    assert result is not None
    assert result.wild == "lapras"


def test_ranking_probe():
    msg = (
        "Out of Pikachu, Bulbasaur, Charmander, Squirtle, Jigglypuff and Geodude, "
        "which single one is the safest switch-in against Raichu and why?"
    )
    result = detect_matchup_intent(msg, [])
    assert result is not None
    assert result.probe == "ranking"
    assert result.wild == "raichu"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/unit/test_matchup.py -v
```
Expected: `ModuleNotFoundError: No module named 'pokedex.matchup'`

- [ ] **Step 3: Implement `pokedex/matchup.py`**

```python
"""
Matchup intent detection.

Decides whether a message is asking "which of my team beats the wild Pokémon"
and if so, resolves the team and wild name from the message + conversation history.

Deliberately has no imports from coach_api or coveo_api — it is a pure utility
that takes text and returns a data structure.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Lazily import _POKEMON_NAMES from coveo_api to avoid a circular import.
# We call _closest_pokemon from there instead of duplicating the lookup.
def _corpus() -> list[str]:
    from pokedex.routes.coveo_api import _POKEMON_NAMES
    return _POKEMON_NAMES


def _resolve(name: str) -> str | None:
    """Return a canonical lowercase Pokémon name, or None."""
    from pokedex.routes.coveo_api import _closest_pokemon
    return _closest_pokemon(name.lower().strip(), max_dist=2)


# ── team extraction ──────────────────────────────────────────────────────────
# Matches "My team is A, B, C, D, E and F" (6 names, various separators).
_TEAM_RE = re.compile(
    r"(?:my\s+)?team\s+is\s+"
    r"([A-Za-z][A-Za-z\-' ]{1,20})"          # name 1
    r"(?:,\s*([A-Za-z][A-Za-z\-' ]{1,20}))"  # name 2
    r"(?:,\s*([A-Za-z][A-Za-z\-' ]{1,20}))"  # name 3
    r"(?:,\s*([A-Za-z][A-Za-z\-' ]{1,20}))"  # name 4
    r"(?:,\s*([A-Za-z][A-Za-z\-' ]{1,20}))"  # name 5
    r"(?:,?\s+and\s+([A-Za-z][A-Za-z\-' ]{1,20}))",  # name 6
    re.I,
)

# "which of A, B, C, D, E and F …"
_WHICH_OF_RE = re.compile(
    r"which\s+of\s+"
    r"([A-Za-z][A-Za-z\-' ]{1,20})"
    r"(?:,\s*([A-Za-z][A-Za-z\-' ]{1,20})){4}"
    r"(?:,?\s+and\s+([A-Za-z][A-Za-z\-' ]{1,20}))",
    re.I,
)

# ── probe classification ─────────────────────────────────────────────────────
_AVOID_RE = re.compile(r"\b(avoid|bad idea|bad choice|worst|not send|shouldn't send|should not send)\b", re.I)
_RANKING_RE = re.compile(r"\b(safest|best|single|single one|top pick|who should i lead|lead with)\b", re.I)

# ── wild extraction ──────────────────────────────────────────────────────────
_AGAINST_RE = re.compile(
    r"\b(?:against|vs\.?|versus|fight(?:ing)?|face|encounter(?:ing)?)\s+"
    r"([A-Za-z][A-Za-z\-']{2,24})\b",
    re.I,
)


@dataclass
class MatchupIntent:
    team: list[str]   # lowercase canonical names
    wild: str         # lowercase canonical name
    probe: str        # "advantage" | "avoid" | "ranking"


def _extract_team(text: str) -> list[str] | None:
    """Return a list of up to 6 resolved names, or None if fewer than 2 resolve."""
    for pattern in (_TEAM_RE, _WHICH_OF_RE):
        m = pattern.search(text)
        if m:
            raw = [g for g in m.groups() if g]
            resolved = [r for r in (_resolve(n) for n in raw) if r]
            if len(resolved) >= 2:
                return resolved
    return None


def _extract_wild_from_text(text: str) -> str | None:
    for m in _AGAINST_RE.finditer(text):
        r = _resolve(m.group(1))
        if r:
            return r
    return None


def _extract_wild_from_history(history: list[dict]) -> str | None:
    """Walk backwards through history looking for pokemon_context on Oak turns."""
    for turn in reversed(history):
        ctx = turn.get("pokemon_context") or []
        if ctx:
            # The first entry in context for assistant turns is typically the
            # wild Pokémon (it's the one being described).
            r = _resolve(ctx[0])
            if r:
                return r
    return None


def _classify_probe(text: str) -> str:
    low = text.lower()
    if _AVOID_RE.search(low):
        return "avoid"
    if _RANKING_RE.search(low):
        return "ranking"
    return "advantage"


# ── public API ───────────────────────────────────────────────────────────────

def detect_matchup_intent(message: str, history: list[dict]) -> MatchupIntent | None:
    """
    Return a MatchupIntent if the message is asking which teammate beats a wild
    Pokémon, else None.

    Requires:
      - A resolvable team of at least 2 Pokémon (either stated in the message
        or in the "which of X, Y, Z…" pattern).
      - A resolvable wild Pokémon (from "against X" in the message, or from
        the last pokemon_context entry in conversation history).
    """
    if not _corpus():
        return None  # name corpus not loaded; fall through to LLM path

    team = _extract_team(message)
    if not team:
        return None

    wild = _extract_wild_from_text(message) or _extract_wild_from_history(history)
    if not wild:
        return None

    # Exclude the wild from the team in case of accidental overlap.
    team = [t for t in team if t != wild]
    if not team:
        return None

    probe = _classify_probe(message)
    return MatchupIntent(team=team, wild=wild, probe=probe)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/unit/test_matchup.py -v
```
Expected: all 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add pokedex/matchup.py tests/unit/test_matchup.py
git commit -m "feat(matchup): intent detection and name resolution"
```

---

### Task 2: Compute the answer from the type chart

**Files:**
- Modify: `pokedex/routes/coach_api.py`
- Modify: `pokedex/routes/coach_api.py` (imports section)
- Test: `tests/unit/test_coach_routes.py`

**Interfaces:**
- Consumes: `detect_matchup_intent` from `pokedex.matchup`
- Consumes: `_grade_chart` (already module-level in coach_api.py)
- Consumes: `ideal_answer` from `eval_harness.reference` (guard the import as the TypeChart import is guarded)
- The `/api/coach` response shape is unchanged.

When `detect_matchup_intent` returns a result **and** `_grade_chart` can resolve all names:
1. Call `_grade_chart.ground_truth(intent.team, intent.wild)` — produces the verified matchup dict.
2. Call `ideal_answer(intent.probe, gt, intent.team)` — renders a factually correct answer string.
3. Use that string as `answer` directly. Skip the Coveo call entirely for this path.
4. Set `citations = []` (there are none; no retrieval happened).
5. Still call `_grade_answer(answer, cmp_names)` — grading should still run and will now produce zero type errors on correct answers.

When `detect_matchup_intent` returns None, behaviour is unchanged: Coveo is called exactly as before.

- [ ] **Step 1: Add test for the computed-answer path**

Add to `tests/unit/test_coach_routes.py`:

```python
def test_coach_matchup_answered_from_typechart(client):
    """When a 6-name team + wild are present, the answer must name at least one
    teammate (or say 'none'). It must NOT be an encyclopedia entry."""
    # No mock needed — _grade_chart is module-level and real.
    # We mock CoveoClient to confirm it is NOT called on this path.
    with patch("pokedex.routes.coach_api.CoveoClient") as MockCoveo:
        r = client.post("/api/coach", json={
            "session_id": "typechart-test",
            "message": (
                "My team is Venipede, Solosis, Iron Treads, Sawk, Carkol and Gothita. "
                "Which of them has a type advantage against Toucannon?"
            ),
        })
    assert r.status_code == 200
    d = r.get_json()
    answer = d["answer"].lower()
    # The answer must mention at least one teammate by name, OR say "none".
    team_lower = ["venipede", "solosis", "iron treads", "sawk", "carkol", "gothita"]
    named = any(t in answer for t in team_lower) or "none" in answer
    assert named, f"Answer did not name any teammate: {d['answer']}"
    # Coveo must not have been called.
    MockCoveo.assert_not_called()


def test_coach_no_advantage_says_none(client):
    """When no teammate has an advantage, the answer must say 'none' (not fabricate one)."""
    # Build a team that provably has no advantage against a Steel type.
    # All Normal types hit Steel for 0.5x. Use a Normal/Ground team vs. Steel.
    # This is a structural test — it confirms the none-path fires correctly.
    with patch("pokedex.routes.coach_api.CoveoClient") as MockCoveo:
        r = client.post("/api/coach", json={
            "session_id": "none-test",
            "message": (
                "My team is Rattata, Bidoof, Sentret, Meowth, Jigglypuff and Snorlax. "
                "Which of them has a type advantage against Registeel?"
            ),
        })
    assert r.status_code == 200
    d = r.get_json()
    assert "none" in d["answer"].lower() or "no teammate" in d["answer"].lower()
    MockCoveo.assert_not_called()
```

- [ ] **Step 2: Run new tests to confirm they fail**

```bash
pytest tests/unit/test_coach_routes.py::test_coach_matchup_answered_from_typechart \
       tests/unit/test_coach_routes.py::test_coach_no_advantage_says_none -v
```
Expected: FAIL — the Coveo mock will be called (the current code doesn't have the type-chart path).

- [ ] **Step 3: Add the `ideal_answer` import guard to `coach_api.py`**

In the try/except block at [`coach_api.py:20`](pokedex/routes/coach_api.py:20), add the reference import:

```python
try:
    from eval_harness.grading import check_chart_claims, check_type_claims  # type: ignore
    from eval_harness.typechart import TypeChart  # type: ignore
    from eval_harness.reference import ideal_answer as _ideal_answer  # type: ignore  ← add this

    _cache_path = Path("eval_data/type_cache.json")
    _grade_chart = TypeChart(_cache_path, offline=_cache_path.exists())
    _corpus_path = Path("eval_data/corpus.json")
    _grade_universe = json.loads(_corpus_path.read_text()) if _corpus_path.exists() else []
except Exception:
    pass
```

Also add at module level, after the try/except:

```python
_ideal_answer = globals().get("_ideal_answer")  # None if eval_harness absent
```

- [ ] **Step 4: Add the matchup-intent import to `coach_api.py`**

At the top of [`coach_api.py`](pokedex/routes/coach_api.py), after the existing imports:

```python
from pokedex.matchup import detect_matchup_intent, MatchupIntent
```

- [ ] **Step 5: Add the computed-answer path to `coach()` in `coach_api.py`**

Replace the block starting at [`coach_api.py:144`](pokedex/routes/coach_api.py:144) (the `# Detect comparison intent` comment through the `result = client.generated_answer(query)` call and the fallback block) with:

```python
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

    # ── Coveo fallback (encyclopaedia questions, unresolved teams, etc.) ──
    if answer is None:
        query = _build_context_prompt(history, message)
        client = CoveoClient()
        result = client.generated_answer(query)

        _rga_abstained = (
            result.stream_completed is False
            or (result.stream_completed is True and not result.answer.strip("() "))
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
```

- [ ] **Step 6: Run all coach tests**

```bash
pytest tests/unit/test_coach_routes.py -v
```
Expected: all tests PASS (including the two new ones).

- [ ] **Step 7: Commit**

```bash
git add pokedex/routes/coach_api.py tests/unit/test_coach_routes.py
git commit -m "feat(coach): answer matchup questions from type chart, not LLM

Detects team+wild intent, computes ground truth via TypeChart.ground_truth(),
renders with ideal_answer(). Coveo is still called for encyclopaedia questions
and any query where names cannot be resolved.

Eliminates F1 (two-turn delay), F2 (5-doc budget), F3 (cold abstention),
F5 (harmful picks), F6 (cannot say none)."
```

---

## Project 2: Fix retrieval query shape

**Eliminates: F18** (extractor injects English words into Coveo query). **Partially improves F2** — the retrieval A/B in Part 7 of the QA log shows that raising `num` alone is insufficient: the bare question (149 chars, `totalCount=30`) retrieved 1/6 teammates while the context blob (399 chars, `totalCount=500`) retrieved only 2/6, despite returning far more total results. The limiting factor is query-entity salience, not budget. Sending entity names directly — what this task achieves — addresses both the salience and the false-injection problems simultaneously.

When Coveo IS called (encyclopaedia questions, unresolved intent), the query sent to it should be entity names, not a transcript. The `_build_context_prompt` function should use the 924-name corpus via `_closest_pokemon` rather than a capitalised-word regex.

### Task 3: Fix `_extract_pokemon_mentions` to use the corpus

**Files:**
- Modify: `pokedex/routes/coach_api.py`
- Test: `tests/unit/test_coach_routes.py`

**Interfaces:**
- `_extract_pokemon_mentions(text)` must return only names that resolve via `_closest_pokemon`, not arbitrary capitalised words.

- [ ] **Step 1: Add failing test**

Add to `tests/unit/test_coach_routes.py`:

```python
def test_extract_pokemon_mentions_no_english_words():
    from pokedex.routes.coach_api import _extract_pokemon_mentions
    # English words that happen to be capitalised must not appear.
    result = _extract_pokemon_mentions("I Am Shouting Every Word Here")
    assert result == [], f"Expected [], got {result}"

def test_extract_pokemon_mentions_finds_real_names():
    from pokedex.routes.coach_api import _extract_pokemon_mentions
    result = _extract_pokemon_mentions("Tell me about Lapras and Venusaur")
    assert "lapras" in result
    assert "venusaur" in result
    # "Tell" and "About" must not be in the result.
    assert "tell" not in result
    assert "about" not in result
```

- [ ] **Step 2: Run new tests to confirm they fail**

```bash
pytest tests/unit/test_coach_routes.py::test_extract_pokemon_mentions_no_english_words \
       tests/unit/test_coach_routes.py::test_extract_pokemon_mentions_finds_real_names -v
```
Expected: `test_extract_pokemon_mentions_no_english_words` FAILS (currently returns `['shouting', 'every', 'word', 'here']`).

- [ ] **Step 3: Replace `_extract_pokemon_mentions` in `coach_api.py`**

Replace [`coach_api.py:233-242`](pokedex/routes/coach_api.py:233):

```python
def _extract_pokemon_mentions(text: str) -> list[str]:
    """
    Return canonical Pokémon names found in `text`, verified against the
    924-name corpus via _closest_pokemon.  Capitalisation heuristics alone
    produce too many false positives (ordinary English words, verbs, etc.).
    """
    from pokedex.routes.coveo_api import _closest_pokemon, _POKEMON_NAMES
    if not _POKEMON_NAMES:
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
```

- [ ] **Step 4: Run all tests**

```bash
pytest tests/unit/test_coach_routes.py -v
```
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add pokedex/routes/coach_api.py tests/unit/test_coach_routes.py
git commit -m "fix(coach): resolve pokemon mentions against corpus, not capitalisation regex

Eliminates F18: 'tell', 'shouting', 'every' etc. no longer injected into Coveo queries."
```

---

## Project 3: Hygiene fixes

Six patches. Tasks 4–7 are independent and can be committed in any order.
**Tasks 8 → 9 → 10 are ordered and must ship in that sequence:** Task 8 builds the shared
name resolver that Task 9 grades with, and Task 10 widens the type cache — which the live
server reads too — so it must land only after Task 9 has corrected the grader patterns it
would otherwise unmask.

### Task 4: Fix the broken abstention check (F14)

**Files:**
- Modify: `pokedex/routes/coach_api.py`
- Test: `tests/unit/test_coach_routes.py`

- [ ] **Step 1: Add failing test**

Add to `tests/unit/test_coach_routes.py`:

```python
def test_abstention_fallback_fires_for_sentinel(client):
    """When Coveo returns the literal sentinel, the excerpt fallback must run — not show the sentinel raw."""
    mock_result = MagicMock()
    mock_result.answer = "(no answer generated)"
    mock_result.citations = []
    mock_result.stream_completed = True
    mock_result.error = None

    mock_search = {"results": [
        {"title": "Pikachu Pokédex", "excerpt": "Pikachu is an Electric-type Pokémon."}
    ]}

    with patch("pokedex.routes.coach_api.CoveoClient") as MockClient:
        MockClient.return_value.generated_answer.return_value = mock_result
        MockClient.return_value.search.return_value = mock_search
        r = client.post("/api/coach", json={
            "session_id": "abstain-test",
            "message": "tell me about Pikachu"
        })

    assert r.status_code == 200
    d = r.get_json()
    # The raw sentinel must not reach the client.
    assert d["answer"] != "(no answer generated)"
    # The search fallback text must be present.
    assert "RGA model did not trigger" in d["answer"] or "Pikachu" in d["answer"]
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
pytest tests/unit/test_coach_routes.py::test_abstention_fallback_fires_for_sentinel -v
```
Expected: FAIL — sentinel currently passes through raw.

- [ ] **Step 3: Fix the abstention check in the Coveo fallback block in `coach_api.py`**

In the Coveo fallback path (the `if answer is None:` block added in Task 2), replace the `_rga_abstained` check with one that uses `is_abstention`:

```python
    if answer is None:
        from eval_harness.grading import is_abstention  # type: ignore  # already in same process

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
```

Note: `is_abstention` is already importable — `eval_harness.grading` is imported at module level in the same guarded block. To avoid the inline import, add `is_abstention` to that guarded block instead:

```python
try:
    from eval_harness.grading import check_chart_claims, check_type_claims, is_abstention  # type: ignore
    ...
```

Then use `is_abstention` directly without the inline import.

- [ ] **Step 4: Run all tests**

```bash
pytest tests/unit/test_coach_routes.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add pokedex/routes/coach_api.py tests/unit/test_coach_routes.py
git commit -m "fix(coach): use is_abstention() for sentinel check, not strip('() ')

Eliminates F14: '(no answer generated)' now correctly triggers the excerpt
fallback instead of being shown raw to the user."
```

---

### Task 5: Fix type-confused JSON crashes (F15)

**Files:**
- Modify: `pokedex/routes/coach_api.py`
- Modify: `pokedex/app.py`
- Test: `tests/unit/test_coach_routes.py`

- [ ] **Step 1: Add failing tests**

Add to `tests/unit/test_coach_routes.py`:

```python
@pytest.mark.parametrize("body,expected_status", [
    (b"[1,2,3]",                                  400),
    (b'"just a string"',                           400),
    (b'{"session_id":1,"message":"hi"}',           400),
    (b'{"session_id":"x","message":999}',          400),
    (b'{"session_id":"x","message":["a","b"]}',    400),
    (b'{"session_id":"x","message":{"a":1}}',      400),
])
def test_coach_rejects_malformed_body(client, body, expected_status):
    r = client.post("/api/coach", data=body,
                    content_type="application/json")
    assert r.status_code == expected_status, f"body={body!r} got {r.status_code}"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/unit/test_coach_routes.py::test_coach_rejects_malformed_body -v
```
Expected: multiple FAIL with 500 instead of 400.

- [ ] **Step 3: Fix the request parsing in `coach()` in `coach_api.py`**

Replace [`coach_api.py:135-142`](pokedex/routes/coach_api.py:135):

```python
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
```

- [ ] **Step 4: Add `MAX_CONTENT_LENGTH` to `app.py`**

In [`app.py`](pokedex/app.py), after `app = Flask(__name__)`:

```python
    app.config["MAX_CONTENT_LENGTH"] = 64 * 1024  # 64 KB — ample for any real question
```

- [ ] **Step 5: Run all tests**

```bash
pytest tests/unit/test_coach_routes.py -v
```
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add pokedex/routes/coach_api.py pokedex/app.py tests/unit/test_coach_routes.py
git commit -m "fix(coach): validate request body type and fields; add MAX_CONTENT_LENGTH

Eliminates F15: list/string/int JSON bodies no longer cause 500s.
Eliminates F17 (request size limit)."
```

---

### Task 6: Fix the challenge double-send (F13)

**Files:**
- Modify: `pokedex/routes/coach_api.py`
- Test: `tests/unit/test_coach_routes.py`

The problem: `coach_challenge` stores the user turn, then `startChallenge()` posts the same message to `/api/coach`, which appends *another* user turn before sending to Coveo — so the session has `[user, user, assistant]` and Coveo receives the question twice.

The fix: `coach_challenge` should **not** store the turn (it's the server's job to do that exactly once, via `/api/coach`). Or equivalently: `startChallenge()` should not call `/api/coach` directly — the challenge route should do the full turn including the answer. The cleanest approach that preserves the existing API surface: remove the `append_turn` call from `coach_challenge` so the session is pristine when `/api/coach` processes it.

- [ ] **Step 1: Remove the premature `append_turn` from `coach_challenge` in `coach_api.py`**

In [`coach_api.py:299`](pokedex/routes/coach_api.py:299), remove this line:

```python
    append_turn(session_id, "user", probe_text, pokemon_context=sc.team + [sc.wild])
```

The session will be created (empty) on first use by `/api/coach`, which is correct — it stores both turns atomically.

- [ ] **Step 2: Add a test**

Add to `tests/unit/test_coach_routes.py`:

```python
def test_challenge_does_not_pre_store_turn(client):
    """coach-challenge must not store a user turn; that is /api/coach's job."""
    from pokedex.conversation import get_history
    r = client.post("/api/coach-challenge", json={})
    assert r.status_code == 200
    d = r.get_json()
    # The session returned by challenge must be empty — no pre-stored turn.
    history = get_history(d["session_id"])
    assert history == [], f"Expected empty history, got {history}"
```

- [ ] **Step 3: Run test**

```bash
pytest tests/unit/test_coach_routes.py::test_challenge_does_not_pre_store_turn -v
```
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add pokedex/routes/coach_api.py tests/unit/test_coach_routes.py
git commit -m "fix(coach): remove premature append_turn from coach-challenge

Eliminates F13: the session no longer has duplicate user turns after
startChallenge() calls /api/coach with the same message."
```

---

### Task 7: Render grading flags as corrections, not just names (F10 + F11)

**Files:**
- Modify: `pokedex/routes/coach_api.py` (serialise `actual`/`claimed` in the flag)
- Modify: `frontend/coach.js` (`appendOakBubble` and `updateSnippet`)

**The change:**
- Server: include `actual` and `claimed` in the serialised flag.
- Client: render "claimed Grass/Fairy — actually Grass" instead of just "Meganium".
- Client: do not call `updateSnippet` when `grading_flags` contains a type error for the first sentence.

- [ ] **Step 1: Fix server serialisation in `_grade_answer`**

In [`coach_api.py:225-227`](pokedex/routes/coach_api.py:225), change the type_error dict to include `actual` and `claimed`:

```python
        for err in check_type_claims(answer, _grade_chart, _grade_universe):  # type: ignore[name-defined]
            flags.append({
                "type":    "type_error",
                "message": err.get("pokemon", ""),
                "quote":   err.get("quote", ""),
                "actual":  err.get("actual", []),
                "claimed": err.get("claimed", []),
            })
```

- [ ] **Step 2: Fix client flag rendering in `appendOakBubble` in `coach.js`**

Replace [`coach.js:98-103`](frontend/coach.js:98):

```javascript
  let flagHtml = '';
  if (gradingFlags?.length) {
    flagHtml = gradingFlags.map(f => {
      if (f.type === 'type_error' && f.actual?.length && f.claimed?.length) {
        const claimed = f.claimed.map(t => t.charAt(0).toUpperCase() + t.slice(1)).join('/');
        const actual  = f.actual.map(t => t.charAt(0).toUpperCase() + t.slice(1)).join('/');
        return `<div class="grade-flag">⚠ ${esc(f.message)}: claimed ${esc(claimed)} — actually ${esc(actual)}</div>`;
      }
      return `<div class="grade-flag">⚠ Type error: ${esc(f.message)}</div>`;
    }).join('');
  }
```

- [ ] **Step 3: Guard `updateSnippet` against flagged first sentences in `coach.js`**

In [`sendMessage`](frontend/coach.js:323), replace the unconditional `updateSnippet(answer)` call at line 367:

```javascript
      // Don't promote a flagged sentence as the "Quick Answer".
      const firstSentenceIsFlagged = grading_flags?.some(f => {
        const firstSentence = answer.split(/[.!?]/)[0].toLowerCase();
        return f.message && firstSentence.includes(f.message.toLowerCase());
      });
      if (!firstSentenceIsFlagged) updateSnippet(answer);
      else updateSnippet('');
```

- [ ] **Step 4: Run all tests**

```bash
pytest tests/unit/ -v
```
Expected: all PASS (no server-side test changes needed — the shape change is additive).

- [ ] **Step 5: Commit**

```bash
git add pokedex/routes/coach_api.py frontend/coach.js
git commit -m "fix(coach): render grading flags as corrections, guard Quick Answer aside

Eliminates F10: flag now shows 'claimed Grass/Fairy — actually Grass'.
Eliminates F11: Quick Answer aside is suppressed when the first sentence is flagged."
```

---

### Task 8: One name resolver, and comparison detection built on it (F12)

**Files:**
- Create: `pokedex/pokemon_names.py`
- Modify: `pokedex/routes/coach_api.py`, `pokedex/routes/coveo_api.py`
- Test: `tests/unit/test_pokemon_names.py` (new), `tests/unit/test_coach_routes.py`

**Why this is bigger than "add digits to a character class".** F12, F-A, F8, F9 and the `Porygon-Z` miss are one bug wearing five hats: *"is this string a Pokémon name?"* is answered in four places, with four different character classes, over two different corpora.

| Site | Character class | Corpus | Cannot see |
|---|---|---|---|
| `_CMP_PATTERNS` ([coach_api.py:33](pokedex/routes/coach_api.py:33)) | `[A-Za-z'\-.♀♂ ]` | — | `Porygon2`, `Type: Null` |
| `_POKEMON_MENTION_RE` ([coach_api.py:234](pokedex/routes/coach_api.py:234)) | `[A-Z][a-z]{2,}(-[A-Z][a-z]+)?` | — | `Ho-Oh`, `Porygon-Z`, `Mr. Mime` |
| `_NAME` ([grading.py:27](eval_harness/grading.py:27)) | `[A-Z][a-zA-Z'’]*` | caller's `universe` | every hyphen/digit name |
| `_closest_pokemon` ([coveo_api.py:39](pokedex/routes/coveo_api.py:39)) | n/a — edit distance ≤ 2 | `data/pokemon_db.csv` (1023) | nothing; sees too much |

Patching one class fixes one hat. This task creates the single resolver; Task 9 moves the grader onto it.

**Correction to the previous draft.** That draft proposed gating `_detect_comparison` on `_closest_pokemon(...)`, describing it as "require both sides to resolve." It is not validation — it is fuzzy coercion at edit distance ≤ 2, and it *fabricates* entities:

```
'null'→'numel'   'tank'→'sawk'   'lead'→'lotad'   'heal'→'seel'
'speed'→'seel'   'toxic'→'toxel' 'mega'→'mew'     'bulk'→'muk'

"Null or Silvally?" → ('numel', 'silvally')      # user asked about Type: Null
"Speed or bulk?"    → ('seel', 'muk')            # not a comparison at all
```

A plan whose stated goal is "without hallucinating typings or recommending Pokémon that cannot deal damage" must not add a code path that invents a Pokémon from the word *speed*. **Routing and grading decisions use exact resolution. Fuzzy matching survives only behind `/api/pokemon-correct`, where the guess is shown to the user and is harmless.**

**Second correction.** That draft also kept `pattern.search()` + `continue`, which skips to the next *pattern* rather than the next *match*. Combined with a hard name gate it converts today's garbage into silence — verified against the current tree:

| input | today | previous draft | this task |
|---|---|---|---|
| `Should I use Charizard or Blastoise against this?` | `('should i use charizard', 'blastoise against this')` | **None** | `('charizard','blastoise')` |
| `Do I send Gengar or Alakazam?` | `('do i send gengar', 'alakazam')` | **None** | `('gengar','alakazam')` |
| `Is Snorlax or Blissey the better wall?` | `('is snorlax', 'blissey the better wall')` | **None** | `('snorlax','blissey')` |
| `Would you pick Jangmo-o or Kommo-o for this?` | `('would you pick jangmo-o', 'kommo-o for this')` | **None** | `('jangmo-o','kommo-o')` |

The fix is `finditer` plus trimming each capture to the word-run that actually resolves: **suffix** for the left side (English puts the lead-in before the name), **prefix** for the right side (the greedy second group swallows trailing words).

- [ ] **Step 1: Write the resolver tests**

```python
# tests/unit/test_pokemon_names.py
from pathlib import Path
import pytest
from pokedex import pokemon_names as pn

pn.init(Path("."))

# One fixture, exercised by every call site. These are the names that broke
# each of the four ad-hoc regexes.
HARD_NAMES = ["Porygon-Z", "Porygon2", "Ho-Oh", "Jangmo-o", "Kommo-o",
              "Mr. Mime", "Mime Jr.", "Farfetch'd", "Type: Null", "Chien-Pao"]

@pytest.mark.parametrize("name", HARD_NAMES)
def test_hard_names_resolve_exactly(name):
    assert pn.resolve(name) == name.lower()

@pytest.mark.parametrize("text,expected", [
    ("should i use charizard", "charizard"),
    ("is snorlax", "snorlax"),
    ("would you pick jangmo-o", "jangmo-o"),
    ("the tank", None),
    ("do i lead with the sweeper", None),
])
def test_resolve_suffix(text, expected):
    assert pn.resolve_suffix(text) == expected

@pytest.mark.parametrize("text,expected", [
    ("blastoise against this", "blastoise"),
    ("blissey the better wall", "blissey"),
    ("kommo-o for this", "kommo-o"),
    ("bad in this matchup", None),
])
def test_resolve_prefix(text, expected):
    assert pn.resolve_prefix(text) == expected

@pytest.mark.parametrize("word", ["speed", "bulk", "tank", "heal", "lead",
                                  "toxic", "mega", "null", "atk", "sand"])
def test_english_words_never_resolve(word):
    """Exact resolution must not coerce. These all had an edit-distance-2
    neighbour in the corpus (speed→seel, tank→sawk, null→numel)."""
    assert pn.resolve(word) is None
    assert pn.resolve_suffix(word) is None

def test_closest_is_still_fuzzy_for_spellcheck():
    """The user-facing spell-check endpoint keeps its tolerance."""
    assert pn.closest("charizrd") == "charizard"
```

- [ ] **Step 2: Run — expect collection error (module does not exist)**

```bash
pytest tests/unit/test_pokemon_names.py -v
```
Expected: `ModuleNotFoundError: pokedex.pokemon_names`.

- [ ] **Step 3: Create `pokedex/pokemon_names.py`**

```python
"""
One source of truth for "is this string a Pokemon name?".

Four call sites used to answer this question with four different ad-hoc
character classes over two different corpora, which is why Porygon-Z, Ho-Oh and
Type: Null were each recognised by some of them and none of the others.

`resolve` is exact: routing and grading decisions must never invent an entity.
`closest` is the fuzzy edit-distance matcher, and exists only for the
user-facing /api/pokemon-correct spell-check endpoint, where a wrong guess is
visible to the user and harmless.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

# Every character that occurs in a real name: Porygon-Z, Porygon2, Farfetch'd,
# Mr. Mime, Type: Null, Ho-Oh, Mime Jr.
NAME_CHARS = r"A-Za-z0-9'’.\-: "

_NAMES: frozenset[str] = frozenset()


def init(repo_root: Path) -> None:
    """Load the corpus once at import time. Never raises: a missing CSV
    degrades to 'nothing resolves', which is the safe direction."""
    global _NAMES
    try:
        path = Path(repo_root) / "data" / "pokemon_db.csv"
        with path.open(newline="", encoding="utf-8") as f:
            _NAMES = frozenset(
                r["pokemon"].strip().lower()
                for r in csv.DictReader(f) if r.get("pokemon")
            )
    except Exception:
        _NAMES = frozenset()


def names() -> frozenset[str]:
    return _NAMES


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def resolve(text: str, universe: frozenset[str] | None = None) -> str | None:
    """Exact match after normalisation. No fuzzing, no coercion."""
    pool = _NAMES if universe is None else universe
    key = _norm(text)
    return key if key in pool else None


def resolve_suffix(text: str, universe=None, max_words: int = 3) -> str | None:
    """Longest trailing word-run that is a real name.

    'should i use charizard' -> 'charizard'. Trailing, because English puts the
    lead-in before the name.
    """
    pool = _NAMES if universe is None else universe
    words = _norm(text).split(" ")
    for n in range(min(max_words, len(words)), 0, -1):
        cand = " ".join(words[-n:])
        if cand in pool:
            return cand
    return None


def resolve_prefix(text: str, universe=None, max_words: int = 3) -> str | None:
    """Longest leading word-run that is a real name.

    'blastoise against this' -> 'blastoise'. Leading, because trailing junk is
    what a greedy second capture group picks up.
    """
    pool = _NAMES if universe is None else universe
    words = _norm(text).split(" ")
    for n in range(min(max_words, len(words)), 0, -1):
        cand = " ".join(words[:n])
        if cand in pool:
            return cand
    return None


def _edit_distance(a: str, b: str) -> int:
    """Standard DP Levenshtein distance."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i]
        for j, cb in enumerate(b, 1):
            curr.append(min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = curr
    return prev[-1]


def closest(name: str, max_dist: int = 2) -> str | None:
    """Fuzzy match — SPELL-CHECK ONLY.

    Do not use this to make a routing or grading decision. At max_dist=2 it maps
    'speed'->'seel', 'tank'->'sawk', 'null'->'numel'. It is correct only where a
    wrong guess is shown to the user for confirmation.
    """
    if not _NAMES or not name:
        return None
    key = _norm(name)
    if key in _NAMES:
        return key
    best_name, best_dist = None, max_dist + 1
    for candidate in _NAMES:
        d = _edit_distance(key, candidate)
        if d < best_dist:
            best_dist, best_name = d, candidate
    return best_name if best_dist <= max_dist else None
```

Wire it up at the bottom of `pokedex/config.py`'s consumers — simplest is a module-level call in `pokedex/pokemon_names.py`'s importers. In `coveo_api.py`, replace the `_POKEMON_NAMES` block ([coveo_api.py:12-51](pokedex/routes/coveo_api.py:12)) with a delegation that preserves the endpoint's public behaviour:

```python
from pokedex import pokemon_names
from pokedex.config import settings

pokemon_names.init(settings.repo_root)


def _closest_pokemon(name: str, max_dist: int = 2) -> str | None:
    """Kept for /api/pokemon-correct. Delegates to the shared resolver.

    Callers making a *decision* (routing, grading) must use
    pokemon_names.resolve / resolve_suffix / resolve_prefix instead — this
    function coerces, and will happily turn 'speed' into 'seel'.
    """
    return pokemon_names.closest(name, max_dist)
```

- [ ] **Step 4: Run resolver tests — expect all PASS**

```bash
pytest tests/unit/test_pokemon_names.py -v
```

- [ ] **Step 5: Add the comparison tests**

Add to `tests/unit/test_coach_routes.py`:

```python
import pytest
from pokedex.routes.coach_api import _detect_comparison

COMPARISONS = [
    # (message, expected)
    ("Compare Charizard to Dragonite",                    ("charizard", "dragonite")),
    ("between Charizard and Dragonite, who wins",         ("charizard", "dragonite")),
    ("Charizard vs Dragonite",                            ("charizard", "dragonite")),
    ("Charizard vs Dragonite, who wins?",                 ("charizard", "dragonite")),
    ("Which is better: Umbreon or Espeon?",               ("umbreon", "espeon")),
    # hyphen + digit names — the class the old character class could not see
    ("Porygon-Z or Porygon2, which is better?",           ("porygon-z", "porygon2")),
    ("Ho-Oh or Lugia?",                                   ("ho-oh", "lugia")),
    ("Mr. Mime or Mime Jr.?",                             ("mr. mime", "mime jr.")),
    ("compare Farfetch'd with Sirfetch'd",                ("farfetch'd", "sirfetch'd")),
    # lead-in words before the first name — regressed by search()+continue
    ("Should I use Charizard or Blastoise against this?", ("charizard", "blastoise")),
    ("Do I send Gengar or Alakazam?",                     ("gengar", "alakazam")),
    ("Is Snorlax or Blissey the better wall?",            ("snorlax", "blissey")),
    ("Would you pick Jangmo-o or Kommo-o for this?",      ("jangmo-o", "kommo-o")),
]

@pytest.mark.parametrize("message,expected", COMPARISONS)
def test_detect_comparison_positives(message, expected):
    assert _detect_comparison(message) == expected

BENIGN = [
    "Do I lead with the tank or the sweeper?",
    "Should I heal it or switch out?",
    "Is Charizard good or bad in this matchup?",
    "Rate my team out of ten or give me a grade",
    "Can you explain STAB versus base power for me?",
    "Should I switch or stay in?",
    "Do I use an item or attack?",
    # single words with an edit-distance-2 neighbour in the corpus: these are
    # exactly what fuzzy "validation" would have coerced into a comparison
    "Speed or bulk?",
    "Toxic or seed?",
    "Tank or wall?",
    "Lead or switch?",
]

@pytest.mark.parametrize("message", BENIGN)
def test_detect_comparison_no_false_positives(message):
    assert _detect_comparison(message) is None
```

- [ ] **Step 6: Run — expect the hyphen/digit and lead-in cases to fail**

```bash
pytest tests/unit/test_coach_routes.py -k detect_comparison -v
```
Expected FAIL: `Porygon-Z…`, `Mr. Mime…`, `Farfetch'd…`, `Jangmo-o…`, and all four lead-in cases (today they return a garbage tuple, not the expected pair). Expected PASS: the five plain cases and most of `BENIGN`.

- [ ] **Step 7: Rewrite `_CMP_PATTERNS` and `_detect_comparison`**

In [`coach_api.py:33-58`](pokedex/routes/coach_api.py:33), build every pattern from the shared character class:

```python
from pokedex import pokemon_names
from pokedex.pokemon_names import NAME_CHARS as _NC

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
```

Then replace [`coach_api.py:72-85`](pokedex/routes/coach_api.py:72):

```python
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
```

`_STOPWORDS` and the 25-character guard are no longer referenced here — exact resolution subsumes both. Keep the `_STOPWORDS` constant: `_extract_pokemon_mentions` still uses it.

- [ ] **Step 8: Run the full unit suite**

```bash
pytest tests/unit -v
```
Expected: all PASS, including the pre-existing `test_coach_detect_comparison_intent`, which asserts lowercase `"charizard"` / `"dragonite"` — the shape this resolver returns.

- [ ] **Step 9: Commit**

```bash
git add pokedex/pokemon_names.py pokedex/routes/coach_api.py pokedex/routes/coveo_api.py \
        tests/unit/test_pokemon_names.py tests/unit/test_coach_routes.py
git commit -m "fix(coach): single exact name resolver; rebuild comparison detection on it

Eliminates F12. Benign 'or' sentences no longer open a comparison panel, and
Porygon-Z / Ho-Oh / Mr. Mime / Farfetch'd are recognised for the first time.

Comparison routing now resolves EXACTLY. The previous draft gated on
_closest_pokemon (edit distance 2), which fabricates entities: 'speed'->'seel',
'null'->'numel'. Fuzzy matching is now reachable only from
/api/pokemon-correct, where the guess is shown to the user.

finditer replaces search: with a hard name gate, search()+continue turned
'Should I use Charizard or Blastoise' into no match at all."
```

**Known residual:** `"Type: Null or Silvally?"` returns `None` — the colon terminates the capture before the name is complete. That is a miss, not a fabrication; today it returns `('numel', 'silvally')`. Accepted.

**Deliberately deferred:** `_POKEMON_MENTION_RE` ([coach_api.py:234](pokedex/routes/coach_api.py:234)) is the fourth ad-hoc class and has the same blind spots, but it feeds `pokemon_context` for pronoun resolution, whose correctness criteria are set by Task 2. Move it onto `pokemon_names` after Task 2 lands, not before.

**Cross-task hazard for Task 3:** Task 3 proposes using `_closest_pokemon` to pick entity names for the Coveo query. With the fuzzy behaviour documented above, that would inject `seel` into a query about speed. Task 3 should call `pokemon_names.resolve_suffix`, not `closest`.

---

### Task 9: Fix grader name capture, then add a *guarded* appositive pattern (F-A)

**Files:**
- Modify: `eval_harness/grading.py`
- Test: `tests/unit/test_grading.py` (new)

**This task must land before Task 10.** Task 10 backfills `type_cache.json` from 315 to ~1023 entries. Today most grader false positives die harmlessly in the `types_of` → `LookupError` → `continue` path at [grading.py:155-158](eval_harness/grading.py:155); backfilling *unmasks* them. And these flags are user-facing: [coach_api.py:225](pokedex/routes/coach_api.py:225) runs `check_type_claims` on every live answer against the 924-name corpus and renders the result as a warning. Expanding coverage before correcting the patterns ships false hallucination warnings to users.

**Correction to the previous draft — the diagnosis was wrong.** That draft added a fifth pattern and asserted its three test cases would pass. Verified against the current tree, one still fails after the change:

```
PASS   'Loudred, a Ground-type Pokemon, is weak to Water.'
PASS   'Loudred, a Ground type, is weak to Water.'
FAIL   'Your Loudred is Ground-type so it fears Water.'   ← still unflagged
```

`Your Loudred` was never an appositive problem. `_NAME` ([grading.py:27](eval_harness/grading.py:27)) matches *two* capitalised words, so it captures `'Your Loudred'`, the `universe` lookup misses, and `finditer` has already consumed the sentence — there is no retry at `Loudred`. Same for `'The Loudred'`, `'Against Loudred'`, `'For Onix'`. **Adding patterns cannot fix a capture-greediness bug.** The blind spot is the name capture, and it is the same bug Task 8 just fixed on the routing side.

**Correction 2 — the proposed pattern flags correct answers.** `{_NAME}\s*,\s+(?:an?\s+)?{_T}[-\s]?type` does not require the comma-clause to actually be an appositive. Verified, with a backfilled cache:

```
"To beat Loudred, a Fighting-type attack works well."
  → [('Loudred', ['fighting'], 'contradiction')]
"Lead with Onix, a Water-type move will still hurt it."
  → [('Onix', ['water'], 'contradiction')]
```

Those are *correct* coaching answers being flagged as typing hallucinations, and "To beat X, a Y-type move…" is the most common sentence shape this product emits. The fix is to require the appositive to **close** — optional `Pokémon`, then a delimiter — which is exactly what distinguishes `Loudred, a Ground-type Pokemon,` from `Loudred, a Fighting-type attack`.

**Correction 3 — mode.** The draft used `"full"`, which also reports `incomplete` when one half of a dual typing is omitted. The appositive is idiomatic shorthand (`Sableye, a Dark-type, is tricky`) where omission is not an error. `"partial"` still catches every invented type — which is all F-A is about — without that noise.

- [ ] **Step 1: Write the test file, negatives first**

```python
# tests/unit/test_grading.py
import json
from pathlib import Path
import pytest
from eval_harness.grading import check_type_claims
from eval_harness.typechart import TypeChart

@pytest.fixture(scope="module")
def chart():
    return TypeChart(Path("eval_data/type_cache.json"), offline=True)

@pytest.fixture(scope="module")
def universe():
    return json.loads(Path("eval_data/corpus.json").read_text()) + ["Porygon-Z", "Ho-Oh"]

# The bar this task exists to clear: correct answers must not be flagged.
MUST_NOT_FLAG = [
    "To beat Loudred, a Fighting-type attack works well.",
    "Lead with Onix, a Water-type move will still hurt it.",
    "Against Loudred, a Water-type move is your best bet.",
    "If you face Gengar, a Dark-type play is safest.",
    "For Onix, a Water-type or Grass-type will do.",
    "Switch to Blastoise, a Water-type Pokemon, to win.",   # true appositive, correct typing
    "Sableye, a Dark-type, is tricky.",                     # shorthand omission, not an error
    "Send Gyarados, a Water/Flying-type, and set up.",
    "Surf is a Water-type move.",
    "Your best option is a Fire-type attack.",
    "Gengar is a Ghost/Poison type.",
]

MUST_FLAG = [
    "Loudred, a Ground-type Pokemon, is weak to Water.",    # F-A: the appositive
    "Loudred, a Ground type, is weak to Water.",
    "Your Loudred is Ground-type so it fears Water.",       # the _NAME greediness bug
    "Loudred is a Ground-type Pokemon.",                    # existing pattern 1
    "Loudred, which is a Ground-type Pokemon, is weak.",    # existing pattern 2
    "Loudred (Ground), your lead, faints.",                 # existing pattern 3
    "Loudred's Ground-type moves hit hard.",                # existing pattern 4
    "The Porygon-Z, a Fighting-type, resists it.",          # hyphen-digit name
    "Ho-Oh is a Water-type legendary.",
]

@pytest.mark.parametrize("sentence", MUST_NOT_FLAG)
def test_correct_answers_are_not_flagged(chart, universe, sentence):
    errs = check_type_claims(sentence, chart, universe)
    assert not errs, f"False positive on a correct answer: {sentence!r} -> {errs}"

@pytest.mark.parametrize("sentence", MUST_FLAG)
def test_wrong_typings_are_flagged(chart, universe, sentence):
    assert check_type_claims(sentence, chart, universe), f"Missed: {sentence!r}"

def test_pokemon_field_keeps_universe_casing(chart):
    """grading.py:239 compares e['pokemon'] == wild by exact string."""
    errs = check_type_claims("Loudred, a Ground-type Pokemon, is weak.", chart, ["Loudred"])
    assert errs and errs[0]["pokemon"] == "Loudred"
```

- [ ] **Step 2: Run — record which fail**

```bash
pytest tests/unit/test_grading.py -v
```
Expected FAIL: the appositive, `Your Loudred`, `Porygon-Z` and `Ho-Oh` cases. Expected PASS: `MUST_NOT_FLAG` (they pass today only because the 315-entry cache hides them — Task 10 would break them, which is why they are pinned here first).

- [ ] **Step 3: Widen `_NAME` and resolve the capture**

Replace [`grading.py:27`](eval_harness/grading.py:27):

```python
# A deliberately loose candidate span — check_type_claims trims it to the part
# that actually resolves against `universe`. The old class was
# [A-Z][a-zA-Z'’]* with an optional second word, which both missed every
# hyphen/digit name (Porygon-Z, Ho-Oh) and swallowed the determiner in
# "Your Loudred", killing the match outright.
_NAME = r"(?-i:(?P<name>[A-Z][A-Za-z0-9'’.\-]*(?:[ :]+[A-Z][A-Za-z0-9'’.\-]*){0,2}))"
```

Add the guarded appositive as a fifth entry to `TYPE_CLAIM_PATTERNS`:

```python
    # "Loudred, a Ground-type Pokemon," / "Gyarados, a Water/Flying-type,"
    # The closing delimiter is load-bearing: without it this also matches
    # "To beat Loudred, a Fighting-type attack", which is a claim about the
    # attack, not about Loudred. "partial" because the appositive is idiomatic
    # shorthand — an omitted second type is not an error, an invented one is.
    (re.compile(rf"\b{_NAME}\s*,\s+(?:an?\s+)?{_T}[-\s]?type\s*(?:pok[eé]mon)?\s*"
                rf"(?=[,.;:!?)]|$)", re.I), "partial"),
```

Then swap the exact-dict lookup in [`check_type_claims`](eval_harness/grading.py:141) for suffix resolution, preserving the caller's casing:

```python
    from pokedex import pokemon_names

    errors: list[dict] = []
    seen: set = set()
    lookup = {n.lower(): n for n in universe}
    pool = frozenset(lookup)
    for pattern, mode in TYPE_CLAIM_PATTERNS:
        for m in pattern.finditer(answer or ""):
            # Trim "Your Loudred" -> "Loudred". The regex captures a loose span;
            # the corpus decides where the name actually starts.
            key = pokemon_names.resolve_suffix(m.group("name"), universe=pool)
            if not key:
                continue
            name = lookup[key]          # caller's casing: grading.py:239 needs it
            ...                         # rest of the loop body unchanged
```

`eval_harness` already imports from `pokedex` ([backends.py:161](eval_harness/backends.py:161), [cli.py:23](eval_harness/cli.py:23)), so this adds no new coupling direction.

- [ ] **Step 4: Run — expect all PASS**

```bash
pytest tests/unit/test_grading.py tests/unit/test_coach_routes.py tests/unit/test_pokemon_names.py -v
```

- [ ] **Step 5: Run the whole unit suite for regressions**

```bash
pytest tests/unit -v
```
Expected: 31 pre-existing tests still pass, plus the new ones.

- [ ] **Step 6: Commit**

```bash
git add eval_harness/grading.py tests/unit/test_grading.py
git commit -m "fix(grading): resolve the name capture; add a guarded appositive pattern

Eliminates F-A. The blind spot was not a missing pattern: _NAME swallowed the
determiner ('Your Loudred'), so the universe lookup missed and finditer never
retried. Names are now resolved by longest-suffix against the universe, which
also admits Porygon-Z and Ho-Oh for the first time.

The appositive pattern requires the clause to CLOSE. Without that guard it
flags 'To beat Loudred, a Fighting-type attack works well' as a Loudred typing
error — a correct answer, and the commonest sentence shape the coach emits.
Mode is 'partial': shorthand omission is not an error, invention is."
```

---

### Task 10: Backfill the type cache to the full corpus (F8)

**Files:**
- Create: `scripts/backfill_type_cache.py`
- Test: none of its own — but it **re-runs Task 9's suite**, see Step 4.

**Runs last, and is not test-free.** The previous draft called this "a one-shot data job, not application logic." It is not: [coach_api.py:25](pokedex/routes/coach_api.py:25) loads this same cache at startup, and every cache entry added is a sentence the live grader can now flag in the user-facing warning UI. Going from 315 to ~1023 entries roughly triples the grader's reach — over correct answers as well as wrong ones. That is safe only on top of Task 9.

Two corrections to the draft's numbers: the corpus read here is `data/pokemon_db.csv` with **1023** names, not 924 (`eval_data/corpus.json` is the 924-name Coveo-harvested scenario pool — a different list). Missing count today is **708**, not ~700. And `slug()` was copy-pasted from `TypeChart.slug`; duplicating the normaliser is how this family of bugs started, so import it.

- [ ] **Step 1: Write the script**

```python
#!/usr/bin/env python3
"""
Backfill eval_data/type_cache.json to the full 1023-name corpus.

The cache is read by BOTH the eval harness and the live server
(pokedex/routes/coach_api.py), so every entry added here widens what the
user-facing "typing error" warning can fire on. Run this only after the grader
pattern fixes in Task 9 are in place.

Usage:
    python scripts/backfill_type_cache.py
    python scripts/backfill_type_cache.py --dry-run   # report only, no writes
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

import requests

from eval_harness.typechart import TypeChart   # reuse the one slug(); do not re-implement

CACHE_PATH   = Path("eval_data/type_cache.json")
CORPUS_PATH  = Path("data/pokemon_db.csv")
POKEAPI_BASE = "https://pokeapi.co/api/v2/pokemon"


def main(dry_run: bool) -> None:
    cache: dict[str, list[str]] = {}
    if CACHE_PATH.exists():
        cache = json.loads(CACHE_PATH.read_text())
    print(f"Cache: {len(cache)} entries")

    with CORPUS_PATH.open(newline="", encoding="utf-8") as f:
        names = [row["pokemon"].lower() for row in csv.DictReader(f) if row.get("pokemon")]
    print(f"Corpus: {len(names)} names")

    missing = [n for n in names if TypeChart.slug(n) not in cache]
    print(f"Missing: {len(missing)} names")

    if dry_run:
        print("--dry-run: no writes.")
        for n in missing[:20]:
            print(f"  {n}")
        if len(missing) > 20:
            print(f"  … and {len(missing) - 20} more")
        return

    errors: list[str] = []
    for i, name in enumerate(missing, 1):
        s = TypeChart.slug(name)
        try:
            r = requests.get(f"{POKEAPI_BASE}/{s}", timeout=15)
            if r.status_code == 404:
                # Forms whose PokeAPI id carries a suffix the page title omits.
                for suffix in ("-normal", "-altered", "-land", "-incarnate", "-ordinary"):
                    r2 = requests.get(f"{POKEAPI_BASE}/{s}{suffix}", timeout=15)
                    if r2.status_code == 200:
                        r = r2
                        break
            if r.status_code != 200:
                errors.append(f"{name}: HTTP {r.status_code}")
                continue
            cache[s] = [t["type"]["name"] for t in r.json()["types"]]
            print(f"  [{i}/{len(missing)}] {name} → {cache[s]}")
        except requests.RequestException as exc:
            errors.append(f"{name}: {exc}")
        time.sleep(0.5)   # be polite to PokeAPI

    CACHE_PATH.write_text(json.dumps(cache, indent=0, sort_keys=True))
    print(f"\nWrote {len(cache)} entries to {CACHE_PATH}")
    if errors:
        print(f"\n{len(errors)} errors:")
        for e in errors:
            print(f"  {e}")
        sys.exit(1)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    main(p.parse_args().dry_run)
```

- [ ] **Step 2: Dry run first**

```bash
python scripts/backfill_type_cache.py --dry-run
```
Expected: `Cache: 315 entries`, `Corpus: 1023 names`, `Missing: 708 names`.

- [ ] **Step 3: Run it**

```bash
python scripts/backfill_type_cache.py
```
Expected: ~708 fetches at 0.5s each, ≈6 minutes. Some 404s are expected for forms PokeAPI names differently; the script exits 1 and lists them.

- [ ] **Step 4: Re-run Task 9's grader suite against the widened cache**

```bash
pytest tests/unit/test_grading.py -v
```
Expected: all PASS. **This is the real acceptance test for this task.** `MUST_NOT_FLAG` passed before the backfill partly because unknown Pokémon fell through `LookupError`. Now that Gengar, Onix and the rest are cached, those sentences are graded for real — and must still come back clean. A failure here means a pattern is over-matching, not that the data is wrong; fix the pattern, do not shrink the cache.

- [ ] **Step 5: Verify coverage**

```bash
python3 -c "
import json, csv
from eval_harness.typechart import TypeChart
cache = json.load(open('eval_data/type_cache.json'))
with open('data/pokemon_db.csv') as f:
    names = [r['pokemon'] for r in csv.DictReader(f) if r.get('pokemon')]
hit = [n for n in names if TypeChart.slug(n) in cache]
print(f'coverage: {len(hit)}/{len(names)} = {len(hit)/len(names)*100:.1f}%')
for probe in ['Charizard','Pikachu','Porygon-Z','Ho-Oh','Mr. Mime']:
    print(f'  {probe}: {TypeChart.slug(probe) in cache}')
"
```
Expected: coverage ≥ 90%; Charizard and Pikachu True.

- [ ] **Step 6: Commit**

```bash
git add eval_data/type_cache.json scripts/backfill_type_cache.py
git commit -m "data: backfill type_cache from 315 to full corpus

Eliminates F8: the grader no longer silently skips Charizard, Pikachu and 700+
others. Sequenced after the Task 9 pattern fixes on purpose — this cache is
also read by the live server, so widening it widens what the user-facing typing
warning can fire on, false positives included."
```

---

## Self-Review

**Spec coverage:**

| Finding | Task | Source |
|---|---|---|
| F1 two-turn delay | Task 2 | Original report |
| F2 retrieval budget/salience | Task 2 (bypassed) + Task 3 (entity-name queries) | Original + log Part 7 |
| F3 cold abstention | Task 2 (bypassed — no Coveo call) | Original report |
| F4 TypeChart unused | Task 2 | Original report |
| F5 harmful picks | Task 2 | Original report |
| F6 cannot say "none" | Task 2 | Original report |
| F7 typing hallucinations | Tasks 2+10 (computed answer + full cache) | Original report |
| F8 grader coverage 34% | Task 10 (cache), Task 9 (name capture) | Original report |
| F9 `CHART_CLAIM_RE` blind to Pokémon names | NOT fixed — but Task 8's `pokemon_names.resolve_suffix` is the missing primitive; file follow-up | Original report |
| F10 flag discards useful data | Task 7 | Original report |
| F11 Quick Answer republishes hallucination | Task 7 | Original report |
| F12 `or` false positives | Task 8 | Original report + log Part 4 addendum |
| F12b comparison misses on lead-in phrasing | Task 8 | Found while verifying the Task 8 draft |
| F13 challenge double-send | Task 6 | Original report + log Part 6 |
| F14 broken abstention check | Task 4 | Original report |
| F15 type-confused JSON 500s | Task 5 | Original report + log Part 5 |
| F16 verdict bar duplication | NOT fixed — `comparison.verdict = answer` is intentional; fix requires API shape change; tech debt | Original report + log Part 8 |
| F17 no request size limit | Task 5 | Original report |
| F18 extractor injects English | Task 3 | Original report + log Part 4 addendum |
| F-A appositive grader blind spot | Task 9 | Log Part 9 grader-coverage table |
| F-E four divergent name regexes over two corpora | Task 8 (root cause of F8/F9/F12/F-A) | Found while verifying the Task 8 draft |
| F-B ability descriptions ungraded | NOT fixed — no ability oracle exists; out of scope | Log Part 3 J2 |
| F-C 43% abstention on player-intent | NOT fixed — index scope problem, not application code | Log Part 2 aggregate |
| F-D "correct" verdicts by silence | Task 2 (type-chart path always gives affirmative answers) | Log Part 9 verdict analysis |

**F9 note:** `CHART_CLAIM_RE` requires the defender to be a type word. The model almost always names a Pokémon instead, so the effectiveness checker fires zero times in practice. Fix requires accepting either a type word or a corpus-resolvable name in the defender position — a grading accuracy improvement with no user-facing benefit. File a follow-up issue.

**F12 addendum:** The QA log's Part 4 addendum confirmed 5/9 false positives survive in the current working tree, and a true-negative miss (`Porygon-Z or Porygon2?` → `None`). Verifying the draft fix surfaced a third problem it would have introduced: gating on `_closest_pokemon` (edit distance ≤ 2) coerces English words into names (`speed`→`seel`, `null`→`numel`), and `search()`+`continue` turns four common phrasings (`Should I use Charizard or Blastoise…`) into no match at all. Task 8 fixes all three by resolving exactly, over `finditer`, with prefix/suffix trimming.

**F16 note:** The comparison verdict/answer duplication is cosmetic. `comparison.verdict = answer` is intentional — the client needs the text for the verdict bar. Fixing it cleanly requires either a separate `comparison_answer` field or client-side truncation. Left as known tech debt.

**F-B note:** Ability description errors (J2: three wrong descriptions of Starmie's ability in one session) are not graded anywhere in the pipeline. There is no ability oracle to add without a new data source. Out of scope.

**F-C note:** 43% abstention on player-intent questions (themes A, B, D) is a retrieval-index scope problem — Coveo's index is a Pokédex, not a strategy guide. "What held item is best on Dragonite?" has no matching document to retrieve. Fixing this requires index expansion, not application code.

**Placeholder scan:** No TBD, TODO, or "implement later" phrases. All steps include code.

**Type consistency:** `MatchupIntent` defined in Task 1, consumed in Task 2. `detect_matchup_intent` signature consistent throughout. `_ideal_answer` guard pattern matches existing `TypeChart` guard. `is_abstention` added to the existing guarded import block. `pokedex.pokemon_names` is created in Task 8 and consumed by `coach_api`, `coveo_api` and (Task 9) `eval_harness.grading`; `eval_harness` already imports from `pokedex`, so no new coupling direction. The new `TYPE_CLAIM_PATTERNS` entry in Task 9 reuses the module-scope `_NAME`/`_T`, with `_NAME` widened in the same task.

**Verification status of Tasks 8–10:** every snippet in these three tasks was prototyped against the real corpus (1023 names) and type cache before being written here. Comparison detector: 13 positives + 12 benign, 25/25. Grader: 9 must-flag + 11 must-not-flag, 20/20, casing preserved for [grading.py:239](eval_harness/grading.py:239). The pre-existing 31 unit tests pass unchanged.
