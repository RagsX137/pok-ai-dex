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
