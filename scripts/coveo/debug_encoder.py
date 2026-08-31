"""
debug_encoder.py
Inspect the raw Coveo response to understand whether the Semantic Encoder
is actually influencing results — checks duration fields, mlInfo, pipeline
used, and per-result rankingInfo.
"""
import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

ORG   = os.getenv("COVEO_ORGANIZATION_ID", "")
TOKEN = os.getenv("COVEO_ACCESS_TOKEN", "")
BASE  = f"https://{ORG}.org.coveo.com"


def search(query, semantic):
    url  = f"{BASE}/rest/search/v2?organizationId={ORG}"
    hdrs = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    body = {
        "q":               query,
        "numberOfResults": 3,
        "searchHub":       "PokedexUI",
        "pipeline":        "default",
        "debug":           True,   # ask Coveo for full ranking debug output
    }
    if semantic:
        body["mlParameters"] = {"useSemanticSearch": True}
    r = requests.post(url, json=body, headers=hdrs, timeout=15)
    r.raise_for_status()
    return r.json()


def inspect(query):
    for label, sem in [("WITHOUT", False), ("WITH", True)]:
        d = search(query, sem)
        print(f"\n{'='*60}")
        print(f"{label} useSemanticSearch  —  query: '{query}'")
        print(f"  duration:          {d.get('duration')}ms")
        print(f"  indexDuration:     {d.get('indexDuration')}ms")
        print(f"  mlResponseTime:    {d.get('mlResponseTime')}ms")
        print(f"  pipeline used:     {d.get('pipeline')}")

        # Any top-level ML / semantic fields Coveo may return
        for key in ["mlInfo", "mlQueryInfos", "semanticSearch",
                    "isSemanticSearch", "encoderModelUsed", "mlActivated"]:
            if key in d:
                print(f"  {key}: {json.dumps(d[key], indent=4)}")

        # Per-result ranking debug
        for i, result in enumerate(d.get("results", [])[:3]):
            print(f"\n  Result #{i+1}: {result.get('title')}")
            print(f"    score={result.get('score')}  percentScore={result.get('percentScore')}")
            ri = result.get("rankingInfo")
            if not ri:
                print("    rankingInfo: (empty)")
            elif isinstance(ri, str):
                # Coveo returns rankingInfo as a plain string when debug=True
                # Print the whole thing so we can see what's in it
                print(f"    rankingInfo (str): {ri[:800]}")
            else:
                print(f"    rankingInfo keys: {list(ri.keys())}")
                for rk in ["mlContribution", "semanticContribution",
                           "documentWeights", "termsWeight", "totalWeight"]:
                    if rk in ri:
                        print(f"    {rk}: {ri[rk]}")


if __name__ == "__main__":
    inspect("electric mouse")
    inspect("psychic clone legendary")
