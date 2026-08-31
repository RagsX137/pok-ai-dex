# Coach Robustness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the coach answer the question it was built to answer — reliably, correctly, without hallucinating typings or recommending Pokémon that cannot deal damage.

**Architecture:** Three sequential projects, each independently shippable. Project 1 routes matchup questions through `TypeChart.ground_truth()` instead of the LLM; the LLM's only remaining job is phrasing a pre-computed answer. Project 2 fixes retrieval query shape so entity names — not transcript fragments — drive Coveo. Project 3 patches hygiene bugs (double-send, broken abstention check, type-confused JSON crashes, grading flag UI, cache coverage).

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

**Eliminates: F1, F2, F3, F5, F6** (the five findings about wrong/late/fabricated answers).

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

**Eliminates: F18** (extractor injects English words into Coveo query), **F2 partially** (retrieval budget), **F3 partially** (cold query shape).

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

Five independent, low-risk patches. Each can be committed separately.

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
- Modify: `frontend/coach.js`
- Test: manual (no server state to unit-test here; the fix is a one-line client change)

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

### Task 8: Fix the `or` comparison false positives (F12)

**Files:**
- Modify: `pokedex/routes/coach_api.py`
- Test: `tests/unit/test_coach_routes.py`

The `or` pattern in `_CMP_PATTERNS[3]` has no name validation. The fix: require both captured sides to resolve against the Pokémon corpus before accepting a comparison match. This is a one-function change to `_detect_comparison`.

- [ ] **Step 1: Add failing tests**

Add to `tests/unit/test_coach_routes.py`:

```python
def test_detect_comparison_no_false_positives():
    from pokedex.routes.coach_api import _detect_comparison
    benign = [
        "Do I lead with the tank or the sweeper?",
        "Should I heal it or switch out?",
        "Is Charizard good or bad in this matchup?",
        "Rate my team out of ten or give me a grade",
    ]
    for msg in benign:
        result = _detect_comparison(msg)
        assert result is None, f"False positive on: {msg!r} → {result}"

def test_detect_comparison_real_pokemon_or():
    from pokedex.routes.coach_api import _detect_comparison
    result = _detect_comparison("Porygon or Porygon2, which is better?")
    # Both are real Pokémon — this should match.
    assert result is not None
    assert "porygon" in result[0]
```

- [ ] **Step 2: Run tests to confirm first test fails**

```bash
pytest tests/unit/test_coach_routes.py::test_detect_comparison_no_false_positives \
       tests/unit/test_coach_routes.py::test_detect_comparison_real_pokemon_or -v
```
Expected: `test_detect_comparison_no_false_positives` FAILS.

- [ ] **Step 3: Add corpus validation to `_detect_comparison`**

Replace [`coach_api.py:72-85`](pokedex/routes/coach_api.py:72):

```python
def _detect_comparison(message: str) -> tuple[str, str] | None:
    """Return (pokemon_a, pokemon_b) if the message is a comparison request.

    Both sides must resolve to a known Pokémon name via _closest_pokemon — this
    prevents benign sentences containing 'or' from being treated as comparisons.
    """
    from pokedex.routes.coveo_api import _closest_pokemon
    for pattern in _CMP_PATTERNS:
        m = pattern.search(message)
        if m:
            a = m.group(1).strip().lower()
            b = m.group(2).strip().lower()
            if a in _STOPWORDS or b in _STOPWORDS:
                continue
            if len(a) > 25 or len(b) > 25:
                continue
            # Require both sides to be resolvable Pokémon names.
            ra = _closest_pokemon(a, max_dist=2)
            rb = _closest_pokemon(b, max_dist=2)
            if ra and rb:
                return ra, rb
    return None
```

- [ ] **Step 4: Run all tests**

```bash
pytest tests/unit/test_coach_routes.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add pokedex/routes/coach_api.py tests/unit/test_coach_routes.py
git commit -m "fix(coach): require corpus validation for both sides of 'or' comparison

Eliminates F12: 'heal it or switch out' no longer triggers comparison cards."
```

---

### Task 9: Backfill type cache to full corpus (F8)

**Files:**
- Create: `scripts/backfill_type_cache.py`
- No test needed — the script is a one-shot data job, not application logic.

This script fetches PokeAPI typings for every name in `data/pokemon_db.csv` that is not already in `eval_data/type_cache.json`, writing them into the cache. It respects offline mode by never touching the cache if run with `--dry-run`. Run it once; commit the updated `eval_data/type_cache.json`.

- [ ] **Step 1: Write the script**

```python
#!/usr/bin/env python3
"""
Backfill eval_data/type_cache.json to the full 924-name corpus.

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

CACHE_PATH   = Path("eval_data/type_cache.json")
CORPUS_PATH  = Path("data/pokemon_db.csv")
POKEAPI_BASE = "https://pokeapi.co/api/v2/pokemon"


def slug(name: str) -> str:
    import re
    s = name.lower().strip()
    s = s.replace("\u2640", "-f").replace("\u2642", "-m")
    s = re.sub(r"[.'\u2019:]", "", s)
    s = re.sub(r"[\s_]+", "-", s)
    return s


def main(dry_run: bool) -> None:
    cache: dict[str, list[str]] = {}
    if CACHE_PATH.exists():
        cache = json.loads(CACHE_PATH.read_text())
    print(f"Cache: {len(cache)} entries")

    names: list[str] = []
    with CORPUS_PATH.open(newline="", encoding="utf-8") as f:
        names = [row["pokemon"].lower() for row in csv.DictReader(f) if row.get("pokemon")]
    print(f"Corpus: {len(names)} names")

    missing = [n for n in names if slug(n) not in cache]
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
        s = slug(name)
        try:
            r = requests.get(f"{POKEAPI_BASE}/{s}", timeout=15)
            if r.status_code == 404:
                # Try common variant suffixes before giving up.
                for suffix in ("-normal", "-altered", "-land", "-incarnate", "-ordinary"):
                    r2 = requests.get(f"{POKEAPI_BASE}/{s}{suffix}", timeout=15)
                    if r2.status_code == 200:
                        r = r2
                        break
            if r.status_code != 200:
                errors.append(f"{name}: HTTP {r.status_code}")
                continue
            types = [t["type"]["name"] for t in r.json()["types"]]
            cache[s] = types
            print(f"  [{i}/{len(missing)}] {name} → {types}")
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
    args = p.parse_args()
    main(args.dry_run)
```

- [ ] **Step 2: Run it**

```bash
python scripts/backfill_type_cache.py
```
Expected: fetches ~700 entries, prints each, writes updated cache. Takes ~6 minutes at 0.5s/request.

- [ ] **Step 3: Verify coverage**

```bash
python3 -c "
import json, csv
cache = json.loads(open('eval_data/type_cache.json').read())
with open('data/pokemon_db.csv') as f:
    names = [row['pokemon'].lower() for row in csv.DictReader(f) if row.get('pokemon')]
print(f'coverage: {len(cache)}/{len(names)} = {len(cache)/len(names)*100:.1f}%')
print('charizard cached:', 'charizard' in cache)
print('pikachu cached:', 'pikachu' in cache)
"
```
Expected: coverage ≥ 90%, charizard and pikachu both True.

- [ ] **Step 4: Commit**

```bash
git add eval_data/type_cache.json scripts/backfill_type_cache.py
git commit -m "data: backfill type_cache to full corpus (~924 entries)

Eliminates F8: grader no longer silently skips Charizard, Pikachu, and 600+ others."
```

---

## Self-Review

**Spec coverage:**

| Finding | Task |
|---|---|
| F1 two-turn delay | Task 2 |
| F2 5-doc budget | Task 2 (bypassed for matchup questions) |
| F3 cold abstention | Task 2 (bypassed — no Coveo call) |
| F4 TypeChart unused | Task 2 |
| F5 harmful picks | Task 2 |
| F6 cannot say "none" | Task 2 |
| F7 typing hallucinations | Tasks 2+9 (computed answer + full cache) |
| F8 34% grader coverage | Task 9 |
| F9 CHART_CLAIM_RE blind to Pokémon names | NOT fixed — requires a grading regex rewrite; filed as known limitation |
| F10 flag discards useful data | Task 7 |
| F11 Quick Answer republishes hallucination | Task 7 |
| F12 `or` false positives | Task 8 |
| F13 challenge double-send | Task 6 |
| F14 broken abstention check | Task 4 |
| F15 type-confused JSON 500s | Task 5 |
| F16 verdict bar duplication | NOT fixed — low leverage; the comparison.verdict field would need decoupling from the answer; left as tech debt |
| F17 no request size limit | Task 5 |
| F18 extractor injects English | Task 3 |

**F9 note:** Fixing `CHART_CLAIM_RE` to match Pokémon names in the defender position requires rewriting the effectiveness claim regex to accept either a type word or a corpus-resolvable name. That is a grading-quality improvement, not a user-facing correctness fix, and is out of scope for this plan. File a follow-up issue.

**F16 note:** The comparison verdict/answer duplication is cosmetic. The comparison block is assembled after the answer is set, and `comparison.verdict = answer` is intentional (the client needs it for the verdict bar). Fixing it requires either a separate `comparison_answer` field or client-side truncation. Left as known tech debt.

**Placeholder scan:** No TBD, TODO, or "implement later" phrases. All steps include code.

**Type consistency:** `MatchupIntent` defined in Task 1, consumed in Task 2. `detect_matchup_intent` signature consistent throughout. `_ideal_answer` guard added in Task 3 uses same pattern as `TypeChart` guard. `is_abstention` import added to the existing guarded block.
