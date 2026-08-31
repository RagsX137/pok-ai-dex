#!/usr/bin/env python3
"""
Probe the Coveo Passage Retrieval API (CPR) and diagnose why it fails.

The real surface is a dedicated Search API v3 endpoint:

    POST https://<org>.org.coveo.com/rest/search/v3/passages/retrieve

It is NOT a flag on /rest/search/v2. An earlier version of this script guessed
at v2 parameters (retrieveFirstSentences, enableSmartSnippets, mlParameters.*)
and found nothing, because none of those exist.

FINDINGS THIS SCRIPT REPRODUCES (2026-08-31):

  1. The API key is bound to a searchHub. Sending any other searchHub in the
     body is rejected with 400 INVALID_PARAMETER before the request ever
     reaches a pipeline. The script auto-detects the bound hub from that error.

  2. An active split test ("default-mirror-1787915454", ratio 0.5) sprays
     roughly half of all traffic onto a mirror pipeline that has no CPR model
     associated. Those requests fail with:

         422 UNPROCESSABLE_ENTITY
         "This API requires a Passage Retrieval model associated to the pipeline."

     Requests that land on `default` return 200 with passages. Identical
     request, two different outcomes, decided by the split test.

  3. Pinning "pipeline": "default" in the body does NOT avoid this — split
     test routing is applied after pipeline resolution, so half of those
     requests are still redirected to the mirror.

Everything printed is meant to be paste-able into a Coveo support ticket:
exact URL, exact body, exact status, exact message, resolved pipeline.

Run with:
    .venv/bin/python scripts/probe_passage_retrieval.py
"""
from __future__ import annotations

import collections
import json
import os
import re
import sys
import time

from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

import requests  # noqa: E402  (after dotenv so env is loaded)

ORG = os.environ.get("COVEO_ORGANIZATION_ID", "")
TOKEN = os.environ.get("COVEO_ACCESS_TOKEN", "")
HUB = os.environ.get("COVEO_SEARCH_HUB", "PokedexUI")
PIPELINE = os.environ.get("COVEO_PIPELINE", "default")

if not ORG or not TOKEN:
    sys.exit("COVEO_ORGANIZATION_ID / COVEO_ACCESS_TOKEN not set in .env")

BASE = f"https://{ORG}.org.coveo.com"
PASSAGES_URL = f"{BASE}/rest/search/v3/passages/retrieve"
SEARCH_URL = f"{BASE}/rest/search/v2?organizationId={ORG}"
HDRS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
    "Accept": "application/json",
}

QUERIES = [
    "What type is Pikachu and what is it weak to?",
    "Charizard",
    "Gengar moves",
    "What is Bulbasaur weak to?",
]
TRIALS = 5
RULE = "=" * 76


def body_for(query: str, hub: str, **extra) -> dict:
    return {
        "query": query,
        "searchHub": hub,
        "localization": {"locale": "en-US", "timezone": "America/New_York"},
        "maxPassages": 5,
        **extra,
    }


def resolved_pipeline(payload: dict) -> str | None:
    """Pull the pipeline name out of an executionReport tree, if present."""
    found: list[str] = []

    def walk(node) -> None:
        if isinstance(node, dict):
            if node.get("name") == "ResolvePipeline":
                name = (node.get("result") or {}).get("pipeline")
                if name:
                    found.append(name)
            for child in node.get("children") or []:
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)

    walk(payload.get("executionReport"))
    return found[0] if found else None


def detect_bound_hub() -> str:
    """The token carries its own searchHub; a mismatch is a hard 400.

    Coveo names both values in the error message, so one deliberately-wrong
    request tells us what the token is actually bound to.
    """
    print(RULE)
    print("1. SEARCH HUB BINDING")
    print(RULE)
    probe = "___mismatch_probe___"
    try:
        r = requests.post(PASSAGES_URL, json=body_for("test", probe), headers=HDRS, timeout=30)
    except requests.RequestException as exc:
        print(f"  TRANSPORT ERROR: {exc}")
        return HUB
    if r.status_code == 200:
        print("  Token is not hub-bound (any searchHub accepted).")
        return HUB
    msg = ""
    try:
        msg = r.json().get("message", "")
    except ValueError:
        msg = r.text[:200]
    print(f"  HTTP {r.status_code}: {msg}")
    m = re.search(r"provided in the authentication '([^']+)'", msg)
    if m:
        bound = m.group(1)
        print(f"\n  -> The API key is bound to searchHub {bound!r}.")
        if bound != HUB:
            print(f"  -> .env COVEO_SEARCH_HUB is {HUB!r}, which this key will REJECT")
            print("     with 400 on the passages endpoint. Using the bound hub below.")
        return bound
    return HUB


def split_test_state() -> str | None:
    """Report split test routing and return the mirror arm's name, if any."""
    print()
    print(RULE)
    print("2. SPLIT TEST STATE (via /rest/search/v2)")
    print(RULE)
    tally: collections.Counter = collections.Counter()
    for _ in range(8):
        try:
            r = requests.post(
                SEARCH_URL,
                json={"q": "Pikachu", "numberOfResults": 1, "pipeline": PIPELINE},
                headers=HDRS,
                timeout=30,
            )
            d = r.json()
        except (requests.RequestException, ValueError) as exc:
            print(f"  ERROR: {exc}")
            return None
        tally[(d.get("pipeline"), d.get("splitTestRun"))] += 1
    for (pipe, split), n in tally.most_common():
        print(f"  {n}/8  pipeline={pipe!r}  splitTestRun={split!r}")

    named = {split for _, split in tally if split}
    arms = {pipe for pipe, _ in tally}
    if not named:
        print("\n  -> No split test on this pipeline.")
        return None

    # The split test is named after its mirror arm, so the name doubles as the
    # pipeline to pin in section 4.
    mirror = sorted(named)[0]
    if len(arms) > 1:
        print(f"\n  -> Split test {mirror!r} is live and traffic IS being split across")
        print(f"     {sorted(arms)}. An ML association present on only one arm")
        print("     produces exactly the intermittent failures seen below.")
    else:
        print(f"\n  -> Split test {mirror!r} still exists, but all 8 requests landed on")
        print(f"     {sorted(arms)[0]!r} — the mirror arm is drawing no traffic.")
        print("     Note this is a routing change, not necessarily a model fix:")
        print("     section 4 pins the mirror directly to test it on its own.")
    return mirror


def passage_trials(hub: str) -> collections.Counter:
    print()
    print(RULE)
    print(f"3. PASSAGE RETRIEVAL — POST {PASSAGES_URL}")
    print(f"   searchHub={hub!r}, {TRIALS} identical trials per query")
    print(RULE)
    outcomes: collections.Counter = collections.Counter()
    for query in QUERIES:
        per_query: collections.Counter = collections.Counter()
        messages: set[str] = set()
        for _ in range(TRIALS):
            try:
                r = requests.post(
                    PASSAGES_URL, json=body_for(query, hub, debug=True), headers=HDRS, timeout=40
                )
                d = r.json()
            except (requests.RequestException, ValueError) as exc:
                per_query["error"] += 1
                messages.add(str(exc)[:120])
                continue
            pipe = resolved_pipeline(d)
            per_query[r.status_code] += 1
            outcomes[(r.status_code, pipe)] += 1
            if r.status_code != 200:
                messages.add(f"{d.get('errorCode') or d.get('type')}: {d.get('message')}")
        ok = per_query.get(200, 0)
        print(f"\n  {ok}/{TRIALS} succeeded — {query!r}")
        print(f"     {dict(per_query)}")
        for m in sorted(messages):
            print(f"     {m}")
    return outcomes


def pin_pipeline(hub: str, mirror: str | None) -> None:
    print()
    print(RULE)
    print("4. DOES PINNING THE PIPELINE HELP?")
    print(RULE)
    if mirror is None:
        print(f"  No split test active — {PIPELINE!r} is the only arm, nothing to")
        print("  compare against. Skipping.")
        return
    results: dict[str, collections.Counter] = {}
    for pipe in (PIPELINE, mirror):
        tally: collections.Counter = collections.Counter()
        for _ in range(TRIALS):
            try:
                r = requests.post(
                    PASSAGES_URL,
                    json=body_for("Gengar moves", hub, pipeline=pipe),
                    headers=HDRS,
                    timeout=40,
                )
            except requests.RequestException:
                tally["error"] += 1
                continue
            tally[r.status_code] += 1
            # Coveo rate-limits this endpoint at PerOrg[5 calls/PT1S]. A 429 is
            # our own request rate, not a passage retrieval failure — keep it
            # out of the pass/fail reading.
            if r.status_code == 429:
                time.sleep(1)
        results[pipe] = tally
        print(f"  pipeline={pipe!r}: {dict(tally)}")

    def rate(t: collections.Counter) -> tuple[int, int]:
        graded = sum(n for s, n in t.items() if s != 429)
        return t.get(200, 0), graded

    good_ok, good_n = rate(results[PIPELINE])
    mirror_ok, mirror_n = rate(results[mirror])
    mirror_gone = results[mirror].get(400, 0) > 0
    print()
    if mirror_gone:
        print(f"  -> {mirror!r} no longer exists (400 Unknown query pipeline).")
        print("     The split test was deleted rather than reconfigured.")
    elif good_n and good_ok == good_n and mirror_n and mirror_ok == 0:
        print(f"  -> {PIPELINE!r} serves passages on every call; the mirror fails on")
        print("     every call. The mirror has no CPR model associated — it has")
        print("     only been taken out of the traffic split. Re-raising the split")
        print("     test ratio would reintroduce the failures.")
    elif mirror_n and mirror_ok == mirror_n:
        print("  -> Both arms serve passages; the CPR model is associated to both.")
    elif good_n and good_ok < good_n:
        print(f"  -> Even pinning {PIPELINE!r} does not reliably avoid the mirror;")
        print("     split test routing is applied after pipeline resolution.")


def verdict(outcomes: collections.Counter) -> None:
    print()
    print(RULE)
    print("VERDICT")
    print(RULE)
    total = sum(outcomes.values())
    ok = sum(n for (status, _), n in outcomes.items() if status == 200)
    print(f"  {ok}/{total} requests returned passages "
          f"({100 * ok // total if total else 0}%)\n")
    for (status, pipe), n in sorted(outcomes.items(), key=lambda kv: -kv[1]):
        print(f"  {n:>3}x  HTTP {status}  pipeline={pipe!r}")
    print()
    if ok == total:
        print("  Passage retrieval is working on every request.")
    elif ok == 0:
        print("  Passage retrieval never returned passages. See messages above.")
    else:
        print("  PARTIAL: the CPR model IS provisioned and DOES return passages,")
        print("  but only on one side of the active split test. The mirror")
        print("  pipeline has no CPR model associated, so it 422s. This is an")
        print("  org configuration gap, not a client bug.")


def main() -> None:
    print(RULE)
    print("COVEO PASSAGE RETRIEVAL (CPR) — PROBE")
    print(RULE)
    print(f"  org       = {ORG}")
    print(f"  pipeline  = {PIPELINE}")
    print(f"  token     = {TOKEN[:6]}…{TOKEN[-4:]} (len {len(TOKEN)})")
    print()
    hub = detect_bound_hub()
    mirror = split_test_state()
    outcomes = passage_trials(hub)
    pin_pipeline(hub, mirror)
    verdict(outcomes)


if __name__ == "__main__":
    main()
