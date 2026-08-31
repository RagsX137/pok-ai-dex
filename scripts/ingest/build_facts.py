#!/usr/bin/env python3
"""Materialise data/pokemon_facts.json from the Passage Retrieval API.

Optional: FactsStore works without this file, paying one live call per Pokemon
per process. Building it makes Coach's fact answers instant and offline.

    .venv/bin/python scripts/ingest/build_facts.py [--limit N] [--only name,name]

Rate limited to the documented PerOrg[5 calls/PT1S] quota. A full corpus run is
~1023 calls, so roughly four minutes.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from pokedex import pokemon_names  # noqa: E402
from pokedex.config import settings  # noqa: E402
from pokedex.coveo import CoveoClient  # noqa: E402
from pokedex.facts import build_facts, fold  # noqa: E402

# The org quota is 5 calls/sec; 4/sec leaves headroom for a live app sharing it.
_INTERVAL = 0.25
_MAX_PASSAGES = 10


def fetch_one(client: CoveoClient, name: str):
    passages = client.retrieve_passages(name, max_passages=_MAX_PASSAGES, clean=False)
    prefix = fold(name) + " "
    mine = [p.text for p in passages if fold(p.title).startswith(prefix)]
    return build_facts(name, mine) if mine else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="stop after N Pokemon")
    ap.add_argument("--only", default="", help="comma-separated names")
    ap.add_argument("--out", default=str(settings.repo_root / "data" / "pokemon_facts.json"))
    args = ap.parse_args()

    pokemon_names.init(REPO_ROOT)
    names = sorted(pokemon_names.names())
    if args.only:
        wanted = {n.strip().lower() for n in args.only.split(",") if n.strip()}
        names = [n for n in names if n in wanted]
    if args.limit:
        names = names[:args.limit]
    if not names:
        print("no names to build", file=sys.stderr)
        return 1

    out_path = Path(args.out)
    # Merge rather than overwrite, so a partial run is resumable and a crash
    # does not throw away the calls already spent.
    existing: dict[str, dict] = {}
    if out_path.exists():
        try:
            existing = json.loads(out_path.read_text(encoding="utf-8"))
        except Exception:
            existing = {}

    client = CoveoClient()
    built = skipped = 0
    for i, name in enumerate(names, 1):
        try:
            facts = fetch_one(client, name)
        except Exception as exc:
            print(f"  {i}/{len(names)} {name}: ERROR {exc}", file=sys.stderr)
            facts = None
        if facts is None:
            skipped += 1
        else:
            existing[fold(name)] = facts.to_dict()
            built += 1
        if i % 25 == 0 or i == len(names):
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(existing, ensure_ascii=False), encoding="utf-8")
            print(f"  {i}/{len(names)}  built={built} skipped={skipped}")
        time.sleep(_INTERVAL)

    out_path.write_text(json.dumps(existing, ensure_ascii=False), encoding="utf-8")
    size_mb = out_path.stat().st_size / 1_000_000
    print(f"\nwrote {out_path} — {len(existing)} entries, {size_mb:.1f} MB "
          f"({built} built, {skipped} had no usable passages)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
