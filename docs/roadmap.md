# Roadmap

Work that is deliberately deferred, with enough context to pick it up cold.
Defects belong in `docs/known-issues.md`; this file is for things that were
scoped out, not things that are broken.

---

## RM-001: Location facts from `## Where to find`

**Deferred from:** `docs/plans/2026-08-31-passage-retrieval-coach.md` (v1 of the
Coach facts pipeline), 2026-08-31, by request.

**What it is:** PokémonDB pages carry a `## Where to find <name>` section — a
per-game pipe table of encounter locations, the same shape as the
`## Pokédex entries` table that v1 already parses. It reaches us through the
passage retrieval path for free; it is present in the merged chunks and simply
is not read.

**Work required:**

1. `facts.py` — add a `locations: list[tuple[str, str]]` field to
   `PokemonFacts` and parse the section with the existing table parser. This is
   the small half; the section is structurally identical to `entries`.
2. `facts.py` — a `render_answer` branch for the topic. Non-trivial: the table
   is long (one row per game), so the prose needs a rule for which games to
   name rather than listing twenty.
3. `fact_intent.py` — a `locations` topic pattern.

**The catch that made it not-v1:** the intent pattern has to not collide with
the dashboard's existing encounter-map feature, which already answers "where
does X live" from PokéAPI browser-side. Two different subsystems answering the
same question from two different sources is a divergence bug waiting to happen.
Decide first which one owns the question; then implement.
