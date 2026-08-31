# Passage retrieval → Coach facts

**Status:** implemented
**Date:** 2026-08-31

Integrate the Coveo Passage Retrieval API (CPR) into Coach as a third answer
source, and use it to surface the PokémonDB page content the app currently
throws away.

---

## Why

`data/pokemon_db.csv` holds 16 numeric columns. The Coveo index holds the
*full scraped PokémonDB page* for each Pokémon. Everything below is already
indexed and retrievable, and none of it reaches the user today:

| Section | Content | In CSV? |
|---|---|---|
| `## Pokédex data` | abilities, incl. hidden ability | no |
| `## Training` | EV yield, catch rate, base exp, growth rate | no |
| `## Breeding` | egg groups, egg cycles | no |
| `## Evolution chart` | full line with levels/conditions | no |
| `## Pokédex entries` | flavour text per game | no |
| `## Moves learned` | level-up / TM / egg moves | no |
| `## Base stats`, `## Type defenses` | — | already covered |

So this is not a re-scrape. It is a parser over text the index already serves.

## Probe findings (2026-08-31)

Measured against the live org before any code was written:

1. **The passages endpoint rejects the app's own searchHub.** The API key is
   bound to `AdminConsole`; `settings.coveo_search_hub` is `PokedexUI`. Sending
   the latter is a hard `400 INVALID_PARAMETER`. Passage calls need their own
   configured hub.
2. **The split test is gone.** `splitTest: null` on every probe; 10/10 passage
   calls returned 200. The intermittent `422 UNPROCESSABLE_ENTITY` that
   `scripts/probe_passage_retrieval.py` documents no longer reproduces. It is
   still treated as possible — any non-200 means "no facts".
3. **"Passages" are page-thirds, not sentences.** Each item is 11–15 KB of
   markdown and `maxPassages: 5` returned the same Bulbasaur document three
   times. Raw passages are unusable as LLM context; sliced sections are ~300
   chars and exactly on point.
4. **A name-only query covers every section.** Querying just the name with
   `maxPassages: 10`, keeping items whose title matches, and merging their text
   yielded all six v1 sections for Bulbasaur, Gengar, Pikachu, Dragonite,
   Mimikyu, Tyranitar, Ho-oh and Farfetch'd — 8/8, awkward names included.
5. **Title matching requires accent folding.** Headings and titles use
   `Pokédex`. Matching on `pokedex` silently misses everything.

## Design

### Pipeline

```
[1] type-chart fast path      unchanged — "what is X weak to" stays deterministic
[2] fact intent  ← NEW        abilities / evolution / training / breeding /
                              entries / moves
[3] CRGA                      unchanged — everything else, plus any [2] miss
```

Branch 2 is best-effort in the same style as the optional `eval_harness`
import: any exception, missing section, or non-200 falls through to CRGA.
Coach never gets worse than it is today.

### Modules

| Unit | Job | Depends on |
|---|---|---|
| `pokedex/config.py` *(edit)* | `coveo_passage_hub` | — |
| `pokedex/coveo.py` *(edit)* | `retrieve_passages(..., clean=False)` | requests |
| `pokedex/facts.py` *(new)* | **Pure.** markdown → `PokemonFacts`; `render_answer` | nothing |
| `pokedex/facts_store.py` *(new)* | file → LRU → live resolution | coveo, facts |
| `pokedex/fact_intent.py` *(new)* | message → `FactIntent(pokemon, topic)` | pokemon_names |

`facts.py` imports nothing from the project. Parsing and rendering are testable
against a checked-in fixture with no server and no network, which is what
`make test-unit` guarantees.

### Answers are rendered, not generated

`render_answer` templates prose off the `PokemonFacts` dataclass, the way
`eval_harness/reference.py::ideal_answer` renders off the type chart. Abilities
and egg groups are facts; routing them through a model to be restated adds a
hallucination surface and another thing for `_grade_answer` to catch.

Citations need a URL and passages return only `title` + `primaryid`, so
`pokemon_names` gains `url_for()` — it already reads the CSV that has the `url`
column. One extra dict, no new file read, no second corpus.

### Persistence

`FactsStore.get(name)` tries `data/pokemon_facts.json` if present, then a
bounded LRU (512, same shape as `conversation.py`), then one live passage call
which it caches. `scripts/ingest/build_facts.py` + `make facts` materialises
the file, throttled to the documented 5 calls/sec org cap. The file is optional
in exactly the way `eval_data/*.json` is.

## Risks

- **Hub binding.** Rotating the key with a different binding 400s every passage
  call. Degrades to CRGA; Coach keeps working.
- **Section miss.** Retrieval is query-driven and cannot address a document by
  id. Measured 8/8 above, but `render_answer` returns `None` on a missing
  section rather than guessing, so a miss falls to CRGA.
- **Rate limit.** 5 calls/sec per org. Runtime is one call per uncached
  Pokémon; the builder throttles.

## Tasks

- [x] `config.py`: `coveo_passage_hub` (no `facts_path` — FactsStore takes the path directly, so config gained only the setting the client needs)
- [x] `coveo.py`: reused the concurrently-landed `retrieve_passages`, adding `clean=False` rather than a second method
- [x] `tests/fixtures/bulbasaur_passage.md` (real captured passage)
- [x] `facts.py` + `test_facts.py`
- [x] `fact_intent.py` + `test_fact_intent.py`
- [x] `facts_store.py` + `test_facts_store.py`
- [x] `pokemon_names.url_for` + test
- [x] `coach_api.py` branch 2 + `test_coach_routes.py` extension
- [x] `test_passages.py` extension (the `clean=False` contract)
- [x] `scripts/ingest/build_facts.py` + `make facts`

## Out of scope (roadmap)

- **`## Where to find` / locations.** Dropped from v1 by request. The section
  parses like the others (per-game pipe table); the work is `render_answer`
  prose plus an intent pattern that does not collide with the existing
  encounter-map feature on the dashboard. See `docs/roadmap.md`.

## Outcome

Implemented 2026-08-31. 206 unit tests pass.

Built on the dashboard passage feature that landed concurrently: Coach shares
its `retrieve_passages`, which gained a `clean=False` flag. The default still
returns cleaned prose for the dashboard evidence panel; Coach needs the
headings and short table cells that cleaning removes, and the junk filter with
them — a chunk that is only a moves table cleans to "" yet is exactly what a
moves question needs.

Verified live end to end:

| Question | Answer |
|---|---|
| What are Gengar's abilities? | Gengar's ability is Cursed Body. It has no hidden ability. |
| How does Charmander evolve? | Charmander evolves into Charmeleon at Level 16, then into Charizard at Level 36. |
| What egg group is Dratini in? | ...the Dragon and Water 1 egg groups... |
| What is Snorlax's catch rate? | ...25 (3.3% with PokéBall, full HP)... |
| What moves does Pikachu learn? | Charm (Lv. 1), Growl (Lv. 1)... and 12 more |

Mimikyu's `## Pokédex entries` was absent from its retrieved chunks, so
`render_answer` returned None and the question fell through to CRGA. That is
the designed behaviour for a section miss, observed working.
