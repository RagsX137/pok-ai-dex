# Pokédex evaluation harness

Repeatable wild-encounter testing for the Agentic Pokédex. Draws a random team
of six and a wild Pokémon from the **live Coveo index**, asks the running app
about the matchup, grades every answer against a type chart, and stores
everything in SQLite so results accumulate across runs.

## Quick start

```bash
python app.py                      # the app under test, on :5003
python -m eval_harness run --label baseline
python -m eval_harness report
```

## Commands

| Command | What it does |
|---|---|
| `run` | Draw scenarios, ask the app, grade, store |
| `report [--run N]` | Scoreboard by probe, backend and axis |
| `runs` | List every run collected so far |
| `show <turn_id>` | One turn in full: query, answer, retrieval, errors, ideal answer |
| `regrade [--run N]` | Re-score **stored** answers with the current grader — no re-querying |
| `export {sft,fewshot,failures} --out F` | Write training / prompting data |
| `review <turn_id> <verdict>` | Attach a human verdict, which overrides the automated one |
| `axes` | List the scenario axes and probes |

## Scenario axes

An axis is a constraint on the draw, so coverage of the interesting cases is
guaranteed rather than left to luck. `--axes no_advantage,zero_damage`.

| Axis | Guarantees |
|---|---|
| `baseline` | Single-type wild with a clean counter available |
| `dual_type` | Dual-type wild — the second type can cancel an apparent advantage |
| `four_x_defence` | A teammate takes 4× — the worst possible pick |
| `four_x_offence` | A teammate hits for 4× |
| `zero_damage` | A teammate has a STAB type that deals 0× |
| `no_advantage` | **Nobody** has an advantage — the honest answer is "none" |
| `immune_wall` | A teammate is immune to the wild Pokémon's STAB |
| `any` | Unconstrained random draw |

## Probes

The question asked about each scenario. `--probes lookup,advantage,pronoun`.

| Probe | Tests |
|---|---|
| `lookup` | Baseline retrieval — does it know this Pokémon? |
| `advantage` | The core task |
| `avoid` | Defensive reasoning |
| `pronoun` | Conversational memory — the wild Pokémon is only "it" |
| `unnamed_team` | Harder memory probe — nothing is restated |
| `ranking` | Forces a single best answer with a reason |

## Backends

`--backends app-coveo,direct-coveo,app-ollama:gemma4:12b-mlx`

- **`app-coveo`** — `POST /api/rga-coveo`. What a trainer in the browser sees.
- **`direct-coveo`** — replays the same CRGA flow straight against Coveo to
  capture `answerGenerated`, the abstention flag [app.py](../app.py) currently
  discards. Run it alongside `app-coveo` to tell "the model declined because
  retrieval was too weak" apart from "something broke".
- **`app-ollama:<model>`** — `POST /api/rga`, the local-model path. Use a model
  that is actually installed (`ollama list`); the UI's dropdown values are not.

## How grading works

Two kinds of check, deliberately separated:

**Objective.** Exact, no judgement involved.
- *Type contradictions* — "Binacle is Rock/Poison" when it is Rock/Water.
- *Type omissions* — "Grimmsnarl is a Dark-type" when it is Dark/Fairy and the
  Fairy half is what wins the fight. Recorded separately from contradictions.
- *Fabricated chart rules* — "Water is super effective against Dark" (it is 1×).
- *Harmful recommendations* — an endorsed teammate whose STAB deals 0×, or that
  takes ≥2× while hitting for ≤1×.
- *Retrieval hit* — was the wild Pokémon's page retrieved at all?
- *Abstention* — Coveo's `answerGenerated: false`, or a sentinel answer.

**Heuristic.** Which teammates the answer actually endorsed, read from clause
polarity. This is the fuzzy part, and it is why:

- every grade records `grade_method`,
- the raw answer is stored verbatim, so `regrade` re-scores history in place
  once the parser improves,
- `review` lets a human override any verdict, and `human_verdict` always wins.

Known gap: distributive claims ("X is Dark, Y is Dark, all of which are
effective against Dragon") are not attributed to a specific attacking type, so
those chart errors are missed. Verified against a hand-graded set of 15 turns,
where the automated grader matched every manual finding and caught one more.

## Schema

`eval_data/pokedex_eval.db` — see [schema.sql](schema.sql).

```
runs ──< scenarios ──< turns ──< retrievals
                          └──── grades  (1:1, always re-derivable)
```

`v_turns` joins all five for ad-hoc SQL. Raw answers are the asset; grades are
derived, so never hand-edit `grades` — use `review`, or fix the grader and
`regrade`.

## Exports

| Format | Shape | Use |
|---|---|---|
| `sft` | `{messages:[user, assistant]}`, assistant = chart-derived correct answer | Fine-tuning / distillation targets. Deduplicated by question. |
| `fewshot` | `{question, bad_answer, why_wrong, good_answer}` | Worked examples for a system prompt |
| `failures` | Flat rows of everything scored wrong | Triage |

The "correct answer" in every export is rendered deterministically from the
type chart by [reference.py](reference.py) — it is never model-generated, so
the targets cannot inherit the failure being measured.

## Reproducibility

Every run records its seed, git SHA, harness version, grade method, backends,
axes and probes. `--seed N` replays the same draws. Omit it and a random seed
is chosen and recorded.

Caches (`eval_data/corpus.json`, `eval_data/type_cache.json`) are committed so
runs reproduce across machines; refresh the corpus with `--refresh-corpus`.
The database itself is gitignored — it accumulates and is regenerable.
