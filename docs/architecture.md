# Architecture

## Request flow for a search

```
Browser (atomic-search-interface)
  → POST /api/coveo-proxy
      Body: { method, path: "/rest/search/v2", body: {...} }
      Server validates path against _ALLOWED_PATH (restricts to /rest/search/v2*)
      Server injects the Coveo bearer token server-side
  → Coveo REST API
  → Results rendered by dashboard.js:renderResultsList
```

The Coveo bearer token is never present in any HTML or JavaScript source. The
browser fetches it at runtime from `/api/coveo-token`, and even then it only
passes it to Atomic, which stores it in memory. The proxy route means all
authenticated Coveo calls go through the server.

`_ALLOWED_PATH` is a compiled regex anchored to `/rest/search/v2*`. The comment
in [`pokedex/routes/coveo_api.py`](../pokedex/routes/coveo_api.py) explains why
a leading `@` in the path would have let a caller steer the request to a
different host by turning the intended hostname into URL userinfo.

---

## The two RGA paths

### `/api/rga-coveo` — Coveo CRGA (Professor Oak)

1. `POST /rest/search/v2` with `enableGenerativeQuestionAnswering: True`.
2. Extract `extendedResults.generativeQuestionAnsweringId` (the stream ID).
   Coveo does not always return it on the first response — the client retries
   up to **6 times at 1-second intervals** before giving up.
3. `GET /rest/organizations/{org}/machinelearning/streaming/{streamId}`
   with `Accept: */*` — consumes the SSE stream of `genqa.*` events.
4. `pokedex.coveo.parse_genqa_stream` folds the events into
   `(answer, citations, error)`.
5. If the stream ID was never issued (RGA model did not fire), the route
   falls back to the top three search excerpts.

The retry budget and all SSE constants (`timeout=45`, `Accept: */*`, the
`"(no answer generated)"` sentinel) are centralised in
[`pokedex/coveo.py`](../pokedex/coveo.py). `CoveoClient.generated_answer()`
owns this flow; the route only shapes the HTTP response.

### `/api/rga` — local Ollama

Takes `{ query, context }` where `context` is the caller's list of
`{title, excerpt}` objects. Passes them to Ollama as a grounded prompt via
`pokedex.ollama_client.chat()`. No Coveo call. Used by `/api/ask` (the agentic
loop) and by the model dropdown when set to a local model.

---

## Why the browser never sees the Coveo key

`/api/coveo-token` returns `{ token, organizationId }` at runtime. The token is
the Coveo API key, which acts as its own search token (no separate `/token`
exchange is needed). It is stored server-side in `pokedex.config.Settings` (read
once at process start from the environment) and returned only through this
endpoint — never baked into HTML or JavaScript.

---

## Where Pokémon data comes from

| Data | Source | When |
|---|---|---|
| Pokédex entries (name, types, excerpt, URL) | `data/pokemon_db.csv`, scraped by `scripts/ingest/scrape_pokedex.py` and indexed into Coveo | Once, manually |
| Artwork | `data/images/`, scraped by `scripts/ingest/scrape_images.py` from pokemondb.net | Once, manually |
| Base stats, moves, encounter locations, sprite | [PokéAPI](https://pokeapi.co) | At runtime in the browser, cached in a JS Map per session |

The Coveo index is the primary search corpus. PokéAPI is called from the browser
only after a result is selected, and results are cached for the session.

---

## The Semantic-PokEncoder

A KNN Ranking Function attached to the Coveo `default` pipeline. It encodes
queries and documents into a shared embedding space and re-ranks results by
cosine similarity. It fires **automatically** — which is why no `mlParameters`
or encoder configuration appears in any request body sent from this app.
`agent.py` and the proxy both send plain search queries; the pipeline handles
the rest.

---

## The type chart lives twice

`frontend/modules/type-chart.js` is the browser-side copy; `eval_harness/typechart.py`
is the Python copy used by the evaluation grader. Both are kept in sync by
`tests/unit/test_type_chart_parity.py`, which parses the JS file and asserts
every cell of the 18×18 matrix matches. A discrepancy means the app has been
showing wrong weaknesses or the grader has been marking correct answers wrong.

---

## Two UIs

- **`/dashboard`** — the primary 3-column dark dashboard. This is where the
  type-effectiveness chips, encounter map, similar-Pokémon grid, and RGA
  recommendation live.
- **`/`** — the original Pokédex-device-shaped UI (red chrome, screen bezel,
  control row). Kept working; served from `frontend/classic/`.
