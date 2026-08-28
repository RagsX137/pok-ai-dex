"""
probe_crga2.py
==============
Quick CRGA smoke-test: fires the search + streams the answer, prints timing.
Useful for verifying the pipeline is alive before running full evals.

Usage:
    python probe_crga2.py
"""
import os, json, time, requests
from dotenv import load_dotenv

load_dotenv()

COVEO_ORG   = os.getenv("COVEO_ORGANIZATION_ID", "")
COVEO_TOKEN = os.getenv("COVEO_ACCESS_TOKEN", "")
COVEO_BASE  = f"https://{COVEO_ORG}.org.coveo.com"

QUERIES = [
    "What type is Pikachu?",
    "How does Eevee evolve into Jolteon?",
    "What is Mewtwo known for?",
]

hdrs_json = {
    "Authorization": f"Bearer {COVEO_TOKEN}",
    "Content-Type":  "application/json",
}


def crga_query(query: str) -> dict:
    """Run one CRGA query end-to-end. Returns {answer, citations, latency_s}."""
    t0 = time.time()

    # Step 1 — search with CRGA trigger
    stream_id = None
    for _ in range(8):
        r = requests.post(
            f"{COVEO_BASE}/rest/search/v2?organizationId={COVEO_ORG}",
            json={
                "q":               query,
                "searchHub":       os.getenv("COVEO_SEARCH_HUB", "PokedexUI"),
                "pipeline":        os.getenv("COVEO_PIPELINE", "default"),
                "numberOfResults": 5,
                "enableGenerativeQuestionAnswering": True,
            },
            headers=hdrs_json,
            timeout=15,
        )
        stream_id = r.json().get("extendedResults", {}).get("generativeQuestionAnsweringId")
        if stream_id:
            break
        time.sleep(1)

    if not stream_id:
        return {"answer": "(no streamId — RGA model may not be firing)", "citations": [],
                "latency_s": round(time.time() - t0, 2)}

    # Step 2 — consume SSE stream
    stream_url = (
        f"{COVEO_BASE}/rest/organizations/{COVEO_ORG}"
        f"/machinelearning/streaming/{stream_id}"
    )
    r2 = requests.get(
        stream_url,
        headers={"Authorization": f"Bearer {COVEO_TOKEN}", "Accept": "*/*"},
        timeout=45,
        stream=True,
    )

    answer_parts: list[str] = []
    citations:    list[dict] = []

    for raw_line in r2.iter_lines():
        if not raw_line:
            continue
        line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
        if not line.startswith("data:"):
            continue
        try:
            event = json.loads(line[5:].strip())
        except ValueError:
            continue
        ptype  = event.get("payloadType", "")
        praw   = event.get("payload", "")
        finish = event.get("finishReason")
        payload = json.loads(praw) if praw else {}
        if ptype == "genqa.messageType":
            delta = payload.get("textDelta", "")
            if delta.strip():
                answer_parts.append(delta)
        elif ptype == "genqa.citationsType":
            citations = payload.get("citations", [])
        elif ptype == "genqa.endOfStreamType" or finish == "COMPLETED":
            break

    return {
        "answer":    "".join(answer_parts).strip() or "(no answer generated)",
        "citations": citations,
        "latency_s": round(time.time() - t0, 2),
    }


if __name__ == "__main__":
    print(f"CRGA smoke-test  org={COVEO_ORG}\n{'='*60}")
    all_ok = True
    for q in QUERIES:
        result = crga_query(q)
        ok = not result["answer"].startswith("(")
        status = "✅" if ok else "❌"
        if not ok:
            all_ok = False
        print(f"{status} [{result['latency_s']:.1f}s]  Q: {q}")
        print(f"   A: {result['answer'][:180]}")
        print(f"   Citations: {len(result['citations'])}\n")
    print("="*60)
    print("All probes passed." if all_ok else "Some probes FAILED — check logs above.")
